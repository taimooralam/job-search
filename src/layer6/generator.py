"""
Layer 6: Outreach & CV Generator

Generates personalized cover letter and tailored CV based on all previous analysis.

Phase 8.1: Enhanced cover letter generator with validation gates.
Phase 8.2: STAR-driven CV generator (to be implemented).
"""

import re
from pathlib import Path
from typing import Dict, Any, Tuple
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from src.common.config import Config
from src.common.state import JobState
from src.layer6.cover_letter_generator import CoverLetterGenerator


CV_SYSTEM_PROMPT = """You are a CV-tailoring assistant. Your job is to create a non-hallucinated, ATS-friendly, personalized CV using only the data provided in the user prompt (job dossier, master CV, and any supporting analysis). Do multi-step reasoning: classify the role, align titles, select and prioritize skills, craft profile and experience sections, and ensure every statement is grounded in the supplied inputs. Compact bullets (STAR-style), keep them factual (may tighten/boost impact modestly without inventing), and mirror the job’s terminology. If any required input is missing, state that and proceed with what you have. Output only the completed CV and a brief integrity check outlining any uncertainties; do not add extra commentary"""


class MarkdownCVGenerator:
    """LLM-driven CV generator that outputs markdown to ./applications/<company>/<role>/CV.md."""

    def __init__(self):
        self.llm = ChatOpenAI(
            model=Config.DEFAULT_MODEL,
            temperature=Config.ANALYTICAL_TEMPERATURE,
            api_key=Config.get_llm_api_key(),
            base_url=Config.get_llm_base_url(),
        )
        self.prompt_path = Path("prompts/cv-creator.prompt.md")

    def _load_prompt_template(self) -> str:
        if self.prompt_path.exists():
            return self.prompt_path.read_text(encoding="utf-8")
        return "Instructions not found (prompts/cv-creator.prompt.md). Use provided context to tailor the CV."

    def _sanitize_path(self, value: str) -> str:
        safe = value.replace("/", "_").replace("\\", "_").replace(" ", "_").replace(",", "").replace(".", "")
        return safe[:80] or "role"

    def _build_user_prompt(self, state: JobState) -> str:
        pain_points = "\n".join(state.get("pain_points") or [])
        strategic_needs = "\n".join(state.get("strategic_needs") or [])
        risks = "\n".join(state.get("risks_if_unfilled") or [])
        success_metrics = "\n".join(state.get("success_metrics") or [])

        company_research = state.get("company_research") or {}
        company_research_text = company_research.get("summary", "")
        if company_research.get("signals"):
            signals = "; ".join(
                f"{sig.get('type', 'signal')}: {sig.get('description', '')}"
                for sig in company_research["signals"]
            )
            company_research_text += f"\nSignals: {signals}"

        role_research = state.get("role_research") or {}
        role_research_text = role_research.get("summary", "")
        if role_research.get("business_impact"):
            role_research_text += "\nImpact: " + "; ".join(role_research["business_impact"])
        if role_research.get("why_now"):
            role_research_text += f"\nWhy now: {role_research['why_now']}"

        prompt_template = self._load_prompt_template()

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

MASTER CV:
{state.get('candidate_profile', '')}
"""

    def _extract_integrity_check(self, content: str) -> str:
        match = re.search(r'(Integrity Check|Integrity)\s*[:\-]?\s*(.*)', content, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(2).strip()
        return "Integrity check not provided."

    def generate_cv(self, state: JobState) -> Tuple[str, str]:
        user_prompt = self._build_user_prompt(state)
        messages = [
            SystemMessage(content=CV_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt)
        ]

        response = self.llm.invoke(messages)
        cv_content = response.content.strip()
        integrity = self._extract_integrity_check(cv_content)

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
        """Initialize both generators."""
        self.cover_letter_gen = CoverLetterGenerator()  # Phase 8.1: Enhanced cover letter generator
        self.cv_gen = MarkdownCVGenerator()  # Markdown CV generator grounded in master CV

    def generate_outputs(self, state: JobState) -> Dict[str, Any]:
        """
        Generate both cover letter and CV.

        Args:
            state: JobState with all previous layer outputs

        Returns:
            Dict with cover_letter, cv_path, and cv_reasoning keys (Phase 8.2)
        """
        try:
            print(f"   Generating cover letter...")
            cover_letter = self.cover_letter_gen.generate_cover_letter(state)
            print(f"   ✓ Cover letter generated ({len(cover_letter)} chars)")

            print(f"   Generating tailored CV...")
            cv_path, cv_reasoning = self.cv_gen.generate_cv(state)
            print(f"   ✓ CV generated: {cv_path}")
            print(f"   ✓ CV reasoning: {cv_reasoning[:100]}...")

            return {
                "cover_letter": cover_letter,
                "cv_path": cv_path,
                "cv_reasoning": cv_reasoning  # Phase 8.2: STAR selection rationale
            }

        except Exception as e:
            error_msg = f"Layer 6 (Generator) failed: {str(e)}"
            print(f"   ✗ {error_msg}")

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
    print("\n" + "="*60)
    print("LAYER 6: Outreach & CV Generator")
    print("="*60)

    generator = Generator()
    updates = generator.generate_outputs(state)

    # Print results
    if updates.get("cover_letter"):
        print(f"\n📄 Cover Letter Preview (first 150 chars):")
        print(f"  {updates['cover_letter'][:150]}...")
    else:
        print("\n⚠️  No cover letter generated")

    if updates.get("cv_path"):
        print(f"\n📋 CV Generated: {updates['cv_path']}")
    else:
        print("\n⚠️  No CV generated")

    print("="*60 + "\n")

    return updates
