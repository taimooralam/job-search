# FireCrawl Contact Discovery: Analysis & Solution Design

## Executive Summary

**Problem**: FireCrawl API calls in the LangGraph pipeline fail with "not allowed to scrape" errors, while the same FireCrawl MCP server works perfectly in Claude Code.

**Root Cause**: Three critical differences:
1. **Query formulation** - Code uses verbose, conversational queries that return generic articles
2. **Response handling** - Code expects `markdown` content but FireCrawl search returns `{url, title, description}`
3. **No adaptive strategy** - Code runs one query and gives up; Claude runs multiple targeted searches

**Solution**: Implement an **AI-powered contact discovery agent** that mimics Claude Code's approach.

---

## Detailed Analysis

### What Works (Claude Code + MCP)

| Query Type | Example Query | Result Quality |
|------------|---------------|----------------|
| Site-specific | `site:linkedin.com/in Atlassian recruiter engineering` | Excellent - direct LinkedIn profiles |
| Boolean operators | `"Atlassian" "Head of Engineering" OR "VP Engineering" LinkedIn` | Excellent - engineering leadership |
| Simple keywords | `Atlassian engineering director VP LinkedIn` | Good - relevant results |

### What Fails (Current Code)

```python
# Current query (people_mapper.py:360-363)
query = (
    f"who are the best 5 people to send my cover letter to for {role_focus} at {company} "
    f"(hiring manager, department head, director/VP, recruiter, head of talent). "
    f"Return pages that show active team leads or recruiting contacts."
)
```

**Why it fails**:
- Search engines interpret "cover letter" as the topic → returns advice articles
- Natural language queries don't map well to SEO-optimized search
- Too many concepts in one query dilutes relevance

### What the Code Expects vs What FireCrawl Returns

```python
# Code expects (people_mapper.py:379-381):
markdown = getattr(result, 'markdown', None)  # Full page content
if markdown:
    return markdown[:1500]

# FireCrawl search ACTUALLY returns:
{
    "url": "https://www.linkedin.com/in/tanyach",
    "title": "Tanya Chen - VP | Head of Engineering @ Atlassian",
    "description": "VP | Head of Engineering @ Atlassian, ex-Meta, ex-Microsoft",
    "position": 1
}
```

**The title and description already contain all the contact information we need!**

---

## Recommended Solution: AI-Powered Contact Discovery Agent

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    Contact Discovery Agent                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Input: company_name, role_title, department                    │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Step 1: Generate Targeted Search Queries (LLM)          │   │
│  │  - Recruiter query: "site:linkedin.com/in {company}      │   │
│  │    recruiter {department}"                                │   │
│  │  - Leadership query: "{company} 'VP Engineering' OR      │   │
│  │    'Director Engineering' LinkedIn"                       │   │
│  │  - Team page query: "{company} engineering team page"    │   │
│  └──────────────────────────────────────────────────────────┘   │
│                           ↓                                      │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Step 2: Execute Parallel FireCrawl Searches             │   │
│  │  - Run 3-5 targeted searches concurrently                │   │
│  │  - Extract {url, title, description} from each           │   │
│  │  - NO scraping of LinkedIn (it's blocked)                │   │
│  └──────────────────────────────────────────────────────────┘   │
│                           ↓                                      │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Step 3: Parse & Structure Results (LLM)                 │   │
│  │  - Extract name from title: "Tanya Chen - VP..."         │   │
│  │  - Extract role from title/description                   │   │
│  │  - Validate company affiliation                          │   │
│  │  - Deduplicate across sources                            │   │
│  └──────────────────────────────────────────────────────────┘   │
│                           ↓                                      │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Step 4: Rank & Filter Contacts (LLM)                    │   │
│  │  - Score relevance to role (recruiter vs hiring mgr)     │   │
│  │  - Prioritize: Recruiter > Hiring Manager > VP > HR      │   │
│  │  - Return top 5 contacts with confidence scores          │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  Output: List[Contact] with name, title, linkedin_url, score    │
└─────────────────────────────────────────────────────────────────┘
```

### Option A: Fix Direct API (Recommended for Cost Efficiency)

**Pros**: Lower cost (fewer LLM calls), simpler implementation
**Cons**: Less adaptive than full agent

#### Implementation Changes

1. **Replace verbose queries with SEO-style queries**:

```python
# NEW: Targeted query patterns
QUERY_TEMPLATES = {
    "recruiters": 'site:linkedin.com/in "{company}" recruiter {department}',
    "leadership": '"{company}" "VP {department}" OR "Director {department}" OR "Head of {department}" LinkedIn',
    "hiring_manager": '"{company}" "{title}" hiring manager LinkedIn',
    "talent_acquisition": '"{company}" talent acquisition recruiter LinkedIn',
}
```

2. **Extract contacts from search metadata (not markdown)**:

```python
def _extract_contact_from_result(self, result: dict) -> Optional[Contact]:
    """Extract contact info from FireCrawl search result metadata."""
    title = result.get("title", "")
    description = result.get("description", "")
    url = result.get("url", "")

    # Parse name from LinkedIn title pattern: "Name - Title at Company"
    if "linkedin.com/in" in url:
        name_match = re.match(r"^([^-|]+)", title)
        name = name_match.group(1).strip() if name_match else None

        # Extract role from title or description
        role = self._extract_role(title, description)

        return Contact(name=name, role=role, linkedin_url=url, source="linkedin")

    return None
```

3. **Run multiple parallel searches**:

```python
async def discover_contacts(self, company: str, title: str, department: str) -> List[Contact]:
    """Run multiple targeted searches in parallel."""
    queries = [
        QUERY_TEMPLATES["recruiters"].format(company=company, department=department),
        QUERY_TEMPLATES["leadership"].format(company=company, department=department),
        QUERY_TEMPLATES["hiring_manager"].format(company=company, title=title),
    ]

    # Execute in parallel
    results = await asyncio.gather(*[
        self._search(query) for query in queries
    ])

    # Flatten and deduplicate
    contacts = []
    for result_set in results:
        for result in result_set:
            contact = self._extract_contact_from_result(result)
            if contact:
                contacts.append(contact)

    return self._deduplicate_and_rank(contacts)
```

4. **Use LLM for structured extraction (optional enhancement)**:

```python
def _parse_contacts_with_llm(self, search_results: List[dict], company: str) -> List[Contact]:
    """Use LLM to extract structured contacts from search results."""
    prompt = f"""Extract contacts from these search results for {company}.

Search Results:
{json.dumps(search_results, indent=2)}

Return JSON array:
[{{"name": "...", "role": "...", "linkedin_url": "...", "relevance": "recruiter|hiring_manager|leadership"}}]

Only include people who CURRENTLY work at {company}. Extract name from the title before the dash."""

    response = self.llm.invoke(prompt)
    return parse_contacts_response(response)
```

### Option B: Full AI Agent with FireCrawl Tools (Maximum Flexibility)

**Pros**: Most flexible, can adapt strategies, handles edge cases
**Cons**: Higher cost (more LLM calls), more complex

#### Implementation with LangGraph

```python
from langgraph.graph import StateGraph, END
from langchain_core.tools import tool

@tool
def search_linkedin_profiles(query: str, limit: int = 5) -> List[dict]:
    """Search for LinkedIn profiles using FireCrawl."""
    response = firecrawl.search(query, limit=limit)
    return _extract_search_results(response)

@tool
def search_company_team(company: str) -> List[dict]:
    """Search for company team/leadership pages."""
    query = f"{company} leadership team executives"
    response = firecrawl.search(query, limit=5)
    return _extract_search_results(response)

# Agent state
class ContactDiscoveryState(TypedDict):
    company: str
    role_title: str
    department: str
    search_results: List[dict]
    contacts: List[Contact]
    attempts: int

# Agent node
def contact_discovery_agent(state: ContactDiscoveryState) -> ContactDiscoveryState:
    """AI agent that reasons about which searches to run."""

    llm_with_tools = llm.bind_tools([search_linkedin_profiles, search_company_team])

    prompt = f"""Find the best people to contact about a {state['role_title']} role at {state['company']}.

Target contacts (in priority order):
1. Technical recruiters for {state['department']}
2. Hiring managers (Engineering Directors, VPs)
3. Department heads
4. Talent acquisition / HR

Use the search tools to find LinkedIn profiles. Use targeted queries like:
- site:linkedin.com/in "{state['company']}" recruiter {state['department']}
- "{state['company']}" "VP Engineering" LinkedIn

Current search results: {len(state['search_results'])} found
Current contacts extracted: {len(state['contacts'])}

{f"Previous attempts: {state['attempts']}. Try different query patterns." if state['attempts'] > 0 else ""}
"""

    response = llm_with_tools.invoke(prompt)
    # Process tool calls and update state...
    return state

# Build graph
graph = StateGraph(ContactDiscoveryState)
graph.add_node("discover", contact_discovery_agent)
graph.add_node("parse", parse_contacts_node)
graph.add_node("rank", rank_contacts_node)

graph.set_entry_point("discover")
graph.add_edge("discover", "parse")
graph.add_edge("parse", "rank")
graph.add_edge("rank", END)
```

---

## Recommended Implementation Path

### Phase 1: Quick Win (1-2 hours)
1. Update query patterns in `people_mapper.py` to use SEO-style queries
2. Extract contact info from `title` and `description` instead of `markdown`
3. Test with real companies

### Phase 2: Enhanced Extraction (2-4 hours)
1. Add LLM-powered contact parsing from search results
2. Run multiple parallel searches (recruiters, leadership, hiring managers)
3. Add confidence scoring and ranking

### Phase 3: Full Agent (Optional, 4-8 hours)
1. Implement LangGraph sub-agent with FireCrawl tools
2. Add adaptive query reformulation
3. Add caching to avoid duplicate searches

---

## Query Patterns That Work

Based on testing, these query patterns consistently return good results:

```python
# Recruiters
'site:linkedin.com/in "{company}" recruiter engineering'
'site:linkedin.com/in "{company}" talent acquisition'

# Engineering Leadership
'"{company}" "Head of Engineering" OR "VP Engineering" OR "Engineering Director" LinkedIn'
'"{company}" "Senior Engineering Manager" LinkedIn'

# Hiring Managers (role-specific)
'"{company}" "{title}" hiring manager engineering LinkedIn'

# General Team
'{company} engineering leadership team LinkedIn'
```

---

## Cost Analysis

| Approach | FireCrawl API Calls | LLM Calls | Est. Cost/Job |
|----------|---------------------|-----------|---------------|
| Current (broken) | 4 | 0 | ~$0.04 |
| Option A (fixed) | 4-6 | 1 | ~$0.08 |
| Option B (agent) | 4-10 | 3-5 | ~$0.20 |

With 100,000 FireCrawl credits/month, you can process ~16,000-25,000 jobs (Option A) or ~10,000-16,000 jobs (Option B).

---

## Conclusion

**Recommended: Option A (Fixed Direct API)** for most use cases:
- Lower cost per job
- Simpler to implement and debug
- Works reliably with the right query patterns
- Can always upgrade to Option B later if needed

**Use Option B (Full Agent)** if:
- Companies have unusual structures
- Need maximum flexibility
- Budget allows for higher LLM costs
- Want self-improving query strategies

The key insight is that **FireCrawl search works great** - the problem was query formulation and response handling, not the API itself.
