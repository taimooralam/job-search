"""
Rule-based AI Job Scorer — Python port of n8n/rule_scoring_ai.js

Level-1 rule scoring for AI/GenAI/LLM engineering and architecture roles.
Keyword taxonomy sourced from:
  - reports/ai_architect_skills_analysis.md (150 LinkedIn JDs)
  - reports/architect-skills-analysis.json (2,702 jobs, 528 AI/ML focused)
  - src/common/ai_classifier.py (11-category regex classifier)

Supported Roles:
  1. AI Engineer (Senior/Lead/Staff/Principal)
  2. AI Architect / AI Solutions Architect
  3. GenAI Engineer / Generative AI Engineer
  4. LLM Engineer / LLM Architect
  5. Agentic AI Engineer / AI Agent Architect
  6. Head of AI / Director of AI / VP of AI
  7. Applied AI Engineer
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

# =============================================================================
# CONFIGURATION
# =============================================================================

TARGET_ROLE_FILTER = [
    "ai_engineer",
    "ai_architect",
    "genai_engineer",
    "llm_engineer",
    "agentic_ai_engineer",
    "ai_leadership",
    "applied_ai_engineer",
]

PROMOTION_THRESHOLD = 60

# =============================================================================
# ROLE DEFINITIONS
# =============================================================================

ROLE_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    "ai_engineer": {
        "displayName": "AI Engineer",
        "titleWeight": 40,
        "exactTitles": [
            "ai engineer", "artificial intelligence engineer",
            "senior ai engineer", "lead ai engineer", "staff ai engineer",
            "principal ai engineer", "ai software engineer", "ai developer",
            "senior artificial intelligence engineer",
        ],
        "partialTitles": ["ai engineer", "artificial intelligence engineer"],
        "excludeIfContains": [
            "sales", "pre-sales", "presales", "marketing",
            "recruiter", "data analyst", "business analyst",
        ],
    },
    "ai_architect": {
        "displayName": "AI Architect",
        "titleWeight": 45,
        "exactTitles": [
            "ai architect", "ai solutions architect", "ai solution architect",
            "artificial intelligence architect", "senior ai architect",
            "lead ai architect", "principal ai architect", "chief ai architect",
            "genai architect", "generative ai architect", "llm architect",
            "ai platform architect", "ai infrastructure architect",
            "ai cloud architect",
        ],
        "partialTitles": [
            "ai architect", "ai solutions architect",
            "genai architect", "llm architect",
        ],
        "excludeIfContains": ["sales", "pre-sales", "presales"],
    },
    "genai_engineer": {
        "displayName": "GenAI Engineer",
        "titleWeight": 45,
        "exactTitles": [
            "genai engineer", "generative ai engineer", "gen ai engineer",
            "senior genai engineer", "lead genai engineer",
            "staff genai engineer", "senior generative ai engineer",
            "lead generative ai engineer",
        ],
        "partialTitles": [
            "genai engineer", "generative ai engineer", "gen ai engineer",
        ],
        "excludeIfContains": ["sales", "pre-sales", "presales", "marketing"],
    },
    "llm_engineer": {
        "displayName": "LLM Engineer",
        "titleWeight": 45,
        "exactTitles": [
            "llm engineer", "llm developer", "large language model engineer",
            "senior llm engineer", "lead llm engineer", "staff llm engineer",
            "llm infrastructure engineer",
        ],
        "partialTitles": ["llm engineer", "llm developer", "large language model"],
        "excludeIfContains": ["sales", "pre-sales", "presales"],
    },
    "agentic_ai_engineer": {
        "displayName": "Agentic AI Engineer",
        "titleWeight": 45,
        "exactTitles": [
            "agentic ai engineer", "ai agent engineer", "ai agent architect",
            "ai agent developer", "agentic engineer", "multi-agent engineer",
        ],
        "partialTitles": ["agentic ai", "ai agent", "multi-agent"],
        "excludeIfContains": ["sales", "pre-sales", "presales", "customer"],
    },
    "applied_ai_engineer": {
        "displayName": "Applied AI Engineer",
        "titleWeight": 40,
        "exactTitles": [
            "applied ai engineer", "applied ai scientist",
            "applied ai researcher", "rag engineer",
            "deep learning engineer", "ai application engineer",
        ],
        "partialTitles": ["applied ai", "rag engineer", "deep learning engineer"],
        "excludeIfContains": ["sales", "pre-sales", "presales"],
    },
    "ai_leadership": {
        "displayName": "Head of AI",
        "titleWeight": 50,
        "exactTitles": [
            "head of ai", "head of artificial intelligence",
            "head of genai", "head of generative ai",
            "director of ai", "director of artificial intelligence",
            "director of genai", "director ai",
            "vp of ai", "vp ai", "vice president of ai", "vice president ai",
            "ai engineering lead", "ai engineering manager",
            "ai team lead", "chief ai officer", "caio",
        ],
        "partialTitles": [
            "head of ai", "director of ai", "vp of ai", "vp ai", "chief ai",
        ],
        "excludeIfContains": [],
    },
}

# =============================================================================
# UNWANTED TITLE KEYWORDS
# =============================================================================

UNWANTED_TITLE_KEYWORDS = [
    "sales", "business development", "accounting", "clinical",
    "marketing", "hr", "human resources", "recruiter", "recruiting",
    "customer success", "customer support", "support engineer",
    "pre-sales", "presales", "field engineer", "implementation",
    "data analyst", "business analyst", "project manager", "program manager",
    "scrum master", "product owner", "qa engineer", "test engineer", "sdet",
    "network engineer", "systems administrator",
    "frontend engineer", "frontend developer", "ui engineer", "ux engineer",
    "ios developer", "android developer", "mobile developer",
    "data scientist", "senior data scientist", "lead data scientist",
    "ml engineer", "machine learning engineer", "senior ml engineer",
    "lead ml engineer", "staff ml engineer",
]

# =============================================================================
# SENIORITY LEVELS
# =============================================================================

SENIORITY_LEVELS = {
    "executive": {"keywords": ["executive", "c-level", "c-suite", "chief", "caio"], "score": 15},
    "director": {"keywords": ["director", "vp", "vice president", "head of", "head"], "score": 12},
    "senior_ic": {"keywords": ["staff", "principal", "distinguished", "fellow"], "score": 10},
    "lead": {"keywords": ["lead", "tech lead", "team lead", "lead software engineer"], "score": 10},
    "senior": {"keywords": ["senior", "sr.", "sr "], "score": 6},
    "mid": {"keywords": ["mid", "intermediate"], "score": 0},
    "junior": {"keywords": ["junior", "jr.", "jr ", "entry", "associate", "intern", "trainee", "graduate"], "score": -25},
}

# =============================================================================
# KEYWORD CATEGORIES
# =============================================================================

GENAI_LLM_KEYWORDS = [
    "generative ai", "genai", "gen ai", "llm", "large language model",
    "gpt", "chatgpt", "claude", "gemini", "openai", "anthropic",
    "transformer", "foundation model", "llm integration", "llm systems",
    "llm applications", "llm ecosystem", "llm proxy", "vllm",
    "text generation", "language model", "multimodal",
]

AGENTIC_AI_KEYWORDS = [
    "agentic", "agentic ai", "ai agent", "ai agents", "agent framework",
    "agentic framework", "agentic workflow", "agentic workflow orchestration",
    "multi-agent", "multi agent", "tool calling", "function calling",
    "langchain", "langgraph", "crewai", "autogen", "semantic kernel",
    "agent orchestration", "autonomous agent",
]

RAG_RETRIEVAL_KEYWORDS = [
    "rag", "retrieval augmented generation", "retrieval-augmented generation",
    "rag pipeline", "rag pipelines", "rag systems",
    "vector database", "vector databases", "vector store", "vector search",
    "embedding", "embeddings", "semantic search",
    "pinecone", "weaviate", "qdrant", "chroma", "chromadb", "faiss",
    "milvus", "pgvector", "opensearch",
    "knowledge graph", "knowledge base", "document retrieval",
]

EVAL_QUALITY_KEYWORDS = [
    "llm evaluation", "llm eval", "eval harness", "evals stack",
    "evaluation systems", "model evaluation", "benchmark",
    "golden dataset", "ground truth", "hallucination detection",
    "guardrails", "content filtering", "safety testing",
    "red teaming", "prompt injection", "adversarial testing",
    "langfuse", "langsmith", "weights & biases", "weights and biases", "wandb",
    "mlflow", "arize", "trulens",
]

FINE_TUNING_KEYWORDS = [
    "fine-tuning", "fine tuning", "finetuning", "model fine-tuning",
    "lora", "qlora", "rlhf", "peft", "sft", "supervised fine-tuning",
    "instruction tuning", "domain adaptation", "transfer learning",
    "llm training", "llm finetuning", "model training",
    "distillation", "quantization", "model optimization",
]

AI_GOVERNANCE_KEYWORDS = [
    "ai governance", "responsible ai", "ai ethics", "ai safety",
    "ai compliance", "ai risk", "model card", "ai policy",
    "eu ai act", "nist ai", "iso 42001",
    "bias detection", "fairness", "transparency", "explainability",
    "model context protocol", "mcp",
]

PROMPT_ENGINEERING_KEYWORDS = [
    "prompt engineering", "prompt design", "prompt optimization",
    "prompt template", "few-shot", "zero-shot", "chain of thought",
    "in-context learning", "prompt chaining",
]

AI_INFRA_KEYWORDS = [
    "sagemaker", "bedrock", "vertex ai", "azure openai", "azure ai",
    "mlops", "llmops", "model serving", "model deployment",
    "model monitoring", "model registry", "ml pipeline", "model pipeline",
    "inference", "streaming inference", "distributed inference",
    "ml inference optimization", "gpu", "cuda", "tpu",
    "pytorch", "tensorflow", "hugging face", "huggingface",
    "deep learning", "deep learning systems", "neural network",
]

CLOUD_INFRA_KEYWORDS = [
    "aws", "gcp", "azure", "cloud", "cloud native", "cloud-native",
    "kubernetes", "k8s", "docker", "terraform",
    "serverless", "lambda", "ecs", "eks",
    "kafka", "data pipelines",
    "ci/cd", "cicd", "devops", "gitops",
]

ARCHITECTURE_KEYWORDS = [
    "architecture", "system design", "systems design", "platform",
    "microservices", "event-driven", "event driven",
    "distributed systems", "api design", "api", "rest api", "graphql",
    "scalability", "high availability", "fault tolerance",
]

LANGUAGES_KEYWORDS = [
    "python", "typescript", "javascript", "node.js", "nodejs",
    "java", "go", "golang", "rust", "c++", "scala",
    "fastapi", "flask", "django",
    "react", "next.js", "nextjs",
    "postgresql", "postgres", "mongodb", "redis", "sql", "nosql",
]

DATA_KNOWLEDGE_KEYWORDS = [
    "data science", "data engineering", "data platform",
    "feature store", "data lake", "data mesh", "data pipeline",
    "etl", "elt", "data warehouse", "analytics",
    "nlp", "natural language processing", "computer vision",
    "text mining", "text classification", "named entity recognition",
]

AI_LEADERSHIP_KEYWORDS = [
    "ai strategy", "ai roadmap", "ai transformation",
    "technology strategy", "technical strategy", "digital transformation",
    "vision", "strategic", "roadmap", "innovation",
    "leadership", "cross-functional", "stakeholder", "executive",
    "build team", "grow team", "mentor", "coaching",
    "engineering excellence", "best practices",
]

ACHIEVEMENT_KEYWORDS = [
    "scaled", "grew", "built", "transformed", "modernized", "migrated", "led",
    "delivered", "shipped", "launched", "deployed", "implemented",
    "reduced", "improved", "increased", "saved", "achieved", "drove",
    "production", "revenue", "cost reduction", "efficiency",
    "latency", "throughput", "accuracy", "precision", "recall",
]

# =============================================================================
# LOCATION & LANGUAGE PREFERENCES
# =============================================================================

REMOTE_POSITIVE = [
    "remote", "remote-first", "distributed", "work from anywhere", "wfh",
    "hybrid", "flexible location", "global", "work from home", "worldwide",
    "remote anywhere", "anywhere in the world", "location flexible",
]

REMOTE_NEGATIVE = [
    "onsite only", "on-site only", "office only", "no remote",
    "must relocate", "relocation required", "in-office",
]

LANGUAGE_NEGATIVE = [
    "fluent arabic", "arabic speaker", "native arabic",
    "fluent spanish", "spanish speaker", "native spanish",
    "fluent french", "french speaker", "native french",
    "fluent german", "german speaker", "native german",
    "fluent mandarin", "mandarin speaker", "native mandarin",
    "fluent japanese", "japanese speaker", "native japanese",
    "fluent korean", "korean speaker", "native korean",
]

# =============================================================================
# ROLE-SPECIFIC WEIGHT CONFIGURATIONS
# =============================================================================

_W = Dict[str, Dict[str, float]]

ROLE_WEIGHTS: Dict[str, _W] = {
    "ai_engineer": {
        "genaiLlm":      {"weight": 3,   "max": 30},
        "agenticAi":     {"weight": 2.5, "max": 25},
        "ragRetrieval":  {"weight": 2.5, "max": 25},
        "evalQuality":   {"weight": 2,   "max": 20},
        "fineTuning":    {"weight": 1.5, "max": 15},
        "aiGovernance":  {"weight": 1,   "max": 10},
        "promptEng":     {"weight": 1.5, "max": 10},
        "aiInfra":       {"weight": 2,   "max": 20},
        "cloudInfra":    {"weight": 1.5, "max": 15},
        "architecture":  {"weight": 1.5, "max": 15},
        "languages":     {"weight": 2,   "max": 20},
        "dataKnowledge": {"weight": 1,   "max": 10},
        "aiLeadership":  {"weight": 1,   "max": 10},
        "achievement":   {"weight": 1,   "max": 10},
    },
    "ai_architect": {
        "genaiLlm":      {"weight": 3,   "max": 30},
        "agenticAi":     {"weight": 2.5, "max": 25},
        "ragRetrieval":  {"weight": 2.5, "max": 25},
        "evalQuality":   {"weight": 2,   "max": 20},
        "fineTuning":    {"weight": 1.5, "max": 15},
        "aiGovernance":  {"weight": 2,   "max": 20},
        "promptEng":     {"weight": 1,   "max": 10},
        "aiInfra":       {"weight": 2.5, "max": 25},
        "cloudInfra":    {"weight": 2,   "max": 20},
        "architecture":  {"weight": 3,   "max": 30},
        "languages":     {"weight": 1.5, "max": 15},
        "dataKnowledge": {"weight": 1.5, "max": 15},
        "aiLeadership":  {"weight": 2,   "max": 20},
        "achievement":   {"weight": 1.5, "max": 15},
    },
    "genai_engineer": {
        "genaiLlm":      {"weight": 3.5, "max": 35},
        "agenticAi":     {"weight": 2.5, "max": 25},
        "ragRetrieval":  {"weight": 2.5, "max": 25},
        "evalQuality":   {"weight": 2,   "max": 20},
        "fineTuning":    {"weight": 2,   "max": 20},
        "aiGovernance":  {"weight": 1,   "max": 10},
        "promptEng":     {"weight": 2,   "max": 15},
        "aiInfra":       {"weight": 2,   "max": 20},
        "cloudInfra":    {"weight": 1.5, "max": 15},
        "architecture":  {"weight": 1.5, "max": 15},
        "languages":     {"weight": 2,   "max": 20},
        "dataKnowledge": {"weight": 1,   "max": 10},
        "aiLeadership":  {"weight": 1,   "max": 10},
        "achievement":   {"weight": 1,   "max": 10},
    },
    "llm_engineer": {
        "genaiLlm":      {"weight": 3.5, "max": 35},
        "agenticAi":     {"weight": 2,   "max": 20},
        "ragRetrieval":  {"weight": 2.5, "max": 25},
        "evalQuality":   {"weight": 2.5, "max": 25},
        "fineTuning":    {"weight": 2.5, "max": 25},
        "aiGovernance":  {"weight": 1,   "max": 10},
        "promptEng":     {"weight": 2,   "max": 15},
        "aiInfra":       {"weight": 2.5, "max": 25},
        "cloudInfra":    {"weight": 1.5, "max": 15},
        "architecture":  {"weight": 1.5, "max": 15},
        "languages":     {"weight": 2,   "max": 20},
        "dataKnowledge": {"weight": 1,   "max": 10},
        "aiLeadership":  {"weight": 0.5, "max": 5},
        "achievement":   {"weight": 1,   "max": 10},
    },
    "agentic_ai_engineer": {
        "genaiLlm":      {"weight": 2.5, "max": 25},
        "agenticAi":     {"weight": 3.5, "max": 35},
        "ragRetrieval":  {"weight": 2.5, "max": 25},
        "evalQuality":   {"weight": 2,   "max": 20},
        "fineTuning":    {"weight": 1,   "max": 10},
        "aiGovernance":  {"weight": 1.5, "max": 15},
        "promptEng":     {"weight": 2,   "max": 15},
        "aiInfra":       {"weight": 2,   "max": 20},
        "cloudInfra":    {"weight": 1.5, "max": 15},
        "architecture":  {"weight": 2,   "max": 20},
        "languages":     {"weight": 2,   "max": 20},
        "dataKnowledge": {"weight": 1,   "max": 10},
        "aiLeadership":  {"weight": 1,   "max": 10},
        "achievement":   {"weight": 1,   "max": 10},
    },
    "applied_ai_engineer": {
        "genaiLlm":      {"weight": 2.5, "max": 25},
        "agenticAi":     {"weight": 2,   "max": 20},
        "ragRetrieval":  {"weight": 3,   "max": 30},
        "evalQuality":   {"weight": 2,   "max": 20},
        "fineTuning":    {"weight": 2,   "max": 20},
        "aiGovernance":  {"weight": 1,   "max": 10},
        "promptEng":     {"weight": 1.5, "max": 15},
        "aiInfra":       {"weight": 2,   "max": 20},
        "cloudInfra":    {"weight": 1.5, "max": 15},
        "architecture":  {"weight": 1.5, "max": 15},
        "languages":     {"weight": 2.5, "max": 25},
        "dataKnowledge": {"weight": 2,   "max": 20},
        "aiLeadership":  {"weight": 0.5, "max": 5},
        "achievement":   {"weight": 1,   "max": 10},
    },
    "ai_leadership": {
        "genaiLlm":      {"weight": 2,   "max": 20},
        "agenticAi":     {"weight": 2,   "max": 20},
        "ragRetrieval":  {"weight": 1.5, "max": 15},
        "evalQuality":   {"weight": 1.5, "max": 15},
        "fineTuning":    {"weight": 1,   "max": 10},
        "aiGovernance":  {"weight": 2.5, "max": 25},
        "promptEng":     {"weight": 0.5, "max": 5},
        "aiInfra":       {"weight": 1.5, "max": 15},
        "cloudInfra":    {"weight": 1,   "max": 10},
        "architecture":  {"weight": 1.5, "max": 15},
        "languages":     {"weight": 0.5, "max": 5},
        "dataKnowledge": {"weight": 1,   "max": 10},
        "aiLeadership":  {"weight": 3,   "max": 30},
        "achievement":   {"weight": 2.5, "max": 25},
    },
}

DEFAULT_WEIGHTS: _W = {
    "genaiLlm":      {"weight": 2.5, "max": 25},
    "agenticAi":     {"weight": 2,   "max": 20},
    "ragRetrieval":  {"weight": 2,   "max": 20},
    "evalQuality":   {"weight": 1.5, "max": 15},
    "fineTuning":    {"weight": 1.5, "max": 15},
    "aiGovernance":  {"weight": 1,   "max": 10},
    "promptEng":     {"weight": 1,   "max": 10},
    "aiInfra":       {"weight": 1.5, "max": 15},
    "cloudInfra":    {"weight": 1.5, "max": 15},
    "architecture":  {"weight": 1.5, "max": 15},
    "languages":     {"weight": 1.5, "max": 15},
    "dataKnowledge": {"weight": 1,   "max": 10},
    "aiLeadership":  {"weight": 1.5, "max": 15},
    "achievement":   {"weight": 1,   "max": 10},
}

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def _contains_any(text: str, keywords: List[str]) -> bool:
    t = (text or "").lower()
    return any(k.lower() in t for k in keywords)


def _count_keywords(text: str, keywords: List[str]) -> int:
    t = (text or "").lower()
    return sum(1 for k in keywords if k.lower() in t)


def _count_keywords_weighted(
    text: str, keywords: List[str], weight_per_match: float = 1, max_score: float = float("inf")
) -> float:
    count = _count_keywords(text, keywords)
    return min(count * weight_per_match, max_score)


# =============================================================================
# ROLE DETECTION
# =============================================================================


def detect_role(title: str) -> Optional[str]:
    """Detect AI role from job title. Returns role key or None."""
    t = (title or "").lower().strip()

    role_order = [
        "ai_leadership",
        "agentic_ai_engineer",
        "llm_engineer",
        "genai_engineer",
        "ai_architect",
        "applied_ai_engineer",
        "ai_engineer",
    ]

    def _has_excluded_word(text: str, excludes: List[str]) -> bool:
        """Check excludes using word boundaries to avoid false hits
        like 'sales' matching inside 'salesforce'."""
        return any(re.search(rf"\b{re.escape(ex.lower())}\b", text) for ex in excludes)

    # Check exact titles first
    for role_key in role_order:
        role = ROLE_DEFINITIONS[role_key]
        for exact_title in role["exactTitles"]:
            if t == exact_title or exact_title in t:
                excludes = role.get("excludeIfContains", [])
                if excludes and _has_excluded_word(t, excludes):
                    continue
                return role_key

    # Fallback: partial titles
    for role_key in role_order:
        role = ROLE_DEFINITIONS[role_key]
        for partial in role["partialTitles"]:
            if partial.lower() in t:
                excludes = role.get("excludeIfContains", [])
                if excludes and _has_excluded_word(t, excludes):
                    continue
                return role_key

    return None


def _get_title_score(title: str, detected_role: Optional[str]) -> int:
    if not detected_role:
        return 0

    t = (title or "").lower().strip()
    role = ROLE_DEFINITIONS[detected_role]

    for exact_title in role["exactTitles"]:
        if t == exact_title:
            return role["titleWeight"]

    for exact_title in role["exactTitles"]:
        if exact_title in t:
            return round(role["titleWeight"] * 0.9)

    for partial in role["partialTitles"]:
        if partial.lower() in t:
            return round(role["titleWeight"] * 0.8)

    return round(role["titleWeight"] * 0.5)


def _get_seniority_score(text: str) -> Dict[str, Any]:
    t = (text or "").lower()
    for level, config in SENIORITY_LEVELS.items():
        for kw in config["keywords"]:
            if kw.lower() in t:
                return {"level": level, "score": config["score"]}
    return {"level": "unknown", "score": 0}


def _count_unwanted_title_keywords(title: str) -> int:
    t = (title or "").lower()
    return sum(1 for kw in UNWANTED_TITLE_KEYWORDS if kw.lower() in t)


# =============================================================================
# MAIN SCORING FUNCTION
# =============================================================================


def compute_rule_score(job: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compute rule-based score for an AI job posting.

    Args:
        job: Dict with keys: title, job_criteria (or job_description), job_description, location

    Returns:
        Dict with: score (0-100), detectedRole, isTargetRole, hasStrongAiSignal,
                   seniorityLevel, breakdown, tier
    """
    title = job.get("title", "")
    job_criteria = job.get("job_criteria", "")
    job_description = job.get("job_description", "") or job.get("description", "")
    location = job.get("location", "")

    title_lower = title.lower()
    crit_lower = job_criteria.lower()
    desc_lower = job_description.lower()
    loc_lower = location.lower()

    full_text = f"{title_lower} {crit_lower} {desc_lower}"
    loc_and_desc = f"{loc_lower} {desc_lower}"

    # --- DETECT ROLE ---
    detected_role = detect_role(title)

    is_target_role = (
        len(TARGET_ROLE_FILTER) == 0
        or (detected_role is not None and detected_role in TARGET_ROLE_FILTER)
    )

    has_strong_ai_signal = not detected_role and (
        _count_keywords(full_text, GENAI_LLM_KEYWORDS) >= 3
        or _count_keywords(full_text, AGENTIC_AI_KEYWORDS) >= 2
        or _count_keywords(full_text, RAG_RETRIEVAL_KEYWORDS) >= 2
    )

    if not is_target_role and not has_strong_ai_signal:
        return {
            "score": 0,
            "detectedRole": detected_role,
            "isTargetRole": False,
            "hasStrongAiSignal": False,
            "breakdown": {},
            "tier": "D",
        }

    weights = ROLE_WEIGHTS.get(detected_role, DEFAULT_WEIGHTS) if detected_role else DEFAULT_WEIGHTS

    # --- 1) TITLE SCORE (0-50) ---
    title_score = _get_title_score(title, detected_role)
    # Only penalize unwanted keywords when no target role was detected.
    # If detect_role() already matched (e.g. "AI Engineer"), substring
    # hits like "sales" in "salesforce" shouldn't reduce the score.
    if detected_role:
        unwanted_count = 0
        unwanted_penalty = 0
    else:
        unwanted_count = _count_unwanted_title_keywords(title)
        unwanted_penalty = min(unwanted_count * 30, 50)

    # --- 2) SENIORITY SCORE (-25 to +15) ---
    seniority_result = _get_seniority_score(f"{title_lower} {crit_lower}")
    seniority_score = seniority_result["score"]

    # --- 3) AI KEYWORD SCORES ---
    kw_scores = {}
    kw_lists = {
        "genaiLlm": GENAI_LLM_KEYWORDS,
        "agenticAi": AGENTIC_AI_KEYWORDS,
        "ragRetrieval": RAG_RETRIEVAL_KEYWORDS,
        "evalQuality": EVAL_QUALITY_KEYWORDS,
        "fineTuning": FINE_TUNING_KEYWORDS,
        "aiGovernance": AI_GOVERNANCE_KEYWORDS,
        "promptEng": PROMPT_ENGINEERING_KEYWORDS,
        "aiInfra": AI_INFRA_KEYWORDS,
        "cloudInfra": CLOUD_INFRA_KEYWORDS,
        "architecture": ARCHITECTURE_KEYWORDS,
        "languages": LANGUAGES_KEYWORDS,
        "dataKnowledge": DATA_KNOWLEDGE_KEYWORDS,
        "aiLeadership": AI_LEADERSHIP_KEYWORDS,
        "achievement": ACHIEVEMENT_KEYWORDS,
    }

    for key, kw_list in kw_lists.items():
        w = weights[key]
        kw_scores[key] = _count_keywords_weighted(full_text, kw_list, w["weight"], w["max"])

    # --- 4) REMOTE PREFERENCE (-10 to +15) ---
    remote_score = 0
    if _contains_any(loc_and_desc, REMOTE_POSITIVE):
        remote_score += 10
    # Extra boost for strong "anywhere" signals in title or description
    anywhere_keywords = ["remote anywhere", "work from anywhere", "anywhere in the world"]
    if _contains_any(f"{title_lower} {desc_lower}", anywhere_keywords):
        remote_score += 5
    if _contains_any(loc_and_desc, REMOTE_NEGATIVE):
        remote_score -= 10

    # --- 5) LANGUAGE REQUIREMENTS (-10 to 0) ---
    language_score = 0
    if _contains_any(desc_lower, LANGUAGE_NEGATIVE):
        language_score -= 10
    chars = list(job_description or "")
    non_ascii = sum(1 for ch in chars if ord(ch) > 127)
    total_chars = len(chars) or 1
    if non_ascii / total_chars > 0.3:
        language_score -= 10

    # --- CALCULATE TOTAL ---
    keyword_total = sum(kw_scores.values())

    raw_score = title_score + seniority_score + keyword_total + remote_score + language_score - unwanted_penalty

    max_keyword_score = sum(w["max"] for w in weights.values())
    max_possible = 50 + 15 + max_keyword_score + 10

    normalized_score = max(0, min(100, round((raw_score / max_possible) * 100)))

    # --- TIER ---
    if normalized_score >= 70:
        tier = "A"
    elif normalized_score >= 50:
        tier = "B"
    elif normalized_score >= 30:
        tier = "C"
    else:
        tier = "D"

    breakdown = {
        "title": title_score,
        "seniority": seniority_score,
        "remote": remote_score,
        "language": language_score,
        "unwantedPenalty": -unwanted_penalty,
    }
    for key, val in kw_scores.items():
        breakdown[key] = round(val)

    return {
        "score": normalized_score,
        "detectedRole": detected_role,
        "isTargetRole": is_target_role or has_strong_ai_signal,
        "hasStrongAiSignal": has_strong_ai_signal,
        "seniorityLevel": seniority_result["level"],
        "breakdown": breakdown,
        "tier": tier,
    }


def should_promote_to_level2(score_result: Dict[str, Any]) -> bool:
    if not score_result.get("isTargetRole"):
        return False
    return score_result["score"] >= PROMOTION_THRESHOLD
