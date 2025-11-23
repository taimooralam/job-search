# Phase 5 – Layer 3: Company & Role Researcher

This document expands **Phase 5** of the roadmap and explains how the Company Researcher and Role Researcher (Layer 3) are designed and implemented to meet the **requirements** and **architecture**.

It covers:

1. Objectives and scope  
2. Inputs, outputs, and data contracts  
3. Company Researcher design  
4. Role Researcher design  
5. Caching, rate limits, and reliability  
6. Alignment with `requirements.md` and `architecture.md`  
7. Testing and quality gates  

---

## 1. Objectives and Scope

**Goal:** Provide rich, accurate context about the company and role that:

- Grounds pain points in real-world company signals.  
- Enables highly targeted fit analysis and outreach.  
- Avoids hallucinations by using scraped web data with strict constraints.  

Layer 3 is split into:

- **Company Researcher** – multi-source company scraping and signal extraction.  
- **Role Researcher** – role- and team-specific context and “why now” narrative.  

Phase 5 corresponds to:

- Phase 5 roadmap items:
  - 5.1 Company Researcher with Multi-Source Scraping  
  - 5.2 Role Researcher  
- The **Company + Role Researcher** section in `architecture.md`.  
- The **Analysis layers** and **FireCrawl with caching** requirements in `requirements.md`.  

---

## 2. Inputs, Outputs, and Data Contracts

### 2.1 Inputs

- `JobState` fields:
  - `company`
  - `title`
  - `location`
  - `pain_points`, `strategic_needs`, `risks_if_unfilled`, `success_metrics` (from Layer 2)
  - Optional: `industry`, `job_url`, other DB metadata.
- Global configuration:
  - FireCrawl base URL and API key.
  - MongoDB `company_cache` TTL configuration.

### 2.2 Outputs

The layer writes:

- `JobState.company_research`:

  ```python
  CompanyResearch = TypedDict(
      "CompanyResearch",
      {
          "summary": str,
          "signals": List[Dict[str, str]],  # type, description, date, source
          "url": str,
      },
  )
  ```

- `JobState.role_research`:

  ```python
  RoleResearch = TypedDict(
      "RoleResearch",
      {
          "summary": str,
          "business_impact": List[str],  # 3-5 bullets
          "why_now": str,
      },
  )
  ```

These outputs feed:

- **Layer 4 (Opportunity Mapper)** – uses company signals and role context in fit analysis.
- **Layer 5 (People Mapper)** – uses company signals to identify relevant contacts.
- **Layer 6 (Outreach & CV)** – uses company and role context for narrative and timing.

---

## 3. Company Researcher (`src/layer3/company_researcher.py`)

### 3.1 Responsibilities

The Company Researcher:

- Uses multiple FireCrawl queries per company.  
- Extracts key signals (funding, acquisitions, leadership, growth, etc.).  
- Summarizes what the company does and how it is positioned.  
- Caches results to avoid repeated scraping.  

### 3.2 Multi-Source Scraping

1. **Canonical company key**
   - Normalize the company name (lowercase, strip punctuation) to use as the cache key.

2. **Cache lookup**
   - Check MongoDB `company_cache` for an existing entry for this company.
   - If present and within TTL (~7 days), use cached data and skip scraping.

3. **FireCrawl queries**
   - For cache misses:
     - Run several FireCrawl searches:
       1. `${company} official site`
       2. `${company} LinkedIn`
       3. `${company} Crunchbase`
       4. `${company} news funding acquisition`
   - Respect rate limits:
     - Use concurrency controls and backoff.
     - Consider staggering requests if jobs share companies.

4. **Content aggregation**
   - For each query:
     - Extract cleaned text, title, and final URL.
   - Aggregate all text and metadata into a single “research bundle” object for the LLM.

### 3.3 Signal Extraction and Summarization

1. **LLM prompt for company signals**
   - Inputs:
     - Aggregated scraped text and URLs.
   - Instructions:
     - Identify signals:
       - Funding rounds (amount, date, investors).
       - Acquisitions (target, date, rationale).
       - Leadership changes.
       - Product launches.
       - Partnerships.
       - Growth indicators.
     - For each signal, output:

       ```json
       {
         "type": "funding" | "acquisition" | "leadership_change" | "product_launch" | "partnership" | "growth" | "other",
         "description": "...",
         "date": "YYYY-MM-DD or 'unknown'",
         "source": "<url>"
       }
       ```

     - Produce a **2–3 sentence summary** explaining what the company does and its market context.
     - If information is missing, use `"unknown"` instead of guessing.
     - Return JSON-only with separate `summary` and `signals` fields.

2. **Non-hallucination constraints**
   - LLM is explicitly told:
     - “Only use facts from the provided scraped text.”
     - “If a detail is not mentioned, mark it as unknown.”
   - This ensures we never invent funding rounds or acquisitions.

3. **State update & cache write**
   - Write:
     - `company_research.summary`
     - `company_research.signals`
     - `company_research.url` (canonical company URL, e.g., from official site).
   - Upsert the entire `company_research` object into `company_cache` with TTL.

---

## 4. Role Researcher (`src/layer3/role_researcher.py`)

### 4.1 Responsibilities

The Role Researcher:

- Focuses on the specific role at the company.  
- Understands responsibilities, KPIs, and cross-functional impact.  
- Synthesizes a **“why now”** narrative using company signals from the Company Researcher.  

### 4.2 FireCrawl Queries for Role Context

1. Build role-specific queries:
   - `"${title}" responsibilities ${company}`
   - `"${title}" KPIs ${industry}` (if industry known).
   - Additional targeted queries as needed.

2. Scrape and aggregate:
   - Use FireCrawl to fetch result pages.
   - Clean and aggregate text into a role-focused research bundle.

### 4.3 LLM Prompt for Role Summary and Business Impact

1. **Inputs**
   - Role research bundle.
   - `JobState.pain_points`, `strategic_needs`.
   - `company_research.signals`.

2. **Instructions**
   - Produce:
     - `summary`: 2–3 sentences that describe:
       - Scope and responsibilities.
       - Where this role sits in the organization.
     - `business_impact`: 3–5 bullet points that describe:
       - How the role drives company outcomes (revenue, risk reduction, efficiency, etc.).
     - `why_now`: 1–2 sentences explicitly linking:
       - The role to at least one company signal (e.g., funding, expansion, leadership change) and relevant pain points.
   - Constraints:
     - No invented responsibilities beyond what can be reasonably inferred from standard role patterns and provided text.
     - No fabricated company events; reuse only `company_research.signals`.
   - Output JSON-only with the `RoleResearch` structure.

3. **State update**
   - Write the validated `RoleResearch` object into `JobState.role_research`.

---

## 5. Caching, Rate Limits, and Reliability

- **Company-level caching**:
  - `company_cache` ensures repeated jobs for the same company reuse research.
  - TTL of ~7 days balances freshness and cost.

- **Job-level efficiency**:
  - Multiple jobs for the same company in a batch should share the same `company_research`, reducing calls.

- **Rate-limit handling**:
  - FireCrawl calls use backoff and concurrency limits.
  - LLM calls also use retry decorators with exponential backoff.

- **Graceful degradation**:
  - If scraping fails entirely:
    - Use a conservative fallback:
      - Minimal `company_research` with `summary = "unknown"` and empty signals list.
      - Minimal `role_research` based on the job description only.
    - Record structured errors in `JobState.errors`.

This approach keeps the system robust even under network or scraping failures.

---

## 6. Alignment with `requirements.md`

Phase 5 fulfills:

- **Analysis layers**:
  - Provides the company and role research described as Layer 3 in the core pipeline.

- **FireCrawl with caching**:
  - Implements multi-source scraping, caching in `company_cache`, and TTL controls.

- **People & profile research**:
  - Supplies company and role context to the People Mapper (Layer 5) so contacts can be framed correctly.

- **Generation & output**:
  - Enables dossiers, cover letters, and CVs to reference concrete company events and role expectations rather than generic statements.

---

## 7. Alignment with `architecture.md`

In the architecture:

- The **Company Researcher**:
  - Uses multiple queries and signal extraction to populate `company_research.summary` and `company_research.signals`.
  - Enforces non-hallucination via context-only rules and “unknown” markers.

- The **Role Researcher**:
  - Builds role-specific context and “why now” narratives using company signals.
  - Directly supports the “pain → proof → plan” pattern in downstream layers.

Phase 5 thus connects external reality (web data) to internal reasoning (pain points, STARs) in a controlled, cache-friendly way.

---

## 8. Testing and Quality Gates

1. **Company Researcher tests**
   - Mock FireCrawl responses for:
     - Companies with rich signals.
     - Companies with almost no public information.
   - Validate:
     - Signal extraction schema.
     - Use of `"unknown"` when data is absent.
     - Cache hit behavior and TTL expiration.

2. **Role Researcher tests**
   - Mock role research bundles and company signals.
   - Verify:
     - `business_impact` has 3–5 concrete, role-specific bullets.
     - `why_now` references at least one `company_research.signal` when available.

3. **End-to-end checks**
   - For 5 test companies and roles:
     - Ensure outputs are plausible and grounded.
     - Confirm no hallucinated funding rounds, acquisitions, or leadership changes appear.

These gates ensure Layer 3 is both informative and safe to build on.

