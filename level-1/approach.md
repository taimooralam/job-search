# Level‑1 Matching Approach (Heuristic + Cheap LLM)

This document describes a cheap, scalable Level‑1 / Level‑1.5 / Level‑2 matching strategy that does **not** require embeddings and minimizes LLM usage while still producing high‑quality candidate–job matching.

The core idea:

- Use a **deterministic heuristic filter** first (Level‑1, no LLM) to shrink the raw firehose from LinkedIn into a smaller, relevant set.
- Then apply a **very cheap LLM relevance gate** on that smaller set (Level‑1.5).
- Only jobs that pass both **Level‑1** and **Level‑1.5** are **promoted to Level‑2**, where the full LangGraph pipeline runs.

---

## 1. Level‑1: Deterministic Heuristic Filter (No LLM)

For each raw job pulled from LinkedIn (stored in `level-1`):

1. **Title filter (hard gate)**

   Accept only if `title` contains at least one of (case‑insensitive):

   - Strong matches (preferred):
     - `Senior Software Architect`, `Software Architect`, `Enterprise Architect`
     - `Chief Technical Officer`, `CTO`
     - `Director of Engineering`, `Director Technology`
     - `Head of Engineering`
     - `VP Engineering`, `Vice President Engineering`, `Vice President Technology`
   - Optional weaker matches (may be lower priority):
     - `Staff Software Engineer`, `Principal Software Engineer`, `Lead Software Engineer`
     - `Technical Lead`, `Tech Lead`, `Engineering Lead`, `Team Lead`

2. **Seniority filter (job_criteria)**

   From `job_criteria`:

   - Require `SENIORITY LEVEL` to be one of:
     - `Mid-Senior level`, `Senior`, `Director`, `Executive`.
   - Drop roles that clearly indicate:
     - `Entry level`, `Associate`, `Intern`, etc.

3. **Location & remote signal**

   - Prefer jobs where `location` or `job_description` contains:
     - `Remote`, `Remote-first`, `Distributed`, `Work from anywhere`, `ROWE`.
   - Down‑rank (or exclude if desired) jobs that clearly require on‑site only:
     - `Onsite`, `On-site`, `office only`, etc.
   - Slightly up‑rank jobs that mention EU/Germany if that is a preference.

4. **Language filter**

   - Down‑rank jobs that explicitly require non‑English fluency (e.g., Arabic, Spanish) or are largely written in another language.
   - Up‑rank or leave neutral if English is the main language and there is no conflicting requirement.

5. **Architecture / domain keyword filter**

   Require at least a few architecture/scale/leadership keywords in `job_description` or `job_criteria`, for example:

   - Architecture / systems:
     - `architecture`, `architect`, `system design`, `distributed systems`, `microservices`, `event-driven`, `DDD`
   - Cloud / scale:
     - `AWS`, `GCP`, `Azure`, `cloud-native`, `scalable`, `high availability`, `multi-tenant`
   - Leadership:
     - `technical leadership`, `technical strategy`, `roadmap`, `mentoring`, `team leadership`

6. **Rule‑based score (0–100)**

   Compute a simple rule‑based score with cheap integer arithmetic:

   - `title_score` (0–40):
     - +40 if strong title match (architect roles).
   - `seniority_score` (0–20):
     - +20 if seniority in desired set.
   - `architecture_keywords_score` (0–20):
     - +5 per matched keyword up to 20.
   - `remote_preference_score` (−10 to +10):
     - +10 for clearly remote‑friendly.
     - −10 for clearly on‑site only.
   - `language_score` (−10 to +10):
     - −10 if job is clearly non‑English / requires non‑English native.
     - 0–+10 if English / EU‑friendly.

   Sum these, clamp to [0, 100] → `rule_score`.

   **Level‑1 pass rule:**

   - A job **passes Level‑1** (and becomes eligible for the Level‑1.5 LLM check) if:
     - `rule_score >= 40–50`, and
     - It passes basic de‑duplication (`dedupeKey`).
   - Optionally, per time window (e.g., per hour), keep only the **top N** Level‑1‑passing jobs by `rule_score` (e.g., top 50–100) to send into Level‑1.5.

This gives you a cheap, deterministic Level‑1 gate without calling any LLM.

---

## 2. Level‑1.5: Cheap LLM Gate (Pre‑Level‑2)

Once jobs pass the deterministic Level‑1 filter, you may still have more than you want to send through LangGraph. You can add a very cheap LLM gate (Level‑1.5) before promotion to Level‑2:

1. **Static candidate summary**

   Instead of sending the full knowledge graph (11 STAR records) on every call, create a concise, static summary:

   - Target roles.
   - Core domains.
   - Key technologies.
   - Location/remote preferences.

   - 3–4 high‑impact highlight bullets (metrics).

   Store this summary as a small JSON or text blob and reuse it for every job.

2. **Yes/No relevance classifier (tiny model)**

   Use a very small LLM (e.g., 8B instruct) with a simple prompt:

   - Input: candidate summary + job title + short snippet of the description.
   - Output: ONLY `YES` or `NO` (is this job relevant for this candidate?).

   - If `NO` → mark as low priority and skip detailed scoring.
   - If `YES` → optionally call a second prompt to get a precise 0–100 LLM score (still cheap compared to running LangGraph on the job).

3. **Full pipeline only for the best jobs**

   Finally, only **promote jobs to Level‑2** and send them into LangGraph (Layers 2–7) where:

   - `rule_score` ≥ threshold (Level‑1 pass), and
   - LLM relevance is `YES` (Level‑1.5 pass), and
   - They are in the top **K** jobs per unit time that you’re willing to process end‑to‑end.

---

## 3. Why This Scales Without Embeddings

- Deterministic filters are extremely cheap and predictable.
- Candidate summary is static, so LLM calls stay short.
- You avoid the complexity and setup of embeddings while still performing reasonably strong matching based on titles, seniority, domain, and key signals (remote, language, geography).
- You can gradually add embeddings later if needed, without changing the basic control flow.
