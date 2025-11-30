"""
Per-Role QA Checks (Phase 3).

Provides hallucination detection and ATS keyword coverage verification
for generated CV bullets.

The QA system uses rule-based verification (not LLM) for reliability:
- Metric verification: Extract and compare numbers/percentages
- Keyword coverage: Case-insensitive matching against JD keywords
- Source grounding: Verify key phrases exist in source

Usage:
    qa = RoleQA()
    qa_result = qa.check_hallucination(role_bullets, source_role)
    ats_result = qa.check_ats_keywords(role_bullets, target_keywords)
"""

import re
from typing import List, Set, Tuple, Optional
from difflib import SequenceMatcher

from src.common.logger import get_logger
from src.layer6_v2.cv_loader import RoleData
from src.layer6_v2.types import (
    GeneratedBullet,
    RoleBullets,
    QAResult,
    ATSResult,
)


class RoleQA:
    """
    Per-role hallucination and ATS quality checks.

    Uses rule-based verification for reliable fact-checking:
    - Metric extraction with regex patterns
    - Fuzzy string matching for source verification
    - Case-insensitive keyword coverage analysis
    """

    # Regex patterns for extracting metrics
    METRIC_PATTERNS = [
        r'\b(\d+(?:\.\d+)?)\s*%',           # Percentages: 75%, 99.9%
        r'\b(\d+(?:\.\d+)?)\s*[xX]',         # Multipliers: 2x, 10X
        r'\b(\d+(?:,\d{3})*)\s*(?:users?|requests?|customers?|engineers?|events?)',  # Counts
        r'\$\s*(\d+(?:\.\d+)?)\s*[MBKmk]?',  # Dollar amounts: $1M, $500K
        r'\b(\d+(?:,\d{3})*)\s*(?:hours?|days?|weeks?|months?)',  # Time savings
        r'\b(\d+)\s*(?:teams?|people|engineers?|members?)',  # Team sizes
        r'\b(\d+(?:\.\d+)?)\s*ms',           # Latency: 50ms
        r'\b(\d+(?:\.\d+)?)\s*(?:GB|TB|MB)',  # Data volumes
    ]

    # Words that indicate ownership/leadership (should be verifiable)
    LEADERSHIP_CLAIMS = [
        "led", "managed", "directed", "headed", "founded",
        "built", "established", "created", "launched", "pioneered",
        "spearheaded", "championed", "orchestrated", "transformed",
    ]

    def __init__(
        self,
        similarity_threshold: float = 0.5,
        metric_tolerance: float = 0.15,
        max_flagged_ratio: float = 0.4,
    ):
        """
        Initialize QA checker.

        Args:
            similarity_threshold: Minimum similarity ratio for fuzzy matching (0-1)
                Default 0.5 is lenient to allow rephrasing
            metric_tolerance: Tolerance for numeric comparisons (0.15 = 15% variance allowed)
                Allows "75%" to match "~70%" or "nearly 80%"
            max_flagged_ratio: Max ratio of bullets that can be flagged and still pass
                Default 0.4 = 40% can be flagged (lenient for small bullet counts)
        """
        self.similarity_threshold = similarity_threshold
        self.metric_tolerance = metric_tolerance
        self.max_flagged_ratio = max_flagged_ratio
        self._logger = get_logger(__name__)

    def _extract_metrics(self, text: str) -> Set[str]:
        """
        Extract all metrics/numbers from text.

        Returns set of metric strings found (e.g., {"75%", "10M", "50ms"}).
        """
        metrics = set()
        text_lower = text.lower()

        for pattern in self.METRIC_PATTERNS:
            matches = re.findall(pattern, text_lower)
            for match in matches:
                # Normalize the metric
                metric = match.replace(",", "")
                metrics.add(metric)

        # Also extract standalone large numbers
        standalone = re.findall(r'\b(\d{2,}(?:,\d{3})*)\b', text)
        for num in standalone:
            metrics.add(num.replace(",", ""))

        return metrics

    def _find_metric_context(self, text: str, metric: str) -> Optional[str]:
        """Find the context around a metric in text."""
        # Find the metric in the text
        pattern = re.escape(metric)
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            start = max(0, match.start() - 50)
            end = min(len(text), match.end() + 50)
            return text[start:end]
        return None

    def _similarity(self, a: str, b: str) -> float:
        """Calculate similarity ratio between two strings."""
        return SequenceMatcher(None, a.lower(), b.lower()).ratio()

    def _metrics_match(self, metric1: str, metric2: str) -> bool:
        """
        Check if two metrics match within tolerance.

        Handles:
        - Exact match: "75" == "75"
        - Numeric tolerance: "75" ~= "70" (within 15%)
        - String similarity: "10M" ~= "10m"
        """
        # Try exact match first
        if metric1 == metric2:
            return True

        # Try numeric comparison with tolerance
        try:
            num1 = float(re.sub(r'[^\d.]', '', metric1))
            num2 = float(re.sub(r'[^\d.]', '', metric2))
            if num1 > 0 and num2 > 0:
                diff = abs(num1 - num2) / max(num1, num2)
                if diff <= self.metric_tolerance:
                    return True
        except (ValueError, ZeroDivisionError):
            pass

        # Fall back to string similarity
        return self._similarity(metric1, metric2) > 0.8

    def _is_grounded_in_source(self, bullet_text: str, source_text: str) -> Tuple[bool, Optional[str]]:
        """
        Check if a bullet's claims are grounded in source.

        Returns:
            Tuple of (is_grounded, issue_description if not grounded)
        """
        # Extract metrics from both
        bullet_metrics = self._extract_metrics(bullet_text)
        source_metrics = self._extract_metrics(source_text)

        # Check each metric in bullet exists in source (with tolerance)
        for metric in bullet_metrics:
            found = any(self._metrics_match(metric, src) for src in source_metrics)
            if not found:
                return False, f"Metric '{metric}' not found in source"

        # Check leadership claims are supported
        bullet_lower = bullet_text.lower()
        for claim in self.LEADERSHIP_CLAIMS:
            if claim in bullet_lower:
                # This claim should have some basis in source
                source_lower = source_text.lower()
                if claim not in source_lower:
                    # Check for synonyms in source
                    has_support = any(
                        alt in source_lower
                        for alt in self.LEADERSHIP_CLAIMS
                    )
                    if not has_support:
                        return False, f"Leadership claim '{claim}' not supported in source"

        return True, None

    def check_hallucination(
        self,
        role_bullets: RoleBullets,
        source_role: RoleData,
    ) -> QAResult:
        """
        Verify all facts in generated bullets appear in source.

        Checks:
        - Metric accuracy (exact or fuzzy match)
        - Achievement presence (key claims supported)
        - Leadership claims have basis

        Args:
            role_bullets: Generated bullets to verify
            source_role: Original role data with achievements

        Returns:
            QAResult with pass/fail status and details
        """
        self._logger.info(f"Running hallucination check for {source_role.company}")

        flagged_bullets = []
        issues = []
        verified_metrics = []

        # Build source corpus from all achievements
        source_corpus = " ".join(source_role.achievements)
        source_metrics = self._extract_metrics(source_corpus)

        for bullet in role_bullets.bullets:
            # Check 1: Verify against declared source_text
            if bullet.source_text:
                is_grounded, issue = self._is_grounded_in_source(
                    bullet.text, bullet.source_text
                )
                if not is_grounded:
                    flagged_bullets.append(bullet.text[:100])
                    issues.append(f"[{source_role.company}] {issue}")
                    continue

            # Check 2: Verify declared metric exists in source
            if bullet.source_metric:
                metric_normalized = bullet.source_metric.replace(",", "").lower()
                found = any(self._metrics_match(metric_normalized, m) for m in source_metrics)
                if not found:
                    flagged_bullets.append(bullet.text[:100])
                    issues.append(
                        f"[{source_role.company}] Declared metric '{bullet.source_metric}' "
                        f"not found in source achievements"
                    )
                    continue
                verified_metrics.append(bullet.source_metric)

            # Check 3: Verify against full source corpus
            bullet_metrics = self._extract_metrics(bullet.text)
            for metric in bullet_metrics:
                found = any(self._metrics_match(metric, m) for m in source_metrics)
                if not found:
                    flagged_bullets.append(bullet.text[:100])
                    issues.append(
                        f"[{source_role.company}] Metric '{metric}' in bullet "
                        f"not found in source achievements"
                    )
                    break
                else:
                    verified_metrics.append(metric)

        # Calculate confidence based on issues found
        total_bullets = len(role_bullets.bullets)
        clean_bullets = total_bullets - len(flagged_bullets)
        confidence = clean_bullets / total_bullets if total_bullets > 0 else 1.0

        # Determine pass/fail using configurable threshold
        # Always allow at least 1 flagged bullet (for roles with few bullets)
        max_allowed = max(1, int(total_bullets * self.max_flagged_ratio))
        passed = len(flagged_bullets) <= max_allowed

        result = QAResult(
            passed=passed,
            flagged_bullets=flagged_bullets,
            issues=issues,
            verified_metrics=list(set(verified_metrics)),
            confidence=confidence,
        )

        self._logger.info(f"QA Result: {'PASS' if passed else 'FAIL'}")
        self._logger.info(f"  Flagged: {len(flagged_bullets)}/{total_bullets}")
        self._logger.info(f"  Confidence: {confidence:.2f}")

        return result

    def check_ats_keywords(
        self,
        role_bullets: RoleBullets,
        target_keywords: List[str],
    ) -> ATSResult:
        """
        Check keyword coverage in generated bullets.

        Uses case-insensitive matching to find JD keywords in bullets.

        Args:
            role_bullets: Generated bullets to check
            target_keywords: JD keywords to look for

        Returns:
            ATSResult with coverage metrics
        """
        # Combine all bullet text
        combined_text = " ".join(b.text.lower() for b in role_bullets.bullets)

        keywords_found = []
        keywords_missing = []

        for keyword in target_keywords:
            kw_lower = keyword.lower()
            # Check for exact match or as part of compound word
            if kw_lower in combined_text or kw_lower.replace(" ", "") in combined_text:
                keywords_found.append(keyword)
            else:
                keywords_missing.append(keyword)

        # Calculate coverage
        coverage_ratio = len(keywords_found) / len(target_keywords) if target_keywords else 0.0

        # Generate suggestions for missing keywords
        suggestions = []
        if keywords_missing[:3]:  # Top 3 missing keywords
            suggestions = [
                f"Consider integrating '{kw}' where it fits naturally"
                for kw in keywords_missing[:3]
            ]

        result = ATSResult(
            keywords_found=keywords_found,
            keywords_missing=keywords_missing,
            coverage_ratio=coverage_ratio,
            suggestions=suggestions,
        )

        self._logger.info(f"ATS Keyword Coverage: {coverage_ratio:.1%}")
        self._logger.info(f"  Found: {len(keywords_found)}/{len(target_keywords)}")

        return result


def run_qa_on_all_roles(
    role_bullets_list: List[RoleBullets],
    source_roles: List[RoleData],
    target_keywords: List[str],
) -> Tuple[List[QAResult], List[ATSResult]]:
    """
    Run QA checks on all generated role bullets.

    Args:
        role_bullets_list: List of generated RoleBullets
        source_roles: List of source RoleData (same order)
        target_keywords: JD keywords to check

    Returns:
        Tuple of (qa_results, ats_results) lists
    """
    qa = RoleQA()
    qa_results = []
    ats_results = []

    for role_bullets, source_role in zip(role_bullets_list, source_roles):
        # Run hallucination check
        qa_result = qa.check_hallucination(role_bullets, source_role)
        qa_results.append(qa_result)

        # Update RoleBullets with QA result
        role_bullets.qa_result = qa_result

        # Run ATS check
        ats_result = qa.check_ats_keywords(role_bullets, target_keywords)
        ats_results.append(ats_result)

        # Update RoleBullets with ATS result
        role_bullets.ats_result = ats_result

    # Summary
    logger = get_logger(__name__)
    passed = sum(1 for r in qa_results if r.passed)
    total = len(qa_results)
    logger.info(f"\nQA Summary: {passed}/{total} roles passed hallucination check")

    avg_coverage = sum(r.coverage_ratio for r in ats_results) / len(ats_results) if ats_results else 0
    logger.info(f"ATS Summary: {avg_coverage:.1%} average keyword coverage")

    return qa_results, ats_results
