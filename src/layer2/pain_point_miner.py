"""
Layer 2: Pain-Point Miner (Enhanced Edition)

Extracts structured pain-point analysis from job descriptions using LLM.
Returns JSON with 4 arrays: pain_points, strategic_needs, risks_if_unfilled, success_metrics.

Phase 1.3 Update: Full JSON output per requirements.md and feedback.md
Phase 4 Update: Added formal JSON schema validation with Pydantic
Phase 5 Update: Enhanced prompts with persona, chain-of-thought reasoning,
                domain-aware few-shot examples, and confidence scoring
                (based on thoughts/prompt-modernization-blueprint.md)
"""

import json
import re
from typing import List, Dict, Any, Optional, Literal
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from tenacity import retry, stop_after_attempt, wait_exponential
from enum import Enum

from src.common.config import Config
from src.common.state import JobState
from src.common.logger import get_logger
from src.common.structured_logger import get_structured_logger, LayerContext


# ===== DOMAIN DETECTION =====

class JobDomain(str, Enum):
    """Job domain categories for domain-aware few-shot examples."""
    TECH_SAAS = "tech_saas"
    FINTECH_BANKING = "fintech_banking"
    HEALTHCARE = "healthcare"
    MANUFACTURING = "manufacturing"
    TRANSPORTATION = "transportation"  # Railways, logistics, etc.
    CONSULTING = "consulting"
    ECOMMERCE = "ecommerce"
    GENERAL = "general"


DOMAIN_KEYWORDS = {
    JobDomain.TECH_SAAS: [
        "saas", "software", "cloud", "api", "microservices", "devops", "ci/cd",
        "kubernetes", "docker", "aws", "azure", "gcp", "scalability", "platform"
    ],
    JobDomain.FINTECH_BANKING: [
        "fintech", "banking", "payment", "transaction", "financial", "trading",
        "compliance", "kyc", "aml", "pci", "fraud", "credit", "lending"
    ],
    JobDomain.HEALTHCARE: [
        "healthcare", "medical", "clinical", "patient", "hipaa", "ehr", "health",
        "pharmaceutical", "biotech", "fda", "clinical trial"
    ],
    JobDomain.MANUFACTURING: [
        "manufacturing", "production", "supply chain", "inventory", "quality control",
        "lean", "six sigma", "factory", "assembly", "oem"
    ],
    JobDomain.TRANSPORTATION: [
        "railway", "rail", "transportation", "logistics", "fleet", "safety system",
        "signaling", "traffic", "aviation", "maritime", "freight"
    ],
    JobDomain.CONSULTING: [
        "consulting", "advisory", "strategy", "transformation", "management consulting",
        "client engagement", "deliverables", "stakeholder"
    ],
    JobDomain.ECOMMERCE: [
        "ecommerce", "e-commerce", "retail", "checkout", "cart", "marketplace",
        "fulfillment", "merchant", "catalog", "product listing"
    ],
}


def detect_domain(title: str, job_description: str) -> JobDomain:
    """Detect job domain from title and description for domain-aware prompting."""
    text = f"{title} {job_description}".lower()

    domain_scores = {}
    for domain, keywords in DOMAIN_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text)
        if score > 0:
            domain_scores[domain] = score

    if domain_scores:
        return max(domain_scores, key=domain_scores.get)
    return JobDomain.GENERAL


# ===== DOMAIN-SPECIFIC FEW-SHOT EXAMPLES =====

DOMAIN_EXAMPLES = {
    JobDomain.TECH_SAAS: {
        "jd_snippet": """Senior Backend Engineer to scale our API platform.
Must have experience with microservices, Kubernetes, and high-throughput systems.
Will own service reliability and lead migration from monolith.""",
        "output": {
            "pain_points": [
                {"text": "Monolithic architecture blocking feature velocity and independent deployments", "evidence": "lead migration from monolith", "confidence": "high"},
                {"text": "API platform cannot handle current traffic growth", "evidence": "'scale our API platform' + 'high-throughput systems'", "confidence": "high"},
                {"text": "Service reliability issues impacting customer experience", "evidence": "'own service reliability' suggests current gaps", "confidence": "medium"}
            ],
            "strategic_needs": [
                {"text": "Enable independent team scaling through microservices decoupling", "evidence": "microservices requirement", "confidence": "high"},
                {"text": "Reduce infrastructure costs through better resource utilization", "evidence": "Kubernetes expertise requested", "confidence": "medium"}
            ],
            "risks_if_unfilled": [
                {"text": "Feature releases blocked by monolith coupling, slowing time-to-market", "evidence": "migration priority implies urgency", "confidence": "high"},
                {"text": "Outages during traffic spikes damaging customer trust", "evidence": "reliability ownership needed", "confidence": "medium"}
            ],
            "success_metrics": [
                {"text": "API latency reduced to <100ms p99", "evidence": "high-throughput requirement", "confidence": "medium"},
                {"text": "Deployment frequency increased from weekly to daily", "evidence": "microservices enable faster deploys", "confidence": "medium"},
                {"text": "Zero monolith dependencies for new services within 12 months", "evidence": "migration mandate", "confidence": "high"}
            ]
        }
    },
    JobDomain.FINTECH_BANKING: {
        "jd_snippet": """Payment Systems Architect to redesign our transaction processing.
Must ensure PCI compliance and handle 10x transaction growth.
Experience with real-time fraud detection required.""",
        "output": {
            "pain_points": [
                {"text": "Current payment infrastructure cannot scale for projected 10x growth", "evidence": "'handle 10x transaction growth' explicit", "confidence": "high"},
                {"text": "PCI compliance gaps creating audit and security risks", "evidence": "'ensure PCI compliance' suggests gaps", "confidence": "medium"},
                {"text": "Fraud detection latency causing financial losses", "evidence": "'real-time fraud detection required'", "confidence": "high"}
            ],
            "strategic_needs": [
                {"text": "Support business expansion without payment bottlenecks", "evidence": "10x growth mandate", "confidence": "high"},
                {"text": "Reduce fraud losses while maintaining transaction approval rates", "evidence": "fraud detection focus", "confidence": "high"}
            ],
            "risks_if_unfilled": [
                {"text": "Payment failures during growth causing revenue loss and churn", "evidence": "scaling explicitly required", "confidence": "high"},
                {"text": "PCI audit failure resulting in fines and merchant account suspension", "evidence": "compliance emphasis", "confidence": "medium"}
            ],
            "success_metrics": [
                {"text": "Payment success rate maintained at 99.9%+ during 10x scale", "evidence": "growth + reliability requirement", "confidence": "high"},
                {"text": "Fraud detection latency under 50ms for real-time decisioning", "evidence": "real-time requirement", "confidence": "medium"},
                {"text": "Full PCI-DSS Level 1 certification achieved", "evidence": "compliance mandate", "confidence": "high"}
            ]
        }
    },
    JobDomain.TRANSPORTATION: {
        "jd_snippet": """Solution Architect for railway signaling systems.
Must understand RAMS criteria and safety-critical software development.
Experience with SIL-4 systems and CENELEC standards required.""",
        "output": {
            "pain_points": [
                {"text": "Legacy signaling systems not meeting modern safety standards", "evidence": "'RAMS criteria' + 'safety-critical' focus", "confidence": "medium"},
                {"text": "Integration challenges between new digital systems and existing infrastructure", "evidence": "architect role for signaling systems", "confidence": "medium"},
                {"text": "Certification bottlenecks slowing system deployments", "evidence": "'SIL-4' + 'CENELEC standards' expertise needed", "confidence": "high"}
            ],
            "strategic_needs": [
                {"text": "Modernize railway infrastructure for increased capacity and reliability", "evidence": "solution architect for signaling", "confidence": "high"},
                {"text": "Achieve regulatory compliance to operate in EU markets", "evidence": "CENELEC standards requirement", "confidence": "high"}
            ],
            "risks_if_unfilled": [
                {"text": "Safety certification delays blocking new line deployments", "evidence": "SIL-4 expertise gap", "confidence": "high"},
                {"text": "Non-compliance with railway safety directives risking operational license", "evidence": "RAMS + CENELEC focus", "confidence": "medium"}
            ],
            "success_metrics": [
                {"text": "SIL-4 certification achieved for new signaling platform", "evidence": "explicit requirement", "confidence": "high"},
                {"text": "System availability target of 99.99% (RAMS 'Availability')", "evidence": "RAMS criteria focus", "confidence": "medium"},
                {"text": "Zero safety-critical defects in deployed systems", "evidence": "safety-critical emphasis", "confidence": "high"}
            ]
        }
    },
    JobDomain.GENERAL: {
        "jd_snippet": """Senior Product Manager to own our core platform roadmap.
Must balance technical debt reduction with new feature delivery.
Will work closely with engineering and design teams.""",
        "output": {
            "pain_points": [
                {"text": "Technical debt accumulation slowing feature development velocity", "evidence": "'balance technical debt reduction' explicit", "confidence": "high"},
                {"text": "Roadmap alignment gaps between product, engineering, and design", "evidence": "'work closely with' suggests coordination needs", "confidence": "medium"},
                {"text": "Core platform lacking clear ownership and strategic direction", "evidence": "'own our core platform roadmap'", "confidence": "high"}
            ],
            "strategic_needs": [
                {"text": "Accelerate product delivery while maintaining platform health", "evidence": "debt vs features balance", "confidence": "high"},
                {"text": "Establish clear product vision to align cross-functional teams", "evidence": "ownership + team coordination", "confidence": "medium"}
            ],
            "risks_if_unfilled": [
                {"text": "Technical debt compounds, making future development exponentially harder", "evidence": "debt focus in JD", "confidence": "high"},
                {"text": "Misaligned priorities between teams causing wasted effort", "evidence": "cross-functional coordination need", "confidence": "medium"}
            ],
            "success_metrics": [
                {"text": "Feature delivery velocity increased by X% while reducing critical bugs", "evidence": "balance mandate", "confidence": "medium"},
                {"text": "Technical debt backlog reduced by X% within first year", "evidence": "explicit debt focus", "confidence": "medium"},
                {"text": "Roadmap alignment score of 90%+ across stakeholder surveys", "evidence": "team coordination emphasis", "confidence": "low"}
            ]
        }
    }
}


# ===== SCHEMA VALIDATION =====

class ConfidenceLevel(str, Enum):
    """Confidence levels for pain point analysis items."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class AnalysisItem(BaseModel):
    """Single analysis item with confidence scoring."""
    text: str = Field(..., min_length=10, description="The analysis statement")
    evidence: str = Field(..., min_length=5, description="JD quote or inference basis")
    confidence: ConfidenceLevel = Field(..., description="Confidence level based on evidence strength")

    @field_validator('text')
    @classmethod
    def validate_not_boilerplate(cls, v: str) -> str:
        """Reject generic boilerplate phrases."""
        boilerplate = [
            "strong communication", "team player", "fast-paced environment",
            "work with stakeholders", "dynamic environment", "self-starter"
        ]
        v_lower = v.lower()
        for phrase in boilerplate:
            if phrase in v_lower:
                raise ValueError(f"Boilerplate phrase detected: '{phrase}'. Be more specific.")
        return v


class EnhancedPainPointAnalysis(BaseModel):
    """
    Enhanced Pydantic schema for pain-point analysis with confidence scoring.

    Each item now includes:
    - text: The actual insight
    - evidence: JD quote or inference basis
    - confidence: high/medium/low based on evidence strength

    This enables downstream processes to weight insights appropriately.
    """
    pain_points: List[AnalysisItem] = Field(
        ...,
        min_length=2,
        max_length=6,
        description="Specific technical/operational problems with evidence"
    )
    strategic_needs: List[AnalysisItem] = Field(
        ...,
        min_length=2,
        max_length=5,
        description="Strategic business reasons for this role"
    )
    risks_if_unfilled: List[AnalysisItem] = Field(
        ...,
        min_length=2,
        max_length=5,
        description="Business consequences if role stays empty"
    )
    success_metrics: List[AnalysisItem] = Field(
        ...,
        min_length=2,
        max_length=6,
        description="Measurable outcomes for success"
    )
    reasoning_summary: Optional[str] = Field(
        None,
        description="Brief summary of key inferences made"
    )
    why_now: Optional[str] = Field(
        None,
        description="Inferred reason why this role is open now"
    )


class LegacyPainPointAnalysis(BaseModel):
    """
    Legacy schema for backward compatibility.
    Maintains original validation constraints for string lists.
    """
    pain_points: List[str] = Field(
        ...,
        min_length=1,
        max_length=8,
        description="1-8 specific technical/operational problems they need solved"
    )
    strategic_needs: List[str] = Field(
        ...,
        min_length=1,
        max_length=8,
        description="1-8 strategic business reasons why this role matters"
    )
    risks_if_unfilled: List[str] = Field(
        ...,
        min_length=1,
        max_length=8,
        description="1-8 consequences if this role stays empty"
    )
    success_metrics: List[str] = Field(
        ...,
        min_length=1,
        max_length=8,
        description="1-8 measurable outcomes for success"
    )

    @field_validator('pain_points', 'strategic_needs', 'risks_if_unfilled', 'success_metrics')
    @classmethod
    def validate_non_empty_strings(cls, v: List[str]) -> List[str]:
        """Ensure all items are non-empty strings."""
        for item in v:
            if not isinstance(item, str) or not item.strip():
                raise ValueError(f"All items must be non-empty strings, got: {item}")
        return v

    @classmethod
    def from_enhanced(cls, enhanced: EnhancedPainPointAnalysis) -> "LegacyPainPointAnalysis":
        """Convert enhanced analysis to legacy format."""
        return cls(
            pain_points=[item.text for item in enhanced.pain_points],
            strategic_needs=[item.text for item in enhanced.strategic_needs],
            risks_if_unfilled=[item.text for item in enhanced.risks_if_unfilled],
            success_metrics=[item.text for item in enhanced.success_metrics],
        )


# Backward-compatible alias for legacy tests and imports
PainPointAnalysis = LegacyPainPointAnalysis


# ===== ENHANCED PROMPT DESIGN =====

ENHANCED_SYSTEM_PROMPT = """# PERSONA
You are a Revenue-Operations Diagnostician — an expert at uncovering the REAL business problems behind job postings. With 15 years analyzing hiring patterns, you see what hiring managers won't say directly: the urgent pain points, the strategic gaps, the "why now" behind every role.

# MISSION
Extract actionable pain points that will help a candidate craft a winning application. Your output directly impacts whether someone lands their dream job by addressing REAL problems, not HR boilerplate.

# CHAIN-OF-THOUGHT PROCESS
Before generating your final JSON, think through these steps:

1. **SYMPTOMS vs ROOT CAUSES**
   - What does the JD explicitly state? (symptoms)
   - What business problem does each requirement reveal? (root causes)

2. **WHY NOW?**
   - What triggered this hire? (growth, turnover, new initiative, compliance deadline?)
   - Look for signals: "scaling", "transformation", "new", "expanding"

3. **EVIDENCE GROUNDING**
   - For each insight, identify the JD quote or logical inference
   - Rate confidence: HIGH (explicit quote), MEDIUM (strong inference), LOW (speculation)

4. **METRIC EXTRACTION**
   - Scan JD for any numbers (percentages, team sizes, timeframes)
   - Use these to make success metrics concrete

# OUTPUT FORMAT
You MUST output in this exact structure:

<reasoning>
- Key trigger: [1 sentence on why role is open now]
- Symptoms found: [bullet list of explicit JD requirements]
- Root causes inferred: [bullet list of underlying problems]
- Confidence gaps: [what's missing/assumed]
</reasoning>

<final>
{json_schema}
</final>

# GUARDRAILS
- ONLY cite facts from the provided JD — never invent company details
- Every "evidence" field must quote or reference specific JD language
- Mark inferences with confidence levels honestly
- If evidence is thin, use LOW confidence — don't fabricate

# FORBIDDEN BOILERPLATE
These phrases indicate lazy analysis. NEVER use them:
❌ "Strong communication skills" | "Team player" | "Fast-paced" | "Stakeholder management"

Instead, be SPECIFIC:
✅ "Technical debt in payment system blocking feature releases (evidence: 'migration from legacy')"
✅ "Compliance deadline creating hiring urgency (evidence: 'GDPR implementation by Q2')"

# SELF-EVALUATION
Before outputting, score your analysis 1-10 on SPECIFICITY.
If score < 8, revise to add more concrete evidence and metrics.
Your reputation depends on actionable, evidence-based insights."""

ENHANCED_USER_TEMPLATE = """# JOB ANALYSIS REQUEST

## JOB DETAILS
**Title:** {title}
**Company:** {company}
**Domain:** {domain}

## JOB DESCRIPTION
{job_description}

---

## QUALITY REFERENCE (Study this structure)

**Example JD Snippet:**
{example_jd}

**Example Output (match this quality):**
```json
{example_output}
```

---

## YOUR TASK
Analyze the JOB DESCRIPTION above with the same rigor.

**Output Schema:**
```json
{{
  "pain_points": [
    {{"text": "specific problem statement", "evidence": "JD quote or inference", "confidence": "high|medium|low"}}
  ],
  "strategic_needs": [
    {{"text": "why role matters strategically", "evidence": "...", "confidence": "..."}}
  ],
  "risks_if_unfilled": [
    {{"text": "consequence of not filling", "evidence": "...", "confidence": "..."}}
  ],
  "success_metrics": [
    {{"text": "measurable outcome", "evidence": "...", "confidence": "..."}}
  ],
  "reasoning_summary": "Brief summary of key inferences",
  "why_now": "Inferred reason for hiring urgency"
}}
```

**Remember:**
1. Start with <reasoning> block (structured bullets)
2. End with <final>{{valid JSON}}</final>
3. Every item needs evidence + confidence rating
4. Score yourself on specificity (aim for 8+)
5. Scan for numbers in JD to ground metrics"""


# ===== MINER CLASS =====

class PainPointMiner:
    """
    Enhanced Pain-Point Miner with domain-aware prompting and confidence scoring.

    Improvements over base version:
    - Persona-driven prompting for business-focused extraction
    - Chain-of-thought reasoning for transparency
    - Domain-specific few-shot examples for quality anchoring
    - Confidence scoring for downstream weighting
    - Structured reasoning output for auditability
    """

    def __init__(self, use_enhanced_format: bool = False):
        """
        Initialize the miner.

        Args:
            use_enhanced_format: If True, returns enhanced format with confidence.
                                If False (default), returns legacy format (string lists)
                                for backward compatibility.
        """
        self.llm = ChatOpenAI(
            model=Config.DEFAULT_MODEL,
            temperature=Config.ANALYTICAL_TEMPERATURE,
            api_key=Config.get_llm_api_key(),
            base_url=Config.get_llm_base_url(),
        )
        self.use_enhanced_format = use_enhanced_format

    def _get_domain_example(self, domain: JobDomain) -> tuple[str, str]:
        """Get domain-appropriate few-shot example."""
        example = DOMAIN_EXAMPLES.get(domain, DOMAIN_EXAMPLES[JobDomain.GENERAL])
        return example["jd_snippet"], json.dumps(example["output"], indent=2)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True
    )
    def _call_llm(
        self,
        title: str,
        company: str,
        job_description: str,
        domain: JobDomain
    ) -> str:
        """Call LLM with enhanced prompts."""
        example_jd, example_output = self._get_domain_example(domain)

        messages = [
            SystemMessage(content=ENHANCED_SYSTEM_PROMPT),
            HumanMessage(
                content=ENHANCED_USER_TEMPLATE.format(
                    title=title,
                    company=company,
                    domain=domain.value,
                    job_description=job_description,
                    example_jd=example_jd,
                    example_output=example_output
                )
            )
        ]

        response = self.llm.invoke(messages)
        return response.content

    def _extract_reasoning(self, response: str) -> str:
        """Extract reasoning block from response."""
        match = re.search(r'<reasoning>(.*?)</reasoning>', response, re.DOTALL)
        return match.group(1).strip() if match else ""

    def _parse_response(self, llm_response: str) -> EnhancedPainPointAnalysis:
        """
        Parse LLM response into structured analysis.

        Handles both <final> tagged format and raw JSON.
        """
        # Extract from <final> tags first
        final_match = re.search(r'<final>(.*?)</final>', llm_response, re.DOTALL)
        if final_match:
            json_str = final_match.group(1).strip()
        else:
            # Fallback to finding JSON object
            json_match = re.search(r'\{.*\}', llm_response, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
            else:
                raise ValueError(f"No JSON found in response: {llm_response[:500]}")

        # Clean up common JSON issues
        json_str = json_str.strip()
        if json_str.startswith("```json"):
            json_str = json_str[7:]
        if json_str.startswith("```"):
            json_str = json_str[3:]
        if json_str.endswith("```"):
            json_str = json_str[:-3]

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse JSON: {e}\nResponse: {json_str[:500]}")

        # Handle legacy format (string arrays) and convert to enhanced
        if data.get("pain_points") and isinstance(data["pain_points"][0], str):
            data = self._convert_legacy_to_enhanced(data)

        try:
            return EnhancedPainPointAnalysis(**data)
        except ValidationError as e:
            error_msgs = [f"{' -> '.join(str(x) for x in err['loc'])}: {err['msg']}"
                        for err in e.errors()]
            raise ValueError(
                f"Schema validation failed:\n" +
                "\n".join(f"  - {msg}" for msg in error_msgs)
            )

    def _convert_legacy_to_enhanced(self, data: Dict) -> Dict:
        """Convert string-only format to enhanced format with defaults."""
        def convert_items(items: List[str]) -> List[Dict]:
            return [
                {"text": item, "evidence": "inferred from JD context", "confidence": "medium"}
                for item in items
            ]

        return {
            "pain_points": convert_items(data.get("pain_points", [])),
            "strategic_needs": convert_items(data.get("strategic_needs", [])),
            "risks_if_unfilled": convert_items(data.get("risks_if_unfilled", [])),
            "success_metrics": convert_items(data.get("success_metrics", [])),
            "reasoning_summary": data.get("reasoning_summary"),
            "why_now": data.get("why_now"),
        }

    def _parse_json_response(self, llm_response: str) -> Dict[str, List[str]]:
        """
        Backward-compatible method for parsing LLM responses.

        Returns legacy format (string lists) for compatibility with existing tests.
        """
        # Try to extract from <final> tags first
        final_match = re.search(r'<final>(.*?)</final>', llm_response, re.DOTALL)
        if final_match:
            json_str = final_match.group(1).strip()
        else:
            # Fallback to finding JSON object
            json_match = re.search(r'\{.*\}', llm_response, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
            else:
                raise ValueError(f"Failed to parse JSON response: No JSON found\nResponse: {llm_response[:500]}")

        # Clean up common JSON issues
        json_str = json_str.strip()
        if json_str.startswith("```json"):
            json_str = json_str[7:]
        if json_str.startswith("```"):
            json_str = json_str[3:]
        if json_str.endswith("```"):
            json_str = json_str[:-3]

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse JSON response: {e}\nResponse: {llm_response[:500]}")

        # Handle empty arrays case
        pain_points = data.get("pain_points", [])
        if not pain_points:
            # Validate with legacy schema - this will raise proper validation error
            try:
                validated = LegacyPainPointAnalysis(**data)
                return validated.model_dump()
            except ValidationError as e:
                error_msgs = [f"{' -> '.join(str(x) for x in err['loc'])}: {err['msg']}"
                            for err in e.errors()]
                raise ValueError(
                    f"JSON schema validation failed:\n" +
                    "\n".join(f"  - {msg}" for msg in error_msgs)
                )

        # Check if already in legacy format (string arrays)
        if isinstance(pain_points[0], str):
            # Validate with legacy schema
            try:
                validated = LegacyPainPointAnalysis(**data)
                return validated.model_dump()
            except ValidationError as e:
                error_msgs = [f"{' -> '.join(str(x) for x in err['loc'])}: {err['msg']}"
                            for err in e.errors()]
                raise ValueError(
                    f"JSON schema validation failed:\n" +
                    "\n".join(f"  - {msg}" for msg in error_msgs)
                )

        # Convert enhanced format to legacy
        if isinstance(pain_points[0], dict):
            legacy_data = {
                "pain_points": [item.get("text", str(item)) for item in data["pain_points"]],
                "strategic_needs": [item.get("text", str(item)) for item in data.get("strategic_needs", [])],
                "risks_if_unfilled": [item.get("text", str(item)) for item in data.get("risks_if_unfilled", [])],
                "success_metrics": [item.get("text", str(item)) for item in data.get("success_metrics", [])],
            }
            try:
                validated = LegacyPainPointAnalysis(**legacy_data)
                return validated.model_dump()
            except ValidationError as e:
                error_msgs = [f"{' -> '.join(str(x) for x in err['loc'])}: {err['msg']}"
                            for err in e.errors()]
                raise ValueError(
                    f"JSON schema validation failed:\n" +
                    "\n".join(f"  - {msg}" for msg in error_msgs)
                )

        raise ValueError(f"JSON schema validation failed: unexpected data format")

    def extract_pain_points(self, state: JobState) -> Dict[str, Any]:
        """
        Extract pain points with enhanced analysis.

        Args:
            state: Current JobState with job_description, title, company

        Returns:
            Dict with pain_points, strategic_needs, risks_if_unfilled, success_metrics
            Format depends on use_enhanced_format setting.
        """
        logger = get_logger(__name__, run_id=state.get("run_id"), layer="layer2")

        try:
            # Detect domain for appropriate examples
            domain = detect_domain(state["title"], state["job_description"])
            logger.info(f"Detected job domain: {domain.value}")

            # Call LLM with enhanced prompts
            llm_response = self._call_llm(
                title=state["title"],
                company=state["company"],
                job_description=state["job_description"],
                domain=domain
            )

            # Extract reasoning for logging
            reasoning = self._extract_reasoning(llm_response)
            if reasoning:
                logger.info("Reasoning summary:")
                for line in reasoning.split('\n')[:5]:  # Log first 5 lines
                    logger.info(f"  {line.strip()}")

            # Parse and validate
            analysis = self._parse_response(llm_response)

            # Log confidence distribution
            all_items = (
                analysis.pain_points +
                analysis.strategic_needs +
                analysis.risks_if_unfilled +
                analysis.success_metrics
            )
            confidence_counts = {
                "high": sum(1 for i in all_items if i.confidence == ConfidenceLevel.HIGH),
                "medium": sum(1 for i in all_items if i.confidence == ConfidenceLevel.MEDIUM),
                "low": sum(1 for i in all_items if i.confidence == ConfidenceLevel.LOW),
            }
            logger.info(f"Confidence distribution: {confidence_counts}")

            if analysis.why_now:
                logger.info(f"Why now: {analysis.why_now}")

            # Return in requested format
            if self.use_enhanced_format:
                result = analysis.model_dump()
            else:
                legacy = LegacyPainPointAnalysis.from_enhanced(analysis)
                result = legacy.model_dump()

            # Log summary
            logger.info("Extracted pain-point analysis:")
            logger.info(f"  Pain points: {len(analysis.pain_points)}")
            logger.info(f"  Strategic needs: {len(analysis.strategic_needs)}")
            logger.info(f"  Risks if unfilled: {len(analysis.risks_if_unfilled)}")
            logger.info(f"  Success metrics: {len(analysis.success_metrics)}")

            return result

        except Exception as e:
            error_msg = f"Layer 2 (Pain-Point Miner) failed: {str(e)}"
            logger.error(error_msg)

            # Return empty structure (don't block pipeline)
            if self.use_enhanced_format:
                return {
                    "pain_points": [],
                    "strategic_needs": [],
                    "risks_if_unfilled": [],
                    "success_metrics": [],
                    "reasoning_summary": None,
                    "why_now": None,
                    "errors": state.get("errors", []) + [error_msg]
                }
            else:
                return {
                    "pain_points": [],
                    "strategic_needs": [],
                    "risks_if_unfilled": [],
                    "success_metrics": [],
                    "errors": state.get("errors", []) + [error_msg]
                }


# ===== LANGGRAPH NODE FUNCTION =====

def pain_point_miner_node(state: JobState) -> Dict[str, Any]:
    """
    LangGraph node function for Layer 2: Pain-Point Miner (Enhanced).

    This is the function that will be called by the LangGraph workflow.

    Args:
        state: Current job processing state

    Returns:
        Dictionary with updates to merge into state
    """
    logger = get_logger(__name__, run_id=state.get("run_id"), layer="layer2")
    struct_logger = get_structured_logger(state.get("job_id", ""))

    logger.info("=" * 60)
    logger.info("LAYER 2: Pain-Point Miner (Enhanced Edition)")
    logger.info("=" * 60)
    logger.info(f"Job: {state['title']} at {state['company']}")
    logger.info(f"Description length: {len(state['job_description'])} chars")

    with LayerContext(struct_logger, 2, "pain_point_miner") as ctx:
        # Use legacy format for backward compatibility with downstream layers
        miner = PainPointMiner(use_enhanced_format=False)
        updates = miner.extract_pain_points(state)

        # Add metadata for structured logging
        pain_points = updates.get("pain_points", [])
        ctx.add_metadata("pain_points_count", len(pain_points))
        ctx.add_metadata("strategic_needs_count", len(updates.get("strategic_needs", [])))

        # Log results
        if pain_points:
            logger.info("Extracted Pain Points:")
            for i, point in enumerate(pain_points, 1):
                if isinstance(point, dict):
                    logger.info(f"  {i}. [{point.get('confidence', '?')}] {point.get('text', point)}")
                else:
                    logger.info(f"  {i}. {point}")

            logger.info("Extracted Strategic Needs:")
            for i, need in enumerate(updates.get("strategic_needs", []), 1):
                if isinstance(need, dict):
                    logger.info(f"  {i}. {need.get('text', need)}")
                else:
                    logger.info(f"  {i}. {need}")
        else:
            logger.warning("No pain-point analysis extracted")

    logger.info("=" * 60)

    return updates
