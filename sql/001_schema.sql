-- AI Hiring Bias Detector -- schema. Every row in this schema is 100%
-- SYNTHETIC (candidates.is_synthetic is always true) -- see
-- docs/methodology_hiring_bias.md.

CREATE TABLE IF NOT EXISTS hiring_bias.candidates (
    candidate_id          TEXT PRIMARY KEY,
    gender                TEXT NOT NULL,
    ethnicity              TEXT NOT NULL,
    education_level       TEXT,
    years_experience      DOUBLE PRECISION,
    role_family           TEXT,
    application_source    TEXT,
    application_date      DATE,
    qualification_score   DOUBLE PRECISION,
    reached_screen        BOOLEAN NOT NULL,
    reached_interview     BOOLEAN NOT NULL,
    reached_offer         BOOLEAN NOT NULL,
    reached_hire          BOOLEAN NOT NULL,
    is_synthetic          BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS hiring_bias.fairness_metrics (
    group_attribute            TEXT NOT NULL,
    group_value                TEXT NOT NULL,
    stage                      TEXT NOT NULL,
    total_at_risk              INT,
    passed                     INT,
    selection_rate             DOUBLE PRECISION,
    reference_group            TEXT,
    reference_selection_rate   DOUBLE PRECISION,
    adverse_impact_ratio       DOUBLE PRECISION,
    computed_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (group_attribute, group_value, stage)
);

CREATE TABLE IF NOT EXISTS hiring_bias.audit_model_coefficients (
    feature       TEXT PRIMARY KEY,
    coef_mean     DOUBLE PRECISION,
    coef_ci_low   DOUBLE PRECISION,
    coef_ci_high  DOUBLE PRECISION
);

-- Audit-model held-out evaluation. Same shape as fraud_pattern's,
-- climate_risk's, and dark_store's model_evaluation (model_name, real
-- metrics, computed_at) for consistency across the portfolio's ML tables --
-- precision/recall/F1/ROC-AUC here since this is a classification problem.
CREATE TABLE IF NOT EXISTS hiring_bias.model_evaluation (
    model_name    TEXT PRIMARY KEY,
    precision     DOUBLE PRECISION,
    recall        DOUBLE PRECISION,
    f1            DOUBLE PRECISION,
    roc_auc       DOUBLE PRECISION,
    threshold     DOUBLE PRECISION,
    computed_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Stratified K-fold cross-validation, fold by fold -- the variance across
-- folds is the point, not just the mean: a fairness-audit model whose
-- accuracy swings a lot fold to fold is itself a reason to trust it less.
CREATE TABLE IF NOT EXISTS hiring_bias.cv_fold_results (
    model_name    TEXT NOT NULL,
    fold_number   INT NOT NULL,
    roc_auc       DOUBLE PRECISION,
    precision     DOUBLE PRECISION,
    recall        DOUBLE PRECISION,
    f1            DOUBLE PRECISION,
    computed_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (model_name, fold_number)
);

-- Calibration: for each bin of predicted P(hire), the mean predicted
-- probability vs. the observed hire rate in that bin -- computed both
-- overall (group_attribute/group_value = 'overall') and per protected
-- group, since miscalibration that differs by group is itself a fairness
-- signal, not just an accuracy footnote.
CREATE TABLE IF NOT EXISTS hiring_bias.calibration_bins (
    model_name             TEXT NOT NULL,
    group_attribute        TEXT NOT NULL,
    group_value             TEXT NOT NULL,
    bin_index               INT NOT NULL,
    bin_lower                DOUBLE PRECISION NOT NULL,
    bin_upper                DOUBLE PRECISION NOT NULL,
    mean_predicted_prob     DOUBLE PRECISION,
    observed_hire_rate      DOUBLE PRECISION,
    n_in_bin                 INT NOT NULL,
    computed_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (model_name, group_attribute, group_value, bin_index)
);

-- Statistical significance behind each hiring_bias.fairness_metrics row: a
-- chi-square test of independence (this group's passed/not-passed counts
-- vs. the reference group's -- a 2x2 contingency table) for the
-- selection-rate gap the four-fifths ratio already flags. Chi-square, not
-- a permutation test: every group/stage cell here has from several dozen
-- to several thousand candidates, comfortably large enough for the
-- chi-square approximation to hold -- a permutation test would converge on
-- the same p-value at far higher compute cost, not a different one, at
-- this sample size.
CREATE TABLE IF NOT EXISTS hiring_bias.fairness_significance_tests (
    group_attribute    TEXT NOT NULL,
    group_value        TEXT NOT NULL,
    stage              TEXT NOT NULL,
    reference_group    TEXT,
    test_name          TEXT NOT NULL,
    chi2_statistic     DOUBLE PRECISION,
    p_value            DOUBLE PRECISION,
    significant_at_05  BOOLEAN,
    computed_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (group_attribute, group_value, stage)
);
