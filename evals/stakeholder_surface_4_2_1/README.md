# Stakeholder Surface 4.2.1 Eval

This eval freezes small reviewed cases for the new `stakeholder_surface`
artifact.

Use it after:

- stakeholder-surface model/schema changes
- prompt changes
- coverage-heuristic changes
- safety/privacy normalization changes
- rollout flag or routing changes

Run:

```bash
./.venv/bin/python scripts/benchmark_stakeholder_surface_4_2_1.py \
  --corpus evals/stakeholder_surface_4_2_1/stakeholder_surface_cases.json
```

The benchmark checks:

- schema validity
- real stakeholder identity precision
- inferred-persona fallback correctness
- ambiguous identity rejection
- safety/privacy cleanliness
- resolved vs inferred labeling correctness
- usefulness of downstream CV preference signals
