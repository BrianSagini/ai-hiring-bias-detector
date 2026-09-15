# ⚖️ AI Hiring Bias Detector

An ethical recruitment analytics platform: a 100% synthetic recruitment funnel with documented,
adjustable bias injection, audited with standard fairness metrics (selection rate, four-fifths
adverse-impact ratio). Part of a 4-project data analytics portfolio
([siblings](#related-projects) below); this repo is fully self-contained and runs on its own.

**Stack**: Apache Airflow 3.3.1 → PostgreSQL 16 → Python/SQL → Streamlit + Plotly → Power BI
(`.pbip` project included, unvalidated — see [Power BI](#power-bi)).

**This system does not automatically decide who should be hired.** It is an audit/analysis tool
only — every output is a group-level rate or ratio, never a per-candidate score or recommendation.

## Data

**100% synthetic.** 20,000 candidates generated with a documented, adjustable bias-injection model
(gender/ethnicity selection-rate multipliers at each funnel stage). No real applicant or employer
data is used anywhere. Full generation methodology: `docs/methodology.md`.

## Quick start

```bash
cp .env.example .env
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"   # -> AIRFLOW_FERNET_KEY
python -c "import secrets; print(secrets.token_urlsafe(32))"                                 # -> AIRFLOW_JWT_SECRET
# paste both into .env

docker compose up -d --build
docker compose ps
```

Airflow UI: http://localhost:8081.

```bash
docker compose exec airflow-scheduler airflow dags unpause hiring_bias_pipeline
docker compose exec airflow-scheduler airflow dags trigger hiring_bias_pipeline
```

Dashboard: http://localhost:8503 once the DAG completes (a few minutes).

Shut down (keeps data): `docker compose down`.

## Pipeline

`hiring_bias_pipeline` DAG: validate config → ensure schema → generate the synthetic candidate
funnel → validate & load → compute fairness metrics (SQL) → train an interpretability-only audit
model → build Power BI views → data-quality check (rejects any non-monotonic funnel, e.g. a
candidate marked hired without an offer).

## What the numbers mean

Selection rate and the four-fifths adverse-impact ratio are computed in SQL exactly per the
standard EEOC methodology. The "audit model" (logistic regression) is interpretability-only —
its coefficients are exposed for inspection, and it **is never used to score, rank, or filter any
candidate.** Results describe this synthetic dataset's construction, not evidence about any real
employer. Full detail and ethical-use disclosure: `docs/methodology.md`.

## Power BI

A real `.pbip` project (`powerbi/HiringBiasDetector.pbip`) exists with the complete data model —
3 tables, 11 DAX measures — **and 12 real visuals across all 4 pages** (see
`docs/powerbi_guide.md`'s visual inventory; page 4's audit-coefficients view still needs to be
added to SQL first, so it uses the fairness tables instead for now). **Rendering is not
verified**: the outer project structure was confirmed openable by Power BI Desktop in one safe
test on a sibling project, but the visual JSON itself was never opened (a second validation
attempt captured unrelated desktop content and was stopped — full account in
`docs/powerbi_guide.md`). This report must never rank or recommend individual candidates, by the
same constraint as the pipeline itself.

## Documentation

`docs/methodology.md` (bias-injection methodology, fairness definitions, ethical safeguards) ·
`docs/powerbi_guide.md` · `docs/database_schema.md` · `docs/data_sources.md`.

## Related projects

Part of a 4-project portfolio, each in its own self-contained repo: Climate Risk & Business
Impact, Dark Store Intelligence, Fraud Pattern Evolution Tracker.
