# Job-Intelligence Workflow System Summary

## System Architecture
You have a **7-layer AI job-intelligence pipeline** that automates personalized job application preparation using **LangGraph** for orchestration. The workflow is stateful, durable, and integrates multiple AI/web services.

## The 7 Layers (Your Process)

### 1. Input Collector (Layer 1)
- Gathers job postings from sources (LinkedIn initially, expandable to Indeed, etc.)
- Jobs stored in MongoDB Atlas with rich metadata (as shown in your sample.json: embeddings, scores, job descriptions)
- Can process jobs from DB or via direct URL input

### 2. Pain-Point Miner (Layer 2)
- Uses LLM (GPT-4) to analyze job descriptions
- Extracts structured pain point analysis:
  - **Pain Points**: 3-5 key challenges/requirements
  - **Strategic Needs**: Business objectives behind the hire
  - **Risks if Unfilled**: What company loses without this role
  - **Success Metrics**: How success will be measured
- Outputs comprehensive pain point dossier section

### 3. Company + Role Researcher (Layer 3)
- **Company Overview**: FireCrawl scrapes company websites, About pages, LinkedIn, news
  - Summary (2-3 sentences)
  - Key Signals (acquisitions, growth, funding, leadership changes)
  - Industry classification
  - Keywords for context
- **Role Research**: Analyzes the specific position
  - Summary of role's business impact
  - "Why Now": Timing significance based on company signals
  - Key skills emphasized
  - Business impact of the role
- Creates rich company + role profile with timing intelligence

### 4. Opportunity Mapper (Layer 4)
- **Hiring Reasoning**: Why this role exists now (based on company signals)
- **Timing Significance**: Why hiring at this specific moment
- **Company Signals**: Acquisitions, growth milestones, product launches that drove the need
- Maps candidate profile to pain points with strategic context
- Produces match scoring (0-100 with rationale)

### 5. People Mapper (Layer 5)
- Identifies **Primary Contacts** (CEO, hiring managers, department heads)
- Identifies **Secondary Contacts** (team members, adjacent roles)
- For EACH person, gathers:
  - Name, role, LinkedIn URL
  - Generates personalized **LinkedIn message** (150-200 chars)
  - Generates personalized **email template** (3-4 paragraphs)
  - Includes **reasoning summary** for why this outreach works
- Outputs per-person outreach intelligence

### 6. Outreach Generator (Layer 6)
- Synthesizes ALL prior layers (pain points, company signals, timing, fit analysis)
- Generates **general cover letter** (not person-specific)
- Creates **tailored CV** with job-specific summary paragraph
- Professional, signal-aware tone that references recent company news

### 7. Output Publisher (Layer 7)
- Generates **Opportunity Dossier** (comprehensive markdown/text report with all sections 1-10)
- Creates **tailored CV** (.docx) customized for the specific job
- Uploads dossier + CV to Google Drive: `/applications/<company>/<role>/`
- Updates Google Sheets tracking log (date, company, role, match score, Drive links, status)
- Sends notifications (Telegram or email) for high-priority matches
- Stores run metadata and validation timestamps in MongoDB

## Output Format: Opportunity Dossier

The final output is a comprehensive **Opportunity Dossier** containing:

1. **Job Summary**: Role, company, location, score, URLs, posting metadata
2. **Job Requirements/Criteria**: Seniority, employment type, job function, industries
3. **Company Overview**: Summary, key signals, industry, keywords
4. **Opportunity Mapper**: Hiring signals, reasoning, timing significance
5. **Role Research**: Summary, "why now", key skills, business impact
6. **Pain Point Analysis**: Pain points, strategic needs, risks if unfilled, success metrics
7. **People & Outreach Mapper**:
   - Primary contacts (4-6 people) with LinkedIn + email templates each
   - Secondary contacts (4-6 people) with LinkedIn + email templates each
   - Each contact includes: name, role, URL, subject line, message, reasoning
8. **Notes**: Hiring manager info, talent acquisition team, additional context
9. **Firecrawl/Opportunity Queries**: Search queries used for research
10. **Validation & Metadata**: Validation status per section, timestamps, source, dedup key

## Technical Stack

- **Workflow Engine**: LangGraph (for stateful, resumable multi-step execution)
- **LLM**: OpenAI GPT-4/3.5 via LangChain
- **Web Scraping**: FireCrawl API (gets original job descriptions, company info)
- **Database**: MongoDB Atlas (stores scraped jobs with embeddings)
- **Job Data Model**: Your sample.json shows jobs have:
  - Embeddings (large: 3072-dim, small: 1536-dim) for semantic search
  - Score field (0-100 match rating)
  - Structured fields: title, company, description, criteria, source, URLs
  - Deduplication keys
- **Output**: Google Drive (CV storage), Google Sheets (application tracking), python-docx (CV generation)
- **Notifications**: Telegram/email for high-scoring matches

## Why LangGraph Over Static Workflows (like n8n)

- **Durability**: Can pause/resume if steps fail (e.g., scraping blocks, CAPTCHA)
- **Complex Logic**: Handles conditional branches, loops through multiple jobs, retries
- **LLM Integration**: Native LangChain integration for tools and models
- **Scalability**: Easier to add new job sources, monitoring via LangSmith
- **State Management**: Passes enriched state through each node

## Key Workflow Features

- **Node-Based Design**: Each layer = one or more nodes that take state, perform task, return updates
- **Sequential Flow**: Mostly linear with potential conditional edges (skip steps if data unavailable)
- **Candidate Profile**: Your "knowledge graph" (detailed experience/skills) fed into multiple nodes
- **Original JD Fetching**: Uses FireCrawl to find full job posting (follows "Apply" links or Google search)
- **Scoring System**: LLM-based rubric (from your n8n workflow) rates match quality

## Current vs Future State

### Currently Implemented (n8n version)
- Has the full 7-layer concept
- Uses custom LLM rubric for scoring
- Outputs to Google ecosystem

### LangGraph Migration Goals
- More resilient (handle failures gracefully)
- CLI-friendly initially, then VPS-deployed persistent service
- Extensible to multiple job platforms
- Better observability and debugging
