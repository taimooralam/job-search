Refactor ALL in-code prompts into ./prompts files with the naming pattern <name>.prompt.md (ASCII only). Update code to load from those files with a small helper. Preserve existing
behavior/formatting, including placeholders.

Scope: move every SYSTEM/USER prompt constant across layers:

- src/layer2/pain_point_miner.py (SYSTEM_PROMPT, USER_PROMPT_TEMPLATE)
- src/layer2_5/star_selector.py (SYSTEM_PROMPT, USER_PROMPT_TEMPLATE)
- src/layer3/company_researcher.py (SYSTEM_PROMPT_COMPANY_SIGNALS, SYSTEM_PROMPT_COMPANY_SIGNALS_STAR_AWARE, USER_PROMPT_COMPANY_SIGNALS_TEMPLATE, SYSTEM_PROMPT_SCRAPE,
  USER_PROMPT_SCRAPE_TEMPLATE, SYSTEM_PROMPT_FALLBACK, USER_PROMPT_FALLBACK_TEMPLATE)
- src/layer3/role_researcher.py (SYSTEM_PROMPT_ROLE_RESEARCH, SYSTEM_PROMPT_ROLE_RESEARCH_STAR_AWARE, USER_PROMPT_ROLE_RESEARCH_TEMPLATE)
- src/layer4/opportunity_mapper.py (SYSTEM_PROMPT, USER_PROMPT_TEMPLATE)
- src/layer5/people_mapper.py (SYSTEM_PROMPT_CLASSIFICATION, USER_PROMPT_CLASSIFICATION_TEMPLATE, SYSTEM_PROMPT_OUTREACH, USER_PROMPT_OUTREACH_TEMPLATE)
- src/layer6/cover_letter_generator.py (SYSTEM_PROMPT, USER_PROMPT_TEMPLATE)
- src/layer6/generator.py (CV_SYSTEM_PROMPT; keep using prompts/cv-creator.prompt.md)
- src/layer6/cv_generator.py (SYSTEM_PROMPT_COMPETENCY_MIX, USER_PROMPT_COMPETENCY_MIX_TEMPLATE, SYSTEM_PROMPT_HALLUCINATION_QA, USER_PROMPT_HALLUCINATION_QA_TEMPLATE)

Implementation steps:

1. Add a helper in src/common/prompts.py:

from pathlib import Path
def load_prompt(path: str) -> str:
p = Path(path)
if p.exists():
return p.read_text(encoding="utf-8")
raise FileNotFoundError(f"Prompt not found: {path}")

2. Create prompt files under ./prompts/ with clear names, e.g.:

- layer2_pain_point_miner.system.prompt.md
- layer2_pain_point_miner.user.prompt.md
- layer2_5_star_selector.system.prompt.md
- layer2_5_star_selector.user.prompt.md
- layer3_company_signals.system.prompt.md
- layer3_company_signals_star_aware.system.prompt.md
- layer3_company_signals.user.prompt.md
- layer3_company_scrape.system.prompt.md
- layer3_company_scrape.user.prompt.md
- layer3_company_fallback.system.prompt.md
- layer3_company_fallback.user.prompt.md
- layer3_role_research.system.prompt.md
- layer3_role_research_star_aware.system.prompt.md
- layer3_role_research.user.prompt.md
- layer4_opportunity_mapper.system.prompt.md
- layer4_opportunity_mapper.user.prompt.md
- layer5_people_classification.system.prompt.md
- layer5_people_classification.user.prompt.md
- layer5_people_outreach.system.prompt.md
- layer5_people_outreach.user.prompt.md
- layer6_cover_letter.system.prompt.md
- layer6_cover_letter.user.prompt.md
- layer6_cv_competency_mix.system.prompt.md
- layer6_cv_competency_mix.user.prompt.md
- layer6_cv_hallucination_qa.system.prompt.md
- layer6_cv_hallucination_qa.user.prompt.md
  (keep prompts/cv-creator.prompt.md as-is; just ensure CV_SYSTEM_PROMPT loads from a file too)

3. In each module, replace hardcoded strings with load_prompt("prompts/<file>.prompt.md"), keeping any `.format(...)` usage intact.
4. Ensure Path imports are present where needed and remove unused prompt constants.
5. Update tests if they assert prompt contents (mock load_prompt or adjust fixtures).
6. Run `python -m pytest`.

Deliverables: updated code loading prompts from files, new prompt files under ./prompts/, tests passing. Keep ENABLE_STAR_SELECTOR default false; no behavioral changes beyond prompt
loading.
