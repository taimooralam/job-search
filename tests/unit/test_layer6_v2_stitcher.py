"""
Unit Tests for Layer 6 V2 Phase 4: Stitcher

Tests:
- Types: StitchedRole, StitchedCV, DeduplicationResult
- Similarity detection for deduplication
- Word budget enforcement
- Cross-role deduplication
- Markdown output generation
"""

import pytest

from src.layer6_v2.types import (
    GeneratedBullet,
    RoleBullets,
    DuplicatePair,
    DeduplicationResult,
    StitchedRole,
    StitchedCV,
)
from src.layer6_v2.stitcher import CVStitcher, stitch_all_roles


# ===== FIXTURES =====

@pytest.fixture
def sample_role_bullets_1():
    """Current role bullets (role 0)."""
    return RoleBullets(
        role_id="01_current_company",
        company="Current Company",
        title="Technical Lead",
        period="2020–Present",
        bullets=[
            GeneratedBullet(
                text="Led team of 10 engineers to deliver critical platform migration ahead of schedule",
                source_text="Led team of 10 engineers",
            ),
            GeneratedBullet(
                text="Reduced production incident rate by 75% through architectural improvements",
                source_text="Reduced incident rate by 75%",
            ),
            GeneratedBullet(
                text="Implemented observability pipeline processing 1B events daily",
                source_text="Implemented observability pipeline",
            ),
        ],
        keywords_integrated=["team", "incident", "observability"],
    )


@pytest.fixture
def sample_role_bullets_2():
    """Previous role bullets (role 1)."""
    return RoleBullets(
        role_id="02_previous_company",
        company="Previous Company",
        title="Senior Engineer",
        period="2018–2020",
        bullets=[
            GeneratedBullet(
                text="Built REST API serving 10M requests per day with 99.9% uptime",
                source_text="Built REST API serving 10M requests",
            ),
            GeneratedBullet(
                text="Led team of 5 engineers to improve test coverage from 40% to 85%",
                source_text="Improved test coverage",
            ),
        ],
        keywords_integrated=["API", "team"],
    )


@pytest.fixture
def sample_role_bullets_3():
    """Early career role bullets (role 2)."""
    return RoleBullets(
        role_id="03_early_company",
        company="Early Company",
        title="Software Engineer",
        period="2016–2018",
        bullets=[
            GeneratedBullet(
                text="Developed Python backend services handling 100K daily transactions",
                source_text="Developed Python backend",
            ),
            GeneratedBullet(
                text="Reduced deployment time by 80% through CI/CD automation",
                source_text="Reduced deployment time by 80%",
            ),
        ],
        keywords_integrated=["Python", "CI/CD"],
    )


@pytest.fixture
def duplicate_role_bullets():
    """Role with bullets that duplicate other roles."""
    return RoleBullets(
        role_id="04_dup_company",
        company="Duplicate Company",
        title="Engineer",
        period="2014–2016",
        bullets=[
            GeneratedBullet(
                # Very similar to role 0 bullet
                text="Led team of 8 engineers to deliver platform migration successfully",
                source_text="Led team",
            ),
            GeneratedBullet(
                # Similar metric to role 1
                text="Built API handling 10M requests daily with high availability",
                source_text="Built API",
            ),
        ],
    )


# ===== TESTS: StitchedRole =====

class TestStitchedRole:
    """Test StitchedRole dataclass."""

    def test_creates_with_bullets(self):
        """Creates StitchedRole with bullet list."""
        role = StitchedRole(
            role_id="test",
            company="Test Co",
            title="Lead",
            location="Munich",
            period="2020-2024",
            bullets=["Bullet 1", "Bullet 2"],
        )
        assert role.bullet_count == 2
        assert role.company == "Test Co"

    def test_calculates_word_count(self):
        """Calculates word count from bullets."""
        role = StitchedRole(
            role_id="test",
            company="Test Co",
            title="Lead",
            location="Munich",
            period="2020-2024",
            bullets=[
                "One two three four five",  # 5 words
                "Six seven eight nine ten",  # 5 words
            ],
        )
        assert role.word_count == 10

    def test_to_markdown(self):
        """Converts to markdown format."""
        role = StitchedRole(
            role_id="test",
            company="Test Company",
            title="Technical Lead",
            location="Munich, DE",
            period="2020–Present",
            bullets=["Led team of engineers", "Built platform"],
        )
        md = role.to_markdown()

        # GAP-006: Now outputs plain text, not markdown
        assert "Test Company" in md
        assert "Technical Lead" in md
        assert "Munich, DE" in md
        assert "2020–Present" in md
        assert "• Led team of engineers" in md
        assert "• Built platform" in md
        # Verify no markdown markers
        assert "###" not in md
        assert "**" not in md


# ===== TESTS: StitchedCV =====

class TestStitchedCV:
    """Test StitchedCV dataclass."""

    def test_calculates_totals(self):
        """Calculates total word and bullet counts."""
        role1 = StitchedRole(
            role_id="1", company="A", title="Lead", location="", period="2020",
            bullets=["One two three", "Four five six"],
        )
        role2 = StitchedRole(
            role_id="2", company="B", title="Eng", location="", period="2019",
            bullets=["Seven eight"],
        )

        cv = StitchedCV(roles=[role1, role2])

        assert cv.total_bullet_count == 3
        assert cv.total_word_count == 8

    def test_to_markdown(self):
        """Converts full CV to plain text (GAP-006: no markdown)."""
        role1 = StitchedRole(
            role_id="1", company="Company A", title="Lead", location="Munich",
            period="2020", bullets=["Achievement 1"],
        )
        role2 = StitchedRole(
            role_id="2", company="Company B", title="Eng", location="Berlin",
            period="2019", bullets=["Achievement 2"],
        )

        cv = StitchedCV(roles=[role1, role2])
        md = cv.to_markdown()

        # GAP-006: Now outputs plain text, not markdown
        assert "Company A" in md
        assert "Company B" in md
        assert "Achievement 1" in md
        assert "Achievement 2" in md
        # Verify no markdown markers
        assert "###" not in md
        assert "**" not in md


# ===== TESTS: DeduplicationResult =====

class TestDeduplicationResult:
    """Test DeduplicationResult dataclass."""

    def test_calculates_dedup_ratio(self):
        """Calculates deduplication ratio."""
        result = DeduplicationResult(
            original_bullet_count=10,
            final_bullet_count=8,
            removed_count=2,
            duplicate_pairs=[],
            compression_applied=False,
        )
        assert result.dedup_ratio == 0.2

    def test_handles_zero_original(self):
        """Handles zero original bullets."""
        result = DeduplicationResult(
            original_bullet_count=0,
            final_bullet_count=0,
            removed_count=0,
            duplicate_pairs=[],
            compression_applied=False,
        )
        assert result.dedup_ratio == 0.0


# ===== TESTS: Similarity Detection =====

class TestSimilarityDetection:
    """Test similarity calculation."""

    def test_identical_bullets_high_similarity(self):
        """Identical bullets have high similarity."""
        stitcher = CVStitcher()
        score, _ = stitcher._calculate_similarity(
            "Led team of 10 engineers to deliver platform",
            "Led team of 10 engineers to deliver platform",
        )
        assert score > 0.9

    def test_different_bullets_low_similarity(self):
        """Very different bullets have low similarity."""
        stitcher = CVStitcher()
        score, _ = stitcher._calculate_similarity(
            "Led team of 10 engineers to deliver platform",
            "Implemented CI/CD pipeline with automated testing",
        )
        assert score < 0.5

    def test_similar_metrics_boost_similarity(self):
        """Similar metrics increase similarity score."""
        stitcher = CVStitcher()
        score1, _ = stitcher._calculate_similarity(
            "Reduced latency by 75%",
            "Improved performance by 75%",
        )
        score2, _ = stitcher._calculate_similarity(
            "Reduced latency by 75%",
            "Improved performance by 50%",
        )
        assert score1 > score2

    def test_similarity_reason_metrics(self):
        """Returns metric-based reason when metrics match."""
        stitcher = CVStitcher()
        _, reason = stitcher._calculate_similarity(
            "Achieved 99.9% uptime",
            "Maintained 99.9% availability",
        )
        assert "metric" in reason.lower() or "99.9" in reason


# ===== TESTS: Deduplication =====

class TestDeduplication:
    """Test cross-role deduplication."""

    def test_finds_duplicate_bullets(
        self, sample_role_bullets_1, duplicate_role_bullets
    ):
        """Detects duplicate bullets across roles."""
        stitcher = CVStitcher(similarity_threshold=0.6)
        duplicates = stitcher._find_duplicates([
            sample_role_bullets_1,
            duplicate_role_bullets,
        ])

        # Should find at least one duplicate (the "Led team" variants)
        assert len(duplicates) >= 1

    def test_keeps_more_recent_version(
        self, sample_role_bullets_1, duplicate_role_bullets
    ):
        """Keeps bullet from more recent role (lower index)."""
        stitcher = CVStitcher(similarity_threshold=0.6)
        duplicates = stitcher._find_duplicates([
            sample_role_bullets_1,  # Role 0 - keep this version
            duplicate_role_bullets,  # Role 1 - remove duplicates
        ])

        # All duplicates should have bullet1_role_index > bullet2_role_index
        # (bullet1 is removed, bullet2 is kept)
        for dup in duplicates:
            assert dup.bullet1_role_index > dup.bullet2_role_index

    def test_no_duplicates_within_same_role(self, sample_role_bullets_1):
        """Does not find duplicates within same role."""
        stitcher = CVStitcher()
        duplicates = stitcher._find_duplicates([sample_role_bullets_1])

        # Same role should not have cross-role duplicates
        assert len(duplicates) == 0


# ===== TESTS: Word Budget =====

class TestWordBudget:
    """Test word budget enforcement."""

    def test_no_trimming_under_budget(
        self, sample_role_bullets_1, sample_role_bullets_2
    ):
        """No trimming when under word budget."""
        stitcher = CVStitcher(word_budget=1000)  # High budget
        bullet_lists = [
            [b.text for b in sample_role_bullets_1.bullets],
            [b.text for b in sample_role_bullets_2.bullets],
        ]

        result, applied = stitcher._enforce_word_budget(
            bullet_lists,
            [sample_role_bullets_1, sample_role_bullets_2],
        )

        assert applied is False
        assert result == bullet_lists

    def test_trims_early_roles_first(
        self, sample_role_bullets_1, sample_role_bullets_2, sample_role_bullets_3
    ):
        """Trims early career roles before recent roles."""
        stitcher = CVStitcher(word_budget=50, min_bullets_per_role=1)
        bullet_lists = [
            [b.text for b in sample_role_bullets_1.bullets],
            [b.text for b in sample_role_bullets_2.bullets],
            [b.text for b in sample_role_bullets_3.bullets],
        ]

        result, applied = stitcher._enforce_word_budget(
            bullet_lists,
            [sample_role_bullets_1, sample_role_bullets_2, sample_role_bullets_3],
        )

        assert applied is True
        # Role 0 should be preserved
        assert len(result[0]) == len(bullet_lists[0])
        # Later roles should be trimmed
        assert len(result[2]) <= len(bullet_lists[2])

    def test_preserves_current_role(
        self, sample_role_bullets_1, sample_role_bullets_2
    ):
        """Never trims current role (role 0)."""
        stitcher = CVStitcher(word_budget=20, min_bullets_per_role=0)
        bullet_lists = [
            [b.text for b in sample_role_bullets_1.bullets],
            [b.text for b in sample_role_bullets_2.bullets],
        ]

        result, _ = stitcher._enforce_word_budget(
            bullet_lists,
            [sample_role_bullets_1, sample_role_bullets_2],
        )

        # Role 0 should be untouched
        assert len(result[0]) == len(bullet_lists[0])


# ===== TESTS: Full Stitching =====

class TestFullStitching:
    """Test full stitching pipeline."""

    def test_stitch_multiple_roles(
        self, sample_role_bullets_1, sample_role_bullets_2, sample_role_bullets_3
    ):
        """Stitches multiple roles together."""
        stitcher = CVStitcher(word_budget=1000)
        result = stitcher.stitch([
            sample_role_bullets_1,
            sample_role_bullets_2,
            sample_role_bullets_3,
        ])

        assert len(result.roles) == 3
        assert result.total_bullet_count > 0
        assert result.deduplication_result is not None

    def test_stitch_with_keyword_tracking(self, sample_role_bullets_1):
        """Tracks keyword coverage in stitched output."""
        stitcher = CVStitcher()
        result = stitcher.stitch(
            [sample_role_bullets_1],
            target_keywords=["team", "incident", "blockchain"],
        )

        assert "team" in result.keywords_coverage
        assert "incident" in result.keywords_coverage
        assert "blockchain" not in result.keywords_coverage

    def test_stitch_removes_duplicates(
        self, sample_role_bullets_1, duplicate_role_bullets
    ):
        """Removes duplicate bullets during stitching."""
        stitcher = CVStitcher(similarity_threshold=0.6)
        result = stitcher.stitch([
            sample_role_bullets_1,
            duplicate_role_bullets,
        ])

        # Total bullets should be less than sum of individual roles
        original_total = (
            sample_role_bullets_1.bullet_count +
            duplicate_role_bullets.bullet_count
        )
        assert result.total_bullet_count < original_total

    def test_convenience_function(
        self, sample_role_bullets_1, sample_role_bullets_2
    ):
        """stitch_all_roles convenience function works."""
        result = stitch_all_roles(
            [sample_role_bullets_1, sample_role_bullets_2],
            word_budget=1000,
            target_keywords=["team"],
        )

        assert len(result.roles) == 2
        assert result.deduplication_result is not None


# ===== TESTS: Markdown Output =====

class TestMarkdownOutput:
    """Test markdown output generation (GAP-006: now plain text)."""

    def test_generates_valid_markdown(
        self, sample_role_bullets_1, sample_role_bullets_2
    ):
        """Generates valid plain text from stitched CV (GAP-006: no markdown)."""
        result = stitch_all_roles([
            sample_role_bullets_1,
            sample_role_bullets_2,
        ])

        md = result.to_markdown()

        # GAP-006: Check structure without markdown markers
        assert "Current Company" in md
        assert "Previous Company" in md
        assert "•" in md  # Bullet points
        # Verify no markdown markers
        assert "###" not in md
        assert "**" not in md

    def test_roles_in_correct_order(
        self, sample_role_bullets_1, sample_role_bullets_2, sample_role_bullets_3
    ):
        """Roles appear in chronological order (most recent first)."""
        result = stitch_all_roles([
            sample_role_bullets_1,
            sample_role_bullets_2,
            sample_role_bullets_3,
        ])

        md = result.to_markdown()

        # Check order by finding positions
        pos_current = md.find("Current Company")
        pos_previous = md.find("Previous Company")
        pos_early = md.find("Early Company")

        assert pos_current < pos_previous < pos_early


# ===== TESTS: Edge Cases =====

class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_role_list(self):
        """Handles empty role list."""
        stitcher = CVStitcher()
        result = stitcher.stitch([])

        assert len(result.roles) == 0
        assert result.total_bullet_count == 0

    def test_single_role(self, sample_role_bullets_1):
        """Handles single role without errors."""
        stitcher = CVStitcher()
        result = stitcher.stitch([sample_role_bullets_1])

        assert len(result.roles) == 1
        assert result.deduplication_result.removed_count == 0

    def test_role_with_empty_bullets(self):
        """Handles role with no bullets."""
        empty_role = RoleBullets(
            role_id="empty",
            company="Empty Co",
            title="None",
            period="2020",
            bullets=[],
        )

        stitcher = CVStitcher()
        result = stitcher.stitch([empty_role])

        assert len(result.roles) == 1
        assert result.total_bullet_count == 0
