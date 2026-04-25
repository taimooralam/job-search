# TAIMOOR ALAM
taimooralam.com · linkedin.com/in/taimooralam · github.com/taimooralam
### Principal Engineer, Generative & Agentic AI
*alamtaimoor.de@gmail.com · +49 176 2979 3925 · Nationality: German*

**PROFESSIONAL SUMMARY**

Platform architect with 10+ years modernizing distributed systems (10x horizontal scaling, deployment cycles from weeks to days), applying infrastructure depth to production AI/MLOps with agentic tool-calling workflows, RAG pipelines, and sub-200ms semantic caching at enterprise scale.

• Built agentic AI architecture for Commander-4 enterprise platform with 5 MCP server tools, Zod-validated structured outputs for tool-calling workflows, and per-silo guardrail profiles via LiteLLM proxy across 42 plugins serving 2,000 users
• Engineered production RAG pipeline with hybrid retrieval (BM25 + RRF fusion k=60), LLM-as-judge reranking via Claude Sonnet, and two-tier semantic caching (L1 SHA-256 ~2ms, L2 S3 Vectors cosine ≥0.95 ~200ms) with evaluation harness (MRR@k, NDCG@k)
• Architected multi-provider LLM gateway (Lantern) with routing across OpenAI/Anthropic/Azure, Qdrant vector database for semantic caching, and eval-driven quality gates reducing redundant API spend by 40%
• Designed event-driven streaming architecture from distributed microservices to OpenSearch, enabling real-time operational dashboards
• Drove AWS-native architecture modernization eliminating 2015-era callback hell through TypeScript microservices with CloudFront caching, EventBridge choreography, and observability pipeline
• Architected AWS auto-scaling infrastructure for bursty traffic using Lambda and ECS, reducing missed impressions by 20%
• Drove Jenkins to GitLab CI migration enabling faster automated deployments and reducing release cycles from weeks to days
• Established CloudWatch and SNS-based monitoring system with Slack alerting integration, significantly reducing MTTR as part of platform reliability transformation

**CORE COMPETENCIES**
**Agentic AI & LLMs:** RAG Pipelines, Agent Frameworks (MCP), Tool Calling, Structured Outputs, Prompt Engineering, LLM Integration, Multi-Provider Routing, Semantic Caching, Guardrail Profiles
**MLOps & Production AI:** Model Evaluation (MRR, NDCG), Vector Databases (S3 Vectors, Qdrant), Hybrid Retrieval (BM25, RRF), LLM-as-Judge, Production Deployment, A/B Testing, Enterprise AI Platform
**System Architecture:** Microservices, CQRS, Domain-Driven Design, Event-Driven Architecture, REST, OpenSearch, RabbitMQ
**Cloud Platform:** AWS (Lambda, ECS, S3, CloudFront, EventBridge), Azure (LLM endpoints), Observability, LiteLLM Gateway
**Technical Excellence:** Python, TypeScript, JavaScript, Node.js, System Architecture, Data Pipeline, CI/CD, JIRA, Documentation

**PROFESSIONAL EXPERIENCE**

**Seven.One Entertainment Group • Technical Lead (Addressable TV & AI Platform)** | Munich, DE | 2020–Present

• Built agentic AI architecture for Commander-4 (Joyia) enterprise platform with 5 MCP server tools for external integrations, Zod schema validation for structured LLM outputs enabling type-safe tool-calling workflows, and composable guardrail profiles with per-silo injection via LiteLLM proxy across 42 workflow plugins
• Engineered production RAG pipeline combining hybrid retrieval (BM25 scoring from scratch on S3 Vectors with RRF fusion k=60), LLM-as-judge reranking via Claude Sonnet/LiteLLM with parallel Promise.all, and two-tier semantic caching (L1 exact-match SHA-256 ~2ms, L2 S3 Vectors cosine ≥0.95 ~200ms)
• Implemented MLOps practices including retrieval evaluation harness with MRR@k and NDCG@k scoring functions (14 unit tests), document ingestion pipeline with SHA-256 change detection for incremental updates, and RAPTOR hierarchical indexing for multi-granularity retrieval across Confluence/Jira knowledge base
• Scaled AWS infrastructure for bursty traffic using Lambda and ECS auto-scaling, reducing missed impressions by 20%
• Eliminated 2015-era callback hell and anti-patterns (app-level log aggregation, code-level caching) by migrating to TypeScript microservices with AWS-native infrastructure (CloudFront caching, EventBridge choreography, observability pipeline)
• Designed event streaming architecture from distributed microservices to OpenSearch, enabling real-time operational dashboards
• Facilitated Jenkins to GitLab CI migration, enabling faster automated deployments and reducing release cycles from weeks to days
• Implemented CloudWatch and SNS-based monitoring system with Slack alerting integration, significantly reducing MTTR as part of platform reliability transformation
**Skills:** Python, TypeScript, RAG, Agent Frameworks (MCP), Vector Databases (S3 Vectors), LLM Integration, Semantic Caching, Tool Calling, Microservices, Domain-Driven Design, Event-Driven Architecture, CQRS, MLOps, Production AI

**PROJECTS**

**Lantern — Multi-Provider LLM Gateway** | github.com/taimooralam/lantern

• Architected multi-provider LLM gateway with LiteLLM routing/fallback across OpenAI, Anthropic, and Azure endpoints, Qdrant vector database for semantic caching, and eval-driven quality gates scoring responses against golden-set references
• Provisioned production observability stack (Prometheus, Grafana, Langfuse tracing) with GitHub Actions CI demonstrating MLOps deployment practices
• Built semantic caching layer using Redis + Qdrant vector similarity reducing redundant API spend by ~40% in testing
**Stack:** Python, FastAPI, LiteLLM, Redis, Qdrant, Docker, Prometheus, Grafana

**Samdock (Daypaio) • Lead Software Engineer** | Munich, DE | 2019–2020

• Built CI/CD pipeline reducing deployment time from hours to minutes, enabling daily releases
• Built multi-tenant CQRS foundation on GCP using NestJS, EventStore, and MongoDB with RxJS pub/sub patterns—enabling 10x horizontal scaling
• Implemented CQRS/event-sourcing architecture with NestJS and EventStore for multi-tenant CRM platform
• Designed RESTful APIs with Swagger/OpenAPI documentation enabling 50% faster partner integrations
• Created reusable Angular component library standardizing UI development across platform
• Event storming leadership—domain discovery from stakeholder workshops to technical model
**Skills:** Microservices, TypeScript, JavaScript, Node.js, NestJS, EventStore, CQRS, Event-Driven Architecture

**KI Labs • Intermediate Backend Engineer** | Munich, DE | 2018–2019

• Built Flask REST APIs over large-scale data pipeline using onion architecture with JWT authentication
• Built Swagger/OpenAPI documentation system for REST APIs improving developer experience
• Built pytest-based multi-layered test suite (unit, E2E, snapshot) for API contract verification, reducing production incidents by 35%
• Optimized MongoDB data layer achieving 60% query response time reduction
• Bi-weekly sprint delivery with consistent quality in consulting environment
**Skills:** Python, Microservices, AWS, Flask, REST API, JWT, APIs, MongoDB

**Fortis (Research Project) • Backend Engineer** | Munich, DE | 2018

• Built microservices backend in Node.js with well-defined service interfaces for research platform
• Implemented RabbitMQ pub/sub messaging enabling asynchronous communication between microservices
• Defined API standards with Swagger/OpenAPI documentation ensuring interface consistency across services
• SCRUM collaboration with research client demos and feedback integration
**Skills:** Microservices, JavaScript, Node.js, SQL, RabbitMQ, Pub/Sub, Event-Driven Architecture, MongoDB

**OSRAM • Software Engineer (IoT)** | Munich, DE | 2016–2018

• Enhanced Erbium CoAP implementation with OSCOAP security features enabling secure multicast communication in IoT lighting networks
• Designed and developed cross-platform Qt/C++ application with QML interface controlling IoT lighting systems via CoAP protocol across mobile and desktop platforms
• Developed Python-based CoAP server acting as CoAP-to-UDP translation middleware, enabling seamless integration of non-CoAP third-party devices
• Developed OpenAIS-compliant CoAP server in Python establishing reusable template adopted by multiple team projects
• Integrated OSRAM legacy lighting products and firmware with modern CoAP OpenAIS ecosystem, ensuring backward compatibility
• Created comprehensive development and installation documentation that became team reference material
**Skills:** Python, C++, C, Qt, CoAP, OSCOAP, UDP, REST

**Clary Icon • Software Engineer** | Islamabad, PK | 2014–2016

• Delivered features across Node.js backend, Qt C++ desktop, and C# WPF desktop platforms within unified video conferencing product
• Reverse-engineered OpenPhone SIP client and extended functionality using Qt C++ widget framework for enhanced call management
• Created C# WPF tutorial system with synthetic voice narration and visual annotations guiding users through video conferencing setup
• Engineered Node.js playback service with WebSocket-based timestamp synchronization handling concurrent video streams for multi-party call replay
• Developed WebRTC video recording system using Licode media server, custom REST APIs, and FFmpeg transcoding pipeline for multi-party call capture
• Enabled compliance and quality review workflows through synchronized multi-party call playback with frame-accurate alignment
**Skills:** JavaScript, Node.js, C++, C#, SQL, WPF, Licode, WebRTC

**EDUCATION & CERTIFICATIONS**
• M.Sc. Computer Science — Technical University of Munich
• B.Sc. Computer Software Engineering — GIK Institute
• AWS Essentials
• ECS & Multi-Region LB
• Data Scientist's Toolbox
• R Programming

**LANGUAGES**
English (C1), German (B2), Urdu (Native)