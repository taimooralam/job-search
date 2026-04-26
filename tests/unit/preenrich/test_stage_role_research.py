"""
Tests for role_research stage (T13).

Verifies:
- Depends on jd_extraction and company_research
- Runs even when company_research was a cache hit (company data materialized in job_doc)
- Missing company_research raises ValueError
- Recruitment agency skips role research
- RoleResearcher failure propagates as ValueError
- Output patch contains role_research
"""

from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

import pytest

from src.preenrich.stages.role_research import RoleResearchStage
from src.preenrich.types import StageContext, StepConfig

# ── Fixtures ─────────────────────────────────────────────────────────────────


_MOCK_COMPANY_RESEARCH = {
    "company_type": "employer",
    "summary": "AI-first company",
    "url": "https://example.com",
    "signals": ["Series B"],
}

_MOCK_ROLE_RESEARCH = {
    "summary": "Lead AI platform engineering",
    "business_impact": [
        "Reduce model latency by 40%",
        "Enable real-time AI features",
        "Drive $2M cost reduction",
    ],
    "why_now": "Post-Series-B headcount expansion for AI capabilities.",
}


def _make_ctx(
    provider: str = "claude",
    job_doc: Optional[Dict[str, Any]] = None,
) -> StageContext:
    if job_doc is None:
        job_doc = {
            "_id": "job_rr_001",
            "title": "AI Platform Lead",
            "company": "NexusTech",
            "description": "Lead AI platform engineering for enterprise customers.",
            "extracted_jd": {"role_category": "ai_engineering"},
            "company_research": _MOCK_COMPANY_RESEARCH,
        }
    return StageContext(
        job_doc=job_doc,
        jd_checksum="sha256:rr001",
        company_checksum="sha256:comp001",
        input_snapshot_id="sha256:rr001",
        attempt_number=1,
        config=StepConfig(provider=provider),
    )


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestRoleResearchStageProtocol:
    def test_has_name(self):
        assert RoleResearchStage().name == "role_research"

    def test_has_dependencies(self):
        deps = RoleResearchStage().dependencies
        assert "jd_extraction" in deps
        assert "company_research" in deps

    def test_has_run_method(self):
        assert callable(RoleResearchStage().run)


class TestRoleResearchStageProviderRouting:
    def test_codex_raises_not_implemented(self):
        ctx = _make_ctx(provider="codex")
        with pytest.raises(NotImplementedError, match="codex provider"):
            RoleResearchStage().run(ctx)

    def test_unknown_provider_raises_value_error(self):
        ctx = _make_ctx(provider="vertex")
        with pytest.raises(ValueError, match="Unsupported provider"):
            RoleResearchStage().run(ctx)


class TestRoleResearchStageContext:
    @patch("src.preenrich.stages.role_research.RoleResearcher")
    def test_runs_with_company_research_from_cache(self, mock_researcher_cls):
        """
        Stage must run even when company_research came from cache (materialized in job_doc).
        This is the explicit behaviour change vs CompanyResearchService (plan §3.4).
        """
        mock_researcher = MagicMock()
        mock_researcher.research_role.return_value = {"role_research": _MOCK_ROLE_RESEARCH}
        mock_researcher_cls.return_value = mock_researcher

        # job_doc has company_research pre-populated (as if materialized from cache)
        ctx = _make_ctx()
        result = RoleResearchStage().run(ctx)

        mock_researcher.research_role.assert_called_once()
        assert result.skip_reason is None

    @patch("src.preenrich.stages.role_research.RoleResearcher")
    def test_output_patch_contains_role_research(self, mock_researcher_cls):
        mock_researcher = MagicMock()
        mock_researcher.research_role.return_value = {"role_research": _MOCK_ROLE_RESEARCH}
        mock_researcher_cls.return_value = mock_researcher

        result = RoleResearchStage().run(_make_ctx())

        assert "role_research" in result.output
        assert result.output["role_research"]["summary"] == _MOCK_ROLE_RESEARCH["summary"]

    @patch("src.preenrich.stages.role_research.RoleResearcher")
    def test_company_research_passed_to_state(self, mock_researcher_cls):
        """company_research must be injected into JobState for RoleResearcher."""
        mock_researcher = MagicMock()
        mock_researcher.research_role.return_value = {"role_research": _MOCK_ROLE_RESEARCH}
        mock_researcher_cls.return_value = mock_researcher

        RoleResearchStage().run(_make_ctx())

        call_arg = mock_researcher.research_role.call_args[0][0]  # JobState
        assert call_arg.get("company_research") == _MOCK_COMPANY_RESEARCH


class TestRoleResearchStageSkipCases:
    def test_missing_company_research_raises_value_error(self):
        ctx = _make_ctx(job_doc={
            "_id": "job_no_cr",
            "title": "AI Lead",
            "company": "NexusTech",
            "description": "Build AI systems.",
            "company_research": None,  # Not populated
        })
        with pytest.raises(ValueError, match="No company_research available"):
            RoleResearchStage().run(ctx)

    def test_missing_jd_text_raises_value_error(self):
        ctx = _make_ctx(job_doc={
            "_id": "job_no_jd",
            "title": "AI Lead",
            "company": "NexusTech",
            "description": "",
            "company_research": _MOCK_COMPANY_RESEARCH,
        })
        with pytest.raises(ValueError, match="No JD text"):
            RoleResearchStage().run(ctx)

    @patch("src.preenrich.stages.role_research.RoleResearcher")
    def test_recruitment_agency_returns_skipped(self, mock_researcher_cls):
        """Role research skipped for recruitment agencies (matches existing behaviour)."""
        ctx = _make_ctx(job_doc={
            "_id": "job_agency",
            "title": "AI Lead",
            "company": "RecruitPro",
            "description": "We place AI engineers.",
            "company_research": {"company_type": "recruitment_agency", "summary": "Recruiter"},
        })
        result = RoleResearchStage().run(ctx)

        assert result.skip_reason == "recruitment_agency"
        mock_researcher_cls.assert_not_called()


class TestRoleResearchStageErrorHandling:
    @patch("src.preenrich.stages.role_research.RoleResearcher")
    def test_researcher_exception_raises_value_error(self, mock_researcher_cls):
        mock_researcher = MagicMock()
        mock_researcher.research_role.side_effect = RuntimeError("LLM timeout")
        mock_researcher_cls.return_value = mock_researcher

        with pytest.raises(ValueError, match="RoleResearcher failed"):
            RoleResearchStage().run(_make_ctx())

    @patch("src.preenrich.stages.role_research.RoleResearcher")
    def test_empty_role_research_raises_value_error(self, mock_researcher_cls):
        mock_researcher = MagicMock()
        mock_researcher.research_role.return_value = {
            "role_research": None,
            "errors": ["No role data found"]
        }
        mock_researcher_cls.return_value = mock_researcher

        with pytest.raises(ValueError, match="role_research stage failed"):
            RoleResearchStage().run(_make_ctx())
