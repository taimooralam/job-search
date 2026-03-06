"""
Unit tests for cross-location deduplication functions in src/common/dedupe.py.

Covers:
- detect_region(): maps location strings to region keys
- consolidate_by_location(): groups by company+title, keeps highest priority region
  with score tiebreak when regions are equal.
"""

import pytest
from typing import Dict, List

from src.common.dedupe import detect_region, consolidate_by_location


# ---------------------------------------------------------------------------
# TestDetectRegion
# ---------------------------------------------------------------------------

class TestDetectRegion:
    """Tests for detect_region(location) -> str."""

    def test_detect_singapore(self):
        """'Singapore' should resolve to asia_pacific."""
        assert detect_region("Singapore") == "asia_pacific"

    def test_detect_dubai(self):
        """'Dubai, UAE' should resolve to emea."""
        assert detect_region("Dubai, UAE") == "emea"

    def test_detect_london(self):
        """'London, United Kingdom' should resolve to eea."""
        assert detect_region("London, United Kingdom") == "eea"

    def test_detect_us_state_abbreviation_ca(self):
        """'San Francisco, CA' must be detected as us via state abbreviation fallback."""
        assert detect_region("San Francisco, CA") == "us"

    def test_detect_us_state_abbreviation_ny(self):
        """'New York, NY' must be detected as us."""
        assert detect_region("New York, NY") == "us"

    def test_detect_us_city_keyword(self):
        """City keyword match ('new york') should also produce us."""
        assert detect_region("New York") == "us"

    def test_detect_pakistan(self):
        """'Karachi, Pakistan' should resolve to pakistan."""
        assert detect_region("Karachi, Pakistan") == "pakistan"

    def test_detect_remote(self):
        """Strings containing 'Remote' should resolve to remote."""
        assert detect_region("Remote") == "remote"

    def test_detect_remote_mixed_case(self):
        """Case-insensitive match: 'Fully Remote' should still resolve to remote."""
        assert detect_region("Fully Remote") == "remote"

    def test_detect_unknown(self):
        """An unrecognized location string should return 'unknown'."""
        assert detect_region("Mars Colony") == "unknown"

    def test_detect_empty_string(self):
        """Empty string should return 'unknown' without raising."""
        assert detect_region("") == "unknown"

    def test_detect_tokyo(self):
        """'Tokyo, Japan' should resolve to asia_pacific."""
        assert detect_region("Tokyo, Japan") == "asia_pacific"

    def test_detect_riyadh(self):
        """'Riyadh, Saudi Arabia' should resolve to emea."""
        assert detect_region("Riyadh, Saudi Arabia") == "emea"

    def test_detect_berlin(self):
        """'Berlin, Germany' should resolve to eea."""
        assert detect_region("Berlin, Germany") == "eea"

    def test_detect_lahore(self):
        """'Lahore, Pakistan' should resolve to pakistan."""
        assert detect_region("Lahore, Pakistan") == "pakistan"

    def test_detect_us_state_abbreviation_tx(self):
        """'Austin, TX' must be detected as us."""
        assert detect_region("Austin, TX") == "us"

    def test_detect_australia(self):
        """'Sydney, Australia' should resolve to asia_pacific."""
        assert detect_region("Sydney, Australia") == "asia_pacific"


# ---------------------------------------------------------------------------
# TestConsolidateByLocation
# ---------------------------------------------------------------------------

class TestConsolidateByLocation:
    """Tests for consolidate_by_location(jobs) -> List[Dict]."""

    def _job(self, company: str, title: str, location: str, score: int) -> Dict:
        return {"company": company, "title": title, "location": location, "score": score}

    def test_keeps_apac_over_us(self):
        """Singapore (asia_pacific) beats NYC (us) for same company+role."""
        jobs = [
            self._job("Acme Corp", "AI Engineer", "New York, NY", 80),
            self._job("Acme Corp", "AI Engineer", "Singapore", 75),
        ]
        result = consolidate_by_location(jobs)

        assert len(result) == 1
        assert result[0]["location"] == "Singapore"

    def test_keeps_emea_over_us(self):
        """Dubai (emea) beats San Francisco (us) for same company+role."""
        jobs = [
            self._job("Acme Corp", "AI Engineer", "San Francisco, CA", 90),
            self._job("Acme Corp", "AI Engineer", "Dubai, UAE", 85),
        ]
        result = consolidate_by_location(jobs)

        assert len(result) == 1
        assert result[0]["location"] == "Dubai, UAE"

    def test_keeps_apac_over_emea(self):
        """asia_pacific priority (6) beats emea priority (5)."""
        jobs = [
            self._job("Acme Corp", "Staff Engineer", "Dubai, UAE", 90),
            self._job("Acme Corp", "Staff Engineer", "Singapore", 85),
        ]
        result = consolidate_by_location(jobs)

        assert len(result) == 1
        assert result[0]["location"] == "Singapore"

    def test_different_titles_kept(self):
        """Same company, different titles must both be retained."""
        jobs = [
            self._job("Acme Corp", "AI Engineer", "New York, NY", 80),
            self._job("Acme Corp", "Data Scientist", "Singapore", 75),
        ]
        result = consolidate_by_location(jobs)

        assert len(result) == 2
        titles = {j["title"] for j in result}
        assert "AI Engineer" in titles
        assert "Data Scientist" in titles

    def test_tiebreak_by_score_same_region(self):
        """When both jobs share the same region, higher score wins."""
        jobs = [
            self._job("Acme Corp", "AI Engineer", "Singapore", 80),
            self._job("Acme Corp", "AI Engineer", "Tokyo, Japan", 90),
        ]
        result = consolidate_by_location(jobs)

        assert len(result) == 1
        assert result[0]["score"] == 90

    def test_tiebreak_by_score_both_us(self):
        """Two US jobs for same company+title: higher score retained."""
        jobs = [
            self._job("Acme Corp", "Backend Engineer", "Seattle, WA", 70),
            self._job("Acme Corp", "Backend Engineer", "Austin, TX", 85),
        ]
        result = consolidate_by_location(jobs)

        assert len(result) == 1
        assert result[0]["score"] == 85

    def test_single_job_passthrough(self):
        """A single-element input should be returned unchanged."""
        jobs = [self._job("Solo Inc", "Dev", "Remote", 50)]
        result = consolidate_by_location(jobs)

        assert len(result) == 1
        assert result[0]["company"] == "Solo Inc"

    def test_empty_list(self):
        """Empty input must return empty list without raising."""
        assert consolidate_by_location([]) == []

    def test_different_companies_kept(self):
        """Different companies with the same title must both be retained."""
        jobs = [
            self._job("Alpha", "AI Engineer", "New York, NY", 80),
            self._job("Beta", "AI Engineer", "Singapore", 75),
        ]
        result = consolidate_by_location(jobs)

        assert len(result) == 2
        companies = {j["company"] for j in result}
        assert "Alpha" in companies
        assert "Beta" in companies

    def test_three_duplicates_keeps_best_region(self):
        """Three versions of same role: highest-priority region wins."""
        jobs = [
            self._job("Corp X", "Engineering Manager", "Karachi, Pakistan", 95),
            self._job("Corp X", "Engineering Manager", "San Francisco, CA", 80),
            self._job("Corp X", "Engineering Manager", "Singapore", 70),
        ]
        result = consolidate_by_location(jobs)

        assert len(result) == 1
        # asia_pacific (6) > us (2) > pakistan (1)
        assert result[0]["location"] == "Singapore"

    def test_unknown_region_loses_to_any_known(self):
        """An 'unknown' region (priority 0) loses to any known region."""
        jobs = [
            self._job("Corp Y", "SRE", "Mars Colony", 100),
            self._job("Corp Y", "SRE", "Dubai, UAE", 60),
        ]
        result = consolidate_by_location(jobs)

        assert len(result) == 1
        assert result[0]["location"] == "Dubai, UAE"

    def test_normalization_handles_punctuation_in_company(self):
        """Company names that normalize to the same string are treated as the same group."""
        # "McKinsey & Co." → "mckinseyco" (& and . removed)
        # "McKinsey Co."   → "mckinseyco" (same after normalization)
        jobs = [
            self._job("McKinsey & Co.", "Consultant", "New York, NY", 80),
            self._job("McKinsey Co.", "Consultant", "Singapore", 70),
        ]
        result = consolidate_by_location(jobs)

        # Both normalize to "mckinseyco|consultant" — consolidation fires
        assert len(result) == 1
        assert result[0]["location"] == "Singapore"

    def test_preserves_all_job_fields(self):
        """The winning job dict must be returned intact with all original fields."""
        jobs = [
            {
                "company": "Acme",
                "title": "Engineer",
                "location": "Singapore",
                "score": 80,
                "source": "linkedin",
                "url": "https://example.com",
            },
            {
                "company": "Acme",
                "title": "Engineer",
                "location": "New York, NY",
                "score": 75,
                "source": "indeed",
                "url": "https://other.com",
            },
        ]
        result = consolidate_by_location(jobs)

        assert len(result) == 1
        winner = result[0]
        assert winner["source"] == "linkedin"
        assert winner["url"] == "https://example.com"
