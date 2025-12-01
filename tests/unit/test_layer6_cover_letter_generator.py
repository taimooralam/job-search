"""
Unit tests for Layer 6 Cover Letter Generator (Phase 8.1).

Tests validation logic, STAR metric presence, JD-specificity, and generic boilerplate detection.
"""

import pytest
from unittest.mock import MagicMock, patch
from pydantic import ValidationError

from src.common.state import JobState


# ===== FIXTURES =====

@pytest.fixture
def sample_job_state():
    """Sample JobState with all required fields for cover letter generation."""
    return {
        "job_id": "test_job_123",
        "title": "Senior Platform Engineer",
        "company": "TechCorp",
        "job_description": "We need a senior engineer to scale our infrastructure and reduce incidents.",
        "pain_points": [
            "System reliability issues causing customer impact",
            "Need to scale infrastructure for 10x growth",
            "Incident response time currently 2+ hours"
        ],
        "strategic_needs": [
            "Build automated monitoring and alerting",
            "Implement chaos engineering practices"
        ],
        "company_research": {
            "summary": "TechCorp is a fast-growing SaaS company recently secured Series B funding",
            "signals": [
                {"type": "funding", "description": "Raised $50M Series B", "date": "2024-01", "source": "techcrunch"},
                {"type": "product_launch", "description": "Launched new enterprise tier", "date": "2024-02", "source": "linkedin"}
            ],
            "url": "https://techcorp.com"
        },
        "role_research": {
            "summary": "Platform engineering role focused on reliability and scale",
            "business_impact": [
                "Reduce system downtime and improve SLA",
                "Enable engineering team to deploy faster",
                "Support 10x customer growth"
            ],
            "why_now": "Series B funding requires enterprise-grade reliability"
        },
        "fit_score": 88,
        "fit_rationale": "Strong match based on STAR #1 (incident reduction) and STAR #2 (scaling expertise)",
        "selected_stars": [
            {
                "company": "AdTech Co",
                "role": "Senior SRE",
                "situation": "Legacy monitoring causing 50+ false alerts daily",
                "task": "Redesign monitoring and incident response",
                "actions": "Built custom alerting logic, trained team on runbooks",
                "results": "Reduced incidents by 75% and MTTR from 4h to 30min",
                "metrics": "75% incident reduction, 87% faster MTTR, $2M cost savings"
            },
            {
                "company": "FinTech Startup",
                "role": "Infrastructure Lead",
                "situation": "Platform could not handle traffic spikes",
                "task": "Build autoscaling infrastructure",
                "actions": "Implemented Kubernetes autoscaling, caching layer",
                "results": "Platform now handles 100x traffic bursts",
                "metrics": "100x traffic capacity, 99.99% uptime, $500K cost avoidance"
            }
        ],
        "candidate_profile": """
Name: Taimoor Alam
Email: taimooralam@example.com
Phone: +1-555-123-4567
LinkedIn: https://linkedin.com/in/taimooralam
Experience: 8+ years in platform engineering and SRE
"""
    }


@pytest.fixture
def valid_cover_letter():
    """A valid cover letter that passes all validation gates."""
    return """I'm eager to apply for the Senior Platform Engineer role at TechCorp. Your recent Series B funding and enterprise tier launch signal ambitious growth, and your explicit need to scale infrastructure for 10x growth while reducing system reliability issues resonates deeply with my eight years of experience building resilient, high-scale distributed systems that directly solve these challenges.

At AdTech Co, I tackled a critical reliability crisis when our legacy monitoring system generated over 50 false alerts daily, causing severe customer impact and extending incident response times beyond acceptable thresholds. I redesigned our entire monitoring and incident response infrastructure from the ground up, implementing custom alerting logic with intelligent filtering and comprehensive runbook automation. The results were transformative: 75% incident reduction, MTTR decreased from 4 hours to just 30 minutes, and $2M in quantified cost savings through reduced downtime and improved team efficiency.

More recently at FinTech Startup, I architected and led infrastructure scaling initiatives that directly addressed platform capacity constraints preventing business growth. By implementing Kubernetes-based autoscaling with sophisticated caching layers and load distribution mechanisms, I enabled our platform to handle 100x traffic bursts seamlessly while maintaining 99.99% uptime, avoiding $500K in potential downtime costs and unlocking new enterprise customer segments.

I'm confident I can help TechCorp achieve enterprise-grade reliability while supporting your rapid growth trajectory following your Series B funding. I'd welcome the opportunity to discuss how my proven experience in infrastructure scaling and reliability engineering aligns with your specific challenges, and explore concrete ways I can contribute measurable impact in the first 90 days.

I have applied for this role. Calendly: https://calendly.com/taimooralam/15min"""


@pytest.fixture
def invalid_cover_letter_no_paragraphs():
    """Invalid: Only 2 paragraphs (needs 3-4)."""
    return """I'm excited to apply for this role at TechCorp. I have lots of experience and would be a perfect fit for this position.

Let me know if you'd like to schedule a call. Thanks!"""


@pytest.fixture
def invalid_cover_letter_no_metrics():
    """Invalid: No quantified metrics (but has enough words and paragraphs)."""
    return """I'm applying for the Senior Platform Engineer role at TechCorp because I'm passionate about building reliable, scalable infrastructure systems that solve real business problems and reduce system reliability issues causing customer impact. Your recent growth and need to scale infrastructure for significant future expansion aligns perfectly with my expertise in platform engineering and reliability engineering work over the past several years across multiple high-growth technology companies and startups.

At AdTech Co, I redesigned our monitoring and incident response systems when we faced challenges with alert fatigue and slow incident response time that was currently taking too long. I implemented better alerting logic, trained the team on improved runbooks, and dramatically reduced incidents and mean time to resolution, resulting in significant cost savings and improved system stability that enabled faster feature development velocity and better customer experiences.

More recently at FinTech Startup, I led infrastructure scaling efforts when our platform struggled to handle traffic growth and needed to scale infrastructure substantially. I implemented advanced autoscaling capabilities with Kubernetes and sophisticated caching mechanisms, enabling the platform to handle massive traffic bursts while maintaining excellent uptime and avoiding substantial downtime costs while unlocking new business opportunities and enterprise customer segments.

I'm eager to bring this experience to TechCorp and help achieve your infrastructure reliability and scaling goals while supporting your growth following your Series B funding. I would welcome the opportunity to discuss how my background aligns with your challenges and explore ways I can contribute immediately upon joining your team.

I have applied for this role. Calendly: https://calendly.com/taimooralam/15min"""


@pytest.fixture
def invalid_cover_letter_generic_boilerplate():
    """Invalid: Contains too many generic phrases (but has enough words, paragraphs, metrics, and JD references)."""
    return """I am excited to apply for the Senior Platform Engineer position at TechCorp because this is my dream job and I believe I'm a perfect fit for this role. I have a strong background in engineering and I'm a great team player who can hit the ground running. Your recent Series B funding and need to scale infrastructure for significant growth, plus addressing system reliability issues causing customer impact, presents an exciting opportunity for someone with my skillset and passion for technology.

At AdTech Co, I worked on monitoring systems and incident response infrastructure, when incident response time was currently taking too long, and reduced incidents by 75% while cutting MTTR from 4 hours to just 30 minutes, saving $2M through improved reliability. I demonstrated my ability to add value quickly and became known as the ideal candidate for difficult infrastructure challenges requiring both technical excellence and collaborative team dynamics.

At FinTech Startup, I enabled the platform to handle 100x traffic bursts while maintaining 99.99% uptime and avoiding $500K in downtime costs. I'm a passionate professional who loves building scalable systems and I'm confident I can make an immediate impact as a perfect fit for your engineering culture and technical needs.

I would be thrilled to discuss this great opportunity further and demonstrate why I'm the perfect fit for your team. I'm excited to add value from day one and hit the ground running with immediate contributions.

I have applied for this role. Calendly: https://calendly.com/taimooralam/15min"""


@pytest.fixture
def invalid_cover_letter_insufficient_words():
    """Invalid: Too few words (< 220)."""
    return """I'm applying for the Senior Platform Engineer role at TechCorp.

I reduced incidents by 75% at AdTech Co and enabled 100x traffic capacity at FinTech Startup.

Let's talk soon.

I have applied for this role. Calendly: https://calendly.com/taimooralam/15min"""


# ===== VALIDATION TESTS =====

class TestCoverLetterValidation:
    """Test cover letter validation logic."""

    def test_validates_paragraph_count_min(self, invalid_cover_letter_no_paragraphs, sample_job_state):
        """Validator rejects letters with < 3 paragraphs."""
        from src.layer6.cover_letter_generator import validate_cover_letter

        with pytest.raises(ValueError) as exc_info:
            validate_cover_letter(invalid_cover_letter_no_paragraphs, sample_job_state)

        assert "paragraph" in str(exc_info.value).lower()
        assert "3" in str(exc_info.value) or "three" in str(exc_info.value).lower()

    def test_validates_paragraph_count_max(self, sample_job_state):
        """Validator accepts 5-paragraph letter (within relaxed max of 5)."""
        from src.layer6.cover_letter_generator import validate_cover_letter

        # 5-paragraph letter with 180+ words (meets word count requirement)
        five_para_letter = """I'm applying for the Senior Platform Engineer role at TechCorp because your recent Series B funding and ambitious growth plans align with my experience in infrastructure scaling and reliability engineering that addresses system reliability issues causing customer impact and enables rapid growth.

At AdTech Co I led critical infrastructure initiatives that reduced incidents by 75% while improving mean time to resolution from four hours to thirty minutes. This transformation saved over two million dollars in operational costs and enabled the engineering team to focus on product development rather than firefighting, directly addressing the need to scale infrastructure for 10x growth.

At FinTech Startup I architected comprehensive autoscaling solutions that enabled the platform to handle 100x traffic bursts seamlessly while maintaining five nines uptime throughout the scaling period. These improvements unlocked new enterprise customer segments and revenue streams for the business while significantly reducing incident response time currently taking too long.

My experience leading cross-functional teams through complex technical transformations positions me well to tackle your infrastructure challenges and support your growth trajectory following your Series B funding round. I've consistently delivered measurable results in high-growth environments similar to TechCorp's current phase.

I'm confident I can contribute immediately to achieving enterprise-grade reliability and operational excellence while supporting rapid customer acquisition and product expansion. I would welcome the opportunity to discuss how my background directly addresses your specific engineering challenges and growth objectives.

I have applied for this role. Calendly: https://calendly.com/taimooralam/15min"""

        # With relaxed constraints (2-5 paragraphs allowed), this 5-paragraph
        # letter should be accepted without raising any validation errors.
        validate_cover_letter(five_para_letter, sample_job_state)

    def test_validates_word_count_min(self, invalid_cover_letter_insufficient_words, sample_job_state):
        """Validator rejects letters with too few words (below relaxed minimum)."""
        from src.layer6.cover_letter_generator import validate_cover_letter

        with pytest.raises(ValueError) as exc_info:
            validate_cover_letter(invalid_cover_letter_insufficient_words, sample_job_state)

        assert "word" in str(exc_info.value).lower()
        assert "180" in str(exc_info.value) or "short" in str(exc_info.value).lower()

    def test_validates_word_count_max(self, sample_job_state):
        """Validator rejects letters with > relaxed maximum word count."""
        from src.layer6.cover_letter_generator import validate_cover_letter

        # Generate a very long letter (> 380 words) with proper paragraph structure
        long_letter = """I'm applying for the Senior Platform Engineer role at TechCorp because your recent Series B funding and ambitious growth plans align perfectly with my extensive experience in building resilient scalable infrastructure systems. Your explicit need to scale infrastructure for tenfold growth while reducing system reliability issues resonates deeply with my eight years of experience building distributed systems. """ + \
            ("""I have worked extensively on monitoring systems incident response infrastructure scaling capabilities autoscaling mechanisms caching layers load distribution and numerous other infrastructure components. """ * 8) + \
            """

At AdTech Co I redesigned monitoring systems and reduced incidents by 75% while cutting MTTR significantly saving millions in costs through improved reliability and team efficiency. """ + \
            ("""I implemented sophisticated alerting logic comprehensive runbook automation intelligent filtering mechanisms and numerous other technical improvements. """ * 5) + \
            """

At FinTech Startup I enabled the platform to handle 100x traffic bursts with excellent uptime avoiding substantial downtime costs. """ + \
            ("""I worked on Kubernetes autoscaling caching mechanisms and load distribution systems. """ * 5) + \
            """

I'm confident I can help TechCorp achieve infrastructure goals while supporting growth.

I have applied for this role. Calendly: https://calendly.com/taimooralam/15min"""

        with pytest.raises(ValueError) as exc_info:
            validate_cover_letter(long_letter, sample_job_state)

        assert "word" in str(exc_info.value).lower()
        assert "420" in str(exc_info.value) or "long" in str(exc_info.value).lower()

    def test_validates_metric_presence(self, invalid_cover_letter_no_metrics, sample_job_state):
        """Validator rejects letters without quantified metrics."""
        from src.layer6.cover_letter_generator import validate_cover_letter

        with pytest.raises(ValueError) as exc_info:
            validate_cover_letter(invalid_cover_letter_no_metrics, sample_job_state)

        assert "metric" in str(exc_info.value).lower() or "quantif" in str(exc_info.value).lower()

    def test_validates_minimum_one_metric(self, sample_job_state):
        """Validator rejects letters with no quantified metrics (≥1 metric required)."""
        from src.layer6.cover_letter_generator import validate_cover_letter

        # Letter with proper structure and length but only ONE quantified metric
        one_metric_letter = """I'm eager to apply for the Senior Platform Engineer role at TechCorp because your recent Series B funding and enterprise tier launch signal ambitious growth. Your explicit need to scale infrastructure for tenfold growth while reducing system reliability issues that are causing customer impact resonates deeply with my eight years of experience building resilient high-scale distributed systems that directly solve exactly these types of technical and operational challenges.

At AdTech Co I tackled a critical reliability crisis when our legacy monitoring system generated numerous false alerts daily causing severe customer impact and extending our incident response times beyond acceptable thresholds. I completely redesigned our entire monitoring and incident response infrastructure from scratch implementing custom alerting logic with intelligent filtering mechanisms and comprehensive runbook automation that our teams could execute efficiently resulting in substantial improvements to our overall operational efficiency and team productivity levels.

More recently at FinTech Startup I architected and led major infrastructure scaling initiatives that directly addressed platform capacity constraints that were preventing business growth and limiting our ability to serve enterprise customers. By implementing sophisticated Kubernetes-based autoscaling with advanced caching layers and intelligent load distribution mechanisms I enabled our platform to handle massive traffic bursts seamlessly while maintaining five nines uptime and reliability which unlocked new enterprise customer segments and revenue streams for the business.

I'm confident I can help TechCorp achieve enterprise-grade reliability and maintain excellent uptime at 98% while supporting your rapid growth trajectory following your Series B funding round.

I have applied for this role. Calendly: https://calendly.com/taimooralam/15min"""

        # This letter has 98% as the ONLY quantified metric - now valid under relaxed metric requirement (≥1).
        # Should not raise.
        validate_cover_letter(one_metric_letter, sample_job_state)

    def test_accepts_letter_with_metrics(self, sample_job_state):
        """Validator accepts letters with one or more distinct quantified metrics."""
        from src.layer6.cover_letter_generator import validate_cover_letter

        # Letter with TWO distinct metrics: 75% and $2M
        two_metrics_letter = """I'm eager to apply for the Senior Platform Engineer role at TechCorp because your recent Series B funding and enterprise tier launch signal ambitious growth. Your explicit need to scale infrastructure for 10x growth while reducing system reliability issues that are causing customer impact resonates deeply with my extensive experience building resilient high-scale distributed systems.

At AdTech Co I tackled a critical reliability crisis when our legacy monitoring system generated over fifty false alerts daily causing severe customer impact and extending our incident response times beyond acceptable thresholds. I completely redesigned our entire monitoring and incident response infrastructure from scratch implementing custom alerting logic with intelligent filtering and comprehensive runbook automation resulting in a 75% incident reduction and $2M in quantified cost savings through reduced downtime and improved team efficiency and operational excellence.

More recently at FinTech Startup I architected and led comprehensive infrastructure scaling initiatives that directly addressed platform capacity constraints preventing business growth and market expansion. By implementing Kubernetes-based autoscaling with sophisticated caching layers I enabled our platform to handle massive traffic bursts seamlessly while maintaining excellent uptime and unlocking new enterprise customer segments and revenue streams.

I'm confident I can help TechCorp achieve enterprise-grade reliability and operational excellence while successfully supporting your rapid growth trajectory and business expansion following your Series B funding round.

I have applied for this role. Calendly: https://calendly.com/taimooralam/15min"""

        # Should not raise - has 75% and $2M as two distinct metrics
        validate_cover_letter(two_metrics_letter, sample_job_state)

    def test_validates_star_company_mentions(self, sample_job_state):
        """Validator rejects letters with metrics but no STAR company mentions (ROADMAP 8.1 requirement)."""
        from src.layer6.cover_letter_generator import validate_cover_letter

        # Letter with proper structure, TWO metrics (75% and $2M), but NO mention of STAR companies
        no_star_companies_letter = """I'm eager to apply for the Senior Platform Engineer role at TechCorp because your recent Series B funding and enterprise tier launch signal ambitious growth and market expansion opportunities. Your explicit need to scale infrastructure for tenfold growth while reducing system reliability issues that are impacting customer satisfaction resonates deeply with my extensive experience building resilient high-scale distributed systems that solve these exact types of challenges.

At my previous company I tackled a critical reliability crisis when our legacy monitoring system generated numerous false alerts daily causing significant operational disruption and customer impact. I completely redesigned our entire monitoring and incident response infrastructure from the ground up implementing custom alerting logic and intelligent filtering mechanisms resulting in a 75% incident reduction and $2M in quantified cost savings through reduced downtime and dramatically improved team efficiency and operational excellence.

At another organization where I held a senior leadership position I architected comprehensive infrastructure scaling initiatives that directly addressed critical platform capacity constraints that were preventing business growth and limiting our market reach. By implementing sophisticated solutions I enabled the platform to handle massive traffic bursts seamlessly while maintaining excellent uptime and reliability metrics and unlocking valuable new enterprise customer segments and revenue streams.

I'm confident I can help TechCorp achieve enterprise-grade reliability and operational excellence while successfully supporting your rapid growth trajectory and business expansion following your Series B funding round.

I have applied for this role. Calendly: https://calendly.com/taimooralam/15min"""

        # Should fail because it has metrics (75%, $2M) but doesn't mention any STAR companies
        with pytest.raises(ValueError) as exc_info:
            validate_cover_letter(no_star_companies_letter, sample_job_state)

        error_msg = str(exc_info.value).lower()
        assert "star" in error_msg or "company" in error_msg or "employer" in error_msg

    def test_accepts_letter_with_star_company_mention(self, sample_job_state):
        """Validator accepts letters that mention at least one STAR company."""
        from src.layer6.cover_letter_generator import validate_cover_letter

        # Letter with metrics AND STAR company mention (AdTech Co)
        with_star_company_letter = """I'm eager to apply for the Senior Platform Engineer role at TechCorp because your recent Series B funding and enterprise tier launch signal ambitious growth and market expansion. Your explicit need to scale infrastructure for tenfold growth while reducing system reliability issues that impact customer satisfaction resonates deeply with my extensive experience building resilient high-scale distributed systems that solve exactly these types of operational challenges.

At AdTech Co I tackled a critical reliability crisis when our legacy monitoring system generated numerous false alerts daily causing severe customer impact and operational disruption. I completely redesigned our entire monitoring and incident response infrastructure from the ground up implementing custom alerting logic and intelligent filtering resulting in a 75% incident reduction and $2M in quantified cost savings through reduced downtime and dramatically improved team efficiency and operational excellence across the organization.

At FinTech Startup I architected comprehensive infrastructure scaling initiatives that directly addressed platform capacity constraints preventing business growth and market expansion. By implementing sophisticated solutions I enabled the platform to handle massive traffic bursts seamlessly while maintaining excellent uptime and reliability and unlocking valuable new enterprise customer segments and revenue streams.

I'm confident I can help TechCorp achieve enterprise-grade reliability and operational excellence while successfully supporting your rapid growth trajectory and business expansion plans following your Series B funding round.

I have applied for this role. Calendly: https://calendly.com/taimooralam/15min"""

        # Should pass because it mentions "AdTech Co" which is in selected_stars
        validate_cover_letter(with_star_company_letter, sample_job_state)

    def test_validates_jd_specificity(self, sample_job_state):
        """Validator rejects letters without JD-specific phrases."""
        from src.layer6.cover_letter_generator import validate_cover_letter

        # Letter with enough words, paragraphs, TWO metrics, STAR company mention, but NO JD-specific content
        # This letter avoids ALL keywords from the pain points:
        # - "system reliability issues causing customer impact"
        # - "need to scale infrastructure for 10x growth"
        # - "incident response time currently 2+ hours"
        # And JD: "We need a senior engineer to scale our infrastructure and reduce incidents"
        generic_letter_without_specifics = """I'm applying for a position at a company because I have extensive background in designing products and leading marketing campaigns across multiple domains and industries over many years of professional work in the business sector and enterprise environments and various types of organizations.

I have strong background in marketing and business leadership roles across different organizations. At AdTech Co I worked on various promotional projects and initiatives that improved overall brand recognition by 75% and achieved substantial revenue enhancements with excellent quarterly targets across all regional markets and client-facing campaigns, enabling company expansion and partner relationship improvements substantially with $500K in contract value.

At another place where I held a leadership position, I led marketing groups and contributed to many successful brand launches while maintaining high content quality standards and implementing comprehensive best practices for content development and publishing processes that benefited the entire marketing organization and improved group velocity considerably through better content platforms and improved workflows.

I'd love to work with your group and contribute to your success in achieving your business objectives and brand goals through my proven background and extensive marketing expertise development. I'm confident my profile and background would be valuable additions to your marketing group and organizational culture in ways that drive meaningful business outcomes and sustainable long-term brand equity for your organization.

I have applied for this role. Calendly: https://calendly.com/taimooralam/15min"""

        with pytest.raises(ValueError) as exc_info:
            validate_cover_letter(generic_letter_without_specifics, sample_job_state)

        assert "specific" in str(exc_info.value).lower() or "job description" in str(exc_info.value).lower() or "pain point" in str(exc_info.value).lower()

    def test_detects_generic_boilerplate(self, invalid_cover_letter_generic_boilerplate, sample_job_state):
        """Validator rejects letters with too many generic phrases."""
        from src.layer6.cover_letter_generator import validate_cover_letter

        with pytest.raises(ValueError) as exc_info:
            validate_cover_letter(invalid_cover_letter_generic_boilerplate, sample_job_state)

        assert "generic" in str(exc_info.value).lower() or "boilerplate" in str(exc_info.value).lower()

    def test_accepts_valid_cover_letter(self, valid_cover_letter, sample_job_state):
        """Validator accepts a well-formed cover letter."""
        from src.layer6.cover_letter_generator import validate_cover_letter

        # Should not raise
        validate_cover_letter(valid_cover_letter, sample_job_state)


# ===== COVER LETTER GENERATOR TESTS =====

class TestCoverLetterGenerator:
    """Test CoverLetterGenerator class."""

    @patch('src.layer6.cover_letter_generator.create_tracked_llm')
    def test_generates_cover_letter_successfully(self, mock_llm_class, sample_job_state, valid_cover_letter):
        """CoverLetterGenerator.generate_cover_letter returns valid letter."""
        from src.layer6.cover_letter_generator import CoverLetterGenerator

        # Mock LLM to return valid cover letter
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = valid_cover_letter
        mock_llm.invoke.return_value = mock_response
        mock_llm_class.return_value = mock_llm

        generator = CoverLetterGenerator()
        result = generator.generate_cover_letter(sample_job_state)

        assert result is not None
        assert len(result) > 200
        assert "75%" in result  # Contains metric
        assert "TechCorp" in result  # Contains company name

    @patch('src.layer6.cover_letter_generator.create_tracked_llm')
    def test_retry_on_invalid_output(self, mock_llm_class, sample_job_state, invalid_cover_letter_no_metrics, valid_cover_letter):
        """Generator retries on validation failure and succeeds with valid output."""
        from src.layer6.cover_letter_generator import CoverLetterGenerator

        # Mock LLM to return invalid then valid
        mock_llm = MagicMock()
        mock_llm_class.return_value = mock_llm

        invalid_response = MagicMock()
        invalid_response.content = invalid_cover_letter_no_metrics

        valid_response = MagicMock()
        valid_response.content = valid_cover_letter

        # First call returns invalid, second returns valid
        mock_llm.invoke.side_effect = [invalid_response, valid_response]

        generator = CoverLetterGenerator()
        result = generator.generate_cover_letter(sample_job_state)

        # Should succeed with valid output after retry
        assert result == valid_cover_letter
        assert mock_llm.invoke.call_count == 2

    @patch('src.layer6.cover_letter_generator.create_tracked_llm')
    def test_raises_after_max_retries(self, mock_llm_class, sample_job_state, invalid_cover_letter_no_metrics):
        """Generator raises error after exhausting retries."""
        from src.layer6.cover_letter_generator import CoverLetterGenerator

        # Mock LLM to always return invalid
        mock_llm = MagicMock()
        mock_llm_class.return_value = mock_llm

        invalid_response = MagicMock()
        invalid_response.content = invalid_cover_letter_no_metrics
        mock_llm.invoke.return_value = invalid_response

        generator = CoverLetterGenerator()

        with pytest.raises(ValueError):
            generator.generate_cover_letter(sample_job_state)

        # Should have tried multiple times (1 initial + 2 retries = 3 total)
        assert mock_llm.invoke.call_count == 3

    @patch('src.layer6.cover_letter_generator.create_tracked_llm')
    def test_includes_company_research_in_prompt(self, mock_llm_class, sample_job_state, valid_cover_letter):
        """Generator includes company research in LLM prompt."""
        from src.layer6.cover_letter_generator import CoverLetterGenerator

        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = valid_cover_letter
        mock_llm.invoke.return_value = mock_response
        mock_llm_class.return_value = mock_llm

        generator = CoverLetterGenerator()
        generator.generate_cover_letter(sample_job_state)

        # Check that prompt includes company research
        call_args = mock_llm.invoke.call_args[0][0]
        prompt_text = str(call_args)

        assert "Series B" in prompt_text or "funding" in prompt_text.lower()
        assert "TechCorp" in prompt_text

    @patch('src.layer6.cover_letter_generator.create_tracked_llm')
    def test_includes_role_research_in_prompt(self, mock_llm_class, sample_job_state, valid_cover_letter):
        """Generator includes role research in LLM prompt."""
        from src.layer6.cover_letter_generator import CoverLetterGenerator

        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = valid_cover_letter
        mock_llm.invoke.return_value = mock_response
        mock_llm_class.return_value = mock_llm

        generator = CoverLetterGenerator()
        generator.generate_cover_letter(sample_job_state)

        # Check that prompt includes role research
        call_args = mock_llm.invoke.call_args[0][0]
        prompt_text = str(call_args)

        assert "reliability" in prompt_text.lower() or "scale" in prompt_text.lower()
        assert "Business Impact" in prompt_text or "Why Now" in prompt_text

    @patch('src.layer6.cover_letter_generator.create_tracked_llm')
    def test_references_star_metrics(self, mock_llm_class, sample_job_state, valid_cover_letter):
        """Generated cover letter references STAR metrics."""
        from src.layer6.cover_letter_generator import CoverLetterGenerator

        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = valid_cover_letter
        mock_llm.invoke.return_value = mock_response
        mock_llm_class.return_value = mock_llm

        generator = CoverLetterGenerator()
        result = generator.generate_cover_letter(sample_job_state)

        # Should contain at least one STAR metric
        has_metric = any(pattern in result for pattern in ["75%", "100x", "$2M", "$500K", "99.99%"])
        assert has_metric, "Cover letter should reference STAR metrics"

    def test_validates_on_generation(self, sample_job_state):
        """Generator validates output before returning."""
        from src.layer6.cover_letter_generator import CoverLetterGenerator

        # This test verifies the integration: generate -> validate -> return
        # We'll use a mock that returns invalid output to trigger validation
        with patch('src.layer6.cover_letter_generator.create_tracked_llm') as mock_llm_class:
            mock_llm = MagicMock()
            mock_llm_class.return_value = mock_llm

            invalid_response = MagicMock()
            invalid_response.content = "Too short"
            mock_llm.invoke.return_value = invalid_response

            generator = CoverLetterGenerator()

            with pytest.raises(ValueError):
                generator.generate_cover_letter(sample_job_state)


# ===== QUALITY GATE TESTS =====

@pytest.mark.quality_gate
class TestCoverLetterQualityGates:
    """Integration-style tests for cover letter quality gates."""

    def test_quality_gate_star_citation(self, valid_cover_letter):
        """Quality gate: Cover letter must cite STAR achievements."""
        # Valid letter should have STAR context
        assert "AdTech Co" in valid_cover_letter or "FinTech Startup" in valid_cover_letter

        # Should have specific results/metrics from STARs
        assert "75%" in valid_cover_letter or "100x" in valid_cover_letter

    def test_quality_gate_company_context(self, valid_cover_letter):
        """Quality gate: Cover letter must reference company research."""
        # Should mention company name
        assert "TechCorp" in valid_cover_letter

        # Should reference company signal (funding, product launch, etc.)
        has_signal = any(keyword in valid_cover_letter.lower() for keyword in ["series b", "funding", "enterprise", "growth"])
        assert has_signal, "Cover letter should reference company signals"

    def test_quality_gate_pain_point_alignment(self, valid_cover_letter, sample_job_state):
        """Quality gate: Cover letter must address pain points."""
        pain_keywords = ["scale", "infrastructure", "reliab", "incident", "growth"]

        matches = sum(1 for keyword in pain_keywords if keyword in valid_cover_letter.lower())
        assert matches >= 2, "Cover letter should address at least 2 pain point themes"


# ===== MASTER-CV COMPANY EXTRACTION TESTS (Phase 8) =====

class TestCompanyExtractionFromMasterCV:
    """Test company extraction from master-cv.md when STAR selector is disabled."""

    def test_extracts_companies_from_em_dash_format(self):
        """Extract companies from 'Role — Company — Location' format."""
        from src.layer6.cover_letter_generator import _extract_companies_from_profile

        profile = """
## Professional Experience

Engineering Manager — AdTech Co — Munich, DE | 2020-2023
- Led team of 10 engineers

Tech Lead — FinTech Startup — Munich, DE | 2018-2020
- Architected microservices
"""
        companies = _extract_companies_from_profile(profile)

        assert "AdTech Co" in companies
        assert "FinTech Startup" in companies

    def test_extracts_companies_from_pipe_format(self):
        """Extract companies from 'Role | Company | Date' format."""
        from src.layer6.cover_letter_generator import _extract_companies_from_profile

        profile = """
## Experience

Engineering Manager | TechCorp Inc | 2020-2023
Senior Developer | StartupCo | 2018-2020
"""
        companies = _extract_companies_from_profile(profile)

        assert "TechCorp Inc" in companies
        assert "StartupCo" in companies

    def test_skips_education_section(self):
        """Companies should not be extracted from education lines."""
        from src.layer6.cover_letter_generator import _extract_companies_from_profile

        profile = """
## Education
B.S. Computer Science | State University | 2015
MBA | Business School | 2020

## Experience
Engineer — RealCompany — Location | 2020-2023
"""
        companies = _extract_companies_from_profile(profile)

        # Should NOT include universities
        assert "State University" not in companies
        assert "Business School" not in companies

        # Should include real company
        assert "RealCompany" in companies

    def test_deduplicates_company_names(self):
        """Duplicate company names should be removed."""
        from src.layer6.cover_letter_generator import _extract_companies_from_profile

        profile = """
## Experience
Senior Engineer — TechCorp — Munich | 2022-2023
Junior Engineer — TechCorp — Munich | 2020-2022
"""
        companies = _extract_companies_from_profile(profile)

        # Should only appear once
        assert companies.count("TechCorp") == 1

    def test_handles_empty_profile(self):
        """Empty profile should return empty list."""
        from src.layer6.cover_letter_generator import _extract_companies_from_profile

        companies = _extract_companies_from_profile("")
        assert companies == []

        companies = _extract_companies_from_profile(None)
        assert companies == []

    def test_filters_job_titles_from_companies(self):
        """Job titles should not be extracted as company names."""
        from src.layer6.cover_letter_generator import _extract_companies_from_profile

        profile = """
## Experience
Senior Engineer | TechCorp | 2020-2023
"""
        companies = _extract_companies_from_profile(profile)

        # Should include company, not job title
        assert "TechCorp" in companies
        assert "Senior Engineer" not in companies


class TestCoverLetterValidationWithMasterCV:
    """Test cover letter validation falls back to master-cv.md companies."""

    def test_validation_uses_master_cv_when_no_selected_stars(self):
        """Validation should use candidate_profile companies when selected_stars is empty."""
        from src.layer6.cover_letter_generator import validate_cover_letter

        state = {
            "selected_stars": [],  # Empty - STAR selector disabled
            "candidate_profile": """
## Experience
Engineering Manager — AdTech Co — Munich | 2020-2023
Tech Lead — FinTech Startup — Munich | 2018-2020
""",
            "pain_points": ["scaling challenges", "team velocity issues"],
            "company_research": {
                "signals": [{"type": "funding", "description": "Series B"}]
            }
        }

        # Letter that mentions a company from master-cv.md (190+ words)
        letter_with_master_cv_company = """I'm applying for a role at TechCorp because their recent Series B funding aligns with my experience scaling infrastructure at AdTech Co where I reduced incidents by 75%. Your focus on rapid growth and need to address scaling challenges resonates deeply with my background building high-performance engineering teams in fast-paced technology environments.

At AdTech Co I tackled significant scaling challenges and improved team velocity by implementing comprehensive agile practices and establishing engineering excellence standards. I reduced release cycles from twelve weeks to just two weeks, achieving measurable improvements in team productivity across all engineering functions. The team engagement scores improved by 60% and we maintained zero attrition over two consecutive years while delivering critical platform capabilities.

My experience at FinTech Startup further reinforced these capabilities, where I led infrastructure scaling initiatives that directly addressed similar challenges to those facing TechCorp in their current growth phase. I architected a microservices migration that scaled the platform from 5K to 500K users while maintaining 99.99% uptime throughout the transition period.

I'm confident I can help address your scaling challenges and team velocity issues with proven experience from my time at AdTech Co and FinTech Startup. I would welcome the opportunity to discuss how my background aligns with your specific needs.

I have applied for this role. Calendly: https://calendly.com/taimooralam/15min"""

        # Should NOT raise because "AdTech Co" is found in master-cv.md
        validate_cover_letter(letter_with_master_cv_company, state)

    def test_validation_fails_when_no_company_mentioned(self):
        """Validation should fail if no company from master-cv.md is mentioned."""
        from src.layer6.cover_letter_generator import validate_cover_letter

        state = {
            "selected_stars": [],  # Empty
            "candidate_profile": """
## Experience
Engineering Manager — AdTech Co — Munich | 2020-2023
""",
            "pain_points": ["challenges"],
            "company_research": {
                "signals": [{"type": "funding", "description": "Series B"}]
            }
        }

        # Letter without any company from profile (190+ words but no AdTech Co mention)
        letter_without_company = """I'm applying for a role at TechCorp because their recent Series B funding aligns with my extensive experience where I reduced incidents by 75% and dramatically improved system reliability across multiple technology organizations throughout my career. Your focus on rapid growth and need to address challenges resonates deeply with my proven track record.

At my previous company I tackled various operational challenges and improved team velocity by implementing comprehensive agile practices, reducing release cycles significantly and achieving measurable improvements in team productivity across all engineering functions. I established code review standards and mentored engineers to senior roles while maintaining exceptional team engagement and retention metrics throughout my tenure.

My experience further reinforced these capabilities, where I led critical infrastructure scaling initiatives that directly addressed similar challenges to those facing TechCorp in their current growth phase. I architected migrations and built platforms that scaled significantly while maintaining excellent uptime and reliability.

I'm confident I can help address your challenges and velocity issues with proven experience from my previous roles in technology companies. I would welcome the opportunity to discuss how my background in engineering leadership and infrastructure scaling directly aligns with your specific needs and growth objectives.

I have applied for this role. Calendly: https://calendly.com/taimooralam/15min"""

        # Should raise because no company from master-cv.md is mentioned
        with pytest.raises(ValueError) as exc_info:
            validate_cover_letter(letter_without_company, state)

        assert "employer" in str(exc_info.value).lower()


class TestCompanyMatchingEdgeCases:
    """Test edge cases in company name matching."""

    def test_case_insensitive_company_matching(self):
        """Company matching should be case-insensitive."""
        from src.layer6.cover_letter_generator import validate_cover_letter

        state = {
            "selected_stars": [],
            "candidate_profile": """
## Experience
Engineer — ADTECH CO — Munich | 2020-2023
""",
            "pain_points": ["scaling challenges", "team velocity issues"],  # Two pain points
            "company_research": {"signals": [{"type": "funding", "description": "Series B"}]}
        }

        # Letter with lowercase version of company (190+ words, references both pain points)
        letter = """I'm applying for the role because I reduced incidents by 75% at adtech co during my time leading the engineering team in their comprehensive infrastructure transformation initiative. Your recent Series B funding and scaling challenges align perfectly with my proven track record building high-performance engineering organizations and addressing team velocity issues.

My experience at adtech co involved tackling significant scaling challenges and implementing advanced processes that improved team velocity significantly across all product development functions. I established engineering excellence standards including comprehensive code review practices and mentored engineers to senior roles while maintaining exceptional team engagement metrics.

The results were measurable improvements in deployment frequency and overall team productivity that I'm confident I can replicate at your organization given similar challenges. We reduced release cycles from twelve weeks to just two weeks while maintaining quality and reliability throughout the transition period.

I would welcome the opportunity to discuss how my proven track record at adtech co directly addresses your specific needs and business objectives. My background in scaling engineering teams and implementing best practices positions me well to contribute immediately to your growth trajectory and help resolve team velocity issues.

I have applied for this role. Calendly: https://calendly.com/taimooralam/15min"""

        # Should NOT raise - case insensitive match
        validate_cover_letter(letter, state)

    def test_partial_company_name_matching(self):
        """Partial company names should match."""
        from src.layer6.cover_letter_generator import validate_cover_letter

        state = {
            "selected_stars": [],
            "candidate_profile": """
## Experience
Engineer — FinTech Startup Inc — Munich | 2020-2023
""",
            # Pain points with at least 3 distinct keywords (>3 chars each): challenges, velocity, deployment
            "pain_points": ["engineering challenges", "team velocity issues", "deployment frequency"],
            "company_research": {"signals": [{"type": "growth", "description": "Expanding"}]}
        }

        # Letter mentioning partial company name (200+ words, references pain point keywords across paragraphs)
        letter = """I'm excited about this opportunity because my experience at FinTech led to significant improvements including reducing incidents by 75% and improving overall team performance metrics across all engineering functions. Your growth trajectory aligns perfectly with my proven track record in fast-paced technology environments addressing similar engineering challenges and velocity concerns.

At FinTech I tackled various technical challenges and implemented comprehensive solutions that improved team velocity and deployment frequency substantially across all product lines. I established engineering excellence standards and mentored engineers to senior roles while maintaining exceptional team engagement throughout my tenure and addressing ongoing velocity issues effectively.

The measurable results from my time there demonstrate my ability to deliver impact quickly and effectively in fast-paced growth environments similar to yours. We scaled the platform significantly while maintaining excellent uptime and reliability metrics throughout the growth period, consistently addressing challenges head on.

I'm confident I can bring the same dedication and results-driven approach to your organization and help address your current challenges and velocity concerns immediately. My background in scaling engineering teams and implementing best practices positions me well to contribute from day one to your growth objectives and operational excellence goals.

I have applied for this role. Calendly: https://calendly.com/taimooralam/15min"""

        # Should NOT raise - "FinTech" matches "FinTech Startup Inc"
        validate_cover_letter(letter, state)


# ===== RELAXED JD-SPECIFICITY TESTS (Phase 8.1) =====

class TestRelaxedJDSpecificity:
    """Test the relaxed keyword/phrase overlap validation for Gate 4."""

    def test_accepts_exact_multiword_phrase_match(self):
        """Condition (a): Accepts letter with exact multi-word phrase from pain points."""
        from src.layer6.cover_letter_generator import validate_cover_letter

        state = {
            "selected_stars": [{"company": "TestCo"}],
            "candidate_profile": "",
            "pain_points": ["scale infrastructure for growth", "reduce system downtime"],
            "job_description": "",
            "company_research": {"signals": []}
        }

        # Letter with exact phrase "scale infrastructure" (2-word phrase from pain point)
        letter = """I'm applying for this engineering role at TestCo because my experience aligns with your need to scale infrastructure for rapid business growth and expansion. Your recent funding round positions you well for this expansion phase, and I bring proven expertise in exactly these types of challenges that require careful planning and execution at scale across multiple environments and geographic regions.

At TestCo I led initiatives that resulted in a 75% improvement in deployment frequency and substantially reduced operational overhead across all production environments. My approach to infrastructure planning has consistently delivered measurable results for high-growth organizations facing similar expansion challenges and operational requirements that demand exceptional reliability and performance under load.

The opportunity to contribute to your scaling efforts excites me because I've successfully navigated similar challenges at previous organizations where growth demands required innovative solutions. We achieved 99.9% uptime while doubling our infrastructure capacity and tripling our user base, demonstrating my ability to balance reliability with aggressive growth demands effectively.

I'm confident my background makes me well-suited to help address your infrastructure scaling needs and would welcome the chance to discuss how I can contribute meaningfully to your team's success during this critical growth phase. My experience positions me to make immediate contributions.

I have applied for this role. Calendly: https://calendly.com/taimooralam/15min"""

        # Should NOT raise - contains exact phrase "scale infrastructure"
        validate_cover_letter(letter, state)

    def test_accepts_keyword_dispersion_across_paragraphs(self):
        """Condition (b): Accepts letter with ≥3 keywords spread across ≥2 paragraphs."""
        from src.layer6.cover_letter_generator import validate_cover_letter

        state = {
            "selected_stars": [{"company": "DataCorp"}],
            "candidate_profile": "",
            # Keywords: monitoring, alerting, observability, incidents (all >3 chars)
            "pain_points": ["improve monitoring coverage", "build alerting systems", "increase observability"],
            "job_description": "Reduce incidents and improve platform reliability",
            "company_research": {"signals": []}
        }

        # Letter uses paraphrased content but hits keywords across paragraphs
        letter = """I'm enthusiastic about joining DataCorp's platform team because my expertise in building comprehensive monitoring solutions and designing intelligent alerting systems directly addresses your operational challenges related to platform reliability. Your focus on reducing incidents while maintaining system performance resonates strongly with my professional background and technical capabilities in this space.

At DataCorp I implemented observability frameworks that gave our teams unprecedented visibility into system health and application performance. This monitoring infrastructure helped reduce our incident rate by 75% while dramatically improving our mean time to detection across all production services and customer-facing applications, enabling faster response and resolution.

My approach to alerting focuses on actionable signals rather than noise, which has proven essential for maintaining engineering productivity and team morale. I built dashboards that increased team awareness of potential issues before they became critical incidents, preventing costly downtime and customer impact through proactive monitoring.

I'm confident my experience with monitoring and alerting platforms can help DataCorp achieve its reliability goals and create a more observable, resilient infrastructure that supports your growth objectives. I would welcome the opportunity to discuss how my technical skills can contribute to your platform engineering team.

I have applied for this role. Calendly: https://calendly.com/taimooralam/15min"""

        # Should NOT raise - hits "monitoring", "alerting", "observability", "incidents" across paragraphs
        validate_cover_letter(letter, state)

    def test_accepts_paraphrased_jd_content(self):
        """Validates that natural paraphrasing of JD content passes validation."""
        from src.layer6.cover_letter_generator import validate_cover_letter

        state = {
            "selected_stars": [{"company": "CloudTech"}],
            "candidate_profile": "",
            "pain_points": [
                "Need experienced engineer to optimize database performance",
                "Must improve query latency for customer-facing applications"
            ],
            "job_description": "We are hiring a senior database engineer to optimize our data layer",
            "company_research": {"signals": []}
        }

        # Letter paraphrases the JD content naturally
        letter = """I'm drawn to CloudTech's database engineering role because I've spent my career focused on optimizing data systems for performance and reliability across multiple environments and use cases. Your need for improved query performance in customer-facing applications aligns perfectly with my experience building high-performance data architectures that deliver results consistently.

At CloudTech I tackled database performance challenges that were limiting our platform's ability to scale effectively and serve our growing customer base. Through careful query optimization and indexing strategies combined with architectural improvements, I reduced average latency by 75% while handling 3x the previous query volume and maintaining data integrity throughout.

My approach to database engineering emphasizes understanding application patterns to design data models that perform well under real-world conditions and varying load patterns. I've consistently delivered measurable improvements in query response times and overall system throughput while ensuring the solutions remain maintainable and scalable.

I'm confident my database optimization expertise can help CloudTech achieve the performance improvements you're seeking for your customer applications and data infrastructure. I would welcome the opportunity to discuss how my technical background can contribute to your data engineering objectives.

I have applied for this role. Calendly: https://calendly.com/taimooralam/15min"""

        # Should NOT raise - has keywords: database, performance, query, latency, optimization
        validate_cover_letter(letter, state)

    def test_rejects_letter_without_jd_content(self):
        """Validates that letters with no JD-related content are rejected."""
        from src.layer6.cover_letter_generator import validate_cover_letter

        state = {
            "selected_stars": [{"company": "TechStartup"}],
            "candidate_profile": "",
            "pain_points": [
                "Kubernetes cluster management challenges",
                "Container orchestration scaling issues"
            ],
            "job_description": "Looking for DevOps engineer to manage our Kubernetes infrastructure",
            "company_research": {"signals": []}
        }

        # Letter about completely different topic (marketing, not DevOps/Kubernetes)
        letter = """I'm applying for a position at TechStartup because I have extensive experience in digital marketing and brand strategy that has driven measurable business results. Your company's growth trajectory excites me, and I believe I can contribute significantly to your marketing initiatives and brand development efforts across multiple channels.

At TechStartup I led campaigns that increased our social media engagement by 75% and drove significant increases in brand awareness across key demographics and target markets. My creative approach to content strategy has consistently delivered measurable results that positively impact revenue and customer acquisition rates substantially.

My background in marketing analytics helps me understand customer behavior and optimize campaigns for maximum impact and return on investment. I've built dashboards that give marketing teams real-time visibility into campaign performance, enabling data-driven decisions and continuous improvement of our marketing strategies.

I'm confident my marketing expertise can help TechStartup achieve its growth objectives and build stronger connections with your target audience through compelling brand storytelling. I would welcome the opportunity to discuss how my marketing background can contribute to your business growth.

I have applied for this role. Calendly: https://calendly.com/taimooralam/15min"""

        with pytest.raises(ValueError) as exc_info:
            validate_cover_letter(letter, state)

        assert "specific" in str(exc_info.value).lower()

    def test_handles_empty_pain_points_gracefully(self):
        """When no pain points provided, Gate 4 should pass (graceful degradation)."""
        from src.layer6.cover_letter_generator import validate_cover_letter

        state = {
            "selected_stars": [{"company": "NoContextCorp"}],
            "candidate_profile": "",
            "pain_points": [],  # No pain points
            "job_description": "",  # No JD either
            "company_research": {"signals": []}
        }

        letter = """I'm applying for the engineering role at NoContextCorp because my background in building scalable systems and leading technical teams across multiple domains makes me well-suited for this opportunity. I'm excited about the potential to contribute meaningfully to your organization's technical objectives and help drive engineering excellence across multiple initiatives and business functions.

At NoContextCorp I achieved a 75% improvement in system reliability through careful architecture decisions and implementation of best practices across all production environments and customer-facing services. My approach consistently delivers measurable results that positively impact the bottom line and customer satisfaction while maintaining technical excellence and operational stability.

My technical expertise spans multiple domains including distributed systems, data processing, and platform engineering with proven results at scale in production environments. I've successfully navigated complex technical challenges at organizations of various sizes and growth stages, consistently delivering value through thoughtful engineering practices and collaborative approaches.

I'm confident I can make meaningful contributions to your engineering team and would welcome the opportunity to discuss how my extensive experience aligns with your current needs and future objectives. My track record demonstrates my ability to deliver results quickly and effectively.

I have applied for this role. Calendly: https://calendly.com/taimooralam/15min"""

        # Should NOT raise - no source content means Gate 4 is skipped
        validate_cover_letter(letter, state)

    def test_single_keyword_in_multiple_paragraphs_insufficient(self):
        """Single keyword repeated doesn't satisfy condition (b) - needs 3 distinct keywords."""
        from src.layer6.cover_letter_generator import validate_cover_letter

        state = {
            "selected_stars": [{"company": "MonoKeywordCo"}],
            "candidate_profile": "",
            # Only provides one real keyword: "analytics" (others are stop words or too short)
            "pain_points": ["build analytics platform"],
            "job_description": "",  # No additional keywords from JD
            "company_research": {"signals": []}
        }

        # Letter mentions "analytics" multiple times but no other keywords from pain points
        letter = """I'm excited about the engineering role at MonoKeywordCo because my expertise in data solutions and information-driven decision making has been central to my career progression and professional development. Your company's focus on leveraging information for business insights and strategic advantage aligns perfectly with my professional background and technical capabilities in this domain.

At MonoKeywordCo I built information pipelines that improved our data processing by 75% and enabled real-time reporting capabilities across multiple business functions and organizational departments. My focus on information quality and data integrity has consistently delivered measurable value to organizations I've worked with throughout my career.

The information challenges you're facing align with problems I've solved before at previous organizations in similar growth stages and business contexts. I've designed information architectures that scale to handle billions of events while maintaining data integrity throughout the entire processing pipeline and data lifecycle effectively.

I'm confident my technical background makes me an excellent fit for this information-focused role, and I would welcome the opportunity to discuss how my skills can contribute to your objectives and help you achieve your important business goals.

I have applied for this role. Calendly: https://calendly.com/taimooralam/15min"""

        # Should raise - only keyword is "platform" or "build" which don't appear much, needs condition (a) or (b)
        with pytest.raises(ValueError) as exc_info:
            validate_cover_letter(letter, state)

        assert "specific" in str(exc_info.value).lower()

    def test_jd_keywords_supplement_pain_points(self):
        """Keywords from job_description should combine with pain_points for matching."""
        from src.layer6.cover_letter_generator import validate_cover_letter

        state = {
            "selected_stars": [{"company": "HybridSourceCo"}],
            "candidate_profile": "",
            "pain_points": ["improve deployment pipeline"],  # Keywords: deployment, pipeline
            "job_description": "Seeking engineer with automation expertise for CI/CD improvements",  # Keywords: automation, expertise
            "company_research": {"signals": []}
        }

        # Letter hits keywords from both sources
        letter = """I'm applying for this role at HybridSourceCo because my expertise in deployment automation aligns perfectly with your CI/CD improvement goals and engineering objectives. Building efficient pipeline systems has been a core focus of my engineering career, and I'm excited to bring this expertise and experience to your organization and team.

At HybridSourceCo I implemented automation solutions that reduced our deployment time by 75% and dramatically improved release reliability across all environments and production systems. My pipeline designs have consistently delivered faster, safer deployments that engineering teams actually want to use and rely on for their daily workflows.

My approach to automation emphasizes reliability and developer experience as core principles that drive adoption and long-term success. I've built deployment systems that teams actually want to use, which drives adoption and improves overall engineering velocity. My expertise spans multiple automation frameworks and deployment strategies.

I'm confident my deployment automation expertise can help HybridSourceCo achieve its CI/CD objectives and improve pipeline efficiency across your engineering organization. I would welcome the opportunity to discuss how my technical background can contribute to your engineering team's goals.

I have applied for this role. Calendly: https://calendly.com/taimooralam/15min"""

        # Should NOT raise - hits deployment, pipeline, automation, expertise across paragraphs
        validate_cover_letter(letter, state)
