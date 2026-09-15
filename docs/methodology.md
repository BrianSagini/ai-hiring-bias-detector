# Project 3 — AI Hiring Bias Detector: Methodology & Limitations

## Data: 100% synthetic

No real applicant, employer, or hiring data is used anywhere in this project. Real anonymized
hiring-funnel datasets with protected-attribute labels are either not freely redistributable, or
carry licensing/ethical constraints that make them inappropriate to bundle in a public portfolio
repo. Instead, `pipeline.py` generates 20,000 synthetic candidates with:

- `gender`, `ethnicity` (protected attributes — deliberately generic group labels, not real
  demographic categories, to avoid implying this models any specific real population)
- `education_level`, `years_experience` (qualification signal)
- `role_family`, `application_source`, `application_date`

## Funnel simulation & bias injection

A synthetic **qualification score** (0–1, from education + experience) drives a baseline pass
probability at each stage (`screen` → `interview` → `offer` → `hire`), so progression is not random
noise — it's grounded in *something* resembling merit, the way selection rate differences in real
data coexist with real qualification variance. Documented multipliers in
`STAGE_BIAS_MULTIPLIER` (pipeline.py) then bias that probability for specific groups at specific
stages:

| Stage | Group | Multiplier |
|---|---|---|
| screen | Woman | 0.90 |
| screen | Non-binary | 0.85 |
| interview | Group C | 0.80 |
| interview | Group D | 0.75 |
| offer | Woman | 0.88 |

These are **deliberately exaggerated versus most real-world measured hiring gaps** so the fairness
metrics below have unambiguous signal to detect in a demo — they are not estimates of any real
company's or industry's actual bias. The funnel is enforced monotonic: a candidate can only reach
a later stage if they passed every earlier one (checked in `validate_funnel` and in the DAG's
final data-quality task).

## Fairness metrics (`hiring_bias.fairness_metrics`, `sql/002_fairness_metrics.sql`)

For `gender` and `ethnicity`, at each funnel stage: **selection rate** (passed / eligible-at-risk
for that stage) and the **4/5ths-rule adverse impact ratio** (a group's selection rate divided by
the highest selection rate among groups for that attribute+stage). A ratio below 0.8 is the
traditional (not legally dispositive — see below) EEOC screening threshold for possible adverse
impact.

## Interpretable audit model (`hiring_bias.audit_model_coefficients`)

A logistic regression predicting `reached_hire` from candidate features (one-hot encoded,
standardized), with coefficients and 95% confidence intervals from 200 bootstrap resamples. This
model exists **only to report which features are associated with the outcome, for interpretability**
— it is never used to score, rank, or decide on any candidate, real or synthetic.

## Ethical constraints (non-negotiable)

- **This system does not automatically decide who should be hired**, and nothing in this codebase
  scores or ranks a candidate for a hiring decision.
- The 4/5ths rule and bootstrap confidence intervals are statistical screening heuristics, not
  legal determinations of discrimination — any real finding of this shape would need legal/HR
  expert review, not just a dashboard number.
- Group labels (`Group A`–`D`, `Woman`/`Man`/`Non-binary`) are synthetic placeholders, not a
  real demographic taxonomy — do not read them as representing any specific real population.
- This entire project is a **methodology demonstration**: how to compute selection-rate fairness
  metrics and an interpretable audit model over funnel data. It is not validated against, and must
  not be deployed on, real candidate data without a full ethical/legal review.
