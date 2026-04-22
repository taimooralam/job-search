# Cover Letter Generation

Only triggered when a cover letter field is detected on the application form.

## Decision Flow
1. If required (marked with *) → generate
2. If optional → ask user: "Cover letter is optional. Generate one? (y/n/skip)"
3. If user declines → skip

## Context Sources
- Job description: MongoDB `description` field
- Pain points: MongoDB `pain_points` field
- Company dossier: GDrive `dossier_*.pdf` in same folder as CV (if exists)
- Applicant profile: `data/applicant-profile.yaml`
- Generated CV: MongoDB `cv_text` field

## Rules
- 3-4 paragraphs, under 300 words
- Lead with value you bring to their specific problem
- Reference 1-2 specific achievements from the tailored CV
- NO generic filler ("I am writing to express my interest...")
- Close with enthusiasm and availability
- Match the tone to the company culture (startup vs enterprise)

## Approval
```
COVER LETTER DRAFT:

{text}

Accept? (y/edit/skip)
```
If "edit" → ask user for changes or their own version.
