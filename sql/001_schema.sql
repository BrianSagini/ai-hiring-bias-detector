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
