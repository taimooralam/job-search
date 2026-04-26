"""
Tests for company_research stage (T12).

BDD scenario S9: 7d cache hit → SKIPPED + per-job materialization via patch.

Verifies:
- Cache hit within 7d → StageResult with skip_reason="company_cache_hit", output patch populated
- Cache hit returns cache_source_job_id set to the company_key
- Cache MISS → CompanyResearcher called, company_cache written, COMPLETED result
- Cache entry expired → treated as MISS
- Company name missing → ValueError
- CompanyResearcher failure → ValueError
- role_research is NOT run here (separate stage)
- Codex raises NotImplementedError
"""

from datetime import datetime, timedelta
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

import pytest

from src.preenrich.stages.company_research import CompanyResearchStage
from src.preenrich.types import StageContext, StepConfig

# ── Fixtures ─────────────────────────────────────────────────────────────────


def _make_ctx(
    provider: str = "claude",
    company_name: str = "Acme Corp",
    job_doc: Optional[Dict[str, Any]] = None,
) -> StageContext:
    if job_doc is None:
        job_doc = {
            "_id": "job_cr_001",
            "title": "Senior AI Engineer",
            "company": company_name,
            "description": "Build AI systems.",
            "extracted_jd": {"role_category": "ai_engineering"},
        }
    return StageContext(
        job_doc=job_doc,
        jd_checksum="sha256:cr001",
        company_checksum="sha256:comp001",
        input_snapshot_id="sha256:cr001",
        attempt_number=1,
        config=StepConfig(provider=provider),
    )


_MOCK_COMPANY_RESEARCH = {
    "company_type": "employer",
    "summary": "Leading AI company",
    "url": "https://acme.example.com",
    "signals": ["Raised Series B", "Expanding AI team"],
}

_CACHED_ENTRY_FRESH = {
    "company_key": "acme corp",
    "company_name": "Acme Corp",
    "company_research": _MOCK_COMPANY_RESEARCH,
    "cached_at": datetime.utcnow() - timedelta(days=3),  # Within 7d TTL
}

_CACHED_ENTRY_EXPIRED = {
    "company_key": "acme corp",
    "company_name": "Acme Corp",
    "company_research": _MOCK_COMPANY_RESEARCH,
    "cached_at": datetime.utcnow() - timedelta(days=10),  # Expired (>7d)
}


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestCompanyResearchStageProtocol:
    def test_has_name(self):
        assert CompanyResearchStage().name == "company_research"

    def test_has_dependencies(self):
        # company_research has no stage dependencies (company name-driven)
        assert CompanyResearchStage().dependencies == []

    def test_has_run_method(self):
        assert callable(CompanyResearchStage().run)


class TestCompanyResearchStageProviderRouting:
    def test_codex_raises_not_implemented(self):
        ctx = _make_ctx(provider="codex")
        with pytest.raises(NotImplementedError, match="codex provider"):
            CompanyResearchStage().run(ctx)

    def test_unknown_provider_raises_value_error(self):
        ctx = _make_ctx(provider="openai")
        with pytest.raises(ValueError, match="Unsupported provider"):
            CompanyResearchStage().run(ctx)


class TestCompanyResearchStageCacheHit:
    @patch("src.preenrich.stages.company_research.get_company_cache_repository")
    def test_cache_hit_within_ttl_returns_skipped(self, mock_get_repo):
        """S9: 7d cache hit → skip_reason="company_cache_hit", patch populated."""
        mock_repo = MagicMock()
        mock_repo.find_by_company_key.return_value = _CACHED_ENTRY_FRESH
        mock_get_repo.return_value = mock_repo

        ctx = _make_ctx()
        result = CompanyResearchStage().run(ctx)

        assert result.skip_reason == "company_cache_hit"

    @patch("src.preenrich.stages.company_research.get_company_cache_repository")
    def test_cache_hit_patch_contains_company_research(self, mock_get_repo):
        """S9: cached data must be materialized into patch (per-job copy)."""
        mock_repo = MagicMock()
        mock_repo.find_by_company_key.return_value = _CACHED_ENTRY_FRESH
        mock_get_repo.return_value = mock_repo

        ctx = _make_ctx()
        result = CompanyResearchStage().run(ctx)

        assert "company_research" in result.output
        assert result.output["company_research"]["summary"] == "Leading AI company"

    @patch("src.preenrich.stages.company_research.get_company_cache_repository")
    def test_cache_hit_legacy_fields_in_patch(self, mock_get_repo):
        """Legacy fields company_summary and company_url must be in patch."""
        mock_repo = MagicMock()
        mock_repo.find_by_company_key.return_value = _CACHED_ENTRY_FRESH
        mock_get_repo.return_value = mock_repo

        ctx = _make_ctx()
        result = CompanyResearchStage().run(ctx)

        assert "company_summary" in result.output
        assert "company_url" in result.output

    @patch("src.preenrich.stages.company_research.get_company_cache_repository")
    def test_cache_hit_cache_source_job_id_is_company_key(self, mock_get_repo):
        """S9: cache_source_job_id must be the canonical company_key."""
        mock_repo = MagicMock()
        mock_repo.find_by_company_key.return_value = _CACHED_ENTRY_FRESH
        mock_get_repo.return_value = mock_repo

        ctx = _make_ctx(company_name="Acme Corp")
        result = CompanyResearchStage().run(ctx)

        assert result.cache_source_job_id == "acme corp"  # company_key (lowercase)

    @patch("src.preenrich.stages.company_research.get_company_cache_repository")
    @patch("src.preenrich.stages.company_research.CompanyResearcher")
    def test_cache_hit_does_not_call_researcher(self, mock_researcher_cls, mock_get_repo):
        """When cache hit, CompanyResearcher must NOT be instantiated."""
        mock_repo = MagicMock()
        mock_repo.find_by_company_key.return_value = _CACHED_ENTRY_FRESH
        mock_get_repo.return_value = mock_repo

        CompanyResearchStage().run(_make_ctx())

        mock_researcher_cls.assert_not_called()


class TestCompanyResearchStageCacheMiss:
    @patch("src.preenrich.stages.company_research.get_company_cache_repository")
    @patch("src.preenrich.stages.company_research.CompanyResearcher")
    def test_cache_miss_calls_researcher(self, mock_researcher_cls, mock_get_repo):
        """Cache miss: CompanyResearcher.research_company must be called."""
        mock_repo = MagicMock()
        mock_repo.find_by_company_key.return_value = None  # Cache MISS
        mock_get_repo.return_value = mock_repo

        mock_researcher = MagicMock()
        mock_researcher.research_company.return_value = {
            "company_research": _MOCK_COMPANY_RESEARCH
        }
        mock_researcher_cls.return_value = mock_researcher

        ctx = _make_ctx()
        result = CompanyResearchStage().run(ctx)

        mock_researcher.research_company.assert_called_once()
        assert result.skip_reason is None  # COMPLETED

    @patch("src.preenrich.stages.company_research.get_company_cache_repository")
    @patch("src.preenrich.stages.company_research.CompanyResearcher")
    def test_cache_miss_writes_cache_entry(self, mock_researcher_cls, mock_get_repo):
        """Fresh research result must be written to company_cache."""
        mock_repo = MagicMock()
        mock_repo.find_by_company_key.return_value = None
        mock_get_repo.return_value = mock_repo

        mock_researcher = MagicMock()
        mock_researcher.research_company.return_value = {
            "company_research": _MOCK_COMPANY_RESEARCH
        }
        mock_researcher_cls.return_value = mock_researcher

        CompanyResearchStage().run(_make_ctx())

        mock_repo.upsert_cache.assert_called_once()
        cache_key_arg = mock_repo.upsert_cache.call_args[0][0]
        assert cache_key_arg == "acme corp"

    @patch("src.preenrich.stages.company_research.get_company_cache_repository")
    @patch("src.preenrich.stages.company_research.CompanyResearcher")
    def test_cache_expired_treated_as_miss(self, mock_researcher_cls, mock_get_repo):
        """Expired cache entry must trigger fresh research."""
        mock_repo = MagicMock()
        mock_repo.find_by_company_key.return_value = _CACHED_ENTRY_EXPIRED
        mock_get_repo.return_value = mock_repo

        mock_researcher = MagicMock()
        mock_researcher.research_company.return_value = {
            "company_research": _MOCK_COMPANY_RESEARCH
        }
        mock_researcher_cls.return_value = mock_researcher

        CompanyResearchStage().run(_make_ctx())

        # Researcher must be called (expired = miss)
        mock_researcher.research_company.assert_called_once()


class TestCompanyResearchStageErrors:
    def test_missing_company_name_raises_value_error(self):
        ctx = _make_ctx(job_doc={
            "_id": "job_no_company",
            "title": "Engineer",
            "company": "",
            "description": "Work.",
        })
        with pytest.raises(ValueError, match="No company name"):
            CompanyResearchStage().run(ctx)

    @patch("src.preenrich.stages.company_research.get_company_cache_repository")
    @patch("src.preenrich.stages.company_research.CompanyResearcher")
    def test_researcher_failure_raises_value_error(self, mock_researcher_cls, mock_get_repo):
        mock_repo = MagicMock()
        mock_repo.find_by_company_key.return_value = None
        mock_get_repo.return_value = mock_repo

        mock_researcher = MagicMock()
        mock_researcher.research_company.side_effect = RuntimeError("WebSearch failed")
        mock_researcher_cls.return_value = mock_researcher

        with pytest.raises(ValueError, match="CompanyResearcher failed"):
            CompanyResearchStage().run(_make_ctx())

    @patch("src.preenrich.stages.company_research.get_company_cache_repository")
    @patch("src.preenrich.stages.company_research.CompanyResearcher")
    def test_empty_company_research_in_result_raises_value_error(self, mock_researcher_cls, mock_get_repo):
        mock_repo = MagicMock()
        mock_repo.find_by_company_key.return_value = None
        mock_get_repo.return_value = mock_repo

        mock_researcher = MagicMock()
        mock_researcher.research_company.return_value = {
            "company_research": None,
            "errors": ["All fallbacks exhausted"]
        }
        mock_researcher_cls.return_value = mock_researcher

        with pytest.raises(ValueError, match="company_research stage failed"):
            CompanyResearchStage().run(_make_ctx())

    @patch("src.preenrich.stages.company_research.get_company_cache_repository")
    @patch("src.preenrich.stages.company_research.CompanyResearcher")
    def test_cache_write_failure_is_non_fatal(self, mock_researcher_cls, mock_get_repo):
        """Cache write failure must not abort the stage — research already succeeded."""
        mock_repo = MagicMock()
        mock_repo.find_by_company_key.return_value = None
        mock_repo.upsert_cache.side_effect = RuntimeError("Mongo write failed")
        mock_get_repo.return_value = mock_repo

        mock_researcher = MagicMock()
        mock_researcher.research_company.return_value = {
            "company_research": _MOCK_COMPANY_RESEARCH
        }
        mock_researcher_cls.return_value = mock_researcher

        # Should not raise — cache write is best-effort
        result = CompanyResearchStage().run(_make_ctx())
        assert result.skip_reason is None  # COMPLETED
        assert "company_research" in result.output
