-- Power BI-facing views for Project 3. Passthrough/aggregation views over
-- tables already populated by 002_fairness_metrics.sql -- no logic
-- duplicated here. These views expose counts/rates only, never a
-- per-candidate hire/no-hire recommendation.

CREATE OR REPLACE VIEW hiring_bias.powerbi_funnel_summary AS
SELECT
    role_family,
    COUNT(*) AS total_applications,
    COUNT(*) FILTER (WHERE reached_screen) AS reached_screen,
    COUNT(*) FILTER (WHERE reached_interview) AS reached_interview,
    COUNT(*) FILTER (WHERE reached_offer) AS reached_offer,
    COUNT(*) FILTER (WHERE reached_hire) AS reached_hire
FROM hiring_bias.candidates
GROUP BY role_family;

CREATE OR REPLACE VIEW hiring_bias.powerbi_fairness_summary AS
SELECT * FROM hiring_bias.fairness_metrics;

CREATE OR REPLACE VIEW hiring_bias.powerbi_group_comparison AS
SELECT
    group_attribute, group_value, stage,
    total_at_risk, passed, selection_rate,
    reference_group, reference_selection_rate, adverse_impact_ratio,
    selection_rate - reference_selection_rate AS rate_difference,
    (adverse_impact_ratio < 0.8) AS fails_four_fifths_rule
FROM hiring_bias.fairness_metrics;
