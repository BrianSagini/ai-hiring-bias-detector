# Data Sources

## 100% synthetic, by deliberate choice

No real recruitment data is used anywhere in this project. Real, labeled hiring-bias datasets with
demographic attributes are either not publicly available, gated behind restrictive licenses, or
ethically unsuitable to redistribute in a public portfolio repo (they'd expose real people's
protected-class information tied to real hiring outcomes). Instead, `pipeline.py` generates a
20,000-candidate synthetic recruitment funnel with a documented, adjustable bias-injection model —
see `docs/methodology.md` for the exact generation logic and injected multipliers.

No API key is required anywhere in this pipeline (the "extraction" step is the generator itself).
