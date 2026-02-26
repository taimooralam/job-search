"""
AI Job Classifier

Regex-based classifier that identifies AI/GenAI/LLM roles from job text.
Zero LLM cost, instant classification using proven keyword patterns.

Categories:
- ai_general: artificial intelligence, machine learning, deep learning
- ai_mention: bare "AI" or "ML" mentions (weak signal)
- genai_llm: generative AI, LLMs, GPT, Claude, transformers
- agentic_ai: AI agents, LangGraph, LangChain, multi-agent
- rag_retrieval: RAG, vector databases, embeddings, semantic search
- mlops_llmops: MLOps, model serving, SageMaker, Bedrock, Vertex AI
- fine_tuning: fine-tuning, LoRA, RLHF, PEFT
- ai_governance: responsible AI, AI ethics, AI safety, compliance
- prompt_engineering: prompt design, prompt optimization
- mcp_protocol: Model Context Protocol
- data_science: data scientist, data engineer, data platform

A job is classified as is_ai_job=True only if it matches at least one
"strong" category (anything except bare ai_mention).
"""

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

# ── AI/GenAI Keyword Definitions ─────────────────────────
# Extracted from scripts/ai_job_trends_analysis.py
AI_KEYWORDS: Dict[str, List[str]] = {
    "ai_general": [
        r"\bartificial intelligence\b", r"\bmachine learning\b",
        r"\bdeep learning\b", r"\bneural network\b",
    ],
    "ai_mention": [
        r"\bAI\b", r"\bML\b",
    ],
    "genai_llm": [
        r"\bgenai\b", r"\bgenerative ai\b", r"\bgen ai\b",
        r"\bLLM\b", r"\blarge language model\b",
        r"\bGPT\b", r"\bChatGPT\b", r"\bClaude\b", r"\bGemini\b",
        r"\btransformer\b", r"\bfoundation model\b",
        r"\bOpenAI\b", r"\bAnthropic\b",
    ],
    "agentic_ai": [
        r"\bagentic\b", r"\bai agent\b", r"\bagent framework\b",
        r"\blang\s?graph\b", r"\blangchain\b",
        r"\bcrewai\b", r"\bautogen\b",
        r"\bmulti.?agent\b", r"\btool.?call\b",
        r"\bfunction.?call\b",
    ],
    "rag_retrieval": [
        r"\bRAG\b", r"\bretrieval.augmented\b",
        r"\bvector.?database\b", r"\bvector.?store\b", r"\bvector.?search\b",
        r"\bembedding\b", r"\bpinecone\b", r"\bweaviate\b",
        r"\bqdrant\b", r"\bchroma\b", r"\bfaiss\b",
        r"\bsemantic.?search\b",
    ],
    "mlops_llmops": [
        r"\bMLOps\b", r"\bLLMOps\b",
        r"\bmodel.?serving\b", r"\bmodel.?deploy\b",
        r"\bmodel.?monitor\b", r"\bmodel.?registry\b",
        r"\blangfuse\b", r"\bweights.?biases\b", r"\bmlflow\b",
        r"\bsagemaker\b", r"\bvertex.?ai\b", r"\bbedrock\b",
        r"\bazure.?openai\b", r"\bazure.?ai\b",
        r"\bmodel.?pipeline\b", r"\bml.?pipeline\b",
    ],
    "fine_tuning": [
        r"\bfine.?tun\b", r"\bLoRA\b", r"\bQLoRA\b",
        r"\bRLHF\b", r"\bpeft\b",
        r"\binstruction.?tuning\b", r"\bdomain.?adapt\b",
    ],
    "ai_governance": [
        r"\bai governance\b", r"\bresponsible ai\b",
        r"\bai ethics\b", r"\bai safety\b",
        r"\beu ai act\b", r"\bnist ai\b",
        r"\bai risk\b", r"\bmodel card\b",
        r"\bai compliance\b",
    ],
    "prompt_engineering": [
        r"\bprompt engineer\b", r"\bprompt design\b",
        r"\bprompt optim\b",
    ],
    "mcp_protocol": [
        r"\bmodel context protocol\b", r"\bMCP\b",
    ],
    "data_science": [
        r"\bdata scientist?\b", r"\bdata engineer\b",
        r"\bdata platform\b", r"\bfeature store\b",
        r"\bdata lake\b", r"\bdata mesh\b",
    ],
}

# Categories that are considered "weak" signals — not sufficient alone
WEAK_CATEGORIES = {"ai_mention"}


@dataclass
class AIClassification:
    """Result of AI job classification."""
    is_ai_job: bool
    ai_categories: List[str]
    ai_category_count: int


def _matches_any(text: str, patterns: List[str]) -> bool:
    """Check if text matches any of the regex patterns."""
    for p in patterns:
        if re.search(p, text, re.IGNORECASE):
            return True
    return False


def build_searchable_text(
    title: Optional[str] = None,
    description: Optional[str] = None,
    job_description: Optional[str] = None,
    job_criteria: Optional[str] = None,
    extracted_jd: Optional[Dict[str, Any]] = None,
) -> str:
    """Build searchable text from individual job fields.

    Used at ingest time (title + description) and backfill (all fields).
    """
    parts = [
        title or "",
        description or "",
        job_description or "",
        job_criteria or "",
    ]

    if extracted_jd:
        for field in ("technical_skills", "top_keywords", "responsibilities",
                       "qualifications", "nice_to_haves"):
            val = extracted_jd.get(field)
            if isinstance(val, list):
                parts.append(" ".join(str(v) for v in val))
            elif val:
                parts.append(str(val))

    return " ".join(parts)


def build_searchable_text_from_doc(doc: Dict[str, Any]) -> str:
    """Build searchable text from a MongoDB document.

    Convenience wrapper that extracts fields from the document dict.
    """
    return build_searchable_text(
        title=doc.get("title"),
        description=doc.get("description"),
        job_description=doc.get("job_description"),
        job_criteria=doc.get("job_criteria"),
        extracted_jd=doc.get("extracted_jd"),
    )


def classify_job_text(text: str) -> AIClassification:
    """Classify searchable text into AI categories.

    A job is is_ai_job=True only if it matches at least one "strong"
    category (anything except bare ai_mention).
    """
    if not text:
        return AIClassification(is_ai_job=False, ai_categories=[], ai_category_count=0)

    categories = []
    for cat, patterns in AI_KEYWORDS.items():
        if _matches_any(text, patterns):
            categories.append(cat)

    has_strong = any(c not in WEAK_CATEGORIES for c in categories)

    return AIClassification(
        is_ai_job=has_strong,
        ai_categories=categories,
        ai_category_count=len(categories),
    )


def classify_job_document(doc: Dict[str, Any]) -> AIClassification:
    """Classify a MongoDB document. Convenience wrapper."""
    text = build_searchable_text_from_doc(doc)
    return classify_job_text(text)
