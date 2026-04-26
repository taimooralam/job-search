"""Tests for src.common.ai_classifier module."""


from src.common.ai_classifier import (
    AIClassification,
    build_searchable_text,
    build_searchable_text_from_doc,
    classify_job_document,
    classify_job_text,
)


class TestClassifyJobText:
    """Tests for classify_job_text()."""

    def test_genai_llm_classification(self):
        text = "We are looking for a GenAI Engineer to build LLM pipelines"
        result = classify_job_text(text)
        assert result.is_ai_job is True
        assert "genai_llm" in result.ai_categories

    def test_agentic_ai_classification(self):
        text = "Build agentic AI systems using LangGraph and multi-agent orchestration"
        result = classify_job_text(text)
        assert result.is_ai_job is True
        assert "agentic_ai" in result.ai_categories

    def test_rag_classification(self):
        text = "Implement RAG pipelines with vector database and semantic search"
        result = classify_job_text(text)
        assert result.is_ai_job is True
        assert "rag_retrieval" in result.ai_categories

    def test_mlops_classification(self):
        text = "MLOps engineer for model serving on SageMaker and Bedrock"
        result = classify_job_text(text)
        assert result.is_ai_job is True
        assert "mlops_llmops" in result.ai_categories

    def test_fine_tuning_classification(self):
        text = "Research on fine-tuning large models with LoRA and RLHF"
        result = classify_job_text(text)
        assert result.is_ai_job is True
        assert "fine_tuning" in result.ai_categories

    def test_ai_governance_classification(self):
        text = "Lead responsible AI governance and AI ethics compliance"
        result = classify_job_text(text)
        assert result.is_ai_job is True
        assert "ai_governance" in result.ai_categories

    def test_prompt_engineering_classification(self):
        text = "Prompt engineer to design and optimize prompts for production"
        result = classify_job_text(text)
        assert result.is_ai_job is True
        assert "prompt_engineering" in result.ai_categories

    def test_data_science_classification(self):
        text = "Data scientist working on feature store and data platform"
        result = classify_job_text(text)
        assert result.is_ai_job is True
        assert "data_science" in result.ai_categories

    def test_non_ai_job(self):
        text = "Senior Java Developer for enterprise banking platform"
        result = classify_job_text(text)
        assert result.is_ai_job is False
        assert result.ai_categories == []
        assert result.ai_category_count == 0

    def test_ai_mention_alone_not_strong(self):
        """A job mentioning only 'AI' or 'ML' in passing should NOT be is_ai_job=True."""
        text = "Build AI-powered CRM dashboards using React and Node.js"
        result = classify_job_text(text)
        assert result.is_ai_job is False
        assert "ai_mention" in result.ai_categories

    def test_ai_mention_with_strong_category(self):
        """ai_mention + a strong category = is_ai_job=True."""
        text = "AI Engineer building LLM applications with GPT and Claude"
        result = classify_job_text(text)
        assert result.is_ai_job is True
        assert "ai_mention" in result.ai_categories
        assert "genai_llm" in result.ai_categories

    def test_multiple_categories(self):
        text = "GenAI engineer with RAG expertise, MLOps on Bedrock, agentic AI"
        result = classify_job_text(text)
        assert result.is_ai_job is True
        assert result.ai_category_count >= 3
        assert "genai_llm" in result.ai_categories
        assert "rag_retrieval" in result.ai_categories
        assert "agentic_ai" in result.ai_categories

    def test_empty_text(self):
        result = classify_job_text("")
        assert result.is_ai_job is False
        assert result.ai_categories == []
        assert result.ai_category_count == 0

    def test_none_text(self):
        """classify_job_text handles empty string; callers handle None."""
        result = classify_job_text("")
        assert result.is_ai_job is False

    def test_case_insensitivity(self):
        text = "MACHINE LEARNING engineer for DEEP LEARNING research"
        result = classify_job_text(text)
        assert result.is_ai_job is True
        assert "ai_general" in result.ai_categories


class TestBuildSearchableText:
    """Tests for build_searchable_text() and build_searchable_text_from_doc()."""

    def test_basic_fields(self):
        text = build_searchable_text(title="AI Engineer", description="Work with LLMs")
        assert "AI Engineer" in text
        assert "Work with LLMs" in text

    def test_with_extracted_jd(self):
        text = build_searchable_text(
            title="ML Engineer",
            extracted_jd={
                "technical_skills": ["Python", "TensorFlow", "RAG"],
                "top_keywords": ["LLM", "GenAI"],
            },
        )
        assert "RAG" in text
        assert "LLM" in text
        assert "GenAI" in text

    def test_from_doc(self):
        doc = {
            "title": "Data Scientist",
            "description": "Build ML models",
            "job_description": "Machine learning role",
            "extracted_jd": {
                "technical_skills": ["Python", "scikit-learn"],
            },
        }
        text = build_searchable_text_from_doc(doc)
        assert "Data Scientist" in text
        assert "Machine learning" in text
        assert "scikit-learn" in text

    def test_none_fields(self):
        text = build_searchable_text(title=None, description=None)
        assert isinstance(text, str)

    def test_extracted_jd_string_values(self):
        text = build_searchable_text(
            extracted_jd={"technical_skills": "Python, Java, Go"},
        )
        assert "Python, Java, Go" in text


class TestClassifyJobDocument:
    """Tests for classify_job_document()."""

    def test_full_document(self):
        doc = {
            "title": "Senior GenAI Engineer",
            "description": "Build LLM applications",
            "job_description": "RAG pipelines with vector databases",
        }
        result = classify_job_document(doc)
        assert result.is_ai_job is True
        assert "genai_llm" in result.ai_categories
        assert "rag_retrieval" in result.ai_categories

    def test_empty_document(self):
        result = classify_job_document({})
        assert result.is_ai_job is False

    def test_classification_from_extracted_jd_only(self):
        """A job with AI keywords only in extracted_jd should still classify."""
        doc = {
            "title": "Software Engineer",
            "description": "Join our team",
            "extracted_jd": {
                "technical_skills": ["LangChain", "RAG", "vector database"],
            },
        }
        result = classify_job_document(doc)
        assert result.is_ai_job is True
        assert "agentic_ai" in result.ai_categories
        assert "rag_retrieval" in result.ai_categories


class TestAIClassificationDataclass:
    """Tests for AIClassification dataclass."""

    def test_fields(self):
        c = AIClassification(is_ai_job=True, ai_categories=["genai_llm"], ai_category_count=1)
        assert c.is_ai_job is True
        assert c.ai_categories == ["genai_llm"]
        assert c.ai_category_count == 1
