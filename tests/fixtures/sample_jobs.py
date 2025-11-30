"""
Sample job descriptions and expected outputs for prompt improvement testing.

Provides test data across multiple domains:
- Tech SaaS (Backend Engineer)
- Fintech (Payments Architect)
- Healthcare (Platform Engineer)
- Transportation/Logistics (Engineering Manager)

Each fixture includes:
- Job details (title, company, description)
- Expected pain points
- Expected fit score range
- Top keywords for ATS testing
"""

from typing import Dict, Any, List


SAMPLE_JOBS: Dict[str, Dict[str, Any]] = {
    "tech_saas_backend_engineer": {
        "title": "Senior Backend Engineer",
        "company": "StreamCo",
        "job_description": """
StreamCo is building the next-generation live streaming platform.

We're looking for a Senior Backend Engineer to join our Platform Team.

**What you'll do:**
- Build scalable API platform handling 10M+ daily active users
- Own service reliability and performance optimization
- Lead migration from monolithic architecture to microservices
- Establish technical standards and best practices for the team
- Collaborate with product and frontend teams on API design

**Must have:**
- 5+ years backend development experience
- Expert-level proficiency in Python or Go
- Deep experience with microservices architecture
- Kubernetes and container orchestration expertise
- High-throughput distributed systems experience
- Strong understanding of database optimization (PostgreSQL, Redis)

**Nice to have:**
- Previous experience at a high-growth SaaS company
- Experience with event-driven architectures
- Background in video streaming or real-time systems
- Leadership or mentorship experience

**What we offer:**
- Series B funded, growing 300% YoY
- Remote-first culture with quarterly offsites
- Competitive salary + equity
- Unlimited PTO
        """.strip(),
        "expected_pain_points": [
            "API platform cannot handle traffic growth efficiently",
            "Monolithic architecture blocking feature velocity",
            "Service reliability and performance optimization needed",
            "Need to establish technical standards and best practices"
        ],
        "expected_fit_score_range": (80, 95),  # For matching candidate profile
        "top_keywords": [
            "Python", "Go", "Microservices", "Kubernetes", "API",
            "PostgreSQL", "Redis", "Distributed Systems", "SaaS",
            "Container Orchestration", "Service Reliability", "Performance Optimization"
        ],
        "role_category": "backend_engineer",
        "seniority_level": "senior",
        "implied_strategic_needs": [
            "Scale platform to support 10M+ users",
            "Migrate from monolith to microservices for velocity",
            "Build reliable foundation for hypergrowth"
        ]
    },

    "fintech_payments_architect": {
        "title": "Payments Platform Architect",
        "company": "PaymentTech",
        "job_description": """
PaymentTech is revolutionizing cross-border payments for SMBs.

We're hiring a Payments Platform Architect to lead our core payments infrastructure.

**The Challenge:**
Our payment processing system handles $500M+ monthly volume but struggles with:
- Reconciliation failures causing 2-3 day delays
- Manual retry logic for failed transactions
- PCI compliance gaps in our current architecture
- 15+ payment gateway integrations with inconsistent interfaces

**Your Mission:**
- Architect event-driven payment orchestration platform
- Design automated reconciliation system
- Lead PCI DSS Level 1 compliance certification
- Standardize payment gateway integration patterns
- Build real-time fraud detection capabilities

**Required:**
- 7+ years in payments, fintech, or financial systems
- Deep understanding of payment rails (ACH, wire, card networks)
- Event-driven architecture and message queues (Kafka, RabbitMQ)
- PCI DSS compliance experience
- Multi-currency and cross-border payment expertise
- Strong system design and architectural documentation skills

**Preferred:**
- Experience at a fintech unicorn or payment processor
- Background in fraud detection or risk systems
- Familiarity with Stripe, Adyen, or similar platforms

**We offer:**
- Series C funded ($100M), profitable business
- Direct impact on $6B+ annual payment volume
- Hybrid work (3 days in-office, SF Bay Area)
        """.strip(),
        "expected_pain_points": [
            "Reconciliation failures causing 2-3 day delays",
            "Manual retry logic for failed transactions inefficient",
            "PCI compliance gaps need immediate resolution",
            "15+ payment gateways with inconsistent interfaces"
        ],
        "expected_fit_score_range": (70, 85),
        "top_keywords": [
            "Payments", "Fintech", "Event-driven Architecture", "Kafka",
            "PCI DSS", "Payment Rails", "Reconciliation", "Fraud Detection",
            "Payment Gateway", "Multi-currency", "System Design", "Compliance"
        ],
        "role_category": "architect",
        "seniority_level": "staff",
        "implied_strategic_needs": [
            "Achieve PCI Level 1 compliance for enterprise customers",
            "Scale payment infrastructure to $10B+ volume",
            "Reduce operational overhead from manual processes"
        ]
    },

    "healthcare_platform_engineer": {
        "title": "Senior Platform Engineer",
        "company": "HealthTech Solutions",
        "job_description": """
HealthTech Solutions builds HIPAA-compliant telehealth infrastructure.

We're seeking a Senior Platform Engineer to strengthen our platform reliability.

**What's broken:**
- Platform incidents increased 40% in Q3 (affecting patient care)
- Deploy cycles take 3-4 hours, limiting hotfix speed
- No comprehensive monitoring across 12 microservices
- HIPAA audit findings from lack of infrastructure-as-code

**What you'll fix:**
- Implement SRE practices and incident management workflows
- Build CI/CD pipeline for <30 min deploy cycles
- Deploy observability stack (metrics, logs, traces)
- Achieve infrastructure-as-code compliance for HIPAA
- Reduce mean-time-to-recovery from 2 hours to <15 minutes

**Requirements:**
- 5+ years platform/DevOps/SRE experience
- Production Kubernetes experience at scale
- Infrastructure-as-code expertise (Terraform, CloudFormation)
- CI/CD pipeline design and implementation
- Healthcare or regulated industry experience (HIPAA, SOC2)
- Strong incident response and on-call experience

**Bonus:**
- AWS Certified Solutions Architect
- Experience with Datadog, New Relic, or Grafana
- Background in telemedicine or healthcare IT

**Benefits:**
- Mission-driven: improving healthcare access
- Series A funded, 50+ hospital partners
- Remote-friendly (US-based)
        """.strip(),
        "expected_pain_points": [
            "Platform incidents increased 40% affecting patient care",
            "Deploy cycles take 3-4 hours limiting hotfix speed",
            "No comprehensive monitoring across microservices",
            "HIPAA audit findings from lack of infrastructure-as-code",
            "Mean-time-to-recovery at 2 hours, need <15 minutes"
        ],
        "expected_fit_score_range": (75, 90),
        "top_keywords": [
            "SRE", "Kubernetes", "CI/CD", "Infrastructure-as-code",
            "Terraform", "HIPAA", "Incident Management", "Observability",
            "Monitoring", "DevOps", "AWS", "Healthcare", "Compliance"
        ],
        "role_category": "platform_engineer",
        "seniority_level": "senior",
        "implied_strategic_needs": [
            "Achieve HIPAA compliance for enterprise expansion",
            "Reduce incidents to maintain patient care quality",
            "Enable rapid hotfixes for critical healthcare systems"
        ]
    },

    "transportation_logistics_manager": {
        "title": "Engineering Manager - Logistics Platform",
        "company": "FreightFlow",
        "job_description": """
FreightFlow is modernizing freight logistics with real-time tracking.

Hiring an Engineering Manager to lead our Logistics Platform team (8 engineers).

**The Situation:**
Team morale is low after 6 months of "death march" sprints. Delivery velocity
has slowed 50% as technical debt compounds. We're losing senior engineers.

Meanwhile, customers are demanding:
- Real-time shipment visibility (currently 2-3 hour delays)
- Automated route optimization (currently manual Excel sheets)
- API integrations with 100+ carrier systems

**Your Charter:**
- Rebuild team culture and restore sustainable pace
- Mentor engineers and create growth paths (3 promotions overdue)
- Improve delivery velocity through process improvements
- Lead technical vision for platform modernization
- Partner with product to define realistic roadmaps

**You have:**
- 3+ years engineering management experience
- Previous experience turning around struggling teams
- Strong technical background (Python, distributed systems)
- Agile/Scrum coaching and process improvement skills
- Experience scaling engineering teams (5→15+)
- Empathy and communication skills for difficult conversations

**You've done:**
- Reduced technical debt while maintaining velocity
- Implemented effective on-call rotations
- Hired and onboarded engineers during hypergrowth
- Negotiated scope and timelines with product stakeholders

**We provide:**
- Series B funded, revolutionizing $800B logistics industry
- Coaching budget for management development
- Remote-first, flexible hours
        """.strip(),
        "expected_pain_points": [
            "Team morale low after 6 months of death march sprints",
            "Delivery velocity slowed 50% due to technical debt",
            "Losing senior engineers, retention crisis",
            "Real-time visibility has 2-3 hour delays",
            "Manual route optimization in Excel sheets",
            "3 promotions overdue, no growth paths"
        ],
        "expected_fit_score_range": (85, 95),
        "top_keywords": [
            "Engineering Manager", "Team Leadership", "Mentorship",
            "Agile", "Process Improvement", "Technical Debt", "Velocity",
            "Team Culture", "Retention", "Python", "Distributed Systems",
            "Hiring", "Performance Management", "Stakeholder Management"
        ],
        "role_category": "engineering_manager",
        "seniority_level": "senior",
        "implied_strategic_needs": [
            "Restore team velocity to meet product roadmap",
            "Retain senior engineers and rebuild culture",
            "Scale team to support platform modernization",
            "Balance technical debt paydown with feature delivery"
        ]
    }
}


def get_sample_job(job_key: str) -> Dict[str, Any]:
    """
    Get a sample job fixture by key.

    Args:
        job_key: One of the keys in SAMPLE_JOBS

    Returns:
        Job fixture dictionary

    Raises:
        KeyError if job_key not found
    """
    if job_key not in SAMPLE_JOBS:
        available = ", ".join(SAMPLE_JOBS.keys())
        raise KeyError(f"Job key '{job_key}' not found. Available: {available}")

    return SAMPLE_JOBS[job_key].copy()


def get_all_job_keys() -> List[str]:
    """Get list of all available job fixture keys."""
    return list(SAMPLE_JOBS.keys())


def create_mock_state_for_job(job_key: str, **overrides) -> Dict[str, Any]:
    """
    Create a mock JobState dictionary for testing.

    Args:
        job_key: Sample job to use as base
        **overrides: Additional state fields to override

    Returns:
        Dictionary mimicking JobState structure

    Example:
        >>> state = create_mock_state_for_job("tech_saas_backend_engineer",
        ...     selected_stars=[{"company": "Previous Corp", "results": "Built API"}])
    """
    job = get_sample_job(job_key)

    base_state = {
        "job_id": f"test_{job_key}",
        "title": job["title"],
        "company": job["company"],
        "job_description": job["job_description"],
        "pain_points": job["expected_pain_points"],
        "strategic_needs": job.get("implied_strategic_needs", []),
        "risks_if_unfilled": [],
        "success_metrics": [],
        "top_keywords": job["top_keywords"],
        "role_category": job.get("role_category", "engineer"),
        "seniority_level": job.get("seniority_level", "senior"),
        "selected_stars": [],
        "company_research": {
            "signals": [
                {
                    "type": "funding",
                    "description": "Series B funded",
                    "source": "Crunchbase"
                }
            ]
        },
        "role_research": {},
        "candidate_profile": SAMPLE_MASTER_CV,
    }

    # Apply overrides
    base_state.update(overrides)

    return base_state


# Sample master CV for testing
SAMPLE_MASTER_CV = """
# Taimoor Alam
taimoor@example.com | +49 123 456 7890 | linkedin.com/in/taimooralam

## Profile
Platform engineering leader with 12+ years building scalable distributed systems.
Led teams delivering strategic infrastructure transformations reducing costs 75%
and improving reliability to 99.9% uptime. Expertise in Python, Kubernetes, AWS,
and SRE practices.

## Professional Experience

### Seven.One Entertainment Group
**Technical Lead - Platform Engineering** | Munich, DE | 2020–Present

- Led team of 12 engineers delivering cloud-native platform migration for 50M+ users
- Reduced AWS infrastructure costs by 75% ($3M annually) through rightsizing and FinOps
- Built CI/CD pipeline using GitHub Actions and Kubernetes, improving deployment frequency 300%
- Designed event-driven microservices architecture handling 10M requests daily with 99.9% uptime
- Mentored 5 senior engineers, promoting 3 to staff level within 18 months
- Implemented SRE practices reducing incident MTTR from 2 hours to 15 minutes

### DataCorp
**Senior Backend Engineer** | Berlin, DE | 2018–2020

- Implemented Python backend services processing 100K daily transactions
- Led migration from monolith to microservices, reducing deployment time from 4 hours to 15 minutes
- Built real-time analytics pipeline using Kafka and PostgreSQL
- Improved API performance by 40% through caching and query optimization
- Led Agile sprint planning for team of 8, improving velocity 40%

### FinanceStartup
**Software Engineer** | Munich, DE | 2015–2018

- Built payment processing system handling $10M monthly volume
- Implemented fraud detection rules reducing chargebacks 60%
- Designed PostgreSQL schema optimization improving query speed 10x
- Mentored 2 junior engineers on Python best practices

## Education
- M.Sc. Computer Science — Technical University of Munich
- B.Sc. Software Engineering — NUST, Pakistan

## Core Skills
**Leadership**: Team Leadership, Mentorship, Hiring, Performance Management
**Technical**: Python, Go, Kubernetes, Docker, Microservices, System Design
**Platform**: AWS, Terraform, CI/CD, GitHub Actions, Infrastructure-as-Code
**Data**: PostgreSQL, Redis, Kafka, Event-Driven Architecture
**Processes**: Agile, SRE, Incident Management, FinOps
""".strip()


# Sample STAR records for testing
SAMPLE_STARS = [
    {
        "id": "star_001",
        "company": "Seven.One Entertainment Group",
        "situation": "Cloud-native platform migration for 50M+ users",
        "task": "Lead team of 12 engineers through complex infrastructure transformation",
        "actions": [
            "Designed event-driven microservices architecture",
            "Implemented GitOps workflow with ArgoCD",
            "Built comprehensive monitoring with Datadog"
        ],
        "results": "99.9% uptime, 300% deployment frequency improvement, 75% cost reduction ($3M/year)"
    },
    {
        "id": "star_002",
        "company": "Seven.One Entertainment Group",
        "situation": "Incident MTTR at 2 hours affecting service reliability",
        "task": "Implement SRE practices and improve incident response",
        "actions": [
            "Built automated alerting and runbook system",
            "Established on-call rotation and escalation policies",
            "Conducted blameless post-mortems"
        ],
        "results": "Reduced MTTR from 2 hours to 15 minutes (87% improvement)"
    },
    {
        "id": "star_003",
        "company": "DataCorp",
        "situation": "Monolith deployment taking 4 hours, limiting velocity",
        "task": "Lead migration to microservices architecture",
        "actions": [
            "Decomposed monolith into 12 domain-bounded services",
            "Built CI/CD pipeline with GitHub Actions",
            "Implemented feature flags for gradual rollouts"
        ],
        "results": "Deployment time reduced from 4 hours to 15 minutes (16x improvement)"
    },
    {
        "id": "star_004",
        "company": "FinanceStartup",
        "situation": "Payment fraud causing $50K monthly chargebacks",
        "task": "Build fraud detection system",
        "actions": [
            "Implemented rule-based fraud scoring",
            "Integrated with external fraud APIs",
            "Built real-time transaction monitoring"
        ],
        "results": "Reduced chargebacks 60% (saving $30K/month)"
    }
]
