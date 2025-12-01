"""
Layer 6: Outreach & CV Generator

Generates personalized cover letter and tailored CV based on all previous analysis.

Phase 8.1: Enhanced cover letter generator with validation gates.
Phase 8.2: STAR-driven CV generator (to be implemented).
"""

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple
from langchain_core.messages import HumanMessage, SystemMessage
from tenacity import retry, stop_after_attempt, wait_exponential

from src.common.config import Config
from src.common.llm_factory import create_tracked_cv_llm
from src.common.state import JobState
from src.common.utils import sanitize_path_component
from src.common.logger import get_logger
from src.common.structured_logger import get_structured_logger, LayerContext
from src.layer6.cover_letter_generator import CoverLetterGenerator


CV_SYSTEM_PROMPT = """You are the second pass of a two-stage CV builder. Convert provided ROLE BULLET EVIDENCE JSON into a non-hallucinated, ATS-friendly, personalized CV that mirrors the job description language.

OUTPUT FORMAT: Use proper Markdown with headers for Word template compatibility:
- `# Candidate Name` (H1 for name)
- `## Section Name` (H2 for Profile, Core Skills, Professional Experience, Education)
- `### Role Title — Company — Location | Dates` (H3 for each job role)
- Use `- ` for bullet points under each role

Rules:
(1) No STAR labels; keep bullets 15–25 words, start with an action verb aligned to the target role category (e.g., lead/coach/drive/architect for manager/lead roles; build/design/ship for IC-heavy roles) and verbs found in the job description. Include a clear metric/result and explicitly reference a provided pain point or success metric.
(2) Drop any bullet that lacks action+metric; do not invent data.
(3) Keep profile/core skills tight and role-specific; align titles to the target job; keep tech details to show hands-on leadership.
(4) If any required input is missing, state that plainly.

Output only the completed CV in proper Markdown format and a brief integrity check at the end; no extra commentary or preambles."""
CV_EVIDENCE_SYSTEM_PROMPT = """You are the first pass of a two-stage CV builder. Generate only JSON capturing bullet ingredients per role. Use the supplied master CV, job description, pain points, and research to pick 7–10 bullets for the last two roles and concise bullets for earlier roles. Each bullet must include: situation (context), action (what was done), result (outcome), metric (number/percentage/time), and pain_point_hit (tie to provided pain points or success metrics). Reject any bullet without a metric or action. Respond with JSON only, schema:
{
  "roles": [
    {
      "role": "Title — Company",
      "bullets": [
        {
          "situation": "",
          "action": "",
          "result": "",
          "metric": "",
          "pain_point_hit": ""
        }
      ]
    }
  ]
}
No markdown or prose."""
STRONG_VERBS = {
    "led", "drove", "architected", "built", "delivered", "designed", "implemented", "launched",
    "optimized", "scaled", "reduced", "improved", "accelerated", "mentored", "modernized",
    "streamlined", "increased", "orchestrated", "stabilized"
}

# Common LLM preambles to strip from CV output
LLM_PREAMBLE_PATTERNS = [
    r"^Here is the updated CV.*?:\s*\n+",
    r"^Here is the CV.*?:\s*\n+",
    r"^Here is the revised CV.*?:\s*\n+",
    r"^Here's the updated CV.*?:\s*\n+",
    r"^Here's the CV.*?:\s*\n+",
    r"^Based on the provided inputs.*?:\s*\n+",
    r"^Below is the.*?CV.*?:\s*\n+",
    r"^I've created.*?CV.*?:\s*\n+",
    r"^The following CV.*?:\s*\n+",
]


def _strip_llm_preamble(content: str) -> str:
    """Remove common LLM preambles from generated CV content."""
    cleaned = content.strip()
    for pattern in LLM_PREAMBLE_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE | re.DOTALL)
    return cleaned.strip()


class MarkdownCVGenerator:
    """LLM-driven CV generator that outputs markdown to ./applications/<company>/<role>/CV.md."""

    def __init__(self):
        # GAP-066: Token tracking enabled via factory
        self.llm = create_tracked_cv_llm(layer="layer6_cv")
        self.prompt_path = Path("prompts/cv-creator.prompt.md")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    def _call_llm(self, messages: list) -> str:
        """
        Call LLM with retry logic for transient failures.

        Uses exponential backoff: 2s, 4s, 8s...up to 30s max wait.

        Args:
            messages: List of SystemMessage/HumanMessage

        Returns:
            Raw response content from LLM

        Raises:
            Exception: After 3 failed attempts
        """
        response = self.llm.invoke(messages)
        return response.content.strip()

    def _load_prompt_template(self) -> str:
        if self.prompt_path.exists():
            return self.prompt_path.read_text(encoding="utf-8")
        return "Instructions not found (prompts/cv-creator.prompt.md). Use provided context to tailor the CV."

    def _sanitize_path(self, value: str) -> str:
        """Sanitize a string for use in filesystem paths."""
        return sanitize_path_component(value, max_length=80)

    def _build_user_prompt(self, state: JobState) -> str:
        # NOTE: Use `or []` to handle None values (state.get returns None if key exists with None value)
        pain_points = "\n".join(state.get("pain_points") or [])
        strategic_needs = "\n".join(state.get("strategic_needs") or [])
        risks = "\n".join(state.get("risks_if_unfilled") or [])
        success_metrics = "\n".join(state.get("success_metrics") or [])

        company_research = state.get("company_research") or {}
        company_research_text = company_research.get("summary") or ""
        signals_list = company_research.get("signals") or []
        if signals_list:
            signals = "; ".join(
                f"{sig.get('type', 'signal')}: {sig.get('description', '')}"
                for sig in signals_list
            )
            company_research_text += f"\nSignals: {signals}"

        role_research = state.get("role_research") or {}
        role_research_text = role_research.get("summary") or ""
        business_impact = role_research.get("business_impact") or []
        if business_impact:
            role_research_text += "\nImpact: " + "; ".join(business_impact)
        why_now = role_research.get("why_now") or ""
        if why_now:
            role_research_text += f"\nWhy now: {why_now}"

        prompt_template = self._load_prompt_template()
        job_description = state.get("job_description") or ""

        return f"""{prompt_template}

JOB DOSSIER:
- Title: {state.get('title', '')}
- Company: {state.get('company', '')}
- Job URL: {state.get('job_url', '')}
- Source: {state.get('source', '')}

PAIN POINTS:
{pain_points or 'Not extracted'}

STRATEGIC NEEDS:
{strategic_needs or 'Not extracted'}

RISKS IF UNFILLED:
{risks or 'Not extracted'}

SUCCESS METRICS:
{success_metrics or 'Not extracted'}

COMPANY RESEARCH:
{company_research_text or 'No research available'}

ROLE RESEARCH:
{role_research_text or 'No role research available'}

JOB DESCRIPTION (FULL TEXT):
{job_description or 'Job description not available'}

MASTER CV:
{state.get('candidate_profile', '')}
"""

    def _extract_integrity_check(self, content: str) -> str:
        match = re.search(r'(Integrity Check|Integrity)\s*[:\-]?\s*(.*)', content, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(2).strip()
        return "Integrity check not provided."

    def _parse_json(self, raw: str) -> Dict[str, Any]:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except json.JSONDecodeError:
                    return {}
        return {}

    def _qa_evidence(self, evidence: Dict[str, Any]) -> List[str]:
        issues: List[str] = []
        roles = evidence.get("roles") or []
        if not roles:
            return ["No roles returned in evidence JSON."]

        for r_index, role in enumerate(roles):
            bullets = role.get("bullets") or []
            if not bullets:
                issues.append(f"Role {r_index + 1} missing bullets.")
                continue

            for b_index, bullet in enumerate(bullets):
                action = (bullet.get("action") or "").strip()
                metric = (bullet.get("metric") or "").strip()
                pain = (bullet.get("pain_point_hit") or "").strip()
                if not action:
                    issues.append(f"Role {r_index + 1} bullet {b_index + 1}: missing action.")
                if not metric:
                    issues.append(f"Role {r_index + 1} bullet {b_index + 1}: missing metric.")
                if not pain:
                    issues.append(f"Role {r_index + 1} bullet {b_index + 1}: missing pain_point_hit.")
        return issues

    def _generate_bullet_evidence(self, user_prompt: str) -> Dict[str, Any]:
        messages = [
            SystemMessage(content=CV_EVIDENCE_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt)
        ]
        response = self._call_llm(messages)
        evidence = self._parse_json(response)
        issues = self._qa_evidence(evidence)

        if issues:
            retry_prompt = user_prompt + "\n\nFIX THE FOLLOWING ISSUES AND REPLY WITH VALID JSON ONLY:\n- " + "\n- ".join(issues)
            retry_messages = [
                SystemMessage(content=CV_EVIDENCE_SYSTEM_PROMPT),
                HumanMessage(content=retry_prompt)
            ]
            retry_response = self._call_llm(retry_messages)
            evidence = self._parse_json(retry_response)
        return evidence

    def _collect_allowed_verbs(self, job_description: str) -> List[str]:
        verbs: List[str] = []
        for line in job_description.splitlines():
            match = re.match(r'^\s*[-*•]?\s*([A-Za-z]+)', line)
            if match:
                verb = match.group(1).lower()
                if verb:
                    verbs.append(verb)
        return verbs

    def _qa_final_bullets(self, cv_content: str, pain_points: List[str], success_metrics: List[str], allowed_verbs: List[str]) -> List[str]:
        issues: List[str] = []
        bullets = re.findall(r'^\s*[-•]\s+(.*)', cv_content, flags=re.MULTILINE)
        allowed = set(v.lower() for v in allowed_verbs) | STRONG_VERBS
        pain_success_terms = [p.lower() for p in (pain_points + success_metrics) if p]

        for idx, bullet in enumerate(bullets):
            first_word = bullet.split()[0].lower() if bullet.split() else ""
            if first_word and first_word not in allowed:
                issues.append(f"Bullet {idx + 1} should start with a strong verb (found '{first_word}').")

            if not re.search(r'\d', bullet):
                issues.append(f"Bullet {idx + 1} missing metric/result.")

            if pain_success_terms and not any(term in bullet.lower() for term in pain_success_terms):
                issues.append(f"Bullet {idx + 1} missing reference to pain point or success metric.")
        return issues

    def _strip_emphasis(self, text: str) -> str:
        """Remove simple markdown emphasis markers used in headings."""
        return text.replace("**", "").replace("__", "").strip()

    def _looks_like_role_meta(self, line: str) -> bool:
        """Return True for company/location/date lines that should be merged into headings."""
        normalized = line.lower()
        has_date_hint = any(char.isdigit() for char in normalized) or "|" in normalized
        return ("—" in normalized or " - " in normalized) and has_date_hint

    def _looks_like_role_title(self, line: str) -> bool:
        """Heuristic to detect role title lines inside experience sections."""
        if line.startswith("#") or line.startswith("-"):
            return False
        return any(keyword in line.lower() for keyword in ["engineer", "lead", "manager", "architect", "director", "cto", "founder"])

    def _merge_role_lines(self, lines: List[str]) -> List[str]:
        """Merge role title line with the following company/date line for cleaner headings."""
        merged: List[str] = []
        skip_next = False

        for idx, line in enumerate(lines):
            if skip_next:
                skip_next = False
                continue

            current = line.strip()
            if idx + 1 < len(lines):
                nxt = lines[idx + 1].strip()
                if self._looks_like_role_title(current) and self._looks_like_role_meta(nxt):
                    merged.append(f"{self._strip_emphasis(current)} — {self._strip_emphasis(nxt)}")
                    skip_next = True
                    continue

            merged.append(current)

        return merged

    def _normalize_markdown_for_template(self, cv_content: str, state: JobState) -> str:
        """
        Standardize markdown structure so pandoc + Word template render cleanly.

        - Converts bold section labels to headings
        - Merges multi-line role headings into a single H3
        - Normalizes bullets to '- ' and removes horizontal rules
        """
        raw_lines = [line.rstrip() for line in cv_content.replace("\r\n", "\n").splitlines()]

        # Drop obvious preambles and horizontal rules that don't map to template styles
        filtered = []
        for line in raw_lines:
            stripped = line.strip()
            if not stripped or stripped in {"---", "***"}:
                continue
            if re.match(r"here is the .*cv", stripped, flags=re.IGNORECASE):
                continue
            filtered.append(stripped)

        if not filtered:
            return cv_content.strip()

        merged_lines = self._merge_role_lines(filtered)
        section_aliases = {
            "profile": "Profile",
            "professional summary": "Professional Summary",
            "summary": "Professional Summary",
            "core skills": "Core Skills",
            "skills": "Core Skills",
            "professional experience": "Professional Experience",
            "experience": "Professional Experience",
            "education": "Education & Certifications",
            "education & certifications": "Education & Certifications",
            "integrity check": "Integrity Check",
        }

        normalized: List[str] = []
        idx = 0

        # Ensure top-level heading for candidate name
        while idx < len(merged_lines) and not merged_lines[idx].strip():
            idx += 1
        if idx < len(merged_lines):
            first_line = merged_lines[idx]
            name_text = self._strip_emphasis(first_line.lstrip("#").strip())
            if not name_text:
                name_text = self._strip_emphasis(first_line)
            normalized.append(f"# {name_text}")
            idx += 1

        last_section = ""

        while idx < len(merged_lines):
            line = merged_lines[idx].strip()
            idx += 1
            if not line:
                continue

            # Preserve existing heading levels
            if line.startswith("#"):
                normalized.append(line)
                if line.startswith("##"):
                    last_section = self._strip_emphasis(line.lstrip("#").strip()).lower()
                continue

            # Bold section labels -> H2
            bold_section = re.match(r"^\*\*(.+?)\*\*:?$", line)
            if bold_section:
                title = bold_section.group(1).strip()
                normalized_title = section_aliases.get(title.lower(), title)
                normalized.append(f"## {normalized_title}")
                last_section = normalized_title.lower()
                continue

            # Integrity check heading and inline content
            if line.lower().startswith("integrity check"):
                normalized.append("## Integrity Check")
                tail = line.split(":", 1)[1].strip() if ":" in line else ""
                if tail:
                    normalized.append(tail)
                last_section = "integrity check"
                continue

            # Role headings inside experience
            if last_section == "professional experience" and (self._looks_like_role_meta(line) or self._looks_like_role_title(line)):
                normalized.append(f"### {self._strip_emphasis(line)}")
                continue

            # Normalize bullets
            if re.match(r"^[•\-]\s+", line):
                bullet_text = re.sub(r"^[•\-]\s+", "", line)
                normalized.append(f"- {bullet_text}")
                continue

            normalized.append(line)

        # Collapse extra blank lines to keep markdown tidy
        final_lines: List[str] = []
        for line in normalized:
            if line == "" and (not final_lines or final_lines[-1] == ""):
                continue
            final_lines.append(line)

        return "\n".join(final_lines).strip() + "\n"

    def generate_cv(self, state: JobState) -> Tuple[str, str]:
        user_prompt = self._build_user_prompt(state)
        pain_points_list: List[str] = state.get("pain_points") or []
        success_metrics_list: List[str] = state.get("success_metrics") or []
        job_description = state.get("job_description") or ""
        allowed_verbs = self._collect_allowed_verbs(job_description)

        evidence = self._generate_bullet_evidence(user_prompt)
        evidence_json = json.dumps(evidence, ensure_ascii=True)

        final_prompt = f"""{user_prompt}

ROLE BULLET EVIDENCE JSON (DO NOT IGNORE):
{evidence_json}
"""
        messages = [
            SystemMessage(content=CV_SYSTEM_PROMPT),
            HumanMessage(content=final_prompt)
        ]

        cv_content = self._call_llm(messages)

        bullet_issues = self._qa_final_bullets(cv_content, pain_points_list, success_metrics_list, allowed_verbs)
        if bullet_issues:
            retry_prompt = final_prompt + "\nPREVIOUS DRAFT FAILED QA (FIX ONLY BULLETS):\n- " + "\n- ".join(bullet_issues)
            retry_messages = [
                SystemMessage(content=CV_SYSTEM_PROMPT),
                HumanMessage(content=retry_prompt)
            ]
            cv_content = self._call_llm(retry_messages)

        integrity = self._extract_integrity_check(cv_content)

        # Strip LLM preambles like "Here is the updated CV..."
        cv_content = _strip_llm_preamble(cv_content)
        cv_content = self._normalize_markdown_for_template(cv_content, state)

        company_clean = self._sanitize_path(state.get("company", "company"))
        role_clean = self._sanitize_path(state.get("title", "role"))
        output_dir = Path("applications") / company_clean / role_clean
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "CV.md"
        output_path.write_text(cv_content, encoding="utf-8")

        return str(output_path), integrity


class Generator:
    """
    Main class orchestrating cover letter and CV generation.

    Phase 8.1: Uses enhanced CoverLetterGenerator with validation gates.
    Phase 8.2: Uses MarkdownCVGenerator grounded in the master CV and job dossier.
    """

    def __init__(self):
        """Initialize generators."""
        # Logger for internal operations
        self.logger = logging.getLogger(__name__)

        self.cover_letter_gen = CoverLetterGenerator()  # Phase 8.1: Enhanced cover letter generator
        self.cv_gen = MarkdownCVGenerator()  # Markdown CV generator grounded in master CV

        # HTML CV generator for web display and PDF export
        try:
            from src.layer6.html_cv_generator import HTMLCVGenerator
            self.html_cv_gen = HTMLCVGenerator()
        except ImportError:
            self.html_cv_gen = None  # Fallback if HTML generator not available

    def generate_outputs(self, state: JobState) -> Dict[str, Any]:
        """
        Generate both cover letter and CV.

        Args:
            state: JobState with all previous layer outputs

        Returns:
            Dict with cover_letter, cv_path, and cv_reasoning keys (Phase 8.2)
        """
        try:
            self.logger.info("Generating cover letter")
            cover_letter = self.cover_letter_gen.generate_cover_letter(state)
            self.logger.info(f"Cover letter generated ({len(cover_letter)} chars)")

            self.logger.info("Generating tailored CV")
            cv_path, cv_reasoning = self.cv_gen.generate_cv(state)
            self.logger.info(f"CV generated: {cv_path}")
            self.logger.info(f"CV reasoning: {cv_reasoning[:100]}...")

            # Generate HTML CV for web display and PDF export
            html_cv_path = None
            if self.html_cv_gen:
                try:
                    self.logger.info("Generating HTML CV")
                    html_cv_path, _ = self.html_cv_gen.generate_html_cv(state)
                    self.logger.info(f"HTML CV generated: {html_cv_path}")
                except Exception as e:
                    self.logger.warning(f"HTML CV generation failed: {e}")

            return {
                "cover_letter": cover_letter,
                "cv_path": cv_path,
                "html_cv_path": html_cv_path,  # New: HTML CV for web display
                "cv_reasoning": cv_reasoning  # Phase 8.2: STAR selection rationale
            }

        except Exception as e:
            error_msg = f"Layer 6 (Generator) failed: {str(e)}"
            self.logger.error(error_msg)

            errors_list = state.get("errors") or []
            if isinstance(errors_list, str):
                errors_list = [errors_list]

            return {
                "cover_letter": None,
                "cv_path": None,
                "errors": errors_list + [error_msg]
            }


# ===== LANGGRAPH NODE FUNCTION =====

def generator_node(state: JobState) -> Dict[str, Any]:
    """
    LangGraph node function for Layer 6: Outreach & CV Generator.

    Args:
        state: Current job processing state

    Returns:
        Dictionary with updates to merge into state
    """
    logger = get_logger(__name__, run_id=state.get("run_id"), layer="layer6")
    struct_logger = get_structured_logger(state.get("job_id", ""))

    logger.info("="*60)
    logger.info("LAYER 6: Outreach & CV Generator")
    logger.info("="*60)

    with LayerContext(struct_logger, 6, "cv_generator") as ctx:
        generator = Generator()
        updates = generator.generate_outputs(state)

        # Read CV content from disk for MongoDB persistence
        cv_path = updates.get("cv_path")
        if cv_path and os.path.exists(cv_path):
            try:
                cv_text = Path(cv_path).read_text(encoding="utf-8")
                updates["cv_text"] = cv_text
                logger.info(f"CV text loaded ({len(cv_text)} chars)")
                ctx.add_metadata("cv_chars", len(cv_text))
            except Exception as e:
                logger.warning(f"Failed to read CV text: {e}")
                updates["cv_text"] = None
        else:
            updates["cv_text"] = None

        # Log results and add metadata
        has_cover_letter = bool(updates.get("cover_letter"))
        has_cv = bool(updates.get("cv_path"))
        ctx.add_metadata("has_cover_letter", has_cover_letter)
        ctx.add_metadata("has_cv", has_cv)

        if has_cover_letter:
            logger.info("Cover Letter Preview (first 150 chars):")
            logger.info(f"  {updates['cover_letter'][:150]}...")
        else:
            logger.warning("No cover letter generated")

        if has_cv:
            logger.info(f"CV Generated: {updates['cv_path']}")
        else:
            logger.warning("No CV generated")

    logger.info("="*60)

    return updates
