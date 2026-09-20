# Model card — audit model evaluation

The interpretability-only logistic regression this project already had (bootstrap coefficient
confidence intervals, `train_and_load_audit_model()`) answers "which features correlate with reaching
hire." This card covers what was added on top of it: does that model's accuracy hold up across folds,
is its predicted probability actually reliable for every protected group, and are the selection-rate
gaps `fairness_metrics` already flags statistically real given the sample size. `evaluate_audit_model()`
is the real function behind all of it — the same one the `evaluate_audit_model` Airflow task calls.

## Data

100% synthetic — see `docs/data_sources.md` and `docs/methodology.md` for the funnel generator and its
documented bias-injection mechanism. 20,000 candidates, 390 (1.95%) reach `hire` — a real, and severe,
class imbalance: `hire` requires independently clearing four sequential stages (screen → interview →
offer → hire), each with its own pass rate well under 100%, so even a maximally-favored candidate's
*ceiling* probability of reaching hire is capped low by the funnel's own structure, before any model
gets involved.

**Split**: single held-out 80/20 (stratified on `reached_hire`, so both splits keep the same ~2% hire
rate), plus 5-fold stratified cross-validation for the reason above — a plain (non-stratified) K-fold on
data this imbalanced risks a fold with almost no positive examples purely by chance.

## Features

Same encoding as the existing bootstrap-CI model, factored into one shared function
(`_build_audit_features()`) so both models are built from a single source of truth, not two encodings
that could drift apart: `gender`, `ethnicity`, `education_level`, `role_family`, `application_source`
(one-hot encoded), `years_experience` (used as-is), all standardized. 17 features after encoding.

## Cross-validation

| Metric | Single split | CV mean | CV std | CV range |
|---|---|---|---|---|
| ROC-AUC | 0.6271 | 0.6328 | 0.0460 | [0.5688, 0.6829] |
| Precision | 0.0 | — | — | 0.0 in every fold |
| Recall | 0.0 | — | — | 0.0 in every fold |
| F1 | 0.0 | 0.0000 | 0.0000 | 0.0 in every fold |

**Precision/recall/F1 are zero, in the single split and in every one of 5 folds — a real result, not a
bug.** Predicted P(hire) on the held-out test set ranges from 0.003 to 0.196 (mean 0.0195); it never
reaches the default 0.5 classification threshold for a single candidate, so nothing is ever predicted
positive. This is a direct consequence of the funnel structure described above (Data), not a modeling
failure — checked by computing the actual predicted-probability range rather than assumed. **ROC-AUC is
the metric that actually carries signal here**, since it's threshold-independent: 0.633 ± 0.046 across 5
folds is modest but real ranking ability, and the tight fold-to-fold range (0.569–0.683) confirms the
single split wasn't a lucky or unlucky draw — this is a stable property of the data.

## Calibration

Computed on the held-out test split's real predictions (never train, never the CV folds), in 10
equal-width bins from 0 to 1, both overall and per protected group. Two distinct findings:

1. **The dominant bin (predicted P(hire) in [0, 0.1), 99.65% of the test set) is well-calibrated for
   every group.** Predicted vs. observed hire rate sit within about a percentage point of each other
   for every gender and ethnicity value, including the smallest group (Non-binary, n=169: predicted
   1.98% vs. observed 2.96% — the largest gap of any group, and still small for a group this size). **No
   evidence of differential miscalibration by group was found in this run.**
2. **The sparse tail bin (predicted P(hire) in [0.1, 0.2)) shows zero observed hires, consistently
   across every single group** (1–8 test-set candidates per group in this bin). Too few points per
   group to support a strong per-group miscalibration claim on its own — reported rather than dropped,
   since silently omitting it would be its own kind of dishonesty about what this run actually showed.

Evidence: `docs/evidence/hiring_calibration_curve.png`, `docs/evidence/hiring_cv_score_distribution.png`.

## Statistical significance of the fairness-metric gaps

Chi-square test of independence (this group's passed/not-passed counts vs. the reference group's, a 2x2
contingency table) for every `fairness_metrics` row — not a permutation test, since every group/stage
cell here has from several dozen to several thousand candidates, comfortably large enough for the
chi-square approximation to hold; a permutation test would converge on the same p-value at far higher
compute cost, not a different one, at this sample size.

**Three gaps are statistically significant (p < 0.05)**, and all three line up with the strongest
injected bias multipliers:

| Group | Stage | Reference | χ² | p-value |
|---|---|---|---|---|
| `ethnicity` Group C | interview | Group A | 19.83 | 8.5 × 10⁻⁶ |
| `ethnicity` Group D | interview | Group A | 14.81 | 1.19 × 10⁻⁴ |
| `gender` Woman | screen | Man | 10.67 | 1.09 × 10⁻³ |

**The near-misses are the more interesting result.** `gender` Non-binary at `screen` has a *numerically
larger* adverse-impact gap than Woman's at the same stage (selection rate 33.2% vs. Man's 36.2%,
AIR 0.918, vs. Woman's AIR 0.938) — and is also a real injected bias (×0.85 multiplier, stronger than
Woman's ×0.90) — but comes back **not significant** (p = 0.0998). `gender` Woman at `offer` (×0.88
multiplier, also real) similarly falls short (p = 0.639). The difference is sample size, not effect
size: only 795 non-binary candidates were at risk at screen (vs. 9,373 women), and only 1,045 women
remained at risk by the offer stage (funnel attrition). **Two real, deliberately-injected biases did not
reach statistical significance in this run** — not because they aren't real, but because smaller
protected groups and later funnel stages systematically have less statistical power to confirm a gap
given the sample available, and that limitation is now visible in the data rather than implicit in a
plain selection-rate table.

Evidence: `docs/evidence/hiring_significance_tests.png`. Full table:
`hiring_bias_model_comparison.ipynb`, Section 7.

## Intended use

This is a methodology demonstration — cross-validated evaluation, per-group calibration, and
significance-tested fairness gaps on synthetic data with documented, known ground truth — not a hiring
model or a fairness-certification tool meant to be applied to real candidates or a real employer's data.
A ratio or p-value here is a statistical screening signal, exactly like the existing four-fifths-rule
ratio; neither is a legal finding, and this audit model never scores, ranks, or decides on any
candidate's outcome, real or synthetic.

## Known limitations

- Single logistic regression, no hyperparameter search — the same untuned-model caveat every other
  project's model card states plainly rather than omits.
- 10-bin calibration is coarse in the sparse tail (1–8 points per group in the second bin) — a finer or
  adaptive binning scheme might resolve more structure there, at the cost of even noisier per-bin
  estimates given how few candidates fall in that range.
- Chi-square, not an exact test (e.g. Fisher's exact) — appropriate given every cell's sample size here,
  but worth naming as a choice, not an oversight.
- Statistical *non-significance* is reported for two real injected biases above; a reader using only the
  significance-test table (not the underlying `fairness_metrics` selection rates and AIRs) could
  mistakenly conclude those two gaps aren't real. They are, by construction — the tests are just
  underpowered to confirm them at this group's sample size. Significance testing narrows which claims
  this tool can make *confidently*; it doesn't replace the underlying rate comparison.
