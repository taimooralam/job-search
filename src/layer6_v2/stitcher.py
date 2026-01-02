"""
CV Stitcher (Phase 4).

Combines per-role bullet sections with cross-role deduplication.

Deduplication Strategy:
- Compare all bullet pairs across different roles
- Use keyword overlap + string similarity for detection
- Keep the version from the more recent role (career progression)
- Track what was removed for transparency

Note: Word budget enforcement has been REMOVED. All roles are included
with full STAR bullets. PDF handles pagination naturally, and users
can edit in the CV editor if needed.

Usage:
    stitcher = CVStitcher()
    stitched_cv = stitcher.stitch(role_bullets_list)
"""

import json
import re
from datetime import datetime
from typing import List, Set, Tuple, Optional, Dict, Callable, TYPE_CHECKING
from difflib import SequenceMatcher
from collections import defaultdict

from src.common.logger import get_logger

if TYPE_CHECKING:
    from src.common.structured_logger import StructuredLogger
from src.layer6_v2.types import (
    RoleBullets,
    StitchedRole,
    StitchedCV,
    DuplicatePair,
    DeduplicationResult,
)


class CVStitcher:
    """
    Combines per-role sections with deduplication.

    Features:
    - Semantic similarity detection for cross-role deduplication
    - Keyword coverage tracking

    Note: Word budget enforcement removed - all roles included with full content.
    """

    # Common achievement keywords that indicate similar bullets
    ACHIEVEMENT_KEYWORDS = {
        "led", "managed", "built", "designed", "implemented", "developed",
        "reduced", "improved", "increased", "optimized", "automated",
        "architected", "scaled", "launched", "delivered", "created",
        "team", "engineers", "platform", "system", "pipeline", "service",
        "performance", "latency", "uptime", "incident", "deployment",
    }

    def __init__(
        self,
        word_budget: Optional[int] = None,  # None = no limit (include all content)
        similarity_threshold: float = 0.75,
        min_bullets_per_role: int = 2,
        skill_whitelist: Optional[dict] = None,  # GAP-001: Whitelist to prevent hallucinated skills
        job_id: Optional[str] = None,
        struct_logger: Optional["StructuredLogger"] = None,
        log_callback: Optional[Callable[[str], None]] = None,
    ):
        """
        Initialize the stitcher.

        Args:
            word_budget: Target word count (None = no limit, include all roles fully)
            similarity_threshold: Threshold for considering bullets as duplicates (0-1)
            min_bullets_per_role: Minimum bullets to keep per role (prevents empty roles)
            skill_whitelist: Dict with 'hard_skills' and 'soft_skills' lists (from CVLoader)
            job_id: Optional job ID for logging correlation
            struct_logger: Optional structured logger for Redis live-tail
            log_callback: Optional callback for in-process log forwarding
        """
        self.word_budget = word_budget  # None = unlimited
        self.similarity_threshold = similarity_threshold
        self.min_bullets_per_role = min_bullets_per_role
        self._logger = get_logger(__name__)
        self._job_id = job_id
        self._struct_logger = struct_logger
        self._log_callback = log_callback

        # GAP-001: Store skill whitelist for validation
        self._skill_whitelist = skill_whitelist
        # Build combined set for efficient case-insensitive lookup
        self._whitelist_set: Optional[Set[str]] = None
        if skill_whitelist:
            hard_skills = skill_whitelist.get("hard_skills", [])
            soft_skills = skill_whitelist.get("soft_skills", [])
            self._whitelist_set = {s.lower() for s in hard_skills + soft_skills}
            self._logger.debug(
                f"Skill whitelist loaded: {len(self._whitelist_set)} unique skills"
            )

    # ===== LOGGING HELPERS (Phase 0 Extension) =====

    @staticmethod
    def _preview(text: str, n: int = 50) -> str:
        """Generate a preview of text: first n chars + '...' + last n chars."""
        if not text:
            return ""
        if len(text) <= n * 2 + 3:
            return text
        return f"{text[:n]}...{text[-n:]}"

    def _emit_struct_log(self, event: str, metadata: dict) -> None:
        """
        Emit structured log for Redis live-tail and in-process callbacks.

        Uses dual-emit pattern:
        1. log_callback for in-process forwarding (CVGenerationService)
        2. struct_logger stdout for subprocess mode (pipeline runner)
        """
        # Emit via log_callback (works in-process for CVGenerationService)
        if self._log_callback:
            try:
                data = {
                    "timestamp": datetime.utcnow().isoformat(),
                    "layer": 6,
                    "layer_name": "stitcher",
                    "event": f"cv_stitch_{event}",
                    "message": metadata.get("message", event),
                    "job_id": self._job_id,
                    "metadata": metadata,
                }
                self._log_callback(json.dumps(data))
            except Exception:
                pass  # Fire-and-forget logging

        # Also emit via struct_logger stdout (works in subprocess mode)
        if self._struct_logger:
            try:
                self._struct_logger.emit(
                    event=f"cv_stitch_{event}",
                    layer=6,
                    metadata=metadata,
                )
            except Exception:
                pass

    def _extract_keywords(self, text: str) -> Set[str]:
        """Extract meaningful keywords from bullet text."""
        words = set(re.findall(r'\b\w+\b', text.lower()))
        return words & self.ACHIEVEMENT_KEYWORDS

    def _extract_metrics(self, text: str) -> Set[str]:
        """Extract metrics/numbers from text."""
        metrics = set()
        # Percentages
        metrics.update(re.findall(r'\d+(?:\.\d+)?%', text))
        # Numbers with context
        metrics.update(re.findall(r'\b\d+(?:,\d{3})*\b', text))
        return metrics

    def _is_skill_in_whitelist(self, skill: str) -> bool:
        """
        GAP-001: Check if skill exists in whitelist (case-insensitive).

        Args:
            skill: Skill name to validate

        Returns:
            True if skill is in whitelist, or True if no whitelist (backward compat)
        """
        if self._whitelist_set is None:
            return True  # No whitelist = no validation (backward compat)
        return skill.lower() in self._whitelist_set

    def _calculate_similarity(self, bullet1: str, bullet2: str) -> Tuple[float, str]:
        """
        Calculate similarity between two bullets.

        Returns:
            Tuple of (similarity_score, reason)
        """
        # String-based similarity
        string_sim = SequenceMatcher(None, bullet1.lower(), bullet2.lower()).ratio()

        # Keyword overlap
        kw1 = self._extract_keywords(bullet1)
        kw2 = self._extract_keywords(bullet2)
        if kw1 and kw2:
            keyword_sim = len(kw1 & kw2) / len(kw1 | kw2)
        else:
            keyword_sim = 0.0

        # Metric overlap (same numbers = likely same achievement)
        metrics1 = self._extract_metrics(bullet1)
        metrics2 = self._extract_metrics(bullet2)
        if metrics1 and metrics2:
            metric_overlap = len(metrics1 & metrics2) / len(metrics1 | metrics2)
        else:
            metric_overlap = 0.0

        # Combined score (weighted)
        combined = 0.5 * string_sim + 0.3 * keyword_sim + 0.2 * metric_overlap

        # Determine reason
        if metric_overlap > 0.5:
            reason = f"Same metrics ({metrics1 & metrics2})"
        elif keyword_sim > 0.6:
            reason = f"Similar keywords ({kw1 & kw2})"
        elif string_sim > 0.7:
            reason = "High text similarity"
        else:
            reason = "General similarity"

        return combined, reason

    def _find_duplicates(
        self,
        role_bullets_list: List[RoleBullets],
    ) -> List[DuplicatePair]:
        """
        Find duplicate bullets across roles.

        Compares bullets from different roles (not within same role).
        Returns pairs where the earlier role's bullet should be removed.
        """
        duplicates = []

        # Compare each role with all subsequent roles
        for i, role1 in enumerate(role_bullets_list):
            for j, role2 in enumerate(role_bullets_list):
                if j <= i:
                    continue  # Only compare later roles

                for b1 in role1.bullets:
                    for b2 in role2.bullets:
                        score, reason = self._calculate_similarity(b1.text, b2.text)

                        if score >= self.similarity_threshold:
                            # Mark the earlier role's bullet (j > i) for removal
                            # Keep the more recent role's version
                            duplicates.append(DuplicatePair(
                                bullet1_text=b2.text,  # Later role (to remove)
                                bullet1_role_index=j,
                                bullet2_text=b1.text,  # Earlier role (to keep)
                                bullet2_role_index=i,
                                similarity_score=score,
                                reason=reason,
                            ))

        return duplicates

    def _remove_duplicates(
        self,
        role_bullets_list: List[RoleBullets],
        duplicates: List[DuplicatePair],
    ) -> List[List[str]]:
        """
        Remove duplicate bullets from role lists.

        Returns list of bullet text lists, one per role.
        """
        # Build set of (role_index, bullet_text) to remove
        to_remove: Set[Tuple[int, str]] = set()
        for dup in duplicates:
            to_remove.add((dup.bullet1_role_index, dup.bullet1_text))

        # Build filtered bullet lists
        result = []
        for i, role_bullets in enumerate(role_bullets_list):
            filtered = [
                b.text for b in role_bullets.bullets
                if (i, b.text) not in to_remove
            ]
            result.append(filtered)

        return result

    def _enforce_word_budget(
        self,
        bullet_lists: List[List[str]],
        role_bullets_list: List[RoleBullets],
    ) -> Tuple[List[List[str]], bool]:
        """
        Enforce word budget by trimming from early-career roles first.

        NOTE: If word_budget is None, no trimming is performed (all content kept).

        Strategy (when budget is set):
        - Never touch role 0 (current role)
        - Trim from the end (earliest roles) first
        - Keep at least min_bullets_per_role per role

        Returns:
            Tuple of (trimmed_bullet_lists, compression_applied)
        """
        # If no word budget set, skip enforcement entirely
        if self.word_budget is None:
            self._logger.info("Word budget disabled - keeping all content")
            return bullet_lists, False

        # Calculate current word count
        total_words = sum(
            sum(len(b.split()) for b in bullets)
            for bullets in bullet_lists
        )

        if total_words <= self.word_budget:
            return bullet_lists, False

        self._logger.info(f"Word budget exceeded: {total_words}/{self.word_budget}")

        # Need to trim
        compression_applied = True
        result = [list(bullets) for bullets in bullet_lists]  # Copy

        # Trim from the end (earliest roles) first
        for i in range(len(result) - 1, 0, -1):  # Skip role 0
            while len(result[i]) > self.min_bullets_per_role:
                # Remove last bullet from this role
                if result[i]:
                    removed = result[i].pop()
                    total_words -= len(removed.split())
                    self._logger.debug(f"Trimmed from role {i}: {removed[:50]}...")

                if total_words <= self.word_budget:
                    break

            if total_words <= self.word_budget:
                break

        # If still over budget, log warning but don't trim current role
        if total_words > self.word_budget:
            self._logger.warning(
                f"Could not meet word budget: {total_words}/{self.word_budget}. "
                "Current role preserved."
            )

        return result, compression_applied

    def _compute_role_skills(
        self,
        hard_skills: List[str],
        soft_skills: List[str],
        target_keywords_lower: set,
        max_skills: int = 8,
    ) -> List[str]:
        """
        Compute combined skills for a role: JD-matching first, then role-specific.

        GAP-001: Now validates skills against whitelist to prevent hallucinations.
        Skills not in the whitelist are filtered out with debug logging.

        Args:
            hard_skills: Technical skills from this role
            soft_skills: Soft skills from this role
            target_keywords_lower: Lowercase JD keywords for matching
            max_skills: Maximum number of skills to include

        Returns:
            List of skills, JD-matching first, then others, capped at max_skills
        """
        all_skills = hard_skills + soft_skills

        # GAP-001: Filter skills against whitelist before processing
        if self._whitelist_set is not None:
            validated_skills = []
            filtered_out = []
            for skill in all_skills:
                if self._is_skill_in_whitelist(skill):
                    validated_skills.append(skill)
                else:
                    filtered_out.append(skill)
            if filtered_out:
                self._logger.debug(
                    f"Filtered out non-whitelist skills: {filtered_out}"
                )
            all_skills = validated_skills

        jd_matching = []
        other_skills = []

        for skill in all_skills:
            if skill.lower() in target_keywords_lower:
                jd_matching.append(skill)
            else:
                other_skills.append(skill)

        # Combine: JD-matching first, then others
        combined = jd_matching + other_skills

        # Deduplicate while preserving order
        seen = set()
        result = []
        for skill in combined:
            skill_lower = skill.lower()
            if skill_lower not in seen:
                seen.add(skill_lower)
                result.append(skill)
                if len(result) >= max_skills:
                    break

        return result

    def _collect_keywords(
        self,
        bullet_lists: List[List[str]],
        target_keywords: Optional[List[str]] = None,
    ) -> List[str]:
        """Collect keywords present in the stitched bullets."""
        if not target_keywords:
            return []

        combined_text = " ".join(
            bullet.lower()
            for bullets in bullet_lists
            for bullet in bullets
        )

        found = []
        for kw in target_keywords:
            if kw.lower() in combined_text:
                found.append(kw)

        return found

    def stitch(
        self,
        role_bullets_list: List[RoleBullets],
        target_keywords: Optional[List[str]] = None,
    ) -> StitchedCV:
        """
        Stitch all roles together with deduplication.

        Args:
            role_bullets_list: List of RoleBullets from per-role generation
            target_keywords: JD keywords to track coverage

        Returns:
            StitchedCV with deduplicated, budget-enforced content
        """
        self._logger.info(f"Stitching {len(role_bullets_list)} roles")

        # Count original bullets
        original_count = sum(rb.bullet_count for rb in role_bullets_list)

        # Phase 0: Emit stitch start
        self._emit_struct_log("subphase_start", {
            "message": f"Starting CV stitching for {len(role_bullets_list)} roles",
            "phase": 4,
            "subphase": "stitch_start",
            "roles_count": len(role_bullets_list),
            "original_bullet_count": original_count,
            "target_keywords_count": len(target_keywords) if target_keywords else 0,
            "roles": [
                {
                    "company": rb.company,
                    "title": rb.title,
                    "bullet_count": rb.bullet_count,
                }
                for rb in role_bullets_list
            ],
        })

        # Step 1: Find duplicates
        duplicates = self._find_duplicates(role_bullets_list)
        self._logger.info(f"Found {len(duplicates)} duplicate pairs")

        # Phase 0: Log duplicate detection results
        if duplicates:
            self._emit_struct_log("decision_point", {
                "message": f"Found {len(duplicates)} duplicate bullet pairs",
                "decision": "duplicate_detection",
                "duplicate_count": len(duplicates),
                "similarity_threshold": self.similarity_threshold,
                "duplicates": [
                    {
                        "bullet1_preview": self._preview(dup.bullet1_text, 40),
                        "bullet1_role": role_bullets_list[dup.bullet1_role_index].company if dup.bullet1_role_index < len(role_bullets_list) else "unknown",
                        "bullet2_preview": self._preview(dup.bullet2_text, 40),
                        "bullet2_role": role_bullets_list[dup.bullet2_role_index].company if dup.bullet2_role_index < len(role_bullets_list) else "unknown",
                        "similarity_score": round(dup.similarity_score, 3),
                        "reason": dup.reason,
                    }
                    for dup in duplicates[:5]  # Limit to first 5 for brevity
                ],
                "showing_first_n": min(5, len(duplicates)),
            })

        # Step 2: Remove duplicates
        bullet_lists = self._remove_duplicates(role_bullets_list, duplicates)
        after_dedup_count = sum(len(b) for b in bullet_lists)

        # Step 3: Enforce word budget
        bullet_lists, compression_applied = self._enforce_word_budget(
            bullet_lists, role_bullets_list
        )
        final_count = sum(len(b) for b in bullet_lists)

        # Phase 0: Log deduplication results
        self._emit_struct_log("decision_point", {
            "message": f"Deduplication complete: {original_count} → {after_dedup_count} → {final_count} bullets",
            "decision": "deduplication_result",
            "original_count": original_count,
            "after_dedup_count": after_dedup_count,
            "final_count": final_count,
            "removed_by_dedup": original_count - after_dedup_count,
            "removed_by_budget": after_dedup_count - final_count,
            "compression_applied": compression_applied,
            "word_budget": self.word_budget,
        })

        # Step 4: Build stitched roles with combined skills
        stitched_roles = []
        target_keywords_lower = {kw.lower() for kw in (target_keywords or [])}
        role_skill_summary = []

        for i, (role_bullets, bullets) in enumerate(zip(role_bullets_list, bullet_lists)):
            # Get location from CVLoader if available, otherwise use empty string
            location = getattr(role_bullets, 'location', '')

            # Compute combined skills: JD-matching first, then role-specific (max 8)
            role_skills = self._compute_role_skills(
                role_bullets.hard_skills,
                role_bullets.soft_skills,
                target_keywords_lower,
                max_skills=8,
            )

            stitched_role = StitchedRole(
                role_id=role_bullets.role_id,
                company=role_bullets.company,
                title=role_bullets.title,
                location=location,
                period=role_bullets.period,
                bullets=bullets,
                skills=role_skills,
            )
            stitched_roles.append(stitched_role)

            # Collect skill summary for logging
            jd_matching_skills = [s for s in role_skills if s.lower() in target_keywords_lower]
            role_skill_summary.append({
                "company": role_bullets.company,
                "bullet_count": len(bullets),
                "skills_count": len(role_skills),
                "jd_matching_skills": jd_matching_skills,
            })

        # Step 5: Collect keyword coverage
        keywords_found = self._collect_keywords(bullet_lists, target_keywords)

        # Phase 0: Log skill compilation results
        self._emit_struct_log("decision_point", {
            "message": f"Compiled skills for {len(stitched_roles)} roles",
            "decision": "skill_compilation",
            "roles_summary": role_skill_summary,
            "total_keywords_found": len(keywords_found),
            "keywords_found": list(keywords_found)[:15],  # Limit for brevity
            "whitelist_active": self._whitelist_set is not None,
            "whitelist_size": len(self._whitelist_set) if self._whitelist_set else 0,
        })

        # Step 6: Build deduplication result
        dedup_result = DeduplicationResult(
            original_bullet_count=original_count,
            final_bullet_count=final_count,
            removed_count=original_count - final_count,
            duplicate_pairs=duplicates,
            compression_applied=compression_applied,
        )

        # Build final result
        stitched_cv = StitchedCV(
            roles=stitched_roles,
            keywords_coverage=keywords_found,
            deduplication_result=dedup_result,
        )

        # Log summary
        self._logger.info(f"Stitching complete:")
        self._logger.info(f"  Original bullets: {original_count}")
        self._logger.info(f"  After dedup: {after_dedup_count}")
        self._logger.info(f"  Final bullets: {final_count}")
        self._logger.info(f"  Total words: {stitched_cv.total_word_count}")
        self._logger.info(f"  Keywords found: {len(keywords_found)}")

        # Phase 0: Emit stitch complete
        self._emit_struct_log("subphase_complete", {
            "message": f"CV stitching complete: {final_count} bullets, {stitched_cv.total_word_count} words",
            "phase": 4,
            "subphase": "stitch_complete",
            "original_bullet_count": original_count,
            "final_bullet_count": final_count,
            "total_word_count": stitched_cv.total_word_count,
            "roles_count": len(stitched_roles),
            "keywords_coverage_count": len(keywords_found),
            "duplicates_removed": len(duplicates),
            "compression_applied": compression_applied,
        })

        return stitched_cv


def stitch_all_roles(
    role_bullets_list: List[RoleBullets],
    word_budget: Optional[int] = None,  # None = no limit
    target_keywords: Optional[List[str]] = None,
    skill_whitelist: Optional[Dict[str, List[str]]] = None,  # GAP-001: Prevent hallucinated skills
) -> StitchedCV:
    """
    Convenience function to stitch all roles.

    Args:
        role_bullets_list: List of RoleBullets from per-role generation
        word_budget: Target word count (None = no limit, include all)
        target_keywords: JD keywords to track
        skill_whitelist: Dict with 'hard_skills' and 'soft_skills' lists (GAP-001)

    Returns:
        StitchedCV with deduplicated content
    """
    stitcher = CVStitcher(word_budget=word_budget, skill_whitelist=skill_whitelist)
    return stitcher.stitch(role_bullets_list, target_keywords)
