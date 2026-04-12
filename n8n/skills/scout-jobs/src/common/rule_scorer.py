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

PROMOTION_THRESHOLD = 40

# Fixed normalization cap — realistic achievable max for a strong-match job.
# Prevents the dynamic max_possible (~382) from crushing all scores into D tier.
NORMALIZATION_CAP = 200

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
            "forward deployed ai engineer", "forward-deployed ai engineer",
            "senior forward deployed ai engineer", "field ai engineer",
            "senior field ai engineer",
            "tech lead ai engineer", "technical lead ai engineer",
            "founding ai engineer", "founding engineer ai",
            "staff software engineer ai", "principal software engineer ai",
        ],
        "partialTitles": ["ai engineer", "artificial intelligence engineer",
                          "forward deployed ai", "forward-deployed ai"],
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
            "principal agentic engineer", "staff agentic engineer",
            "lead agentic engineer", "senior agentic engineer",
            "agentic ai architect", "principal agentic ai engineer",
        ],
        "partialTitles": ["agentic ai", "ai agent", "multi-agent", "agentic engineer"],
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
            "head of machine learning", "head of ml",
            "director of ai", "director of artificial intelligence",
            "director of genai", "director ai", "director ai engineering",
            "ai director", "director of machine learning",
            "vp of ai", "vp ai", "vice president of ai", "vice president ai",
            "vp engineering ai", "vp of artificial intelligence",
            "ai engineering lead", "ai engineering manager",
            "senior ai engineering manager", "ai team lead",
            "chief ai officer", "caio",
            # Manager / Delivery Lead variants
            "ai engineering manager", "ai delivery lead", "ai engineering delivery lead",
            "engineering manager ai", "engineering manager genai",
            "engineering manager llm", "ai product engineering manager",
            "director of research and applied ai", "director research applied ai",
            "director research & applied ai",
            # Head of variants
            "head of enterprise ai", "head of enterprise llm",
            "head of llm platform", "head of ai platform",
            "head of applied ai", "head of ai engineering",
            "head of agentic ai",
        ],
        "partialTitles": [
            "head of ai", "head of genai", "head of machine learning",
            "director of ai", "director ai", "ai director",
            "vp of ai", "vp ai", "chief ai",
            "head of enterprise ai", "head of llm", "head of applied ai",
            "head of ai engineering", "head of agentic",
            "ai engineering manager", "engineering manager ai",
        ],
        "excludeIfContains": [
            "sales", "pre-sales", "presales", "marketing", "customer success",
        ],
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
    "ml researcher", "research scientist",
    "computer vision", "robotics", "firmware",
    "devops engineer",
]

# Hard negatives: always penalize these in title, even if a target role was detected.
# Prevents "AI Sales Engineer" or "Java AI Developer" from scoring well.
TITLE_HARD_NEGATIVES = [
    "java", "sales", "account", "account manager", "account executive",
    "data scientist", "ml researcher", "machine learning research",
    "computer vision engineer", "robotics engineer",
    "android engineer", "ios engineer",
    "firmware engineer", "network engineer",
]

# JD body negative signals — scanned in description only (not title).
JD_NEGATIVE_SIGNALS = {
    "hard": {
        "keywords": [
            "pytorch", "tensorflow", "keras", "jax", "mxnet",
            "cuda", "gpu programming", "model training at scale",
            "rlhf", "reinforcement learning from human feedback",
            "fine-tuning pipeline", "model fine-tuning",
            "kaggle", "competition", "research paper",
            "phd required", "phd preferred",
            "android development", "ios development", "kotlin", "swift",
            "mobile genai", "on-device ai", "on-device ml",
            "manufacturing domain", "manufacturing experience required",
            "time-series forecasting", "predictive maintenance",
            "computer vision required", "opencv required",
            "matlab required",
        ],
        "penalty_per_match": 8,
        "max_penalty": 35,
    },
    "soft": {
        "keywords": [
            "azure required", "azure experience required", "azure as primary",
            "gcp required", "gcp experience required", "google cloud required",
            "databricks required", "databricks experience",
            "snowflake required", "snowflake experience",
            "spark required", "apache spark",
            "scikit-learn", "sklearn",
            "data scientist", "data science team",
            "feature engineering", "feature store",
            "model registry", "model serving infrastructure",
            "mlflow required",
        ],
        "penalty_per_match": 4,
        "max_penalty": 20,
    },
}

LACKING_TECH = [
    "pytorch", "tensorflow", "keras", "cuda", "scikit-learn",
    "azure", "gcp", "databricks", "snowflake", "spark",
    "android", "ios", "kotlin", "swift", "flutter",
    "computer vision", "opencv",
]

# =============================================================================
# SENIORITY LEVELS
# =============================================================================

SENIORITY_LEVELS = {
    "executive": {"keywords": ["executive", "c-level", "c-suite", "chief", "caio"], "score": 35},
    "director": {"keywords": ["director", "vp", "vice president", "head of", "head"], "score": 30},
    "senior_ic": {"keywords": ["staff", "principal", "distinguished", "fellow"], "score": 28},
    "lead": {"keywords": ["lead", "tech lead", "team lead", "lead software engineer"], "score": 25},
    "senior": {"keywords": ["senior", "sr.", "sr "], "score": 15},
    "mid": {"keywords": ["mid", "intermediate"], "score": 0},
    "junior": {"keywords": ["junior", "jr.", "jr ", "entry", "associate", "intern", "trainee", "graduate"], "score": -25},
}

# Bonus awarded when title contains BOTH a senior leadership signal AND an AI/tech signal.
# Examples: "Lead AI Engineer" (+20), "Head of AI Platform" (+20), "Staff LLM Engineer" (+20).
# This compensates for the normalization penalty when keyword counts are low
# (i.e. JDs that are heavy on leadership language and lighter on tech keyword density).
SENIOR_AI_TITLE_COMBO_BONUS = 20

# Senior title signals that qualify for the combo bonus
SENIOR_TITLE_SIGNALS = [
    "lead", "tech lead", "technical lead", "staff", "principal", "distinguished",
    "head of", "director", "vp", "vice president", "chief", "founding", "founding engineer",
    "senior", "sr ",
]

# AI/tech signals in the title that qualify for the combo bonus
AI_TITLE_SIGNALS = [
    "ai", "artificial intelligence", "llm", "genai", "gen ai", "generative",
    "agentic", "rag", "ml", "machine learning", "nlp", "deep learning",
]

# =============================================================================
# KEYWORD CATEGORIES
# =============================================================================

GENAI_LLM_KEYWORDS = [
    "generative ai", "genai", "gen ai", "llm", "large language model",
    "gpt", "chatgpt", "claude", "gemini", "openai", "anthropic",
    "transformer", "foundation model", "llm integration", "llm systems",
    "llm applications", "llm ecosystem", "llm proxy", "vllm",
    "text generation", "language model", "multimodal",
    "llmops", "llm ops",
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
    "llmops", "llm ops", "ai ops", "aiops",
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

# GCC high-demand location bonus — war-driven talent exodus + Vision 2030
# Roles in these countries get a scoring boost due to acute talent shortage (Mar 2026)
GCC_PRIORITY_LOCATIONS = [
    "united arab emirates", "uae", "dubai", "abu dhabi", "sharjah",
    "saudi arabia", "ksa", "riyadh", "jeddah", "jidda", "neom", "dammam",
    "qatar", "doha",
]
GCC_LOCATION_BONUS = 12

# Europe remote bonus (P2)
EUROPE_LOCATIONS = [
    "germany", "netherlands", "france", "belgium", "austria", "switzerland",
    "sweden", "denmark", "norway", "finland", "ireland", "united kingdom",
    "spain", "portugal", "italy", "estonia", "latvia", "lithuania",
    "iceland", "luxembourg",
]
EUROPE_REMOTE_BONUS = 15
GERMANY_REMOTE_BONUS = 10  # stacks with Europe bonus (P3)

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

# Common stop words per language — if 5+ unique matches found, JD is likely not in English
NON_ENGLISH_STOPWORDS = {
    "french": ["nous", "vous", "pour", "dans", "avec", "votre", "notre", "sont", "cette", "être", "faire", "aussi", "même", "lors", "chez"],
    "german": [" und ", " oder ", " für ", " mit ", " auf ", " ihre ", " wir ", " über ", " sich ", " nach ", " eine ", " sein ", " werden ", " haben "],
    "spanish": [" para ", " con ", " por ", " una ", " los ", " las ", " del ", " como ", " ser ", " sus ", " esta ", " nuestro ", " sobre ", " entre "],
    "italian": [" per ", " con ", " una ", " dei ", " del ", " alla ", " nella ", " sono ", " questa ", " nostro ", " come ", " anche ", " essere ", " tra "],
    "portuguese": [" para ", " com ", " uma ", " dos ", " das ", " pela ", " como ", " ser ", " sua ", " nosso ", " sobre ", " entre ", " este ", " essa "],
}
NON_ENGLISH_THRESHOLD = 5  # minimum unique stop words to flag as non-English

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
        "architecture":  {"weight": 2.5, "max": 25},
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


def _compute_jd_negative_penalties(text: str) -> tuple:
    """Scan JD body for negative signals. Returns (hard_penalty, soft_penalty)."""
    hard_count = sum(1 for kw in JD_NEGATIVE_SIGNALS["hard"]["keywords"] if kw in text)
    soft_count = sum(1 for kw in JD_NEGATIVE_SIGNALS["soft"]["keywords"] if kw in text)
    hard_penalty = min(hard_count * JD_NEGATIVE_SIGNALS["hard"]["penalty_per_match"],
                       JD_NEGATIVE_SIGNALS["hard"]["max_penalty"])
    soft_penalty = min(soft_count * JD_NEGATIVE_SIGNALS["soft"]["penalty_per_match"],
                       JD_NEGATIVE_SIGNALS["soft"]["max_penalty"])
    return (hard_penalty, soft_penalty)


def _compute_experience_mismatch_penalty(text: str) -> int:
    """Penalize JDs requiring multi-year experience in technologies candidate lacks."""
    penalty = 0
    for tech in LACKING_TECH:
        pattern = rf"(\d+)\+?\s*(?:years?|yrs?)\s+(?:of\s+)?(?:experience\s+(?:with|in|using)\s+)?{re.escape(tech)}"
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            years = int(match.group(1))
            if years >= 2:
                penalty += min(years * 4, 20)
    return min(penalty, 30)


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

    # Hard negatives: always penalize java/sales/account in title, even with detected role.
    # Uses word boundaries to avoid false hits (e.g. "salesforce" won't match "sales").
    hard_neg_count = sum(
        1 for kw in TITLE_HARD_NEGATIVES
        if re.search(rf"\b{re.escape(kw.lower())}\b", title_lower)
    )
    if hard_neg_count:
        unwanted_penalty += hard_neg_count * 25

    # --- 2) SENIORITY SCORE (-25 to +35) ---
    seniority_result = _get_seniority_score(f"{title_lower} {crit_lower}")
    seniority_score = seniority_result["score"]

    # --- 2b) SENIOR + AI TITLE COMBO BONUS ---
    # When the title combines a senior leadership signal WITH an AI/tech signal, award a bonus.
    # This prevents "Head of AI Platform" or "Staff LLM Engineer" from scoring low purely
    # because their JD keyword density is lower (e.g. more strategic language than tech terms).
    senior_ai_combo_bonus = 0
    has_senior_signal = any(sig in title_lower for sig in SENIOR_TITLE_SIGNALS)
    has_ai_signal = any(sig in title_lower for sig in AI_TITLE_SIGNALS)
    if has_senior_signal and has_ai_signal:
        senior_ai_combo_bonus = SENIOR_AI_TITLE_COMBO_BONUS

    # --- 2c) PROVEN FIT BONUS — roles with interview success get +15 ---
    proven_fit_bonus = 0
    proven_fit_patterns = ["forward deployed", "forward-deployed", "field ai engineer"]
    if any(p in title_lower for p in proven_fit_patterns):
        proven_fit_bonus = 15

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

    # --- 4) REMOTE PREFERENCE (-10 to +20) ---
    remote_score = 0
    # Remote in title is a strong signal
    remote_title_keywords = ["remote", "fully remote", "100% remote"]
    if _contains_any(title_lower, remote_title_keywords):
        remote_score += 15
    elif _contains_any(loc_and_desc, REMOTE_POSITIVE):
        remote_score += 10
    # Significant boost for worldwide/anywhere remote — P1 priority
    anywhere_keywords = ["remote anywhere", "work from anywhere", "anywhere in the world",
                         "worldwide", "global remote", "fully remote worldwide",
                         "remote - worldwide", "100% remote"]
    if _contains_any(f"{title_lower} {desc_lower}", anywhere_keywords):
        remote_score += 15
    if _contains_any(loc_and_desc, REMOTE_NEGATIVE):
        remote_score -= 10

    # --- 5) LANGUAGE REQUIREMENTS (-30 to 0) ---
    language_score = 0
    if _contains_any(desc_lower, LANGUAGE_NEGATIVE):
        language_score -= 10
    chars = list(job_description or "")
    non_ascii = sum(1 for ch in chars if ord(ch) > 127)
    total_chars = len(chars) or 1
    if non_ascii / total_chars > 0.3:
        language_score -= 10
    # Detect JDs written in non-English languages (French, German, Spanish, Italian, Portuguese)
    text_to_check = f" {title_lower} {desc_lower} "
    for lang, stopwords in NON_ENGLISH_STOPWORDS.items():
        matches = sum(1 for sw in stopwords if sw in text_to_check)
        if matches >= NON_ENGLISH_THRESHOLD:
            language_score -= 20
            break

    # --- 5b) JD BODY NEGATIVE SIGNALS ---
    jd_body = f"{crit_lower} {desc_lower}"
    jd_hard_penalty, jd_soft_penalty = _compute_jd_negative_penalties(jd_body)
    jd_negative_penalty = jd_hard_penalty + jd_soft_penalty
    experience_penalty = _compute_experience_mismatch_penalty(jd_body)

    # --- 6) LOCATION BONUSES ---
    gcc_bonus = 0
    if _contains_any(loc_lower, GCC_PRIORITY_LOCATIONS):
        gcc_bonus = GCC_LOCATION_BONUS

    # Europe remote bonus (P2) — stacks if job is remote + European location
    europe_bonus = 0
    is_remote = remote_score > 0
    if is_remote and _contains_any(loc_lower, EUROPE_LOCATIONS):
        europe_bonus = EUROPE_REMOTE_BONUS
    # Germany remote extra bonus (P3) — stacks on top of Europe
    if is_remote and ("germany" in loc_lower or "deutschland" in loc_lower):
        europe_bonus += GERMANY_REMOTE_BONUS

    # --- CALCULATE TOTAL ---
    keyword_total = sum(kw_scores.values())

    raw_score = (
        title_score
        + seniority_score
        + senior_ai_combo_bonus
        + proven_fit_bonus
        + keyword_total
        + remote_score
        + language_score
        + gcc_bonus
        + europe_bonus
        - unwanted_penalty
        - jd_negative_penalty
        - experience_penalty
    )

    # Use fixed normalization cap instead of theoretical max to prevent score crushing.
    # Old formula: max_possible = ~382, making tier C (25%) require raw 96 — nearly impossible.
    # New: NORMALIZATION_CAP = 200, so tier C (25%) = raw 50, much more reachable.
    normalized_score = max(0, min(100, round((raw_score / NORMALIZATION_CAP) * 100)))

    # --- TIER ---
    if normalized_score >= 70:
        tier = "A"
    elif normalized_score >= 50:
        tier = "B"
    elif normalized_score >= 25:
        tier = "C"
    else:
        tier = "D"

    breakdown = {
        "title": title_score,
        "seniority": seniority_score,
        "seniorAiCombo": senior_ai_combo_bonus,
        "provenFit": proven_fit_bonus,
        "remote": remote_score,
        "language": language_score,
        "gccBonus": gcc_bonus,
        "europeBonus": europe_bonus,
        "unwantedPenalty": -unwanted_penalty,
        "jdNegativeHard": -jd_hard_penalty,
        "jdNegativeSoft": -jd_soft_penalty,
        "experienceMismatch": -experience_penalty,
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
