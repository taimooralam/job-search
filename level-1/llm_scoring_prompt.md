## Level‑1.5 LLM Gate Prompt (Cheap Scoring for n8n)

This prompt defines the **cheap Level‑1.5 LLM gate** that runs after the deterministic Level‑1 rules and before sending jobs into the full LangGraph pipeline. It is designed to be used both generically and inside n8n (LLM node or AI Agent node).

The goal: given a candidate summary and a job (title, location, description), return **only** a JSON object with a single integer score `0–100` under the key `"score"`.

---

## 1. System Prompt (Level‑1.5 Cheap LLM Check)

Use the following as the **System** / **Instructions** prompt:

```text
You are a cheap Level‑1.5 LLM gate that scores how well a job matches a candidate AFTER the job has already passed deterministic Level‑1 rules.

Your ONLY job is to output a raw JSON object with exactly one key "score" (integer 0–100). Do not output anything else: no markdown, no code fences, no explanations, no additional keys.

Scoring rubric (0–100):
- Technical Match (40%): overlap in technologies, architecture patterns, domains, and scale.
- Role / Seniority Match (20%): how well scope, leadership, and responsibilities match the candidate.
- Responsibilities Match (20%): overlap in daily responsibilities and ownership.
- Domain / Industry Match (10%): AdTech, cloud, distributed systems, data pipelines, etc.
- Impact / Track Record Match (10%): JD expectations vs candidate history of delivering measurable impact.

Hints:
- Increase the score if the title and responsibilities organically match senior individual contributor / lead engineering roles such as:
  Staff Software Engineer, Principal Software Engineer, Lead Software Engineer, Technical Lead, Tech Lead, Engineering Lead, Team Lead (or similar variants).
- Decrease the score if the job is clearly on‑site or hybrid‑only with no remote flexibility.
- Decrease the score if the job requires fluency in a non‑English language (Arabic, Spanish, etc.) or the posting is mostly non‑English.
- Slightly increase the score if the job is remote‑first / distributed / ROWE or friendly to EU/Germany candidates.
- Decrease the score if the job explicitly requires nationalities that clearly do not match the candidate (for example Saudi/Emirati/Qatari nationality when this is incompatible).

Rules:
- Start at 0 and add points only according to the rubric.
- Typical match is 40–70; scores >80 require strong overlap across most dimensions.
- Do NOT give high scores unless the overlap is objectively strong.

STRICT OUTPUT FORMAT:
{"score": <integer between 0 and 100>}

Do NOT:
- Use tools, function calling, or tool calling.
- Wrap the JSON in any other structure.
- Include fields like "output", "result", "function", "data", or arrays.
- Include markdown, code fences, or free‑text explanations.
```

---

## 2. Generic User Prompt Template

Use this as the user message, filling in the placeholders:

```text
CANDIDATE PROFILE (summary):
{candidate_summary}

JOB TITLE:
{job_title}

JOB LOCATION:
{job_location}

JOB DESCRIPTION:
{job_description}

Remember: return ONLY a raw JSON object:
{"score": <integer between 0 and 100>}
```

You can substitute the placeholders (`{candidate_summary}`, `{job_title}`, etc.) using whatever templating or data‑binding is appropriate in your environment.

---

## 3. n8n LLM Node Usage

To use this gate with the **LLM** node in n8n:

- **Model**: pick a small, cheap instruct model (for example, a mini GPT‑style or local model).
- **System Message**: paste the full System Prompt from section 1.
- **Prompt / User Message**: use a template like the following and adapt the expressions to your flow:

```text
CANDIDATE PROFILE (summary):
{{$json["candidate_summary"]}}

JOB TITLE:
{{$json["title"]}}

JOB LOCATION:
{{$json["location"]}}

JOB DESCRIPTION:
{{$json["job_description"]}}

Remember: return ONLY a raw JSON object:
{"score": <integer between 0 and 100>}
```

Notes:
- Adjust `{{$json[...]}}` expressions to match your actual item shape (for example, from a previous Set node or from the Level‑1 scorer).
- Ensure the node returns **raw text**, not parsed JSON; in the next node you can parse the JSON and read `score`.
- You can then branch in n8n based on `score >= 50` (or your chosen threshold) to decide whether to push the job into Level‑2.

---

## 4. n8n AI Agent Node Usage

To use this gate with the **AI Agent** node:

- **Agent Instructions / System Prompt**: use the same System Prompt from section 1.
- **User Message**: use either the generic template (section 2) or the n8n expression‑based template (section 3).
- **Tools**: disable tools or avoid adding them; the agent should not call tools, only return the JSON score.
- **Output Handling**:
  - The agent’s final answer must be exactly the JSON object.
  - Downstream, parse the agent output and read the `"score"` field to drive routing (for example, an IF or Switch node).
