"""
Independent CV Review Service — Hiring Manager Perspective.

Uses GPT/Codex to critique a CV from a hiring manager's viewpoint,
focusing on what they see in the top 1/3 vs what they WANT to see.
Completely independent from the pipeline's CVGrader.

No imports from src/layer6_v2 — this is a standalone "second opinion".

Shared pure logic (prompts, taxonomy, document builder) lives in
cv_review_core.py to avoid duplication with the bulk review script.
"""

import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from bson import ObjectId
from pymongo import MongoClient

from src.common.master_cv_store import MasterCVStore
from src.services.cv_review_core import (
    DEFAULT_CV_REVIEW_MODEL,
    REVIEWER_SYSTEM_PROMPT,
    build_cv_review_document,
    build_user_prompt,
    derive_bridge_quality_score,
    derive_failure_modes,
    derive_headline_evidence_bounded,
    parse_review_json,
)
from src.services.operation_base import OperationResult, OperationService

logger = logging.getLogger(__name__)

# Backwards-compat aliases for any external code that imported the old names
_derive_failure_modes = derive_failure_modes
_derive_headline_evidence_bounded = derive_headline_evidence_bounded
_derive_bridge_quality_score = derive_bridge_quality_score


class CVReviewService(OperationService):
    """
    Independent GPT-based CV reviewer from a hiring manager's perspective.

    Sends a single large prompt to GPT with:
    - The generated CV
    - The extracted JD (structured intelligence)
    - The master CV (for hallucination checking)
    - All quality rules baked into the system prompt

    Returns structured JSON critique — completely separate from CVGrader.
    """

    operation_name = "cv-review"

    def __init__(self, model: Optional[str] = None) -> None:
        """
        Initialize the CV review service.

        Args:
            model: OpenAI model override. Defaults to CV_REVIEW_MODEL env var,
                   then falls back to "gpt-4o".
        """
        self.model = model or os.getenv("CV_REVIEW_MODEL", DEFAULT_CV_REVIEW_MODEL)
        self._mongo_uri = os.getenv("MONGODB_URI")
        if not self._mongo_uri:
            raise ValueError("MONGODB_URI environment variable is required")

    # ------------------------------------------------------------------
    # MongoDB helpers (direct pymongo — avoids Motor dependency cycle)
    # ------------------------------------------------------------------

    def _get_collection(self):
        """Return the level-2 MongoClient collection (sync)."""
        client = MongoClient(self._mongo_uri)
        db = client.get_default_database()
        return db["level-2"]

    # ------------------------------------------------------------------
    # Prompt builders
    # ------------------------------------------------------------------

    def _build_user_prompt(
        self,
        cv_text: str,
        extracted_jd: Dict[str, Any],
        master_cv_text: str,
        pain_points: Optional[Any],
        company_research: Optional[Any],
    ) -> str:
        """Build user prompt — delegates to cv_review_core.build_user_prompt."""
        # Load project files from disk (relative to repo root)
        project_base = Path(__file__).resolve().parents[2] / "data" / "master-cv" / "projects"
        project_texts: Dict[str, str] = {}
        for name in ("commander4.md", "lantern.md"):
            path = project_base / name
            try:
                if path.exists():
                    project_texts[name] = path.read_text(encoding="utf-8")
            except OSError:
                pass

        return build_user_prompt(
            cv_text=cv_text,
            extracted_jd=extracted_jd,
            master_cv_text=master_cv_text,
            pain_points=pain_points,
            company_research=company_research,
            project_texts=project_texts,
        )

    # ------------------------------------------------------------------
    # Core execution
    # ------------------------------------------------------------------

    async def execute(
        self,
        job_id: str,
        tier: str = "quality",
        progress_callback: Optional[Callable] = None,
        log_callback: Optional[Callable[[str], None]] = None,
        **kwargs,
    ) -> OperationResult:
        """
        Run an independent hiring-manager CV review for a job.

        Steps:
        1. Fetch job document from MongoDB (level-2)
        2. Extract cv_text, extracted_jd, pain_points, company_research
        3. Load master CV via MasterCVStore
        4. Build system + user prompts
        5. Call OpenAI API (json_object response format)
        6. Persist cv_review to MongoDB
        7. Return OperationResult

        Args:
            job_id: MongoDB ObjectId string for the job document.
            tier: Model tier string (kept for API compatibility, unused for routing).
            progress_callback: Optional layer-level progress callback.
            log_callback: Optional log line callback for live streaming.

        Returns:
            OperationResult with cv_review data on success.
        """
        run_id = self.create_run_id()
        t_start = time.perf_counter()

        def _log(msg: str) -> None:
            logger.info(msg)
            if log_callback:
                try:
                    log_callback(msg)
                except Exception:
                    pass

        _log(f"CV review starting for job {job_id} (model={self.model})")

        try:
            # ----------------------------------------------------------------
            # 1. Fetch job document
            # ----------------------------------------------------------------
            collection = self._get_collection()
            try:
                job = collection.find_one({"_id": ObjectId(job_id)})
            except Exception as exc:
                return self.create_error_result(
                    run_id,
                    f"Invalid job_id format: {exc}",
                    int((time.perf_counter() - t_start) * 1000),
                )
            if not job:
                return self.create_error_result(
                    run_id,
                    "Job not found",
                    int((time.perf_counter() - t_start) * 1000),
                )

            _log(f"Fetched job: {job.get('company', '?')} — {job.get('title', '?')}")

            # ----------------------------------------------------------------
            # 2. Extract required fields
            # ----------------------------------------------------------------
            cv_text: Optional[str] = job.get("cv_text") or None
            if not cv_text:
                # Fallback: check cv_editor_state
                editor_state = job.get("cv_editor_state") or {}
                if isinstance(editor_state, dict):
                    cv_text = editor_state.get("text") or editor_state.get("content") or None
            if not cv_text:
                return self.create_error_result(
                    run_id,
                    "No CV generated for this job yet",
                    int((time.perf_counter() - t_start) * 1000),
                )

            extracted_jd: Optional[Dict[str, Any]] = job.get("extracted_jd") or None
            if not extracted_jd:
                return self.create_error_result(
                    run_id,
                    "JD not extracted yet — run analyze-job first",
                    int((time.perf_counter() - t_start) * 1000),
                )

            pain_points = job.get("pain_points")
            company_research = job.get("company_research")  # often absent — handle gracefully

            # ----------------------------------------------------------------
            # 3. Load master CV text
            # ----------------------------------------------------------------
            master_cv_text = ""
            try:
                master_cv_text = MasterCVStore().get_candidate_profile_text() or ""
                if master_cv_text:
                    _log(f"Master CV loaded ({len(master_cv_text)} chars)")
                else:
                    _log("Warning: master CV returned empty text")
            except Exception as exc:
                _log(f"Warning: could not load master CV — hallucination check will be limited: {exc}")

            # ----------------------------------------------------------------
            # 4. Build prompts
            # ----------------------------------------------------------------
            user_prompt = self._build_user_prompt(
                cv_text=cv_text,
                extracted_jd=extracted_jd,
                master_cv_text=master_cv_text,
                pain_points=pain_points,
                company_research=company_research,
            )
            _log(f"Prompts built (user_prompt={len(user_prompt)} chars)")

            # ----------------------------------------------------------------
            # 5. Call Codex CLI (uses ChatGPT Plus OAuth — no API key needed)
            # ----------------------------------------------------------------
            _log(f"Calling Codex CLI ({self.model}) for hiring-manager review...")

            # Build the full prompt for codex exec
            full_prompt = (
                f"{REVIEWER_SYSTEM_PROMPT}\n\n"
                f"{user_prompt}\n\n"
                "IMPORTANT: Return ONLY valid JSON matching the schema above. No markdown, no explanation, just the JSON object."
            )

            # Ensure codex auth is available — credentials mount has it at /app/credentials/
            codex_auth_src = "/app/credentials/codex-auth.json"
            codex_auth_dst = os.path.expanduser("~/.codex/auth.json")
            if os.path.exists(codex_auth_src) and not os.path.exists(codex_auth_dst):
                os.makedirs(os.path.dirname(codex_auth_dst), exist_ok=True)
                import shutil
                shutil.copy2(codex_auth_src, codex_auth_dst)
                _log(f"Copied codex auth from {codex_auth_src}")

            try:
                # Write prompt to temp file — codex exec reads from stdin pipe
                import tempfile
                prompt_file = tempfile.NamedTemporaryFile(
                    mode="w", suffix=".txt", delete=False, dir="/tmp"
                )
                prompt_file.write(full_prompt)
                prompt_file.close()
                _log(f"Prompt written to {prompt_file.name} ({len(full_prompt)} chars)")

                # Pipe prompt via stdin using shell redirection
                result = subprocess.run(
                    f"cat {prompt_file.name} | codex exec -m {self.model} --full-auto",
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=300,  # 5 min timeout
                    env={**{k: v for k, v in os.environ.items() if k != "OPENAI_API_KEY"}, "NO_COLOR": "1"},
                )

                # Cleanup temp file
                try:
                    os.unlink(prompt_file.name)
                except OSError:
                    pass
                raw_content = result.stdout.strip()

                if result.returncode != 0:
                    error_msg = result.stderr.strip() or f"Codex exec failed with code {result.returncode}"
                    _log(f"Codex CLI error: {error_msg}")
                    return self.create_error_result(
                        run_id, f"Codex CLI failed: {error_msg}",
                        int((time.perf_counter() - t_start) * 1000),
                    )

                if not raw_content:
                    return self.create_error_result(
                        run_id, "Codex CLI returned empty response",
                        int((time.perf_counter() - t_start) * 1000),
                    )

            except subprocess.TimeoutExpired:
                return self.create_error_result(
                    run_id, "Codex CLI timed out after 300s",
                    int((time.perf_counter() - t_start) * 1000),
                )
            except FileNotFoundError:
                return self.create_error_result(
                    run_id, "Codex CLI not found — ensure @openai/codex is installed",
                    int((time.perf_counter() - t_start) * 1000),
                )

            # Parse JSON from codex output (may contain extra text before/after)
            review = parse_review_json(raw_content)
            if review is None:
                return self.create_error_result(
                    run_id,
                    f"Failed to parse review JSON from Codex output: {raw_content[:500]}",
                    int((time.perf_counter() - t_start) * 1000),
                )

            _log(
                f"Review complete: verdict={review.get('verdict', '?')} "
                f"would_interview={review.get('would_interview', '?')} "
                f"confidence={review.get('confidence', '?')}"
            )

            # Codex CLI doesn't expose token counts
            input_tokens = 0
            output_tokens = 0

            # ----------------------------------------------------------------
            # 6. Derive structured taxonomy from review
            # ----------------------------------------------------------------
            failure_modes = derive_failure_modes(review)
            headline_bounded = derive_headline_evidence_bounded(review)
            bridge_score = derive_bridge_quality_score(review)

            # ----------------------------------------------------------------
            # 7. Build cv_review document and persist to MongoDB
            # ----------------------------------------------------------------
            cv_review = build_cv_review_document(
                review, self.model, failure_modes, headline_bounded, bridge_score,
            )

            collection.update_one(
                {"_id": ObjectId(job_id)},
                {"$set": {"cv_review": cv_review}},
            )
            _log("cv_review persisted to MongoDB")

            duration_ms = int((time.perf_counter() - t_start) * 1000)
            return self.create_success_result(
                run_id=run_id,
                data=cv_review,
                cost_usd=0.0,  # OpenAI costs tracked externally
                duration_ms=duration_ms,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                model_used=self.model,
            )

        except Exception as exc:
            logger.exception(f"CVReviewService failed for job {job_id}: {exc}")
            return self.create_error_result(
                run_id,
                str(exc),
                int((time.perf_counter() - t_start) * 1000),
            )
