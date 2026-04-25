# Step 9 Scoring Summary

Scored pairs: 12

## Verdict distribution
- STRONG_MATCH: 0
- GOOD_MATCH: 9
- NEEDS_WORK: 3
- WEAK_MATCH: 0

## Gate failures
- must_have_coverage_gate: 2
- unsafe_claim_gate: 0
- persona_fit_gate: 0

## Pair detail
| Category | Job ID | Overall | Verdict | Failed gates | Top failure | CV source |
|----------|--------|---------|---------|--------------|-------------|-----------|
| ai_architect_eea | 69610d7b6dd552ab7ec2d666 | 7.0 | GOOD_MATCH | - | Missing required AWS certification (Solutions Architect Professional or ML Specialty); only has AWS Essentials refs=data |  |
| ai_architect_global | 696808c4515e64c5ca05acee | 6.97 | NEEDS_WORK | must_have_coverage_gate | JD requires expert-level Pulumi experience but CV only mentions Terraform refs=data/eval/raw/ai_architect_global/jd_text |  |
| ai_architect_ksa_uae | 69296b3b45fa3c355f849ed4 | 7.15 | GOOD_MATCH | - | No Kubernetes experience despite JD explicitly requiring cloud platforms or Kubernetes refs=data/eval/raw/ai_architect_k |  |
| ai_eng_manager_eea | 69275eb345fa3c355f8435ab | 7.97 | GOOD_MATCH | - | JD emphasizes conversational AI agents and voice agents but CV focuses on AI workflow platform without conversational ex |  |
| head_of_ai_eea | 699f001187737d491c3ab803 | 6.95 | NEEDS_WORK | must_have_coverage_gate | LLM Integration and AI stack terms listed in skills without any evidence in experience section refs=data/eval/generated_ |  |
| head_of_ai_global | 69825fa77d41dc1e8a360e27 | 8.15 | GOOD_MATCH | - | Missing explicit remote-first collaboration keywords despite JD emphasis on remote work refs=data/eval/raw/head_of_ai_gl |  |
| head_of_ai_ksa | 6925c1c545fa3c355f83fce1 | 7.5 | GOOD_MATCH | - | CV states 10+ years experience but JD requires 12+ years; actual timeline shows ~12 years but summary undersells refs=da |  |
| head_of_ai_uae | 6978c1aa7d41dc1e8a0eabe1 | 7.38 | GOOD_MATCH | - | No geospatial or GIS workflow experience despite being core JD requirement for multi-sensor fusion platform refs=data/ev |  |
| senior_ai_engineer_eea | 69381c28c9b1888e56022ad3 | 8.1 | GOOD_MATCH | - | Kafka not explicitly mentioned despite JD requiring event-driven with Kafka refs=data/eval/raw/senior_ai_engineer_eea/jd |  |
| staff_ai_engineer_eea | 6957aaad6dd552ab7ec2ccd8 | 6.97 | NEEDS_WORK | - | Missing Golang proficiency explicitly required by JD refs=data/eval/raw/staff_ai_engineer_eea/jd_texts/01_reddit_inc_sta |  |
| staff_ai_engineer_global | 6957aa9a6dd552ab7ec2ccd7 | 7.35 | GOOD_MATCH | - | Years of experience gap: CV shows 10+ years vs JD requirement of 15+ years software engineering refs=data/eval/generated |  |
| tech_lead_ai_eea | 6925a6c845fa3c355f83f8ec | 8.05 | GOOD_MATCH | - | TypeScript dominates over Python in recent roles despite Python being 70.7% required for category refs=data/eval/generat |  |

## Recommendation
- 3 pairs scored NEEDS_WORK or WEAK_MATCH. Run Step 8b stage diagnostics targeting the dominant failure cluster: 'missing required aws certification (solutions architect'.
