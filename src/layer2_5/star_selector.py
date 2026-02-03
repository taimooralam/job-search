"""
Layer 2.5: STAR Selector

Maps job pain points to candidate's 2-3 most relevant STAR achievements.
Uses LLM to score each STAR's relevance to each pain point.

Phase 4 Enhancement: Integrates JD annotation boost to prioritize STAR records
that have been manually linked to annotations.
"""

import re
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
from tenacity import retry, stop_after_attempt, wait_exponential

from src.common.config import Config
from src.common.unified_llm import invoke_unified_sync
from src.common.state import JobState
from src.common.star_parser import parse_star_records
from src.common.types import STARRecord
from src.common.annotation_boost import AnnotationBoostCalculator


# ===== PROMPT DESIGN =====

SYSTEM_PROMPT = """You are an expert career consultant specializing in achievement-based job matching.

Your task: Score how relevant each candidate STAR achievement is to specific job pain points.

For each STAR record, evaluate its relevance to EACH pain point on a 0-10 scale:
- 0-2: Not relevant, no transferable skills
- 3-5: Somewhat relevant, general transferable skills
- 6-7: Relevant, demonstrates related experience
- 8-9: Highly relevant, directly addresses this pain point
- 10: Perfect match, proven results in exactly this area

Consider:
- Direct experience with the same problem/technology
- Quantified results and metrics
- Scale and complexity of achievement
- Recency and role seniority

Be precise and evidence-based."""

USER_PROMPT_TEMPLATE = """Analyze how well these candidate achievements address the job's needs across 4 dimensions:

=== JOB ANALYSIS (4 DIMENSIONS) ===

PAIN POINTS:
{pain_points}

STRATEGIC NEEDS:
{strategic_needs}

RISKS IF UNFILLED:
{risks_if_unfilled}

SUCCESS METRICS:
{success_metrics}

=== CANDIDATE STAR RECORDS ===
{star_summaries}

=== YOUR SCORING ===
For EACH STAR, rate its relevance to EACH item across ALL 4 dimensions (0-10 scale):

Format your response EXACTLY as:
STAR_ID: <uuid>
Pain Point 1: <score>
Pain Point 2: <score>
...
Strategic Need 1: <score>
Strategic Need 2: <score>
...
Risk 1: <score>
Risk 2: <score>
...
Success Metric 1: <score>
Success Metric 2: <score>
...
Aggregate: <sum of all scores>
Reasoning: <1-2 sentences explaining fit>

---

STAR_ID: <next uuid>
...

Continue for all STARs."""


class STARSelector:
    """
    Selects 2-3 most relevant STAR records for a job based on pain points.
    """

    def __init__(self):
        """Initialize and load STAR records."""
        # Load STAR records from knowledge base
        kb_path = Path(__file__).parent.parent.parent / "knowledge-base.md"
        self.star_records = parse_star_records(str(kb_path))
        print(f"Loaded {len(self.star_records)} STAR records")

    def _format_dimension(self, items: List[str], prefix: str) -> str:
        """Format a dimension as numbered list."""
        if not items:
            return f"No {prefix.lower()} identified."
        return "\n".join(f"{prefix} {i}: {item}"
                        for i, item in enumerate(items, 1))

    def _format_star_summaries(self, stars: List[STARRecord]) -> str:
        """Format STAR records as compact summaries for LLM."""
        summaries = []
        for star in stars:
            # Handle canonical schema with List fields
            domain_str = ', '.join(star.get('domain_areas', [])) or 'N/A'
            tasks_str = '; '.join(star.get('tasks', []))[:150] or 'N/A'
            results_str = '; '.join(star.get('results', []))[:200] or 'N/A'
            metrics_str = '; '.join(star.get('metrics', [])) or 'N/A'
            situation_str = (star.get('situation', '') or '')[:200]

            summary = f"""
STAR_ID: {star['id']}
Company: {star['company']}
Role: {star.get('role_title', '')}
Domain: {domain_str}
Situation: {situation_str}...
Task: {tasks_str}...
Results: {results_str}...
Key Metrics: {metrics_str}
Pain Points Addressed: {', '.join(star.get('pain_points_addressed', [])) or 'N/A'}
Outcome Types: {', '.join(star.get('outcome_types', [])) or 'N/A'}
""".strip()
            summaries.append(summary)

        return "\n\n---\n\n".join(summaries)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    def _score_stars(self, state: JobState) -> str:
        """Call LLM to score all STARs against all 4 dimensions."""

        user_prompt = USER_PROMPT_TEMPLATE.format(
            pain_points=self._format_dimension(state.get('pain_points', []), "Pain Point"),
            strategic_needs=self._format_dimension(state.get('strategic_needs', []), "Strategic Need"),
            risks_if_unfilled=self._format_dimension(state.get('risks_if_unfilled', []), "Risk"),
            success_metrics=self._format_dimension(state.get('success_metrics', []), "Success Metric"),
            star_summaries=self._format_star_summaries(self.star_records)
        )

        # Use unified LLM with step config
        result = invoke_unified_sync(
            prompt=user_prompt,
            system=SYSTEM_PROMPT,
            step_name="star_selection",
            job_id=state.get("job_id", "unknown"),
            validate_json=False,  # Response is formatted text, not JSON
        )

        if not result.success:
            raise RuntimeError(f"STAR scoring LLM failed: {result.error}")

        return result.content

    def _parse_scores(self, llm_response: str, num_pain_points: int) -> List[Dict[str, Any]]:
        """
        Parse LLM scoring response into structured data.

        Returns:
            List of dicts with keys: star_id, scores (list), aggregate, reasoning
        """
        scored_stars = []

        # Split by STAR records (looking for STAR_ID:)
        star_blocks = re.split(r'\n---\n|\nSTAR_ID:', llm_response)

        for block in star_blocks:
            if not block.strip():
                continue

            # Extract STAR ID
            id_match = re.search(r'([0-9a-f-]{36}|UUID-STAR-\d+)', block, re.IGNORECASE)
            if not id_match:
                continue

            star_id = id_match.group(1)

            # Extract pain point scores
            scores = []
            for i in range(1, num_pain_points + 1):
                score_pattern = f'Pain Point {i}:\\s*(\\d+)'
                score_match = re.search(score_pattern, block)
                if score_match:
                    scores.append(int(score_match.group(1)))
                else:
                    scores.append(0)  # Default to 0 if not found

            # Extract aggregate
            agg_match = re.search(r'Aggregate:\\s*(\\d+)', block)
            aggregate = int(agg_match.group(1)) if agg_match else sum(scores)

            # Extract reasoning
            reasoning_match = re.search(r'Reasoning:\\s*(.+?)(?=\n\n|$)', block, re.DOTALL)
            reasoning = reasoning_match.group(1).strip() if reasoning_match else ""

            scored_stars.append({
                'star_id': star_id,
                'scores': scores,
                'aggregate': aggregate,
                'reasoning': reasoning
            })

        return scored_stars

    def _select_top_stars(
        self,
        scored_stars: List[Dict[str, Any]],
        pain_points: List[str],
        annotation_calculator: Optional[AnnotationBoostCalculator] = None,
    ) -> Tuple[List[STARRecord], Dict[str, List[str]], Dict[str, float]]:
        """
        Select top 2-3 STARs and create pain point mapping.

        Phase 4: Applies annotation boost to prioritize STAR records
        that have been manually linked to annotations.

        Args:
            scored_stars: List of scored STAR records
            pain_points: List of job pain points
            annotation_calculator: Optional calculator for annotation boost

        Returns:
            Tuple of (selected_stars, star_to_pain_mapping, annotation_boosts)
        """
        # Phase 4: Apply annotation boost to aggregate scores
        annotation_boosts: Dict[str, float] = {}

        if annotation_calculator and annotation_calculator.has_annotations():
            for scored in scored_stars:
                star_id = scored['star_id']
                boost_result = annotation_calculator.get_boost_for_star(star_id)

                if boost_result.boost != 1.0:
                    # Apply boost to aggregate score
                    original_score = scored['aggregate']
                    boosted_score = original_score * boost_result.boost
                    scored['aggregate'] = boosted_score
                    scored['annotation_boost'] = boost_result.boost
                    scored['annotation_ids'] = boost_result.contributing_annotations
                    annotation_boosts[star_id] = boost_result.boost
                    print(f"   📌 STAR {star_id[:8]}... boosted: {original_score:.0f} → {boosted_score:.0f} ({boost_result.boost:.1f}x)")

        # Sort by aggregate score (descending)
        scored_stars.sort(key=lambda x: x['aggregate'], reverse=True)

        # Select top 2-3 (at least 2, up to 3)
        top_count = min(3, max(2, len(scored_stars)))
        top_scored = scored_stars[:top_count]

        # Get full STAR records
        selected_stars = []
        star_id_to_record = {star['id']: star for star in self.star_records}

        for scored in top_scored:
            star_id = scored['star_id']
            if star_id in star_id_to_record:
                selected_stars.append(star_id_to_record[star_id])

        # Create mapping: pain_point -> [star_ids that scored >= 7]
        star_to_pain_mapping = {}

        for i, pain_point in enumerate(pain_points):
            relevant_star_ids = []
            for scored in top_scored:
                if i < len(scored['scores']) and scored['scores'][i] >= 7:
                    relevant_star_ids.append(scored['star_id'])

            if relevant_star_ids:
                star_to_pain_mapping[f"Pain Point {i+1}"] = relevant_star_ids

        return selected_stars, star_to_pain_mapping, annotation_boosts

    def select_stars(self, state: JobState) -> Dict[str, Any]:
        """
        Layer 2.5: STAR Selector node.

        Selects 2-3 best STAR records matching job across 4 dimensions.

        Phase 4 Enhancement: Applies annotation boost to prioritize STAR records
        that have been manually linked to JD annotations.

        Args:
            state: JobState with pain_points, strategic_needs, risks_if_unfilled,
                   success_metrics, and optionally jd_annotations

        Returns:
            Dict with selected_stars, star_to_pain_mapping, and annotation metadata
        """
        pain_points = state.get('pain_points', [])
        strategic_needs = state.get('strategic_needs', [])
        risks = state.get('risks_if_unfilled', [])
        metrics = state.get('success_metrics', [])

        # Phase 4: Get JD annotations for boost calculation
        jd_annotations = state.get('jd_annotations')
        annotation_calculator = AnnotationBoostCalculator(jd_annotations) if jd_annotations else None

        total_items = len(pain_points) + len(strategic_needs) + len(risks) + len(metrics)

        if total_items == 0:
            print("⚠️  No job analysis data found, skipping STAR selection")
            return {
                'selected_stars': [],
                'star_to_pain_mapping': {},
                'all_stars': self.star_records  # Phase 8.2: Still provide full library
            }

        print(f"\n{'='*80}")
        print(f"LAYER 2.5: STAR SELECTOR")
        print(f"{'='*80}")
        print(f"Job analysis dimensions:")
        print(f"  - Pain points: {len(pain_points)}")
        print(f"  - Strategic needs: {len(strategic_needs)}")
        print(f"  - Risks if unfilled: {len(risks)}")
        print(f"  - Success metrics: {len(metrics)}")
        print(f"Available STARs: {len(self.star_records)}")

        # Phase 4: Log annotation status
        if annotation_calculator and annotation_calculator.has_annotations():
            stats = annotation_calculator.get_stats()
            print(f"📌 Annotation boost ACTIVE:")
            print(f"   - Active annotations: {stats['total_active']}")
            print(f"   - STARs linked: {stats['stars_linked']}")
            print(f"   - Core strengths: {stats['core_strengths']}")

        try:
            # Score all STARs
            print("Scoring STARs across all dimensions...")
            llm_response = self._score_stars(state)

            # Parse scores
            scored_stars = self._parse_scores(llm_response, total_items)
            print(f"Scored {len(scored_stars)} STARs")

            # Select top STARs (Phase 4: with annotation boost)
            selected_stars, mapping, annotation_boosts = self._select_top_stars(
                scored_stars, pain_points, annotation_calculator
            )

            print(f"✅ Selected {len(selected_stars)} top STARs:")
            for i, star in enumerate(selected_stars, 1):
                role_title = star.get('role_title', 'Unknown')[:50]
                boost_info = ""
                if star['id'] in annotation_boosts:
                    boost_info = f" [📌 {annotation_boosts[star['id']]:.1f}x boost]"
                print(f"   {i}. {star['company']} - {role_title}...{boost_info} (ID: {star['id'][:8]}...)")

            result = {
                'selected_stars': selected_stars,
                'star_to_pain_mapping': mapping,
                'all_stars': self.star_records,  # Phase 8.2: Provide full library for CV generation
            }

            # Phase 4: Include annotation metadata if boosts were applied
            if annotation_boosts:
                result['annotation_boosts'] = annotation_boosts
                result['annotation_influenced'] = True

            return result

        except Exception as e:
            print(f"❌ STAR selection failed: {e}")
            # Graceful degradation: return first 2 STARs
            fallback_stars = self.star_records[:2]
            return {
                'selected_stars': fallback_stars,
                'star_to_pain_mapping': {},
                'all_stars': self.star_records,  # Phase 8.2: Still provide full library even on error
                'errors': [f"STAR selection error: {str(e)}"]
            }


# ===== NODE FUNCTION =====

def select_stars(state: JobState) -> Dict[str, Any]:
    """
    LangGraph node function for Layer 2.5.

    Args:
        state: Current job state

    Returns:
        State updates with selected STARs
    """
    selector = STARSelector()
    return selector.select_stars(state)
