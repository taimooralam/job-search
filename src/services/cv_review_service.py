"""
Independent CV Review Service — Hiring Manager Perspective.

Uses GPT/Codex to critique a CV from a hiring manager's viewpoint,
focusing on what they see in the top 1/3 vs what they WANT to see.
Completely independent from the pipeline's CVGrader.

No imports from src/layer6_v2 — this is a standalone "second opinion".
"""

import json
import logging
import os
import subprocess
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from bson import ObjectId
from pymongo import MongoClient

from src.common.master_cv_store import MasterCVStore
from src.services.operation_base import OperationResult, OperationService

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# System prompt — all quality rules baked in as hiring-manager context
# ---------------------------------------------------------------------------

REVIEWER_SYSTEM_PROMPT = """\
You are an experienced hiring manager reviewing a CV for a specific role. You have 15 years of experience hiring engineering leaders and architects.

## Your Review Process

You review CVs the way real hiring managers do:
1. First 6 seconds: scan the top 1/3 (headline, tagline, key achievements, core competencies)
2. Next 30 seconds: check if experience matches the role requirements
3. Final pass: verify claims, check for red flags, assess fit

## What You're Looking For

### Top 1/3 Assessment (MOST IMPORTANT)
The top 1/3 determines if the CV gets read or rejected. Evaluate:
- **Headline**: Does it match the exact JD title? Does it signal seniority correctly?
- **Tagline/Profile**: Is it in third-person absent voice (no pronouns: I, my, we, our)? Does it answer: Who are you? What problems do you solve? What proof do you have? Why should I call you?
- **Key Achievements**: Are there 5-6 quantified achievements with real metrics? Do they align with the role's pain points?
- **Core Competencies**: Are there 10-12 ATS-friendly keywords that match the JD? Are they organized in relevant sections?

### Hiring Manager Questions
For each section, answer:
- "Would this make me want to keep reading?"
- "Does this address MY pain points as the hiring manager?"
- "Would this person solve the problems I'm hiring for?"
- "Is there proof, or just claims?"

### ATS Survival Check
- Are the top 10-20 JD keywords present in the CV?
- Do acronyms have their full form expanded? (e.g., "Kubernetes (K8s)")
- Are keywords front-loaded (in first 3 words of bullets)?
- Is keyword density adequate (each important keyword appears 2-4 times)?

### Anti-Hallucination Check
- Compare CV claims against the MASTER CV provided
- Flag any technology or metric that appears in the CV but NOT in the master CV
- Especially flag technologies that appear in the JD but not in the master CV (likely injected)
- Verify all percentages and numbers match the master CV (15% tolerance)

### Ideal Candidate Alignment
Compare the CV's positioning against the JD's ideal candidate profile:
- Does the CV's identity match the archetype the JD describes?
- Are the key traits visible in the CV?
- Does the experience level match?

## Anti-Hallucination Rules for Rewrites

HARD CONSTRAINTS — you MUST NOT violate these:
- Do NOT add metrics (percentages, numbers, dollar amounts) unless they appear verbatim in the master CV
- Do NOT add technologies unless the master CV lists them in that role's context
- Do NOT add team sizes, headcounts, or org scope unless stated in master CV
- Do NOT add business impact claims (revenue, cost savings, user counts) not in master CV
- Do NOT inflate scope (e.g., "led" → "transformed organization" without evidence)
- Do NOT add leadership claims (led, managed, directed) to roles where master CV shows IC work
- If a JD keyword has NO evidence in master CV, do NOT inject it — mark as grounding: "gap"

SOFT GUIDELINES:
- Rewrite for clarity and impact WITHIN the bounds of what the master CV supports
- Front-load JD-relevant keywords that ARE in the master CV
- Use stronger action verbs only when the master CV supports the claim's scope
- When evidence is thin, rewrite conservatively — precise over impressive
- Flag inferences with grounding: "inferred"

ROLE EXTRACTION:
- First, identify all roles and projects from the CV text
- Use their exact employer/project names as keys in experience_items
- Only emit rewrites for items actually present in the CV
- Mark each as type: "role" or type: "project"

## Output Format

Return a JSON object with exactly this structure:
{
  "verdict": "STRONG_MATCH" | "GOOD_MATCH" | "NEEDS_WORK" | "WEAK_MATCH",
  "confidence": 0.0-1.0,
  "would_interview": true/false,
  "top_third_assessment": {
    "headline_verdict": "string — what works/doesn't work",
    "tagline_verdict": "string — pronoun check, 4-question framework",
    "achievements_verdict": "string — quantified? aligned? compelling?",
    "competencies_verdict": "string — ATS-friendly? relevant? organized?",
    "first_impression_score": 1-10,
    "first_impression_summary": "In 6 seconds, a hiring manager would think: ..."
  },
  "pain_point_alignment": {
    "addressed": ["pain point 1 — how CV addresses it"],
    "missing": ["pain point X — not covered in CV"],
    "coverage_ratio": 0.0-1.0
  },
  "hallucination_flags": [
    {"claim": "...", "issue": "not found in master CV", "severity": "high|medium|low"}
  ],
  "ats_assessment": {
    "keyword_coverage": "X/Y keywords found",
    "missing_critical_keywords": ["kw1", "kw2"],
    "acronym_issues": ["K8s mentioned but Kubernetes not expanded"],
    "ats_survival_likely": true/false
  },
  "strengths": ["strength 1", "strength 2"],
  "weaknesses": ["weakness 1", "weakness 2"],
  "rewrite_suggestions": {
    "headline": {
      "current": "exact headline from CV",
      "rewritten": "improved headline",
      "reason": "why",
      "grounding": "grounded|inferred|gap",
      "source_evidence": "quote from master CV"
    },
    "tagline": {
      "current": "exact tagline from CV",
      "rewritten": "improved tagline",
      "reason": "why",
      "grounding": "grounded|inferred|gap",
      "source_evidence": "quote from master CV"
    },
    "core_competencies": {
      "current": ["list of current competencies"],
      "rewritten": ["list of improved competencies"],
      "reason": "why",
      "grounding": "grounded",
      "source_evidence": "..."
    },
    "key_achievements": {
      "current": ["list of current achievements"],
      "rewritten": ["list of improved achievements"],
      "reason": "why",
      "grounding": "grounded",
      "source_evidence": "..."
    },
    "experience_items": {
      "Company Name": {
        "type": "role|project",
        "current": ["bullet 1", "bullet 2"],
        "rewritten": ["improved bullet 1", "improved bullet 2"],
        "reason": "why",
        "grounding": "grounded|inferred",
        "source_evidence": "..."
      }
    }
  },
  "ideal_candidate_fit": {
    "archetype_match": "string — how well CV matches the JD archetype",
    "trait_coverage": {"present": [], "missing": []},
    "experience_level_match": "string"
  }
}
"""


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
        self.model = model or os.getenv("CV_REVIEW_MODEL", "gpt-5.4-mini")
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
        """
        Build the user-side prompt from job data.

        Args:
            cv_text: The generated CV markdown text.
            extracted_jd: Structured JD extraction document.
            master_cv_text: Master CV text for hallucination checking.
            pain_points: Mined pain points (list or None).
            company_research: Company research dict or None.

        Returns:
            Formatted user prompt string.
        """
        sections: List[str] = []

        sections.append("## JOB DESCRIPTION INTELLIGENCE")
        sections.append(f"Title: {extracted_jd.get('title', 'Unknown')}")
        sections.append(f"Company: {extracted_jd.get('company', 'Unknown')}")
        sections.append(f"Role Category: {extracted_jd.get('role_category', 'Unknown')}")
        sections.append(f"Seniority: {extracted_jd.get('seniority_level', 'Unknown')}")

        responsibilities = extracted_jd.get("responsibilities", [])
        if responsibilities:
            resp_lines = "\n".join(f"- {r}" for r in responsibilities)
            sections.append(f"\nResponsibilities:\n{resp_lines}")

        technical_skills = extracted_jd.get("technical_skills", [])
        if technical_skills:
            sections.append(f"\nRequired Technical Skills: {', '.join(technical_skills)}")

        top_keywords = extracted_jd.get("top_keywords", [])
        if top_keywords:
            sections.append(f"\nTop ATS Keywords: {', '.join(top_keywords)}")

        implied_pain_points = extracted_jd.get("implied_pain_points", [])
        if implied_pain_points:
            pain_lines = "\n".join(f"- {p}" for p in implied_pain_points)
            sections.append(f"\nImplied Pain Points:\n{pain_lines}")

        ideal = extracted_jd.get("ideal_candidate_profile") or {}
        if ideal:
            sections.append("\nIdeal Candidate Profile:")
            sections.append(f"  Archetype: {ideal.get('archetype', 'Unknown')}")
            sections.append(f"  Identity: {ideal.get('identity_statement', '')}")
            key_traits = ideal.get("key_traits", [])
            if key_traits:
                sections.append(f"  Key Traits: {', '.join(key_traits)}")

        if pain_points:
            if isinstance(pain_points, list):
                pp_lines = "\n".join(f"- {p}" for p in pain_points)
                sections.append(f"\nMined Pain Points:\n{pp_lines}")
            else:
                sections.append(f"\nMined Pain Points:\n{str(pain_points)}")

        if company_research:
            try:
                cr_text = json.dumps(company_research, default=str)[:2000]
            except Exception:
                cr_text = str(company_research)[:2000]
            sections.append(f"\nCompany Research:\n{cr_text}")

        sections.append("\n## MASTER CV (Source of Truth for Hallucination Check)")
        sections.append(master_cv_text[:8000] if master_cv_text else "Master CV not available")

        # Append AI project files for complete source-of-truth context
        from pathlib import Path
        project_base = Path(__file__).resolve().parents[2] / "data" / "master-cv" / "projects"
        sections.append("\n## AI PROJECT FILES (Additional Source of Truth)")
        for project_file in ("commander4.md", "lantern.md"):
            project_path = project_base / project_file
            try:
                if project_path.exists():
                    project_text = project_path.read_text(encoding="utf-8")
                    sections.append(f"\n### {project_file}")
                    sections.append(project_text[:3000])
            except OSError:
                pass  # File unreadable, skip gracefully

        sections.append("\n## CV TO REVIEW")
        sections.append(cv_text)

        sections.append("\n## INSTRUCTIONS")
        sections.append(
            "Review this CV from a hiring manager's perspective. "
            "Focus on the top 1/3 first. "
            "Return your assessment as JSON per the schema in your instructions."
        )

        return "\n\n".join(sections)

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
            try:
                # Try direct parse first
                review: Dict[str, Any] = json.loads(raw_content)
            except json.JSONDecodeError:
                # Extract JSON from mixed output (codex may prepend status lines)
                import re
                json_match = re.search(r'\{[\s\S]*\}', raw_content)
                if json_match:
                    try:
                        review = json.loads(json_match.group())
                    except json.JSONDecodeError as exc:
                        return self.create_error_result(
                            run_id,
                            f"Codex returned invalid JSON: {exc}\nRaw: {raw_content[:500]}",
                            int((time.perf_counter() - t_start) * 1000),
                        )
                else:
                    return self.create_error_result(
                        run_id,
                        f"No JSON found in Codex output: {raw_content[:500]}",
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
            # 6. Build cv_review document and persist to MongoDB
            # ----------------------------------------------------------------
            cv_review: Dict[str, Any] = {
                "reviewed_at": datetime.now(timezone.utc).isoformat(),
                "model": self.model,
                "reviewer": "independent_gpt",
                "verdict": review.get("verdict"),
                "would_interview": review.get("would_interview"),
                "confidence": review.get("confidence"),
                "first_impression_score": (
                    review.get("top_third_assessment", {}).get("first_impression_score")
                ),
                "full_review": review,
            }

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

        except openai.AuthenticationError as exc:
            logger.error(f"OpenAI authentication error: {exc}")
            return self.create_error_result(
                run_id,
                "Codex CLI authentication failed — check codex auth",
                int((time.perf_counter() - t_start) * 1000),
            )
        except openai.RateLimitError as exc:
            logger.error(f"OpenAI rate limit: {exc}")
            return self.create_error_result(
                run_id,
                f"OpenAI rate limit exceeded: {exc}",
                int((time.perf_counter() - t_start) * 1000),
            )
        except openai.APIError as exc:
            logger.error(f"OpenAI API error: {exc}")
            return self.create_error_result(
                run_id,
                f"OpenAI API error: {exc}",
                int((time.perf_counter() - t_start) * 1000),
            )
        except Exception as exc:
            logger.exception(f"CVReviewService failed for job {job_id}: {exc}")
            return self.create_error_result(
                run_id,
                str(exc),
                int((time.perf_counter() - t_start) * 1000),
            )
