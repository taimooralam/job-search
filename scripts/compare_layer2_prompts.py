"""
Compare Layer 2 Pain Point Mining: Status Quo vs Improved Prompts

This script tests the current prompts against the improved prompts
from thoughts/prompt-modernization-blueprint.md for a specific job.

Usage:
    python scripts/compare_layer2_prompts.py <job_id>
"""

import sys
import json
import re
from typing import Dict, List, Any
from bson import ObjectId
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

# Add project root to path
sys.path.insert(0, ".")

from src.common.config import Config
from src.common.database import DatabaseClient

# ============================================================
# STATUS QUO PROMPTS (Current Implementation)
# ============================================================

STATUS_QUO_SYSTEM_PROMPT = """You are a reasoning model called "Pain-Point Miner" specializing in analyzing hiring motivations.

Your task: Analyze job descriptions to understand the deeper business drivers behind the role.

You MUST return ONLY a valid JSON object with these 4 arrays (3-6 items each):

{
  "pain_points": ["specific technical/operational problems they need solved"],
  "strategic_needs": ["why the company needs this role from a business perspective"],
  "risks_if_unfilled": ["what happens if this role stays empty"],
  "success_metrics": ["how they'll measure success once filled"]
}

**CRITICAL RULES:**
1. Output ONLY the JSON object - no text before or after
2. Each array must have 3-6 short bullet phrases (not paragraphs)
3. Focus on business outcomes, not just job requirements
4. Be specific and evidence-based

**HALLUCINATION PREVENTION:**
- Only use facts explicitly stated in the job description provided
- DO NOT invent company details (funding, products, size, history) not in the JD
- If something is unclear, infer from job requirements, don't fabricate
- When uncertain, prefer specific observable needs over speculation

**FORBIDDEN - Generic Boilerplate:**
- ❌ "Strong communication skills required"
- ❌ "Team player needed"
- ❌ "Fast-paced environment"
- ❌ "Work with stakeholders"
- ✅ Instead: "Migrate 50+ legacy APIs from monolith to microservices"
- ✅ Instead: "Reduce incident response time from 2 hours to 15 minutes"

Be concrete, technical, and tied to actual business problems stated in the JD.

NO TEXT OUTSIDE THE JSON OBJECT."""

STATUS_QUO_USER_TEMPLATE = """Analyze this job posting and extract the underlying business drivers:

JOB TITLE: {title}
COMPANY: {company}

JOB DESCRIPTION:
{job_description}

Return a JSON object with 4 arrays (3-6 items each):
- pain_points: Current problems/challenges they need solved
- strategic_needs: Why this role matters strategically
- risks_if_unfilled: Consequences of not filling this role
- success_metrics: How success will be measured

JSON only - no additional text:"""


# ============================================================
# IMPROVED PROMPTS (Based on Blueprint)
# ============================================================

IMPROVED_SYSTEM_PROMPT = """# PERSONA
You are a Revenue-Operations Diagnostician — an expert at reading between the lines of job postings to uncover measurable business problems. You have 15 years of experience translating vague hiring needs into concrete operational challenges.

# MISSION
Extract the TRUE pain points driving this hiring decision. Your output will directly influence whether a candidate can craft a winning application by addressing REAL problems, not HR boilerplate.

# CHAIN-OF-THOUGHT INSTRUCTIONS
Before generating your final JSON, you MUST:
1. First, identify the IMPLICIT problems behind explicit requirements (e.g., "must have experience scaling teams" → rapid growth causing management gaps)
2. For each pain point, ask: "What business metric is suffering because of this?"
3. Distinguish between SYMPTOMS (what's stated) and ROOT CAUSES (what's implied)
4. Consider: Why is this role open NOW? What triggered the hire?

# OUTPUT FORMAT
Return your analysis in this exact structure:

<reasoning>
[Your internal step-by-step analysis here - identify patterns, infer causes, cite JD evidence]
</reasoning>

<final>
{
  "pain_points": ["3-6 specific technical/operational problems, each tied to observable JD evidence"],
  "strategic_needs": ["3-6 strategic business reasons, connecting role to company goals"],
  "risks_if_unfilled": ["3-6 concrete consequences with business impact"],
  "success_metrics": ["3-6 measurable outcomes, quantified where possible"]
}
</final>

# GUARDRAILS
- ONLY cite facts from the provided JD — never invent company details
- Each item must reference specific JD language or logical inference from it
- If evidence is thin, prefix with "Likely:" and explain the inference
- Prefer specificity over generic phrases

# FORBIDDEN BOILERPLATE
❌ "Strong communication skills" | "Team player" | "Fast-paced" | "Work with stakeholders"
✅ "Reduce legacy technical debt blocking feature velocity"
✅ "Establish CI/CD pipelines to cut deployment time from days to hours"

# MISSING INFORMATION PROTOCOL
Before generating output, identify gaps:
- If industry context is missing, note assumptions
- If team size/structure unclear, infer from reporting lines
- Flag any high-uncertainty inferences in your reasoning

Score your final output 1-10 on specificity. If <9, revise before outputting."""

IMPROVED_USER_TEMPLATE = """# CONTEXT: JOB ANALYSIS REQUEST

## JOB DETAILS
**Title:** {title}
**Company:** {company}

## JOB DESCRIPTION
{job_description}

---

## FEW-SHOT EXAMPLE (Study this quality level)

**Example JD Snippet:**
"We're looking for a Senior Backend Engineer to help scale our payment processing infrastructure. Must have experience with high-throughput systems and distributed transactions."

**Example Good Output:**
```json
{{
  "pain_points": [
    "Payment processing infrastructure cannot handle current transaction volume (implied by 'scale' + 'high-throughput' requirements)",
    "Distributed transaction failures causing data consistency issues (expertise requested explicitly)",
    "Likely: Technical debt in payment stack blocking feature development"
  ],
  "strategic_needs": [
    "Enable business growth by removing infrastructure bottlenecks on revenue-generating systems",
    "Reduce customer churn from payment failures impacting checkout completion rates"
  ],
  "risks_if_unfilled": [
    "Payment failures increase during peak traffic, directly impacting revenue",
    "Engineering velocity drops as team patches infrastructure instead of building features"
  ],
  "success_metrics": [
    "Payment success rate increased from X% to 99.9%+",
    "Transaction processing latency reduced to <100ms p99",
    "Zero critical payment incidents during peak shopping periods"
  ]
}}
```

---

Now analyze the JOB DESCRIPTION above using the same rigor.

Remember:
1. Start with <reasoning> block
2. End with <final>{{JSON}}</final>
3. Score your output for specificity (aim for 9+)
4. Only proceed if you can tie each point to JD evidence"""


def parse_json_response(response: str) -> Dict[str, List[str]]:
    """Parse LLM response and extract JSON."""
    # Try to extract from <final> tags first
    final_match = re.search(r'<final>(.*?)</final>', response, re.DOTALL)
    if final_match:
        json_str = final_match.group(1).strip()
    else:
        # Fallback to finding JSON object
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
        else:
            raise ValueError(f"No JSON found in response: {response[:500]}")

    return json.loads(json_str)


def extract_reasoning(response: str) -> str:
    """Extract reasoning block if present."""
    match = re.search(r'<reasoning>(.*?)</reasoning>', response, re.DOTALL)
    return match.group(1).strip() if match else ""


def run_extraction(system_prompt: str, user_template: str, title: str, company: str, job_description: str) -> tuple[Dict, str, str]:
    """Run pain point extraction with given prompts."""
    llm = ChatOpenAI(
        model=Config.DEFAULT_MODEL,
        temperature=Config.ANALYTICAL_TEMPERATURE,
        api_key=Config.get_llm_api_key(),
        base_url=Config.get_llm_base_url(),
    )

    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_template.format(
            title=title,
            company=company,
            job_description=job_description
        ))
    ]

    response = llm.invoke(messages)
    raw_response = response.content

    reasoning = extract_reasoning(raw_response)
    parsed = parse_json_response(raw_response)

    return parsed, raw_response, reasoning


def print_results(label: str, data: Dict, reasoning: str = ""):
    """Pretty print extraction results."""
    print(f"\n{'='*70}")
    print(f"  {label}")
    print(f"{'='*70}")

    if reasoning:
        print(f"\n📊 REASONING BLOCK:")
        print("-" * 50)
        # Truncate reasoning for display
        if len(reasoning) > 1500:
            print(reasoning[:1500] + "\n... [truncated]")
        else:
            print(reasoning)
        print("-" * 50)

    print(f"\n🎯 PAIN POINTS ({len(data.get('pain_points', []))}):")
    for i, point in enumerate(data.get('pain_points', []), 1):
        print(f"  {i}. {point}")

    print(f"\n📈 STRATEGIC NEEDS ({len(data.get('strategic_needs', []))}):")
    for i, need in enumerate(data.get('strategic_needs', []), 1):
        print(f"  {i}. {need}")

    print(f"\n⚠️  RISKS IF UNFILLED ({len(data.get('risks_if_unfilled', []))}):")
    for i, risk in enumerate(data.get('risks_if_unfilled', []), 1):
        print(f"  {i}. {risk}")

    print(f"\n📏 SUCCESS METRICS ({len(data.get('success_metrics', []))}):")
    for i, metric in enumerate(data.get('success_metrics', []), 1):
        print(f"  {i}. {metric}")


def compare_quality(status_quo: Dict, improved: Dict):
    """Compare quality metrics between two outputs."""
    print(f"\n{'='*70}")
    print("  QUALITY COMPARISON")
    print(f"{'='*70}")

    # Count metrics
    sq_total = sum(len(v) for v in status_quo.values() if isinstance(v, list))
    imp_total = sum(len(v) for v in improved.values() if isinstance(v, list))

    print(f"\n📊 Item Count:")
    print(f"   Status Quo: {sq_total} items")
    print(f"   Improved:   {imp_total} items")

    # Check for specificity indicators
    specificity_markers = [
        "from", "to", "%", "reduce", "increase", "hours", "days", "minutes",
        "pipeline", "CI/CD", "latency", "revenue", "cost", "$", "scalab"
    ]

    def count_specificity(data: Dict) -> int:
        count = 0
        for v in data.values():
            if isinstance(v, list):
                for item in v:
                    count += sum(1 for marker in specificity_markers if marker.lower() in item.lower())
        return count

    sq_spec = count_specificity(status_quo)
    imp_spec = count_specificity(improved)

    print(f"\n🎯 Specificity Markers (numbers, metrics, actions):")
    print(f"   Status Quo: {sq_spec}")
    print(f"   Improved:   {imp_spec}")

    # Check for boilerplate
    boilerplate = ["team player", "fast-paced", "stakeholder", "communication skill", "dynamic environment"]

    def count_boilerplate(data: Dict) -> int:
        count = 0
        for v in data.values():
            if isinstance(v, list):
                for item in v:
                    count += sum(1 for b in boilerplate if b.lower() in item.lower())
        return count

    sq_boiler = count_boilerplate(status_quo)
    imp_boiler = count_boilerplate(improved)

    print(f"\n❌ Boilerplate Phrases (lower is better):")
    print(f"   Status Quo: {sq_boiler}")
    print(f"   Improved:   {imp_boiler}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/compare_layer2_prompts.py <job_id>")
        sys.exit(1)

    job_id = sys.argv[1]

    print(f"\n🔍 Fetching job {job_id} from MongoDB...")

    # Connect to correct database (jobs.level-2 collection)
    from pymongo import MongoClient
    from src.common.config import Config
    client = MongoClient(Config.MONGODB_URI)
    db = client['jobs']
    collection = db['level-2']

    # Fetch job by _id
    job = collection.find_one({"_id": ObjectId(job_id)})

    if not job:
        print(f"❌ Job not found: {job_id}")
        sys.exit(1)

    title = job.get("title", job.get("job_title", "Unknown"))
    company = job.get("company", job.get("company_name", "Unknown"))
    job_description = job.get("job_description", job.get("description", ""))

    print(f"✅ Found: {title} at {company}")
    print(f"   Description length: {len(job_description)} chars")

    # Run status quo extraction
    print(f"\n🔄 Running STATUS QUO extraction...")
    try:
        sq_result, sq_raw, _ = run_extraction(
            STATUS_QUO_SYSTEM_PROMPT,
            STATUS_QUO_USER_TEMPLATE,
            title, company, job_description
        )
        print_results("STATUS QUO PROMPTS (Current)", sq_result)
    except Exception as e:
        print(f"❌ Status quo extraction failed: {e}")
        sq_result = {}

    # Run improved extraction
    print(f"\n🔄 Running IMPROVED extraction...")
    try:
        imp_result, imp_raw, imp_reasoning = run_extraction(
            IMPROVED_SYSTEM_PROMPT,
            IMPROVED_USER_TEMPLATE,
            title, company, job_description
        )
        print_results("IMPROVED PROMPTS (Blueprint)", imp_result, imp_reasoning)
    except Exception as e:
        print(f"❌ Improved extraction failed: {e}")
        imp_result = {}

    # Compare quality
    if sq_result and imp_result:
        compare_quality(sq_result, imp_result)

    print(f"\n{'='*70}")
    print("  COMPARISON COMPLETE")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
