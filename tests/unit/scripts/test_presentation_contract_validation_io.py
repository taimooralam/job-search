from pathlib import Path

from bson import ObjectId

from scripts.presentation_contract_validation_io import (
    load_validation_fixture,
    validation_target_key,
)

FIXTURE_PATH = Path("data/presentation_contract_fixtures/low_ai_adjacent_full_upstream.json")


def test_load_validation_fixture_coerces_object_id_and_preserves_upstream_payload() -> None:
    job = load_validation_fixture(FIXTURE_PATH)

    assert isinstance(job["_id"], ObjectId)
    assert job["job_id"] == "fixture-low-ai-adjacent-platform-architect"
    assert job["pre_enrichment"]["outputs"]["classification"]["ai_taxonomy"]["intensity"] == "adjacent"


def test_validation_target_key_sanitizes_user_facing_identifier() -> None:
    key = validation_target_key({"job_id": "fixture:low ai/adjacent"})

    assert key == "fixture-low-ai-adjacent"
