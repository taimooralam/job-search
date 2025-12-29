# Seven.One Entertainment Group

**Role**: Technical Lead (Addressable TV)
**Location**: Munich, DE
**Period**: 2020–Present
**Is Current**: true
**Career Stage**: Senior/Leadership (Position 1 of 6 — Current Role)
**Duration**: 5 years

---

## Design Notes

Per the CV generation critique recommendations:
- Using **variant selection** instead of pure generation
- Each achievement has multiple emphasis variants for JD matching
- Allowing **format diversity** (not forcing ARIS on everything)
- **Qualitative specificity** balanced with verifiable metrics
- All variants are **interview-defensible**
- Current role — **flagship achievements** with maximum depth

---

## Achievements

### Achievement 1: Legacy Modernization & Platform Transformation

**Core Fact**: Diagnosed and transformed legacy 2015-era JavaScript AdTech platform—plagued by callback hell, mixed-criticality endpoints (consumer requests vs TV signal-affecting calls), and application-level anti-patterns—into autonomous event-driven TypeScript microservices on AWS. Shifted infrastructure responsibilities from application code to AWS-native services: caching to CloudFront, async orchestration to EventBridge choreography, observability to dedicated pipeline. Achieved 75% incident reduction, 3 years zero downtime, and reduced costs across people, compute, storage, and complexity—while continuously shipping features.

**Variants**:
- **Architecture**: Transformed platform with mixed-criticality endpoints (consumer requests vs TV signal-affecting calls) into autonomous event-driven microservices, moving orchestration from frontend clients to EventBridge choreography—achieving zero-maintenance async workflows
- **Technical**: Eliminated 2015-era callback hell and anti-patterns (app-level log aggregation, code-level caching) by migrating to TypeScript microservices with AWS-native infrastructure (CloudFront caching, EventBridge choreography, observability pipeline)
- **Leadership**: Built organizational buy-in for infrastructure-first approach over application-level workarounds, convincing product ownership to invest in tech debt resolution that yielded 75% incident reduction
- **Impact**: Reduced costs across 6 dimensions (people, knowledge, tech, compute, storage, complexity) through platform transformation—3 years zero downtime, 75% fewer incidents, near-zero maintenance
- **Initiative**: Took ownership of neglected legacy system others avoided, driving multi-year transformation that converted a "don't touch it" monolith into a state-of-the-art autonomous platform
- **Communication**: Bridged business and technical stakeholders using system visualizations (Miro diagrams) to explain why infrastructure investment would pay off—then delivered on that promise
- **Short**: Legacy transformation—moved infra from app to AWS, 75% fewer incidents, 3yr zero downtime, zero maintenance

**Keywords**: legacy modernization, microservices, TypeScript, AWS Lambda, EventBridge, ECS, CloudFront, event-driven architecture, choreography, monolith decomposition, AdTech, distributed systems, large-scale, system design, scalability, mixed-criticality, infrastructure-first, tech debt

**Interview Defensibility**: ✅ Can explain:
- Why choreography over orchestration (frontend was orchestrating async workflows → moved to EventBridge; services became autonomous and auto-scalable; upfront investment → zero maintenance)
- Mixed-criticality problem (some endpoints served millions of consumer requests with failure tolerance, others affected TV broadcast signal with zero tolerance)
- Anti-patterns fixed (app-level log aggregation → observability pipeline; Redis caching in code → CloudFront at infra level; frontend orchestration → EventBridge choreography)
- Buy-in challenges (team mindset shift from app to infra responsibility; product trust for tech debt investment; proving ROI through reduced incidents)
- Unique approach (bird's-eye view to specifics; Miro diagrams to explain systems to both business and tech audiences)

**Differentiators**: See `docs/differentiators.md` → Seven.One #1

---

### Achievement 2: Architectural Runway & Technical Debt Strategy

**Core Fact**: Designed and implemented Architectural Runway approach to simultaneously address extensive technical debt and accelerate feature development. Executed strategic multi-year roadmap achieving ~70% refactoring of complex distributed system components while continuously delivering business-critical features.

**Variants**:
- **Strategy**: Designed Architectural Runway balancing technical debt reduction with feature delivery, achieving 70% system refactoring over multi-year roadmap
- **Architecture**: Implemented incremental architectural transformation strategy enabling 70% codebase modernization without disrupting business delivery
- **Leadership**: Led strategic technical debt initiative using Architectural Runway pattern, balancing quality with shipping velocity
- **Impact**: Enabled sustained feature delivery while achieving 70% system modernization through strategic architectural planning
- **Short**: Architectural Runway strategy—70% refactoring while shipping features continuously

**Keywords**: architectural runway, technical debt, strategic planning, incremental modernization, refactoring, legacy systems

**Interview Defensibility**: ✅ Can explain Architectural Runway concept, prioritization framework, how debt was quantified, trade-off decisions

---

### Achievement 3: Real-Time Observability Pipeline

**Core Fact**: Led initiative to architect and realize data observability pipeline channeling billions of events daily to OpenSearch on AWS. Real-time dashboards uncovered issues and debug scenarios previously invisible, increasing shipping speed, faster issue resolution, and significant revenue increase.

**Variants**:
- **Technical**: Architected OpenSearch-based observability pipeline on AWS processing billions of events daily, transforming operational visibility and reducing costs across multiple dimensions
- **Impact**: Built observability infrastructure that reduced operational costs by 10x and enabled previously impossible debugging scenarios
- **Architecture**: Designed event streaming architecture from distributed microservices to OpenSearch, enabling real-time operational dashboards
- **Leadership**: Led observability initiative from concept to production, transforming team's ability to detect and resolve issues proactively
- **Short**: Observability pipeline—billions of daily events, 10x cost reduction, real-time debugging

**Keywords**: observability, OpenSearch, AWS, event streaming, real-time analytics, dashboards, monitoring, data pipeline, distributed systems, high-scale

**Interview Defensibility**: ✅ Can explain pipeline architecture, why OpenSearch, cost optimization strategies, specific debugging scenarios enabled

---

### Achievement 4: DDD & Engineering Excellence Standards

**Core Fact**: Enhanced system architecture and reduced technical debt by introducing Domain-Driven Design framework. Established ubiquitous language and bounded contexts, reducing developer onboarding from 6 to 3 months, improving team velocity by 25%, and reducing requirement misalignment by 40%.

**Variants**:
- **Architecture**: Introduced Domain-Driven Design with bounded contexts and ubiquitous language, reducing requirement misalignment by 40%
- **Leadership**: Established DDD framework as engineering standard, cutting developer onboarding time from 6 to 3 months
- **Process**: Implemented DDD principles enabling consistent business-tech communication and 25% velocity improvement
- **Mentoring**: Mentored engineers on DDD patterns, fostering decoupled modules and autonomous backend microservices
- **Code Review**: Conducted architectural code reviews ensuring adherence to DDD patterns and bounded context boundaries
- **Short**: DDD adoption—50% faster onboarding, 25% velocity gain, 40% fewer requirement misalignments

**Keywords**: Domain-Driven Design, DDD, bounded contexts, ubiquitous language, engineering standards, onboarding, velocity, code review, architectural review

**Interview Defensibility**: ✅ Can explain specific bounded contexts, how ubiquitous language was established, measurement methodology

---

### Achievement 5: GDPR/TCF Compliance & Regulatory Success

**Core Fact**: Led GDPR/TCF compliance program across multiple product lines, implementing consent management platform that passed BLM regulatory audits. First movers in EU region for TCF GDPR-approved compliant CMP, protecting €30M annual revenue exposure.

**Variants**:
- **Compliance**: Led GDPR/TCF compliance program implementing consent management platform that passed BLM regulatory audits, protecting €30M revenue
- **Leadership**: Drove regulatory compliance initiative as first-movers in EU for TCF-approved CMP, establishing professional relationship with Bavarian Media Authority
- **Architecture**: Designed TCF-compliant consent management architecture integrated across multiple product lines for regulatory approval
- **Impact**: Preserved €30M annual revenue through successful GDPR compliance implementation and multiple regulatory audits
- **Short**: GDPR/TCF compliance—€30M revenue protected, first-mover EU TCF-approved CMP

**Keywords**: GDPR, TCF, compliance, consent management, CMP, regulatory, BLM, privacy, data protection

**Interview Defensibility**: ✅ Can explain TCF framework, CMP architecture, audit process, regulatory relationship management

---

### Achievement 6: Technical Vision & Business Alignment

**Core Fact**: Devised technical vision and roadmap aligned with company strategy of increasing reach and consented users. Preserved and increased ad impressions (15% YoY growth) despite global industry-wide decline in linear TV viewership through adaptive algorithmic blacklisting and ad supply optimization.

**Variants**:
- **Strategy**: Devised technical roadmap aligned with business OKRs, achieving 15% YoY impression growth despite declining linear TV market
- **Innovation**: Developed adaptive algorithmic blacklisting technique increasing reach and revenue by ~20% against industry headwinds
- **Leadership**: Aligned technical architecture with company strategy, turning industry decline into competitive advantage
- **Impact**: Preserved ad revenue through technical innovation despite global linear TV viewership decline
- **Short**: Technical vision driving 15% growth against declining market through algorithmic innovation

**Keywords**: technical strategy, OKRs, business alignment, ad optimization, algorithmic blacklisting, AdTech, impression growth

**Interview Defensibility**: ✅ Can explain blacklisting algorithm, how OKRs translated to technical decisions, market context

---

### Achievement 7: Scalability & Performance Optimization

**Core Fact**: Led and optimized scaling of multi-million user backend systems around bursty traffic patterns using Lambda and ECS auto-scaling. Reduced missed impressions by 20% while optimizing cost-performance balance.

**Variants**:
- **Technical**: Scaled AWS infrastructure for bursty traffic using Lambda and ECS auto-scaling, reducing missed impressions by 20%
- **Architecture**: Designed auto-scaling patterns handling multi-million user traffic bursts while optimizing cloud costs
- **Performance**: Optimized backend systems for bursty traffic patterns, balancing cost-performance and reducing missed impressions
- **Innovation**: Used agentic AI to expedite scaling optimization process for multi-million user systems
- **Short**: Auto-scaling architecture—20% fewer missed impressions, cost-optimized bursty traffic handling

**Keywords**: AWS, Lambda, ECS, auto-scaling, performance, scalability, bursty traffic, cost optimization

**Interview Defensibility**: ✅ Can explain scaling triggers, cost optimization strategies, traffic patterns, agentic AI usage

---

### Achievement 8: Monitoring & Incident Management

**Core Fact**: Implemented comprehensive monitoring and alerting system significantly reducing MTTR through proactive incident detection and automated response workflows. Cultivated culture of incident management and blameless postmortems as part of platform reliability transformation.

**Variants**:
- **Technical**: Implemented CloudWatch and SNS-based monitoring system with Slack alerting integration, significantly reducing MTTR as part of platform reliability transformation
- **Architecture**: Architected alerting strategy using CloudWatch, SNS, and Slack—defining where alerts were needed and facilitating team-wide implementation
- **SME**: Served as subject matter expert on alerting architecture, designing CloudWatch/SNS/Slack monitoring system and guiding implementation across teams
- **Leadership**: Cultivated blameless postmortem culture and defined alerting standards, transforming incident response from reactive to proactive
- **Process**: Established incident management culture with blameless postmortems, improving operational excellence
- **Impact**: Transformed platform reliability through strategic alerting architecture, significantly reducing MTTR and enabling faster feature delivery
- **Short**: CloudWatch/SNS/Slack alerting architecture—SME on alerting strategy, significant MTTR reduction, blameless postmortems

**Keywords**: monitoring, alerting, MTTR, incident management, postmortems, operational excellence, automation, CloudWatch, SNS, Slack, AWS, alerting strategy

**Interview Defensibility**: ✅ Can explain alerting strategy, postmortem process, specific MTTR improvements, automation examples

---

### Achievement 9: Engineering Team Development & Mentorship

**Core Fact**: Mentored 10+ senior engineers on architectural patterns, event-driven design, and cloud best practices. Promoted 3 engineers to lead positions. Maintained low turnover through growth opportunities and cultural incentives.

**Variants**:
- **Leadership**: Mentored 10+ senior engineers on architecture and cloud patterns, promoting 3 to lead positions
- **Culture**: Cultivated knowledge-sharing culture through mentoring with kindness and patience, creating ripple effect across department
- **Retention**: Maintained low turnover by incentivizing growth through technology upgrades and cultural initiatives
- **Development**: Developed engineering talent through architectural mentorship and career pathing
- **Management**: Led talent development through regular coaching, growing 3 engineers to lead positions while maintaining low turnover
- **Short**: Mentored 10+ engineers, promoted 3 to leads, maintained low turnover through growth culture

**Keywords**: mentoring, coaching, leadership, talent development, team building, culture, retention, career growth, people management, performance management, code review

**Interview Defensibility**: ✅ Can describe specific mentorship approaches, promotion criteria, retention strategies

---

### Achievement 10: Innovation Culture (Lean Friday)

**Core Fact**: Cultivated culture of innovation by establishing Lean Friday: one Friday per sprint where team works on any technical improvement. Resulted in breakthrough tools increasing team productivity by orders of magnitude.

**Variants**:
- **Culture**: Established Lean Friday innovation program resulting in breakthrough productivity tools
- **Leadership**: Created structured innovation time producing tools that improved development, QA, and business processes
- **Process**: Implemented Lean Friday practice enabling team-driven innovation and productivity improvements
- **Impact**: Innovation program produced breakthrough tools increasing productivity by orders of magnitude
- **Short**: Lean Friday initiative—breakthrough tools, orders of magnitude productivity gains

**Keywords**: innovation, culture, Lean Friday, productivity, continuous improvement, team empowerment

**Interview Defensibility**: ✅ Can describe specific tools created, how Lean Friday was structured, productivity measurements

---

### Achievement 11: Hiring & Team Building

**Core Fact**: Led hiring process for software engineers by defining selection criteria, designing interview strategies, and developing technical assessments. Scaled delivery across matrixed cross-functional engineering teams.

**Variants**:
- **Leadership**: Led engineering hiring by defining selection criteria and designing technical assessments
- **Process**: Designed interview strategies and evaluation frameworks for engineering recruitment
- **Scaling**: Scaled delivery across matrixed cross-functional teams through strategic hiring and team building
- **Short**: Engineering hiring leadership—selection criteria, technical assessments, cross-functional scaling

**Keywords**: hiring, recruitment, interviews, technical assessments, team building, cross-functional, scaling

**Interview Defensibility**: ✅ Can describe selection criteria, interview format, assessment design, cross-functional coordination

---

### Achievement 12: CI/CD & Deployment Excellence

**Core Fact**: Drove enhancement and modernization of CI/CD pipelines, fostering culture of atomic deployments. Reduced release cycles from weeks to days, improving delivery predictability by 25%.

**Variants**:
- **Technical**: Facilitated Jenkins to GitLab CI migration, enabling faster automated deployments and reducing release cycles from weeks to days
- **Leadership**: Drove CI/CD modernization from Jenkins to GitLab CI, enabling team adoption of atomic deployments and improving delivery predictability by 25%
- **Process**: Fostered atomic deployment culture improving delivery predictability by 25%
- **Impact**: CI/CD modernization reduced release cycles from weeks to days with improved predictability
- **Short**: Jenkins→GitLab CI migration—release cycles from weeks to days, 25% better predictability

**Keywords**: CI/CD, deployment, atomic deploys, release cycles, DevOps, automation, delivery, Jenkins, GitLab CI, pipeline migration

**Interview Defensibility**: ✅ Can explain pipeline architecture, atomic deployment strategy, predictability measurement

---

### Achievement 13: Subject Matter Expertise & Stakeholder Collaboration

**Core Fact**: Consulted as subject matter expert on technical challenges in Addressable TV domain. Collaborated with product owners, enterprise architects, and stakeholders to identify core business metrics and led their realization across technical stack.

**Variants**:
- **Expertise**: Served as subject matter expert on Addressable TV technical challenges and possibilities
- **Collaboration**: Collaborated with product owners and enterprise architects to translate business metrics into technical implementations
- **Leadership**: Bridged business and technical domains, identifying core metrics and leading their realization
- **Short**: Addressable TV subject matter expert—business metric realization across technical stack

**Keywords**: subject matter expert, SME, Addressable TV, AdTech, stakeholder collaboration, business metrics

**Interview Defensibility**: ✅ Can explain Addressable TV domain, specific technical challenges, stakeholder collaboration examples

---

### Achievement 14: Risk Management & Strategic Communication

**Core Fact**: Analyzed system risks and communicated them transparently to all business stakeholders, keeping them well-informed about consequences of future business decisions. Took hard decisions despite ambiguity, executed quickly, and collected data to adapt.

**Variants**:
- **Leadership**: Analyzed and communicated system risks transparently to business stakeholders for informed decision-making
- **Strategy**: Made decisive calls amid ambiguity, executed quickly, and collected data to iterate
- **Communication**: Maintained transparent risk communication enabling informed business decisions
- **Short**: Risk analysis and transparent stakeholder communication for informed business decisions

**Keywords**: risk management, stakeholder communication, transparency, decision-making, ambiguity, strategic communication

**Interview Defensibility**: ✅ Can describe specific risks identified, communication approach, decisions made under ambiguity

---

## Skills

**Hard Skills**:
- **Languages**: TypeScript, JavaScript, Python, Java, Bash
- **Cloud**: AWS (Lambda, ECS, EventBridge, S3, CloudFront, SNS, SQS, Fargate), Terraform, Serverless, Cloud Architecture, Cloud Infrastructure
- **Architecture**: Domain-Driven Design, Event-Driven Architecture, Microservices, CQRS, Distributed Systems, Software Architecture, System Architecture, System Design, Scalable Systems, High-Availability Systems
- **Data**: OpenSearch, Elasticsearch, Redis, Event Streaming, Data Pipeline, Data Pipelines, Big Data, Batch Processing, Analytics Dashboards
- **Observability**: Monitoring, Logging, Metrics, Observability, Observability Platforms, Datadog, DataOps
- **DevOps**: CI/CD, Infrastructure as Code, Docker, Container Orchestration, Containerization, GitHub, GitHub Actions, Jenkins, DevOps, Automation, Automation Platforms
- **Backend**: Backend Development, API Design, API Integration, APIs, REST APIs, Performance Optimization, Code Review, Unit Testing, TDD
- **Frontend**: Angular, Frontend Development, Frontend Frameworks
- **Media**: HbbTV, Media Encoding, Service Delivery Platforms
- **Domains**: AdTech, Addressable TV, GDPR, TCF, Consent Management, Third-Party System Integration

**Soft Skills**: Technical Leadership, Mentoring, Strategic Planning, Stakeholder Management, Risk Analysis, Hiring & Interviewing, Cross-Functional Collaboration, Change Management, Innovation Culture, Blameless Postmortems, Accountability, Adaptability, Analytical Thinking, Autonomy, Clear Communication, Coaching, Collaboration, Communication, Conflict Resolution, Continuous Improvement Mindset, Continuous Learning, Creativity, Cross-Functional Team Leadership, Culture Building, Curiosity, Customer Focus, Decision Making, Documentation, Empathy, Entrepreneurial Mindset, Executive Presence, Executive Stakeholder Management, Feedback Delivery, Flexibility, Growth Mindset, Influence, Initiative, Innovation, Interpersonal Skills, Leadership, Ownership, People Management, Performance Management, Presentation Skills, Prioritization, Problem Solving, Product Mindset, Project Management, Relationship Building, Requirements Analysis, Resourcefulness, Self-Motivation, Stakeholder Communication, Stakeholder Engagement, Strategic Alignment, Strategic Leadership, Strategic Thinking, Team Building, Team Collaboration, Team Development, Team Leadership, Team Management, Technical Advisory, Technical Communication, Thought Leadership, Written Communication

---

## Context for Generation

### Role Summary
Technical Lead driving platform modernization, architectural excellence, and team development at Seven.One Entertainment Group (ProSiebenSat.1 subsidiary). Responsible for AdTech platform serving millions of impressions daily across German broadcast TV digital properties.

### Key Technologies
| Category | Technologies |
|----------|--------------|
| Cloud | AWS Lambda, ECS, EventBridge, S3, CloudFront |
| Languages | TypeScript, JavaScript, Python |
| Architecture | DDD, Event-Driven, Microservices, CQRS |
| Data | OpenSearch, Redis |
| Infrastructure | Terraform, Serverless Framework |
| Compliance | GDPR, TCF, CMP |

### Business Context
- **Company**: Seven.One Entertainment Group (ProSiebenSat.1 Media)
- **Domain**: Addressable TV advertising technology
- **Scale**: Millions of daily ad impressions
- **Challenge**: Maintaining revenue growth despite declining linear TV viewership
- **Regulatory**: GDPR/TCF compliance with BLM oversight

### Leadership Scope
- 10+ engineers mentored
- 3 engineers promoted to lead
- Cross-functional matrixed teams
- Multi-year transformation ownership
- €30M revenue responsibility (compliance)

---

## LinkedIn Consistency Check

- [x] Technical Lead title and tenure
- [x] Platform transformation scope
- [x] AWS/serverless architecture
- [x] DDD and microservices
- [x] Team leadership numbers
- [x] GDPR/compliance work

---

## Selection Guide by JD Type

| JD Emphasis | Recommended Achievements |
|-------------|-------------------------|
| Platform/Modernization | 1, 2 (transformation, architectural runway) |
| Architecture/Design | 1, 3, 4 (microservices, observability, DDD) |
| Leadership/Management | 4, 9, 10, 11 (DDD standards, mentoring, culture, hiring) |
| AWS/Cloud | 1, 3, 7 (Lambda/ECS, observability, scaling) |
| Data/Analytics | 3 (observability pipeline) |
| Compliance/Regulatory | 5 (GDPR/TCF) |
| Strategy/Vision | 2, 6, 14 (runway, business alignment, risk) |
| DevOps/CI/CD | 8, 12 (monitoring, deployment) |
| AdTech/Media | 6, 13 (impression growth, SME) |
| Culture/Mentoring | 9, 10 (team development, Lean Friday) |
| Scaling/Performance | 7 (auto-scaling, bursty traffic) |
| Process/Agile | 4, 8, 12 (DDD, postmortems, atomic deploys) |

---

## Interview Preparation Notes

### Flagship Stories (Know Cold)

1. **Platform Transformation** (Achievement 1)
   - Why event-driven over request-response
   - EventBridge choreography patterns
   - Zero downtime migration strategy
   - 75% incident reduction measurement

2. **GDPR/TCF Compliance** (Achievement 5)
   - TCF framework explanation
   - CMP architecture decisions
   - BLM audit process
   - €30M revenue protection calculation

3. **DDD Introduction** (Achievement 4)
   - How bounded contexts were identified
   - Ubiquitous language workshops
   - Onboarding time measurement
   - Velocity improvement calculation

### Metrics to Defend

| Metric | Source/Calculation |
|--------|-------------------|
| 75% incident reduction | Before/after incident tracking |
| 3 years zero downtime | Monitoring system records |
| 6→3 months onboarding | New hire time-to-productivity |
| 25% velocity improvement | Sprint burndown comparison |
| 40% requirement misalignment reduction | Rework tracking |
| €30M revenue protection | Annual advertising revenue exposure |
| 60% MTTR reduction | Incident resolution time tracking |
| 15% YoY impression growth | Business metrics dashboards |
