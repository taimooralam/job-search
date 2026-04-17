"""
T7 — jd_structure stage adapter.

Validates:
- JDStructureStage.run() produces a StageResult with processed_jd_sections
- Output patch key is "processed_jd_sections"
- provider_used and prompt_version are set
- Stage satisfies StageBase protocol
"""

import pytest
from unittest.mock import patch, MagicMock
from dataclasses import dataclass
from typing import Any, Optional

from src.preenrich.types import StageContext, StepConfig
from src.preenrich.stages.base import StageBase


# ---------------------------------------------------------------------------
# Minimal mocks for layer1_4 dependency
# ---------------------------------------------------------------------------


@dataclass
class _FakeLLMMetadata:
    backend: str = "rule"
    model: Optional[str] = None
    cost_usd: Optional[float] = 0.0


@dataclass
class _FakeSection:
    section_type: Any
    title: str
    content: str
    char_start: int
    char_end: int


class _FakeSectionType:
    def __init__(self, val: str):
        self.value = val


@dataclass
class _FakeProcessedJD:
    sections: list


def _mock_process_jd_sync(description: str, use_llm: bool = False):
    """Minimal mock returning two sections."""
    sections = [
        _FakeSection(
            section_type=_FakeSectionType("responsibilities"),
            title="Responsibilities",
            content="Build ML models",
            char_start=0,
            char_end=20,
        ),
        _FakeSection(
            section_type=_FakeSectionType("requirements"),
            title="Requirements",
            content="5+ years Python",
            char_start=21,
            char_end=40,
        ),
    ]
    return _FakeProcessedJD(sections=sections), _FakeLLMMetadata()


def _make_ctx(description="We are looking for ML engineers.") -> StageContext:
    return StageContext(
        job_doc={"_id": "job1", "description": description},
        jd_checksum="sha256:abc",
        company_checksum="sha256:co",
        input_snapshot_id="sha256:snap",
        attempt_number=1,
        config=StepConfig(provider="claude", prompt_version="v1"),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@patch("src.layer1_4.jd_processor.process_jd_sync", side_effect=_mock_process_jd_sync)
def test_jd_structure_run_returns_stage_result(mock_fn):
    """JDStructureStage.run() returns a StageResult with output patch."""
    from src.preenrich.stages.jd_structure import JDStructureStage

    stage = JDStructureStage()
    ctx = _make_ctx()
    result = stage.run(ctx)

    assert result is not None
    assert "processed_jd_sections" in result.output
    sections = result.output["processed_jd_sections"]
    assert isinstance(sections, list)
    assert len(sections) == 2


@patch("src.layer1_4.jd_processor.process_jd_sync", side_effect=_mock_process_jd_sync)
def test_jd_structure_section_shape(mock_fn):
    """Each section in output has required fields."""
    from src.preenrich.stages.jd_structure import JDStructureStage

    stage = JDStructureStage()
    result = stage.run(_make_ctx())
    sections = result.output["processed_jd_sections"]

    for s in sections:
        assert "section_type" in s
        assert "title" in s
        assert "content" in s
        assert "char_start" in s
        assert "char_end" in s


@patch("src.layer1_4.jd_processor.process_jd_sync", side_effect=_mock_process_jd_sync)
def test_jd_structure_provider_and_prompt_version(mock_fn):
    """StageResult has provider_used and prompt_version set."""
    from src.preenrich.stages.jd_structure import JDStructureStage

    stage = JDStructureStage()
    result = stage.run(_make_ctx())

    assert result.prompt_version is not None
    # provider_used comes from llm_metadata.backend
    assert result.provider_used is not None


@patch("src.layer1_4.jd_processor.process_jd_sync", side_effect=_mock_process_jd_sync)
def test_jd_structure_duration_ms_set(mock_fn):
    """duration_ms is set (may be 0 in fast test env)."""
    from src.preenrich.stages.jd_structure import JDStructureStage

    stage = JDStructureStage()
    result = stage.run(_make_ctx())
    assert result.duration_ms is not None
    assert result.duration_ms >= 0


@patch("src.layer1_4.jd_processor.process_jd_sync", side_effect=_mock_process_jd_sync)
def test_jd_structure_satisfies_stage_base_protocol(mock_fn):
    """JDStructureStage satisfies StageBase protocol."""
    from src.preenrich.stages.jd_structure import JDStructureStage

    stage = JDStructureStage()
    assert isinstance(stage, StageBase)
    assert stage.name == "jd_structure"
    assert stage.dependencies == []


@patch("src.layer1_4.jd_processor.process_jd_sync", side_effect=_mock_process_jd_sync)
def test_jd_structure_empty_description(mock_fn):
    """Empty description is handled without error."""
    from src.preenrich.stages.jd_structure import JDStructureStage

    stage = JDStructureStage()
    ctx = _make_ctx(description="")
    result = stage.run(ctx)
    assert "processed_jd_sections" in result.output
