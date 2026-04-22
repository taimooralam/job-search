# Priority Sorting Logic

Sort jobs for maximum ROI. Lower score = higher priority. Categories aligned with `scripts/scout_linkedin_jobs.py` SEARCH_PROFILES and REGION_CONFIGS.

## Priority Tiers

| Tier | Score | Label | Criteria |
|------|-------|-------|----------|
| 1 | 0 | REM | Fully remote |
| 2 | 10 | AI | AI role (title/is_ai_job/ai_categories) |
| 3 | 12 | LEAD | Leadership: Engineering Manager, Head of Engineering, VP Engineering, Director of Engineering, CTO, etc. |
| 4 | 14 | STAFF | Staff/Principal: Staff Engineer, Principal Engineer, Staff Architect, Distinguished Engineer |
| 5 | 16 | TL | Tech Lead: Tech Lead, Technical Lead, Lead Engineer, Engineering Lead, Team Lead |
| 6 | 18 | E+AI | EMEA + AI role (boosted) |
| 7 | 20 | EMEA | EMEA region |
| 8 | 25 | G+AI | Gulf + AI role (boosted) |
| 9 | 30 | GULF | UAE / KSA / GCC |
| 10 | 40 | GLOB | Global / other |

Within each tier: sort by `cv_generated_at` descending (most recent first).

**Cross-cutting boosts:**
- AI roles in geo tiers (EMEA/Gulf/Global) get -5 bonus
- Leadership/Staff/TL roles that are also AI get the AI tier (10) instead — AI always wins

## Detection Patterns

### Remote
```python
REMOTE = re.compile(r'\bremote\b|\bfully remote\b|\b100% remote\b|\bwork from anywhere\b|\bwfh\b|\bwork from home\b|\bdistributed\b|\banywhere\b', re.I)
```
Search in: title, location, description, extracted_jd.remote_policy

### AI Roles (from scout SEARCH_PROFILES["ai"] + ["ai_leadership"])
Title keywords: AI Engineer, AI Architect, AI Lead, GenAI Engineer, LLM Engineer, Agentic AI Engineer, Applied AI Engineer, Head of AI, AI Tech Lead, Tech Lead AI, Engineering Lead AI, Director of AI, VP of AI, Chief AI Officer, AI Engineering Manager, Head of Artificial Intelligence, Head of GenAI, AI Director, Head of Machine Learning, Director AI Engineering

Broad signals: `\bAI\b`, `\bLLM\b`, `\bmachine learning\b`, `\bNLP\b`, `\bGenAI\b`, `\bdeep learning\b`, `\bRAG\b`, `\bagentic\b`, `\bGPT\b`

Also check: `is_ai_job` field, `ai_categories` array

### Leadership Roles (score 12)
Title keywords: Engineering Manager, Head of Engineering, VP Engineering, VP of Engineering, Director of Engineering, Director Engineering, CTO, Chief Technology Officer, Head of Technology, Head of Platform, Engineering Director, SVP Engineering

### Staff/Principal Roles (score 14)
Title keywords: Staff Engineer, Staff Software Engineer, Principal Engineer, Principal Software Engineer, Staff Architect, Distinguished Engineer, Staff Backend Engineer, Staff Frontend Engineer, Staff Platform Engineer, Staff ML Engineer, Staff AI Engineer

### Tech Lead Roles (score 16)
Title keywords: Tech Lead, Technical Lead, Lead Engineer, Lead Software Engineer, Engineering Lead, Team Lead, Lead Backend Engineer, Lead Frontend Engineer, Lead Platform Engineer, Lead Architect

**Note:** If a role matches both a seniority tier AND AI, use the AI tier (10) — AI is always higher priority.

### EMEA (from scout REGION_CONFIGS["emea"])
Countries: Germany, Netherlands, France, Belgium, Austria, Sweden, Denmark, Norway, Finland, Iceland, Italy, Spain, Portugal, Greece, Estonia, Latvia, Lithuania, Ireland, Switzerland, Turkey, United Kingdom, South Africa

Cities: Berlin, London, Amsterdam, Paris, Madrid, Lisbon, Dublin, Brussels, Vienna, Zurich, Stockholm, Copenhagen, Oslo, Helsinki, Milan, Munich, Hamburg, Frankfurt, Barcelona, Prague, Warsaw, Bucharest, Budapest, Athens, Luxembourg, Istanbul

### Gulf (from scout REGION_CONFIGS["mena"] + ["gcc_priority"])
Countries/cities: UAE, Dubai, Abu Dhabi, Saudi Arabia, KSA, Riyadh, Jeddah, Dammam, Qatar, Doha, Kuwait, Bahrain, Manama, Oman, Muscat, Morocco, Sharjah

## AI Cross-Tier Boost
If a job is AI-related AND in a geo tier (EMEA/Gulf/Global), subtract 5 from its tier score. This promotes "AI Engineer in Dubai" above "SWE Manager in Dubai".

## Display Format
```
 # | Pri  | Company | Title | Location | AI? | CV Generated
---|------|---------|-------|----------|-----|-------------
 1 | REM  | ACME    | AI Eng | Remote  | Yes | 2026-04-03
```

Ask: **"Proceed with these {N} jobs? (y/n/pick numbers)"**
