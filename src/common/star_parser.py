"""
Canonical STAR Record Parser

Parses knowledge-base.md into structured canonical STAR achievement objects.
Handles all 20+ fields including pain points, outcome types, and embeddings.
"""

import re
from typing import Any, Dict, List, Optional

from src.common.types import STARRecord


def parse_star_records(knowledge_base_path: str) -> List[STARRecord]:
    """
    Parse knowledge-base.md into canonical STAR objects.

    Args:
        knowledge_base_path: Path to knowledge-base.md file

    Returns:
        List of canonical STARRecord dicts with all fields

    Raises:
        FileNotFoundError: If knowledge base file not found
        ValueError: If parsing fails
    """
    try:
        with open(knowledge_base_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        raise FileNotFoundError(f"Knowledge base file not found: {knowledge_base_path}")

    # Find all STAR record sections
    record_pattern = r'={50,}\s*STAR RECORD #\d+\s*={50,}(.*?)(?=={50,}\s*STAR RECORD #\d+\s*={50,}|={50,}\s*$|\Z)'
    matches = re.findall(record_pattern, content, re.DOTALL)

    if not matches:
        raise ValueError("No STAR records found in knowledge base")

    star_records: List[STARRecord] = []

    for i, record_text in enumerate(matches, 1):
        try:
            star = _parse_single_star(record_text.strip())
            star_records.append(star)
        except Exception as e:
            print(f"Warning: Failed to parse STAR record #{i}: {e}")
            continue

    if len(star_records) == 0:
        raise ValueError("Failed to parse any STAR records")

    return star_records


def _parse_single_star(record_text: str) -> STARRecord:
    """Parse a single STAR record from text into canonical format."""

    def get_line_value(label: str, text: str) -> str:
        """Extract value from a single-line field like 'ID: value'."""
        pattern = f'^{re.escape(label)}\\s*(.+?)$'
        match = re.search(pattern, text, re.MULTILINE)
        return match.group(1).strip() if match else ""

    def get_section(label: str, text: str, end_markers: List[str]) -> str:
        """Extract a multi-line section between markers."""
        start_pattern = f'^{re.escape(label)}\\s*$'
        start_match = re.search(start_pattern, text, re.MULTILINE)
        if not start_match:
            return ""

        start_pos = start_match.end()

        # Find end (first occurrence of any end marker)
        end_pos = len(text)
        for marker in end_markers:
            end_pattern = f'^{re.escape(marker)}'
            end_match = re.search(end_pattern, text[start_pos:], re.MULTILINE)
            if end_match:
                candidate_end = start_pos + end_match.start()
                if candidate_end < end_pos:
                    end_pos = candidate_end

        section = text[start_pos:end_pos].strip()
        return section

    def parse_bullet_list(text: str) -> List[str]:
        """Parse bullet-pointed text into a list of strings."""
        if not text:
            return []

        # Split by bullet points (•, -, *, or numbered)
        lines = []
        for line in text.split('\n'):
            line = line.strip()
            if line.startswith('• ') or line.startswith('- ') or line.startswith('* '):
                lines.append(line[2:].strip())
            elif re.match(r'^\d+\.\s+', line):
                # Handle numbered lists
                lines.append(re.sub(r'^\d+\.\s+', '', line).strip())
            elif line and lines:
                # Continuation of previous line
                lines[-1] = lines[-1] + ' ' + line
            elif line:
                # Non-bullet text, treat as single item
                lines.append(line)

        return [l for l in lines if l]

    def parse_delimited_list(text: str, delimiter: str = '•') -> List[str]:
        """Parse delimited text into a list of strings."""
        if not text:
            return []

        if delimiter in text:
            items = text.split(delimiter)
            return [item.strip() for item in items if item.strip()]
        else:
            # If no delimiter found, try comma separation
            items = text.split(',')
            if len(items) > 1:
                return [item.strip() for item in items if item.strip()]
            # Otherwise return as single item
            return [text.strip()] if text.strip() else []

    # Extract single-line fields
    star_id = get_line_value('ID:', record_text)
    company = get_line_value('COMPANY:', record_text)
    role_title = get_line_value('ROLE TITLE:', record_text)
    period = get_line_value('PERIOD:', record_text)

    # Extract delimited fields
    domain_areas_str = get_line_value('DOMAIN AREAS:', record_text)
    domain_areas = parse_delimited_list(domain_areas_str)

    ats_keywords_str = get_line_value('ATS KEYWORDS:', record_text)
    ats_keywords = parse_delimited_list(ats_keywords_str)

    target_roles_str = get_line_value('TARGET ROLES:', record_text)
    target_roles = parse_delimited_list(target_roles_str)

    categories_str = get_line_value('CATEGORIES:', record_text)
    categories = parse_delimited_list(categories_str)

    hard_skills_str = get_line_value('HARD SKILLS:', record_text)
    hard_skills = parse_delimited_list(hard_skills_str)

    soft_skills_str = get_line_value('SOFT SKILLS:', record_text)
    soft_skills = parse_delimited_list(soft_skills_str)

    # Extract multi-line narrative sections
    end_markers = [
        'SITUATION:', 'TASK:', 'ACTIONS:', 'RESULTS:', 'IMPACT', 'CONDENSED',
        'ATS KEYWORDS', 'TARGET ROLES', 'CATEGORIES', 'HARD SKILLS', 'SOFT SKILLS',
        'METRICS:', 'PAIN POINTS ADDRESSED:', 'OUTCOME TYPES:', 'SENIORITY', 'METADATA'
    ]

    background_context = get_section('BACKGROUND CONTEXT:', record_text, end_markers)
    situation = get_section('SITUATION:', record_text, end_markers)
    impact_summary = get_section('IMPACT SUMMARY:', record_text, end_markers)
    condensed_version = get_section('CONDENSED VERSION:', record_text, end_markers)

    # Extract bullet-list sections
    task_section = get_section('TASK:', record_text, end_markers)
    tasks = [task_section] if task_section and not task_section.startswith('•') else parse_bullet_list(task_section)

    actions_section = get_section('ACTIONS:', record_text, end_markers)
    actions = parse_bullet_list(actions_section)

    results_section = get_section('RESULTS:', record_text, end_markers)
    results = parse_bullet_list(results_section)

    metrics_section = get_section('METRICS:', record_text, ['SENIORITY WEIGHTS:', 'METADATA:', 'TARGET ROLES', 'CATEGORIES', 'PAIN POINTS ADDRESSED:', 'OUTCOME TYPES:'])
    metrics = parse_bullet_list(metrics_section)

    # Extract new fields (pain points and outcome types)
    pain_points_section = get_section('PAIN POINTS ADDRESSED:', record_text, ['OUTCOME TYPES:', 'SENIORITY', 'METADATA'])
    pain_points_addressed = parse_bullet_list(pain_points_section)

    outcome_types_section = get_section('OUTCOME TYPES:', record_text, ['SENIORITY', 'METADATA', 'TARGET ROLES'])
    outcome_types = parse_bullet_list(outcome_types_section)

    # Extract metadata section
    metadata: Dict[str, Any] = {}

    # Parse seniority weights
    seniority_section = get_section('SENIORITY WEIGHTS:', record_text, ['METADATA:'])
    if seniority_section:
        weights = {}
        for line in seniority_section.split('\n'):
            if ':' in line:
                role_pattern, weight = line.rsplit(':', 1)
                role_pattern = role_pattern.strip()
                try:
                    weights[role_pattern] = float(weight.strip())
                except ValueError:
                    pass
        if weights:
            metadata['seniority_weights'] = weights

    # Parse metadata lines
    metadata_section = get_section('METADATA:', record_text, ['===', 'STAR RECORD'])
    if metadata_section:
        for line in metadata_section.split('\n'):
            if ':' in line:
                key, value = line.split(':', 1)
                metadata[key.strip().lower().replace(' ', '_')] = value.strip()

    # Validate required fields
    if not star_id:
        raise ValueError(f"Missing ID field. Record preview: {record_text[:200]}")
    if not company:
        raise ValueError(f"Missing COMPANY field for ID: {star_id}")
    if not role_title:
        raise ValueError(f"Missing ROLE TITLE field for ID: {star_id}")

    # Ensure we have at least one metric
    if not metrics:
        # Try to extract from results
        for result in results:
            # Look for patterns like "75%" or "3 months" or "10x"
            if re.search(r'\d+[%x]|\d+\s*(months?|years?|days?|weeks?)', result):
                metrics.append(result)

    return STARRecord(
        id=star_id,
        company=company,
        role_title=role_title,
        period=period,
        domain_areas=domain_areas,
        background_context=background_context,
        situation=situation,
        tasks=tasks,
        actions=actions,
        results=results,
        impact_summary=impact_summary,
        condensed_version=condensed_version,
        ats_keywords=ats_keywords,
        categories=categories,
        hard_skills=hard_skills,
        soft_skills=soft_skills,
        metrics=metrics,
        pain_points_addressed=pain_points_addressed,
        outcome_types=outcome_types,
        target_roles=target_roles,
        metadata=metadata,
        embedding=None  # Will be generated separately
    )


def validate_star_record(star: STARRecord) -> List[str]:
    """
    Validate a STAR record and return list of issues.

    Args:
        star: STARRecord to validate

    Returns:
        List of validation issues (empty if valid)
    """
    issues = []

    # Check required fields
    if not star['id']:
        issues.append("Missing ID")
    if not star['company']:
        issues.append("Missing company")
    if not star['role_title']:
        issues.append("Missing role title")
    if not star['period']:
        issues.append("Missing period")

    # Check for at least one metric
    if not star['metrics']:
        issues.append("Missing quantified metrics")

    # Check for pain points addressed
    if not star['pain_points_addressed']:
        issues.append("Missing pain points addressed")

    # Check for outcome types
    if not star['outcome_types']:
        issues.append("Missing outcome types")

    # Check for key narrative elements
    if not star['situation']:
        issues.append("Missing situation")
    if not star['actions']:
        issues.append("Missing actions")
    if not star['results']:
        issues.append("Missing results")

    # Check for condensed version
    if not star['condensed_version']:
        issues.append("Missing condensed version")

    return issues