# Form Field Mapping

> **NOTE**: For known portals, use the playbook's `batch_fill_scripts` instead of this module.
> The batch script fills ALL fields in one `javascript_tool` call. This module is only needed
> for unknown portals where you must build a dynamic fill script at runtime.
> Also check `question_cache` in `applicant-profile.yaml` — it has pattern-matched answers
> for 25+ common questions across all portals.

Map form labels to values from `data/applicant-profile.yaml`. Use fuzzy matching — labels vary across portals.

## Mapping Rules

| Field pattern (case-insensitive) | Profile value |
|----------------------------------|---------------|
| first name, given name, vorname | `Taimoor` |
| last name, family name, surname, nachname | `Alam` |
| full name, name | `Taimoor Alam` |
| email, e-mail | `personal.email` |
| phone, telephone, mobile, telefon | `personal.phone` |
| linkedin, linkedin url | `personal.linkedin` |
| website, portfolio | `personal.website` |
| github | `personal.github` |
| city, location, current location, standort | `personal.location` |
| country | `Germany` |
| address | **ASK USER** |
| work authorization, authorized to work, right to work | `Yes` (EU work right) |
| visa sponsorship, require sponsorship | `No` |
| willing to relocate, relocation | `Yes` |
| years of experience, experience | `10` |
| current company, employer | `professional.current_company` |
| current title, job title, current role | `professional.current_title` |
| notice period, availability, when can you start | `3 months` |
| earliest start date, start date | Calculate: today + 3 months |
| education, degree, highest education | `M.Sc. Computer Science, Technical University of Munich` |
| salary expectation, expected salary, compensation | `negotiable` |
| how did you hear, source, referral | `LinkedIn` |
| gender, ethnicity, race, veteran, disability | `Prefer not to say` or skip |

## Tools to Use
- `mcp__claude-in-chrome__find` → locate form elements
- `mcp__claude-in-chrome__form_input` → fill text fields and selects
- `mcp__claude-in-chrome__computer` → click checkboxes and radio buttons

## Unknown Questions
If a field doesn't match any mapping:
1. Check `custom_answers` in the profile first
2. Check the **job dossier PDF** in the GDrive folder (has pain points, JD details)
3. Check **`data/master-cv/`** — read `projects/lantern_skills.json` for verified AI/tech skills, `roles/01_seven_one_entertainment.md` for current role stack, `role_skills_taxonomy.json` for role-specific competencies
4. Synthesize an answer grounded in the master-CV data — do NOT guess or hallucinate skills

**Tech stack questions**: Use verified skills from `lantern_skills.json` + current role stack. Tailor to the job type (AI/ML role → Python, FastAPI, LangGraph, LiteLLM, AWS; Backend role → TypeScript, AWS Lambda/ECS/EventBridge; Full-stack → add React/Tailwind).

Only ask the user if the answer cannot be derived from the above sources. If saving a new answer, append to `custom_answers` in `data/applicant-profile.yaml`.
