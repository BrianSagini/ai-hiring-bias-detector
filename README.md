# AI Hiring Bias Detector

This is an audit tool, not a hiring tool. It never scores, ranks, or recommends a candidate — every
number it produces is a group-level rate or ratio, computed the way an EEOC compliance review would
compute it. I built it to practice the analytics side of algorithmic fairness: selection-rate
disparities, the four-fifths adverse-impact rule, and an interpretable audit model, over a
recruitment funnel I control end to end.

The funnel — 20,000 synthetic candidates moving through screen → interview → offer → hire — is
entirely generated, with bias multipliers I wrote in myself at specific stages so the fairness
metrics have something real to detect. Group labels (`Group A`–`D`, `Woman`/`Man`/`Non-binary`) are
placeholders, not a real demographic taxonomy, and the injected gaps are deliberately larger than
most measured real-world hiring gaps — this shows the methodology works, it isn't a claim about any
real employer.

**Stack**: Apache Airflow 3.3.1 → PostgreSQL 16 → Python/SQL → Streamlit + Plotly → Power BI.

## Setup

```bash
cp .env.example .env
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"   # -> AIRFLOW_FERNET_KEY
python -c "import secrets; print(secrets.token_urlsafe(32))"                                 # -> AIRFLOW_JWT_SECRET
# paste both into .env

docker compose up -d --build
docker compose ps
```

Unpause and trigger the DAG from the Airflow UI (http://localhost:8081) or:

```bash
docker compose exec airflow-scheduler airflow dags unpause hiring_bias_pipeline
docker compose exec airflow-scheduler airflow dags trigger hiring_bias_pipeline
```

Dashboard's up at http://localhost:8503 a few minutes after the DAG finishes.
`docker compose down` stops everything without losing data.

## The pipeline

Validate config → ensure schema → generate the synthetic candidate funnel → validate and load →
compute fairness metrics in SQL → train the audit model → build the Power BI views → a
data-quality check that rejects anything non-monotonic (a candidate marked hired without ever
having an offer, for instance — that shouldn't be possible and I wanted the pipeline to actually
catch it if it happened).

## Fairness metrics

Selection rate and the four-fifths adverse-impact ratio, computed in SQL per the standard EEOC
methodology, for every group at every funnel stage. Alongside that, I trained a logistic
regression as an interpretability-only audit model — its coefficients and confidence intervals are
there to show which features associate with the hire outcome, and that's all it does. It doesn't
touch a single candidate's outcome, real or synthetic, and I built it that way deliberately, not
as an afterthought.

I want to be clear about what this doesn't do too: a ratio below 0.8 here is a statistical
screening signal, not a legal finding — a real adverse-impact question needs legal and HR review,
not a dashboard number. Full methodology, the exact bias multipliers I used, and the full ethical
constraints list: `docs/methodology.md`.

## Power BI

Data model I built by hand — 3 tables, 11 DAX measures, matched against the SQL above — across a
4-page, 20-visual report. The color system follows the same rule as the fairness metrics
themselves: amber accents are reserved for compliance-indicator numbers (the 4/5ths-rule flag,
adverse-impact ratio), and I never color a chart by demographic group in a way that would make one
group visually stand out as "the problem." I opened every page in Power BI Desktop and confirmed
it renders correctly with real data before calling it finished — see `docs/evidence/` for the
screenshots and `docs/powerbi_guide.md` for the full page layout and design reasoning.

One page's ideal content — a breakdown of the audit model's own coefficients — needs a SQL view I
haven't built yet, so that page currently shows the fairness detail tables instead. Everything
else in the report is real.

## More docs

`docs/methodology.md` has the full bias-injection design and the ethical constraints this project
holds itself to. `docs/database_schema.md` and `docs/data_sources.md` cover the data model and why
I chose synthetic data over a real dataset.

## The rest of the portfolio

Same Airflow → Postgres → dashboard → Power BI shape, different problem each time: Climate Risk &
Business Impact, Dark Store Intelligence, Fraud Pattern Evolution Tracker.
