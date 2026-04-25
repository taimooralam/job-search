# Step 9 Scoring Summary

Scored pairs: 4

## Verdict distribution
- STRONG_MATCH: 0
- GOOD_MATCH: 0
- NEEDS_WORK: 1
- WEAK_MATCH: 3

## Gate failures
- must_have_coverage_gate: 4
- unsafe_claim_gate: 2
- persona_fit_gate: 3

## Pair detail
| Category | Job ID | Overall | Verdict | Failed gates | Top failure | CV source |
|----------|--------|---------|---------|--------------|-------------|-----------|
| ai_architect_global | 696808c4515e64c5ca05acee | 5.0 | WEAK_MATCH | must_have_coverage_gate,unsafe_claim_gate,persona_fit_gate | Zero AI/ML experience despite JD requiring model fine-tuning and agentic systems refs=data/eval/raw/ai_architect_global/ |  |
| head_of_ai_global | 69825fa77d41dc1e8a360e27 | 5.22 | WEAK_MATCH | must_have_coverage_gate,unsafe_claim_gate,persona_fit_gate | No generative AI experience evidenced despite JD requiring it as core requirement refs=outputs/cMatter__Reech_Corporatio |  |
| staff_ai_engineer_eea | 6957aaad6dd552ab7ec2ccd8 | 5.05 | WEAK_MATCH | must_have_coverage_gate | Zero search and recommendation systems experience against 8+ years required refs=data/eval/raw/staff_ai_engineer_eea/jd_ |  |
| tech_lead_ai_eea | 6925a6c845fa3c355f83f8ec | 5.97 | NEEDS_WORK | must_have_coverage_gate,persona_fit_gate | Zero Python evidence despite 70.7% category requirement - CV shows .NET Core and Node.js stack refs=outputs/KAIZEN_GAMIN |  |

## Recommendation
- 4 pairs scored NEEDS_WORK or WEAK_MATCH. Run Step 8b stage diagnostics targeting the dominant failure cluster: 'zero ai/ml experience despite jd requiring'.
