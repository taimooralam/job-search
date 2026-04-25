# TAIMOOR ALAM
taimoor.alam12@gmail.com · +49 176 2979 3925 · Nationality: German
linkedin.com/in/taimooralam · github.com/taimooralam

### Software Architect – Cloud, AI & Distributed Systems

**PROFESSIONAL SUMMARY**

System architect with 10+ years driving infrastructure evolution (20% performance gains, weeks-to-days releases) and implementing research-informed retrieval algorithms with custom BM25 scoring and evaluation metrics.

• Architected AWS-native microservices infrastructure eliminating 2015-era anti-patterns (callback hell, app-level log aggregation, code-level caching), implementing Event-Driven architecture with CloudFront caching and EventBridge choreography
• Architected event-driven CRM platform from scratch using CQRS and EventStore, enabling real-time data consistency across microservices and scaling to 25 paying tenants within startup timeline
• Designed domain-driven architecture balancing startup agility with enterprise scalability, enabling 10x growth through careful trade-off analysis and architectural decision-making
• Architected AWS infrastructure for bursty traffic patterns using Lambda and ECS auto-scaling, reducing missed impressions by 20%
• Designed AWS observability infrastructure with CloudWatch and SNS alerting, significantly reducing MTTR through platform reliability transformation
• Optimized data layer queries through indexing strategies and query pattern analysis, achieving 60% response time reduction

**CORE COMPETENCIES**
**System Architecture:** Microservices, Event-Driven Architecture, Domain-Driven Design, CQRS, CRM, Distributed Systems, ORM
**Programming Languages:** C++, C#, Python, JavaScript, TypeScript, Node.js, C, SQL
**Cloud & Infrastructure:** AWS, Lambda, ECS, EventBridge, CloudFront, S3, MySQL, MongoDB, NoSQL
**Development & Tools:** Git, CI/CD, REST APIs, WebSocket, Middleware, Qt, WPF, RabbitMQ, Flask, NestJS
**AI & LLM:** RAG, Hybrid Search, BM25, Vector Search, Semantic Caching, LiteLLM, MCP, Zod
**Practices:** Agile, GDPR, JWT, Blameless Postmortems, Observability, E2E Testing, Code Review

**PROFESSIONAL EXPERIENCE**

**Seven.One Entertainment Group • Technical Lead (Addressable TV)** | Munich, DE | 2020–Present

• Scaled AWS infrastructure for bursty traffic using Lambda and ECS auto-scaling, reducing missed impressions by 20%
• Eliminated 2015-era callback hell and anti-patterns (app-level log aggregation, code-level caching) by migrating to TypeScript microservices with AWS-native infrastructure (CloudFront caching, EventBridge choreography, observability pipeline)
• Facilitated Jenkins to GitLab CI migration, enabling faster automated deployments and reducing release cycles from weeks to days
• Implemented CloudWatch and SNS-based monitoring system with Slack alerting integration, significantly reducing MTTR as part of platform reliability transformation
• Implemented hybrid retrieval with BM25 scoring from scratch for S3 Vectors (no inverted index available) and RRF fusion (k=60)
• Built LLM-as-judge reranking via Claude Sonnet/LiteLLM with parallel Promise.all execution
• Architected two-tier semantic cache: L1 sha256 exact-match (~2ms) and L2 S3 Vectors cosine similarity (≥0.95, ~200ms) with custom S3VectorSemanticCache in Python
• Developed MRR@k/NDCG@k retrieval evaluation functions with 14 unit tests for search quality validation
**Skills:** Microservices, TypeScript, JavaScript, Python, Domain-Driven Design, Event-Driven Architecture, CQRS, System Architecture

**Samdock (Daypaio) • Lead Software Engineer** | Munich, DE | 2019–2020

• Implemented CQRS/event-sourcing architecture with NestJS and EventStore for multi-tenant CRM platform
• Built CI/CD pipeline reducing deployment time from hours to minutes, enabling daily releases
• Designed architecture balancing startup agility with enterprise scalability for 10x growth
• Designed RESTful APIs with Swagger/OpenAPI documentation enabling 50% faster partner integrations
• Created reusable Angular component library standardizing UI development across platform
• Built web-based SaaS CRM from scratch to production with 25 paying tenants within startup timeline
**Skills:** Microservices, TypeScript, JavaScript, Node.js, NestJS, EventStore, CQRS, Event-Driven Architecture

**KI Labs • Intermediate Backend Engineer** | Munich, DE | 2018–2019

• Optimized MongoDB data layer achieving 60% query response time reduction
• Built Flask REST APIs over large-scale data pipeline using onion architecture with JWT authentication
• Built Swagger/OpenAPI documentation system for REST APIs improving developer experience
• Built pytest-based multi-layered test suite (unit, E2E, snapshot) for API contract verification, reducing production incidents by 35%
• Bi-weekly sprint delivery with consistent quality in consulting environment
**Skills:** Microservices, AWS, Python, Flask, REST API, JWT, APIs, MongoDB

**Fortis (Research Project) • Backend Engineer** | Munich, DE | 2018

• Designed Node.js microservices architecture establishing service boundaries and communication contracts
• Implemented RabbitMQ pub/sub messaging enabling asynchronous communication between microservices
• Defined API standards with Swagger/OpenAPI documentation ensuring interface consistency across services
• Collaborated with research stakeholders through regular demonstrations and iterative feedback
**Skills:** Microservices, JavaScript, Node.js, SQL, RabbitMQ, Pub/Sub, Event-Driven Architecture, MongoDB

**OSRAM • Software Engineer (IoT)** | Munich, DE | 2016–2018

• Enhanced Erbium CoAP implementation with OSCOAP security features enabling secure multicast communication in IoT lighting networks
• Integrated OSRAM legacy lighting products and firmware with modern CoAP OpenAIS ecosystem, ensuring backward compatibility
• Developed OpenAIS-compliant CoAP server in Python establishing reusable template adopted by multiple team projects
• Developed Python-based CoAP server acting as CoAP-to-UDP translation middleware, enabling seamless integration of non-CoAP third-party devices
• Designed and developed cross-platform Qt/C++ application with QML interface controlling IoT lighting systems via CoAP protocol across mobile and desktop platforms
• Technical documentation reducing support overhead and onboarding friction
**Skills:** Python, C++, C, Qt, CoAP, OSCOAP, UDP, REST

**Clary Icon • Software Engineer** | Islamabad, PK | 2014–2016

• Created C# WPF tutorial system with synthetic voice narration and visual annotations guiding users through video conferencing setup
• Reverse-engineered OpenPhone SIP client and extended functionality using Qt C++ widget framework for enhanced call management
• Developed WebRTC video recording system using Licode media server, custom REST APIs, and FFmpeg transcoding pipeline for multi-party call capture
• Engineered Node.js playback service with WebSocket-based timestamp synchronization handling concurrent video streams for multi-party call replay
• Delivered features across Node.js backend, Qt C++ desktop, and C# WPF desktop platforms within unified video conferencing product
**Skills:** JavaScript, Node.js, C++, C#, SQL, WPF, Licode, WebRTC

**PROJECTS**

**Commander-4 (Joyia) — Enterprise AI Workflow Platform**
Enterprise AI workflow platform at ProSiebenSat.1 serving 2,000 users with 42 plugins
*Stack: TypeScript, Python, S3 Vectors, LiteLLM, Redis, DynamoDB, Vercel AI SDK, Zod, MCP*
• Designed governed structured-output architecture using Zod schema validation for all LLM responses, 5 MCP server tools for external integrations, and per-silo guardrail injection via LiteLLM proxy
• Implemented retrieval evaluation harness with MRR@k and NDCG@k scoring functions and two-tier semantic cache validated against 14 unit tests
• Built hybrid retrieval pipeline combining BM25 scoring with RRF fusion (k=60) and LLM-as-judge reranking via Claude Sonnet/LiteLLM
• Engineered document ingestion pipeline processing Confluence XML and Jira ADF with sentence-boundary chunking (500-token windows, 50-token overlap) and RAPTOR hierarchical indexing

**Lantern — LLM Quality Gateway**
Multi-provider LLM gateway with routing/fallback, semantic caching, and production observability
*Stack: FastAPI, Pydantic V2, LiteLLM, Redis, Qdrant, Docker Compose, Prometheus, Grafana | Python 3.11*
• Architected multi-provider LLM gateway with LiteLLM routing, model registry, request validation, and automatic fallback across OpenAI, Anthropic, and Azure endpoints
• Implemented eval-driven quality gates with golden-set evaluation, scoring LLM responses against reference outputs
• Provisioned full observability stack (Prometheus, Grafana, Langfuse tracing) with GitHub Actions CI for production-grade operations
• Built semantic caching layer using Redis + Qdrant vector similarity to deduplicate LLM calls

**EDUCATION & CERTIFICATIONS**
• M.Sc. Computer Science — Technical University of Munich
• B.Sc. Computer Software Engineering — GIK Institute
• AWS Essentials
• ECS & Multi-Region LB
• Data Scientist's Toolbox
• R Programming

**LANGUAGES**
English (C1), German (B2), Urdu (Native)