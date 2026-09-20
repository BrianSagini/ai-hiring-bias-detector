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

Live public dashboard: https://ai-hiring-bias-detector.streamlit.app/ (reads from a shared cloud
database, not this local stack). Your own local run's dashboard is up at http://localhost:8503 a
few minutes after the DAG finishes. Live H2O AutoML results:
https://ai-hiring-bias-automl.streamlit.app/ (also reads from the shared cloud database).
`docker compose down` stops everything without losing data.

## The pipeline

Validate config → ensure schema → generate the synthetic candidate funnel → validate and load →
compute fairness metrics in SQL → train the audit model → cross-validate and calibrate it → build
the Power BI views → a data-quality check that rejects anything non-monotonic (a candidate marked
hired without ever having an offer, for instance — that shouldn't be possible and I wanted the
pipeline to actually catch it if it happened).

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

## Machine learning

Only 1.95% of the 20,000 synthetic candidates reach `hire` — real class imbalance, since `hire`
means clearing four sequential stages in a row. Stratified 5-fold cross-validation (never plain
K-fold, which risks a fold with almost no positive examples by chance) puts the audit model's
ROC-AUC at 0.633 ± 0.046, close enough to the single held-out split's 0.627 to confirm that split
wasn't a lucky draw. Precision/recall/F1 are zero at the default 0.5 threshold, in every fold — not
a bug: no candidate's predicted P(hire) ever reaches 0.5, a direct consequence of the funnel's
compounding stage-by-stage attrition, checked directly rather than assumed. ROC-AUC, being
threshold-independent, is the metric that actually carries signal here.

For a fairness tool specifically, I also checked whether that predicted probability is *reliable*
for every group, not just overall — calibration that differs by group would be its own fairness
problem, separate from accuracy. In the bin holding 99.65% of the test set, predicted and observed
hire rates agree within about a percentage point for every gender and ethnicity value; no
differential miscalibration was found. And I ran a chi-square significance test on every
selection-rate gap the fairness metrics above flag: three come back significant (p < 0.05), and all
three line up with the strongest bias multipliers I injected. Two *other* real injected biases
(gender at offer, and the Non-binary screen-stage gap — numerically the largest adverse-impact gap
of any group) don't reach significance at this sample size, because smaller groups and later funnel
stages have less statistical power to confirm a gap even when it's real by construction. That
distinction — which gaps this tool can and can't confidently confirm, given the sample — is the
actual point of adding significance testing, not just a bigger table of numbers.

This training/evaluation run is a real Airflow task (`evaluate_audit_model`, wired into
`hiring_bias_pipeline` right after the existing audit-model training step), not a notebook run in
isolation — it writes real rows to `model_evaluation`, `cv_fold_results`, `calibration_bins`, and
`fairness_significance_tests`. `hiring_bias_model_comparison.ipynb` is the same analysis end to
end (class-imbalance check, cross-validation, calibration, significance testing) for anyone who
wants to see the reasoning and code side by side, calling the exact same `pipeline.py` functions
the DAG does rather than reimplementing any of it. Calibration curves and the CV score
distribution are real images generated from this exact run, in `docs/evidence/`. Full numbers and
known limitations: `docs/model_card.md`.

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
