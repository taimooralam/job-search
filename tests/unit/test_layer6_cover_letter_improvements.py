"""
Unit tests for Layer 6a Cover Letter Generator prompt improvements.

Tests cover:
1. Source citation rules (STAR records, company research)
2. Generic phrase detection and validation
3. Pain point mapping (at least 2 pain points addressed)
4. Quality gates (paragraph count, word count, personalization)

Based on: plans/prompt-optimization-plan.md Section B (Layer 6a improvements)
"""

import pytest
from unittest.mock import MagicMock, patch

from src.layer6.cover_letter_generator import (
    CoverLetterGenerator,
    validate_cover_letter,
    GENERIC_BOILERPLATE_PHRASES,
)


# ===== VALID LETTER TEMPLATE =====
# This template passes ALL validation gates (180+ words, 3-4 paragraphs, metrics, STAR companies, signals, pain points)

VALID_LETTER_TEMPLATE = """Your Series B funding signals ambitious growth plans requiring enterprise-grade API performance and operational efficiency to support rapid customer acquisition and market expansion across enterprise segments. This strategic investment demonstrates strong market confidence and requires systematic improvements in both technical infrastructure and deployment automation capabilities to achieve competitive differentiation and support your product roadmap effectively.

At TechCorp, I reduced API p99 latency from 800ms to 120ms (85% improvement), recovering $2M ARR through systematic Redis caching implementation and database query optimization techniques. This experience directly addresses your stated pain points around API latency causing customer churn and performance degradation affecting user retention across your platform. The technical approach involved profiling slow endpoints, implementing multi-tier caching strategies, and optimizing database indices for high-throughput query patterns.

At DataCo, I automated deployment pipelines reducing cycle time from 4 hours to 15 minutes (16x improvement) through GitHub Actions CI/CD implementation and infrastructure as code practices using Terraform and Ansible. This eliminates manual deployment bottlenecks and addresses your need for rapid feature releases and deployment automation to increase engineering velocity. The solution included automated testing gates, rollback capabilities, and environment parity validation.

I have applied for this role. Calendly: https://calendly.com/taimooralam/15min"""


# ===== FIXTURES =====

@pytest.fixture
def sample_job_state():
    """Standard job state with all fields needed for cover letter generation."""
    return {
        "job_id": "test_job_123",
        "title": "Senior Backend Engineer",
        "company": "StreamCo",
        "job_description": "Build scalable API platform for 10M users. Must have microservices expertise.",
        "pain_points": [
            "API latency >500ms causing customer churn",
            "Manual deployment taking 3+ hours",
            "No infrastructure as code"
        ],
        "strategic_needs": [
            "Build automated CI/CD pipeline",
            "Implement infrastructure as code"
        ],
        "company_research": {
            "summary": "StreamCo is a fast-growing SaaS company",
            "signals": [
                {
                    "type": "funding",
                    "description": "Raised $50M Series B",
                    "date": "2024-01",
                    "source": "techcrunch"
                },
                {
                    "type": "product_launch",
                    "description": "Launched enterprise tier",
                    "date": "2024-02",
                    "source": "linkedin"
                }
            ],
            "url": "https://streamco.com"
        },
        "role_research": {
            "summary": "Backend engineering role focused on API performance",
            "business_impact": [
                "Reduce API latency to improve customer retention",
                "Automate deployment to increase velocity"
            ],
            "why_now": "Series B funding requires enterprise-grade performance"
        },
        "fit_score": 92,
        "fit_rationale": "Strong match based on API optimization and deployment automation experience",
        "selected_stars": [
            {
                "company": "TechCorp",
                "role": "Senior Backend Engineer",
                "situation": "API latency at 800ms p99 causing 15% customer churn",
                "task": "Reduce API latency below 200ms",
                "actions": "Implemented Redis caching, optimized database queries, added CDN",
                "results": "Reduced p99 latency from 800ms to 120ms (85% improvement)",
                "metrics": "85% latency reduction, 800ms to 120ms p99, recovered $2M ARR"
            },
            {
                "company": "DataCo",
                "role": "DevOps Lead",
                "situation": "Manual deployments taking 4 hours, blocking releases",
                "task": "Automate deployment pipeline",
                "actions": "Built CI/CD with GitHub Actions, automated testing, infrastructure as code",
                "results": "Reduced deployment time from 4h to 15min",
                "metrics": "16x faster deployments (4h to 15min), 95% reduction in deployment errors"
            }
        ],
        "candidate_profile": """
Name: Taimoor Alam
Email: taimoor@example.com
LinkedIn: https://linkedin.com/in/taimooralam
Experience: 8+ years in backend engineering
"""
    }


# ===== SOURCE CITATION TESTS =====

class TestSourceCitationRules:
    """Test that cover letters cite STAR records and company research properly."""

    def test_cover_letter_cites_star_company_name(self, sample_job_state):
        """Cover letter must cite at least one STAR company by name."""
        # Should pass - valid letter cites TechCorp and DataCo
        validate_cover_letter(VALID_LETTER_TEMPLATE, sample_job_state)
        assert "techcorp" in VALID_LETTER_TEMPLATE.lower()
        assert "dataco" in VALID_LETTER_TEMPLATE.lower()

    def test_cover_letter_cites_metric_from_star(self, sample_job_state):
        """Cover letter must include at least one metric from STAR achievements."""
        # Should pass - contains metrics from STARs (85%, 16x, $2M)
        validate_cover_letter(VALID_LETTER_TEMPLATE, sample_job_state)
        assert "85%" in VALID_LETTER_TEMPLATE
        assert "16x" in VALID_LETTER_TEMPLATE
        assert "$2M" in VALID_LETTER_TEMPLATE

    def test_validation_detects_missing_star_citation(self, sample_job_state):
        """Validation should fail if no STAR company is mentioned."""
        # Letter without any STAR company names (TechCorp/DataCo) - uses generic "a technology company" instead
        letter_without_star = """Your Series B funding signals ambitious growth plans requiring enterprise-grade API performance and operational efficiency to support rapid customer acquisition and market expansion across enterprise segments. This strategic investment demonstrates strong market confidence and requires systematic improvements in both technical infrastructure and deployment automation capabilities to achieve competitive differentiation and support your ambitious product roadmap effectively.

In my previous role at a technology company, I achieved significant improvements in API performance metrics by implementing advanced caching strategies and database query optimization techniques. The results included substantial latency reductions from 800ms to 120ms (85% improvement) and cost savings of over two million dollars that benefited the entire organization and improved customer satisfaction significantly across all product lines and services, recovering significant recurring revenue from at-risk customers.

At another organization where I led DevOps initiatives, I implemented comprehensive CI/CD automation that dramatically reduced deployment cycle times from 4 hours to 15 minutes (16x improvement). These improvements enabled faster feature releases and better product quality through automated testing gates, rollback capabilities, and validation processes that caught issues early in the development cycle and improved team velocity significantly.

I have applied for this role. Calendly: https://calendly.com/taimooralam/15min"""

        with pytest.raises(ValueError, match="employer|company|experience"):
            validate_cover_letter(letter_without_star, sample_job_state)

    def test_cover_letter_references_company_signal(self, sample_job_state):
        """Cover letter must reference at least one company signal (funding, launch, etc)."""
        # Should pass - VALID_LETTER_TEMPLATE mentions "Series B funding"
        validate_cover_letter(VALID_LETTER_TEMPLATE, sample_job_state)
        assert "series b" in VALID_LETTER_TEMPLATE.lower()


# ===== GENERIC PHRASE DETECTION TESTS =====

class TestGenericPhraseDetection:
    """Test detection and rejection of generic marketing language."""

    def test_detects_excited_to_apply_phrase(self):
        """Should detect 'i am excited to apply' as generic phrase."""
        assert "i am excited to apply" in [p.lower() for p in GENERIC_BOILERPLATE_PHRASES]

    def test_detects_perfect_fit_phrase(self):
        """Should detect 'perfect fit' variants as generic phrases."""
        generic_lower = [p.lower() for p in GENERIC_BOILERPLATE_PHRASES]
        assert any("perfect fit" in phrase for phrase in generic_lower)

    def test_detects_team_player_phrase(self):
        """Should detect 'team player' as generic phrase."""
        assert "team player" in [p.lower() for p in GENERIC_BOILERPLATE_PHRASES]

    def test_detects_hit_ground_running_phrase(self):
        """Should detect 'hit the ground running' as generic phrase."""
        assert "hit the ground running" in [p.lower() for p in GENERIC_BOILERPLATE_PHRASES]

    def test_detects_passionate_about_phrase(self):
        """Should detect 'passionate about' as generic phrase."""
        assert "passionate about" in [p.lower() for p in GENERIC_BOILERPLATE_PHRASES]

    def test_validation_rejects_multiple_generic_phrases(self, sample_job_state):
        """Validation should reject letters with >2 generic boilerplate phrases."""
        # Letter with 4+ generic phrases: "i am excited to apply", "dream job", "perfect fit for this role", "team player", "hit the ground running"
        # Must be 180+ words to reach the generic phrase gate
        generic_letter = """I am excited to apply for this dream job at StreamCo because this role is a perfect fit for this role and my background. Your recent Series B funding signals ambitious growth plans requiring enterprise-grade API performance and operational efficiency that I believe I can contribute to significantly as a skilled team player who can hit the ground running from day one with immediate impact on your engineering organization.

At TechCorp, I reduced API p99 latency from 800ms to 120ms (85% improvement), recovering $2M ARR through systematic implementation of Redis caching and database query optimization strategies. This directly addresses your pain points around API latency causing customer churn and performance issues affecting customer retention and satisfaction across your entire platform and product ecosystem.

At DataCo, I automated deployment pipelines reducing cycle time from 4 hours to 15 minutes (16x improvement) through GitHub Actions CI/CD implementation and infrastructure as code practices using Terraform and Ansible. This eliminates manual deployment bottlenecks and addresses your need for rapid feature releases and deployment automation to increase engineering velocity across the organization.

I have applied for this role. Calendly: https://calendly.com/taimooralam/15min"""

        with pytest.raises(ValueError, match="generic|boilerplate"):
            validate_cover_letter(generic_letter, sample_job_state)

    def test_validation_accepts_letter_without_generic_phrases(self, sample_job_state):
        """Validation should pass for letters with ≤2 generic phrases."""
        # VALID_LETTER_TEMPLATE has 0 generic phrases
        validate_cover_letter(VALID_LETTER_TEMPLATE, sample_job_state)

    def test_counts_generic_phrases_accurately(self):
        """Should accurately count generic phrase occurrences."""
        text_with_phrases = """I am excited to apply for this perfect fit for this role where I can be a team player."""

        count = sum(1 for phrase in GENERIC_BOILERPLATE_PHRASES if phrase in text_with_phrases.lower())

        # Contains: "i am excited to apply", "perfect fit for this role", "team player" = 3 phrases
        assert count == 3


# ===== PAIN POINT MAPPING TESTS =====

class TestPainPointMapping:
    """Test that cover letters address specific pain points from job analysis."""

    def test_cover_letter_addresses_api_latency_pain_point(self, sample_job_state):
        """Cover letter should explicitly address API latency pain point."""
        # VALID_LETTER_TEMPLATE addresses "API latency causing customer churn"
        validate_cover_letter(VALID_LETTER_TEMPLATE, sample_job_state)
        assert "latency" in VALID_LETTER_TEMPLATE.lower()
        assert "churn" in VALID_LETTER_TEMPLATE.lower()

    def test_cover_letter_addresses_deployment_pain_point(self, sample_job_state):
        """Cover letter should explicitly address deployment automation pain point."""
        # VALID_LETTER_TEMPLATE addresses "manual deployment"
        validate_cover_letter(VALID_LETTER_TEMPLATE, sample_job_state)
        assert "deployment" in VALID_LETTER_TEMPLATE.lower()

    def test_semantic_pain_point_matching(self, sample_job_state):
        """Should match pain points semantically via keywords."""
        # VALID_LETTER_TEMPLATE uses semantic matches: "API", "latency", "deployment"
        validate_cover_letter(VALID_LETTER_TEMPLATE, sample_job_state)


# ===== QUALITY GATE TESTS =====

class TestQualityGates:
    """Test structural quality gates (paragraph count, word count, personalization)."""

    def test_paragraph_count_minimum_2_paragraphs(self, sample_job_state):
        """Cover letter must have at least 2 substantial paragraphs."""
        # Only 1 paragraph - should fail
        short_letter = """At TechCorp I reduced API latency 85% from 800ms to 120ms recovering $2M ARR and at DataCo I automated deployments 16x faster from 4 hours to 15 minutes. Your Series B funding requires this. I have applied for this role. Calendly: https://calendly.com/taimooralam/15min"""

        with pytest.raises(ValueError, match="paragraph"):
            validate_cover_letter(short_letter, sample_job_state)

    def test_paragraph_count_maximum_5_paragraphs(self, sample_job_state):
        """Cover letter must have at most 5 substantial paragraphs."""
        # 6 paragraphs - should fail
        long_letter = """Your Series B funding signals growth requiring API performance improvements to reduce customer churn through systematic latency reduction and infrastructure optimization strategies across the organization.

At TechCorp I reduced API p99 latency from 800ms to 120ms achieving 85% improvement that recovered $2M in annual recurring revenue through Redis caching and query optimization techniques.

At DataCo I automated deployment pipelines reducing cycle time from 4 hours to 15 minutes through GitHub Actions and infrastructure as code implementation strategies and practices.

My experience with microservices architecture and cloud infrastructure positions me well to address your technical challenges around scalability and performance optimization requirements effectively.

I have deep expertise in both backend engineering and DevOps practices that enable rapid delivery of high-quality software solutions meeting business objectives and engineering excellence.

My track record demonstrates consistent delivery of measurable improvements in system performance and operational efficiency across multiple organizations and technology stacks successfully.

I have applied for this role. Calendly: https://calendly.com/taimooralam/15min"""

        with pytest.raises(ValueError, match="paragraph"):
            validate_cover_letter(long_letter, sample_job_state)

    def test_word_count_minimum_180_words(self, sample_job_state):
        """Cover letter must be at least 180 words."""
        # Short letter with proper 3-paragraph structure but only ~120 words - should fail word count gate
        short_letter = """Your Series B funding signals ambitious growth plans requiring enterprise-grade API performance and operational efficiency to support rapid customer acquisition and market expansion across enterprise segments effectively.

At TechCorp, I reduced API p99 latency from 800ms to 120ms (85% improvement), recovering $2M ARR through systematic Redis caching implementation and database query optimization techniques that address your pain points around API latency causing customer churn.

At DataCo, I automated deployment pipelines reducing cycle time from 4 hours to 15 minutes (16x improvement). I have applied for this role. Calendly: https://calendly.com/taimooralam/15min"""

        with pytest.raises(ValueError, match="180|short"):
            validate_cover_letter(short_letter, sample_job_state)

    def test_word_count_maximum_420_words(self, sample_job_state):
        """Cover letter must be at most 420 words."""
        # Very long letter (>420 words) with proper paragraph structure - should fail word count gate
        long_letter = """Your Series B funding signals ambitious growth plans requiring enterprise-grade API performance and operational efficiency to support rapid customer acquisition and market expansion across enterprise segments. This strategic investment demonstrates strong market confidence and requires systematic improvements in both technical infrastructure and deployment automation capabilities to achieve competitive differentiation and support your ambitious product roadmap effectively. The funding round validates your market position and creates opportunities for significant technical advancement. Your engineering organization is positioned to scale rapidly with the right technical foundation and expertise in building high-performance systems that can handle millions of concurrent users while maintaining sub-second response times.

At TechCorp, I led comprehensive API optimization initiatives that reduced p99 latency from 800ms to 120ms, achieving 85% improvement through systematic implementation of Redis caching layers and database query optimization techniques. This directly addresses your pain points around API latency causing customer churn and performance degradation affecting user retention across your platform. The technical approach involved profiling slow endpoints, implementing multi-tier caching strategies, optimizing database indices for high-throughput query patterns, and establishing comprehensive monitoring dashboards to track performance metrics in real-time across the entire system infrastructure. This work also included implementing connection pooling, query result caching, and asynchronous processing patterns that further improved system responsiveness and scalability under high load conditions during peak traffic periods and promotional events that drove significant user growth.

At DataCo, I led comprehensive deployment automation initiatives that transformed manual processes into fully automated CI/CD pipelines, reducing deployment cycle time from 4 hours to 15 minutes through GitHub Actions implementation and infrastructure as code practices using Terraform and Ansible. This eliminates manual deployment bottlenecks and addresses your need for rapid feature releases and deployment automation to increase engineering velocity across the organization. The solution included automated testing gates, rollback capabilities, environment parity validation, and comprehensive monitoring integration. I also established canary deployment strategies and feature flag systems that enabled safe, gradual rollouts with automated rollback triggers based on error rate thresholds and latency degradation metrics.

Additionally, I bring extensive expertise in microservices architecture design, cloud infrastructure optimization using AWS and GCP, container orchestration with Kubernetes, and observability implementation using Prometheus and Grafana. My experience spans multiple technology stacks and organizational contexts, consistently delivering measurable improvements in system performance and operational efficiency that drive meaningful business outcomes. I have led cross-functional teams through complex migrations and modernization initiatives while maintaining system reliability and performance guarantees. My contributions have directly impacted revenue growth and customer satisfaction metrics across multiple organizations.

I have applied for this role. Calendly: https://calendly.com/taimooralam/15min"""

        with pytest.raises(ValueError, match="420|long"):
            validate_cover_letter(long_letter, sample_job_state)

    def test_must_include_calendly_link(self, sample_job_state):
        """Cover letter must include Calendly link."""
        # Letter with 180+ words, passes all gates except Calendly link requirement
        letter_without_calendly = """Your Series B funding signals ambitious growth plans requiring enterprise-grade API performance and operational efficiency to support rapid customer acquisition and market expansion across enterprise segments. This strategic investment demonstrates strong market confidence and requires systematic improvements in both technical infrastructure and deployment automation capabilities to achieve competitive differentiation and support your product roadmap effectively.

At TechCorp, I reduced API p99 latency from 800ms to 120ms (85% improvement), recovering $2M ARR through systematic Redis caching implementation and database query optimization techniques. This experience directly addresses your stated pain points around API latency causing customer churn and performance degradation affecting user retention across your platform. The technical approach involved profiling slow endpoints, implementing multi-tier caching strategies, and optimizing database indices for high-throughput query patterns.

At DataCo, I automated deployment pipelines reducing cycle time from 4 hours to 15 minutes (16x improvement) through GitHub Actions CI/CD implementation and infrastructure as code practices using Terraform and Ansible. This eliminates manual deployment bottlenecks and addresses your need for rapid feature releases and deployment automation to increase engineering velocity. The solution included automated testing gates, rollback capabilities, and environment parity validation.

I have applied for this role."""

        with pytest.raises(ValueError, match="[Cc]alendly"):
            validate_cover_letter(letter_without_calendly, sample_job_state)

    def test_must_state_already_applied(self, sample_job_state):
        """Cover letter must state application has been submitted."""
        # Letter with 180+ words, passes all gates except "applied" statement requirement
        letter_without_applied = """Your Series B funding signals ambitious growth plans requiring enterprise-grade API performance and operational efficiency to support rapid customer acquisition and market expansion across enterprise segments. This strategic investment demonstrates strong market confidence and requires systematic improvements in both technical infrastructure and deployment automation capabilities to achieve competitive differentiation and support your product roadmap effectively.

At TechCorp, I reduced API p99 latency from 800ms to 120ms (85% improvement), recovering $2M ARR through systematic Redis caching implementation and database query optimization techniques. This experience directly addresses your stated pain points around API latency causing customer churn and performance degradation affecting user retention across your platform. The technical approach involved profiling slow endpoints, implementing multi-tier caching strategies, and optimizing database indices for high-throughput query patterns.

At DataCo, I automated deployment pipelines reducing cycle time from 4 hours to 15 minutes (16x improvement) through GitHub Actions CI/CD implementation and infrastructure as code practices using Terraform and Ansible. This eliminates manual deployment bottlenecks and addresses your need for rapid feature releases and deployment automation to increase engineering velocity. The solution included automated testing gates, rollback capabilities, and environment parity validation.

Calendly: https://calendly.com/taimooralam/15min"""

        with pytest.raises(ValueError, match="applied"):
            validate_cover_letter(letter_without_applied, sample_job_state)

    def test_valid_letter_passes_all_gates(self, sample_job_state):
        """VALID_LETTER_TEMPLATE should pass all validation gates."""
        # Should not raise any exception
        validate_cover_letter(VALID_LETTER_TEMPLATE, sample_job_state)


# ===== INTEGRATION TESTS =====

class TestCoverLetterGeneratorIntegration:
    """Integration tests for cover letter generation with validation."""

    @patch('src.layer6.cover_letter_generator.create_tracked_llm')
    def test_generator_produces_valid_cover_letter(self, mock_llm_class, sample_job_state):
        """Generator should produce cover letter passing all validation gates."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = VALID_LETTER_TEMPLATE
        mock_llm.invoke.return_value = mock_response
        mock_llm_class.return_value = mock_llm

        generator = CoverLetterGenerator()
        result = generator.generate_cover_letter(sample_job_state)

        # Should produce valid output
        assert result is not None
        assert len(result.split()) >= 180
        assert "techcorp" in result.lower() or "dataco" in result.lower()
        assert "85%" in result or "16x" in result

    @patch('src.layer6.cover_letter_generator.create_tracked_llm')
    def test_generator_fails_after_max_retries(self, mock_llm_class, sample_job_state):
        """Generator should raise error after exhausting retries."""
        # Always return invalid output (too short)
        invalid_letter = """Short letter without required elements."""

        mock_llm = MagicMock()
        mock_llm_class.return_value = mock_llm

        invalid_response = MagicMock()
        invalid_response.content = invalid_letter
        mock_llm.invoke.return_value = invalid_response

        generator = CoverLetterGenerator()

        with pytest.raises(ValueError):
            generator.generate_cover_letter(sample_job_state)
