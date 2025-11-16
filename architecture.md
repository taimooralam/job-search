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
- Extracts 3-5 key challenges/requirements the company wants to solve
- Outputs bullet points of main technical problems and responsibilities

### 3. Company + Role Researcher (Layer 3)
- Uses FireCrawl to scrape company websites, About pages, news
- Gathers context: what the company does, products, size, recent events
- May use LLM for general knowledge about company/role
- Creates concise company profile

### 4. Opportunity Mapper (Layer 4)
- Takes candidate's "knowledge graph" (your skills/experience profile)
- Maps your background to each pain point from Layer 2
- LLM generates tailored fit analysis: "How you solve their problems"
- Produces match scoring (likely the "score: 85" in your sample.json)

### 5. People Mapper (Layer 5)
- Identifies key people for outreach (hiring managers, recruiters, referrals)
- Uses LinkedIn search via FireCrawl or LinkedIn API
- *Currently optional/placeholder for future implementation*

### 6. Outreach Generator (Layer 6)
- Synthesizes outputs from Layers 2-5
- LLM drafts personalized cover letter/email
- References specific pain points, company insights, and your fit
- Professional yet enthusiastic tone

### 7. Output Publisher (Layer 7)
- Creates tailored CV (.docx) customized for the specific job
- Uploads CV to Google Drive (specific folder)
- Updates Google Sheets tracking log (date, company, role, match score, links)
- Sends notifications (Telegram or email) for high-priority matches

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
