"""
Unit tests for src/common/rule_scorer.py

Covers:
- Role detection (exact and partial titles)
- Seniority scoring
- Senior+AI title combo bonus
- Tier assignment
- Score normalization
- Regression: lead/architect/director roles must not be discarded (score > 0, tier != D)
"""

import pytest

from src.common.rule_scorer import (
    compute_rule_score,
    detect_role,
    should_promote_to_level2,
    PROMOTION_THRESHOLD,
    SENIOR_AI_TITLE_COMBO_BONUS,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

AI_JD_BASE = (
    "We are looking for an experienced engineer to build LLM applications. "
    "Experience with generative AI, RAG, vector databases, Python, AWS required. "
    "Lead team members, define roadmap, deliver production systems."
)

MINIMAL_JD = ""


def score(title: str, description: str = AI_JD_BASE, location: str = "Remote") -> dict:
    return compute_rule_score(
        {"title": title, "job_description": description, "location": location}
    )


# ---------------------------------------------------------------------------
# Role detection
# ---------------------------------------------------------------------------


class TestDetectRole:
    def test_exact_ai_engineer(self):
        assert detect_role("AI Engineer") == "ai_engineer"

    def test_lead_ai_engineer(self):
        assert detect_role("Lead AI Engineer") == "ai_engineer"

    def test_staff_ai_engineer(self):
        assert detect_role("Staff AI Engineer") == "ai_engineer"

    def test_tech_lead_ai_engineer(self):
        assert detect_role("Tech Lead AI Engineer") == "ai_engineer"

    def test_principal_ai_engineer(self):
        assert detect_role("Principal AI Engineer") == "ai_engineer"

    def test_ai_architect(self):
        assert detect_role("AI Architect") == "ai_architect"

    def test_llm_architect(self):
        assert detect_role("LLM Architect") == "ai_architect"

    def test_principal_agentic_engineer(self):
        assert detect_role("Principal Agentic Engineer") == "agentic_ai_engineer"

    def test_agentic_engineer(self):
        assert detect_role("Agentic Engineer") == "agentic_ai_engineer"

    def test_head_of_ai(self):
        assert detect_role("Head of AI") == "ai_leadership"

    def test_head_of_ai_platform(self):
        assert detect_role("Head of AI - Enterprise LLM Platform") == "ai_leadership"

    def test_ai_engineering_manager(self):
        assert detect_role("AI Engineering Manager") == "ai_leadership"

    def test_director_research_applied_ai(self):
        assert detect_role("Director Research & Applied AI") == "ai_leadership"

    def test_head_of_agentic_ai(self):
        assert detect_role("Head of Agentic AI") == "ai_leadership"

    def test_no_role_sales(self):
        assert detect_role("Sales Engineer") is None

    def test_no_role_frontend(self):
        assert detect_role("Frontend Developer") is None

    def test_excludes_sales_from_ai_engineer(self):
        # "AI Sales Engineer" should be excluded
        assert detect_role("AI Sales Engineer") is None


# ---------------------------------------------------------------------------
# Seniority scoring
# ---------------------------------------------------------------------------


class TestSeniorityScoring:
    def test_lead_score(self):
        result = score("Lead AI Engineer")
        assert result["breakdown"]["seniority"] == 25

    def test_staff_score(self):
        result = score("Staff AI Engineer")
        assert result["breakdown"]["seniority"] == 28

    def test_principal_score(self):
        result = score("Principal AI Engineer")
        assert result["breakdown"]["seniority"] == 28

    def test_director_score(self):
        result = score("Director of AI Engineering")
        assert result["breakdown"]["seniority"] == 30

    def test_head_of_score(self):
        result = score("Head of AI")
        assert result["breakdown"]["seniority"] == 30

    def test_senior_score(self):
        result = score("Senior AI Engineer")
        assert result["breakdown"]["seniority"] == 15

    def test_junior_penalty(self):
        result = score("Junior AI Engineer")
        assert result["breakdown"]["seniority"] == -25

    def test_executive_score(self):
        result = score("Chief AI Officer")
        assert result["breakdown"]["seniority"] == 35


# ---------------------------------------------------------------------------
# Senior+AI title combo bonus
# ---------------------------------------------------------------------------


class TestSeniorAiComboBonus:
    def test_lead_ai_gets_combo(self):
        result = score("Lead AI Engineer")
        assert result["breakdown"]["seniorAiCombo"] == SENIOR_AI_TITLE_COMBO_BONUS

    def test_staff_llm_gets_combo(self):
        result = score("Staff LLM Engineer")
        assert result["breakdown"]["seniorAiCombo"] == SENIOR_AI_TITLE_COMBO_BONUS

    def test_principal_agentic_gets_combo(self):
        result = score("Principal Agentic Engineer")
        assert result["breakdown"]["seniorAiCombo"] == SENIOR_AI_TITLE_COMBO_BONUS

    def test_head_of_ai_gets_combo(self):
        result = score("Head of AI Platform")
        assert result["breakdown"]["seniorAiCombo"] == SENIOR_AI_TITLE_COMBO_BONUS

    def test_director_ai_gets_combo(self):
        result = score("Director of AI Engineering")
        assert result["breakdown"]["seniorAiCombo"] == SENIOR_AI_TITLE_COMBO_BONUS

    def test_senior_ai_engineer_gets_combo(self):
        result = score("Mastercard Agentic AI - Senior Software Engineer")
        assert result["breakdown"]["seniorAiCombo"] == SENIOR_AI_TITLE_COMBO_BONUS

    def test_no_combo_without_ai_signal(self):
        # "Staff Software Engineer" with no AI in title but AI in JD (to pass the AI signal check)
        result = score(
            "Staff Software Engineer",
            description="Build LLM applications with Python. Generative AI, RAG, vector databases.",
        )
        assert result["breakdown"]["seniorAiCombo"] == 0

    def test_no_combo_without_senior_signal(self):
        # No senior qualifier — just "AI Developer"
        result = score("AI Developer", description=MINIMAL_JD)
        assert result["breakdown"]["seniorAiCombo"] == 0


# ---------------------------------------------------------------------------
# Tier assignment
# ---------------------------------------------------------------------------


class TestTierAssignment:
    def test_tier_b_strong_match(self):
        """A role with a rich AI JD scores at least tier B (>= 50)."""
        rich_jd = (
            "Build and lead llm applications and agentic ai systems. "
            "Generative AI, genai, large language model, openai, anthropic, claude. "
            "RAG pipeline, retrieval augmented generation, vector database, pinecone, embeddings. "
            "Agentic workflows, langgraph, langchain, multi-agent, autonomous agents. "
            "LLM evaluation, langsmith, evals, hallucination detection, guardrails. "
            "Fine-tuning, RLHF, LoRA, model training. "
            "AI infra: sagemaker, bedrock, azure openai, mlops, llmops, pytorch, huggingface. "
            "Cloud: aws, gcp, kubernetes, terraform. Python, typescript, fastapi. "
            "AI leadership, ai strategy, roadmap, cross-functional stakeholders. "
            "Delivered production systems, scaled, improved latency, drove efficiency. "
            "Remote anywhere, work from anywhere worldwide."
        )
        result = score("Lead AI Engineer", rich_jd)
        assert result["score"] >= 50, f"Expected tier B+, got score={result['score']}, breakdown={result['breakdown']}"
        assert result["tier"] in ("A", "B")

    def test_tier_a_requires_very_rich_jd(self):
        """Tier A (>= 70) requires an exact-match title AND saturating most keyword categories."""
        very_rich_jd = (
            "Lead ai engineer building genai llm generative ai applications. "
            "Agentic ai, ai agents, multi-agent, langchain, langgraph, crewai, autogen. "
            "RAG, retrieval augmented generation, vector database, pinecone, weaviate, embeddings. "
            "LLM evaluation, langsmith, hallucination detection, guardrails, red teaming. "
            "Fine-tuning RLHF LoRA QLora instruction tuning model training. "
            "AI governance responsible ai eu ai act. "
            "Prompt engineering chain of thought few-shot zero-shot. "
            "Sagemaker bedrock vertex ai azure openai mlops llmops pytorch huggingface gpu cuda. "
            "AWS gcp azure kubernetes docker terraform serverless lambda kafka. "
            "Architecture microservices distributed systems api design scalability. "
            "Python typescript javascript fastapi react postgresql mongodb redis. "
            "Data science nlp natural language processing computer vision. "
            "AI strategy roadmap vision leadership cross-functional stakeholders mentor coach. "
            "Scaled delivered shipped reduced latency improved throughput drove revenue production. "
            "Remote anywhere work from anywhere worldwide."
        )
        # Use exact-match title to get the full title weight
        result = score("Lead AI Engineer", very_rich_jd)
        # The normalization denominator is large; 65+ is a genuinely strong match
        assert result["score"] >= 65, f"Expected tier A, got score={result['score']}, breakdown={result['breakdown']}"
        assert result["tier"] == "A"

    def test_tier_c_not_d_for_lead_architect_roles(self):
        """
        Regression test: The following roles were historically discarded as false negatives.
        They must now score >= 25 (tier C or better) with a standard AI JD.
        """
        roles = [
            "Tech Lead AI Engineer",
            "AI Engineering Manager / Delivery Lead",
            "Principal Agentic Engineer",
            "Head of AI - Enterprise LLM Platform",
            "Director Research & Applied AI",
            "Staff AI Engineer",
        ]
        for title in roles:
            result = score(title)
            assert result["score"] >= 25, (
                f"'{title}' scored {result['score']} — expected >= 25 (tier C or better). "
                f"Breakdown: {result['breakdown']}"
            )
            assert result["tier"] in ("A", "B", "C"), (
                f"'{title}' landed in tier {result['tier']} — should not be discarded (D)"
            )

    def test_mastercard_agentic_ai_senior_sw(self):
        """Regression: 'Mastercard Agentic AI - Senior Software Engineer' must not be tier D."""
        result = score(
            "Mastercard Agentic AI - Senior Software Engineer",
            description="Build agentic ai systems. LLM, langchain, python, microservices, aws. Generative ai applications.",
            location="Dubai, UAE",
        )
        assert result["score"] >= 25, f"Scored {result['score']}, breakdown: {result['breakdown']}"
        assert result["tier"] != "D"

    def test_tier_d_for_irrelevant_roles(self):
        result = score("Sales Account Executive", description="Sell software products to enterprise clients.")
        assert result["tier"] == "D"

    def test_zero_score_for_excluded_role(self):
        result = score("Frontend Developer", description="Build React UI components.")
        assert result["score"] == 0


# ---------------------------------------------------------------------------
# Promotion threshold
# ---------------------------------------------------------------------------


class TestPromotionThreshold:
    def test_threshold_value(self):
        assert PROMOTION_THRESHOLD == 40

    def test_promotes_above_threshold(self):
        result = score("Lead AI Engineer", AI_JD_BASE + " agentic langgraph rag vector embeddings langsmith mlflow eval")
        if result["score"] >= PROMOTION_THRESHOLD:
            assert should_promote_to_level2(result) is True

    def test_no_promote_below_threshold(self):
        result = {
            "score": 35,
            "isTargetRole": True,
        }
        assert should_promote_to_level2(result) is False

    def test_no_promote_non_target_role(self):
        result = {
            "score": 80,
            "isTargetRole": False,
        }
        assert should_promote_to_level2(result) is False


# ---------------------------------------------------------------------------
# JD negative signals & experience mismatch
# ---------------------------------------------------------------------------


class TestJDNegativeSignals:
    """Test JD body negative signals and experience mismatch penalties."""

    def test_pytorch_heavy_jd_scores_lower(self):
        base_result = score("Senior AI Engineer")
        pytorch_jd = AI_JD_BASE + " Required: 3+ years PyTorch, TensorFlow, CUDA, model training."
        pytorch_result = score("Senior AI Engineer", pytorch_jd)
        assert pytorch_result["score"] < base_result["score"] - 10

    def test_manufacturing_domain_penalized(self):
        jd = "AI Engineer for manufacturing. Time-series forecasting, predictive maintenance, PyTorch."
        result = score("AI Engineer", jd)
        assert result["breakdown"]["jdNegativeHard"] < 0

    def test_azure_required_soft_penalty(self):
        jd = "AI Architect. Azure required. Azure OpenAI, Databricks experience, Azure ML."
        result = score("AI Architect", jd)
        assert result["breakdown"]["jdNegativeSoft"] < 0
        assert result["score"] > 20

    def test_good_fit_jd_no_penalty(self):
        result = score("AI Architect")
        assert result["breakdown"]["jdNegativeHard"] == 0
        assert result["breakdown"]["jdNegativeSoft"] == 0
        assert result["breakdown"]["experienceMismatch"] == 0

    def test_experience_mismatch_penalty(self):
        jd = "Requires 5+ years of TensorFlow and 3+ years PyTorch experience. " + AI_JD_BASE
        result = score("ML Engineer", jd)
        assert result["breakdown"]["experienceMismatch"] < 0

    def test_mobile_genai_penalized(self):
        jd = "GenAI on Android. Kotlin, on-device ML, mobile GenAI, TensorFlow Lite."
        result = score("Senior AI Engineer", jd)
        assert result["breakdown"]["jdNegativeHard"] < 0

    def test_data_scientist_title_penalized(self):
        result = score("Senior Data Scientist", "ML models, scikit-learn, pandas.")
        assert result["score"] < 35

    def test_penalties_capped(self):
        worst_jd = (
            "PyTorch TensorFlow CUDA RLHF fine-tuning Kaggle Android iOS "
            "manufacturing computer vision keras jax mxnet on-device ai "
            "azure required gcp required databricks required snowflake required "
            "scikit-learn sklearn data scientist feature engineering mlflow required"
        )
        result = score("AI Engineer", worst_jd)
        assert result["score"] >= 0
        assert result["breakdown"]["jdNegativeHard"] >= -35
        assert result["breakdown"]["jdNegativeSoft"] >= -20


class TestLanguagePenalty:
    def test_non_english_jd_loses_location_bonus_and_scores_lower(self):
        english_result = score(
            "Senior AI Engineer",
            description=(
                "Build LLM applications with generative AI, RAG, vector databases, "
                "Python, AWS, and LangGraph. Remote worldwide role."
            ),
            location="Remote, Germany",
        )
        german_result = score(
            "Senior AI Engineer",
            description=(
                "Wir suchen eine erfahrene Person für generative AI und RAG. "
                "Mit Python, AWS und LangGraph bauen Sie produktive Systeme. "
                "Remote in Deutschland."
            ),
            location="Remote, Germany",
        )

        assert english_result["breakdown"]["europeBonus"] > 0
        assert german_result["breakdown"]["language"] <= -35
        assert german_result["breakdown"]["europeBonus"] == 0
        assert german_result["score"] < english_result["score"] - 10

    def test_explicit_non_english_requirement_blocks_europe_bonus(self):
        result = score(
            "Senior AI Engineer",
            description=(
                "Build LLM applications with Python, AWS, and RAG. "
                "Fluent German required for customer workshops."
            ),
            location="Remote, Germany",
        )

        assert result["breakdown"]["language"] <= -20
        assert result["breakdown"]["europeBonus"] == 0
