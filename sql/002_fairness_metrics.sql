-- Selection rates and the 4/5ths-rule adverse impact ratio, per funnel
-- stage, for gender and ethnicity. adverse_impact_ratio = this group's
-- selection rate / the highest selection rate among groups for that
-- attribute+stage (the conventional 4/5ths-rule denominator) -- a ratio
-- below 0.8 is the traditional (not legally dispositive) screening
-- threshold for possible adverse impact. See docs/methodology_hiring_bias.md.

WITH base AS (
    SELECT
        candidate_id, gender, ethnicity,
        TRUE AS eligible_screen, reached_screen AS passed_screen,
        reached_screen AS eligible_interview, reached_interview AS passed_interview,
        reached_interview AS eligible_offer, reached_offer AS passed_offer,
        reached_offer AS eligible_hire, reached_hire AS passed_hire
    FROM hiring_bias.candidates
),
stage_stats AS (
    SELECT 'gender' AS group_attribute, gender AS group_value, 'screen' AS stage,
           COUNT(*) FILTER (WHERE eligible_screen) AS total_at_risk,
           COUNT(*) FILTER (WHERE eligible_screen AND passed_screen) AS passed
    FROM base GROUP BY gender
    UNION ALL
    SELECT 'gender', gender, 'interview',
           COUNT(*) FILTER (WHERE eligible_interview), COUNT(*) FILTER (WHERE eligible_interview AND passed_interview)
    FROM base GROUP BY gender
    UNION ALL
    SELECT 'gender', gender, 'offer',
           COUNT(*) FILTER (WHERE eligible_offer), COUNT(*) FILTER (WHERE eligible_offer AND passed_offer)
    FROM base GROUP BY gender
    UNION ALL
    SELECT 'gender', gender, 'hire',
           COUNT(*) FILTER (WHERE eligible_hire), COUNT(*) FILTER (WHERE eligible_hire AND passed_hire)
    FROM base GROUP BY gender
    UNION ALL
    SELECT 'ethnicity', ethnicity, 'screen',
           COUNT(*) FILTER (WHERE eligible_screen), COUNT(*) FILTER (WHERE eligible_screen AND passed_screen)
    FROM base GROUP BY ethnicity
    UNION ALL
    SELECT 'ethnicity', ethnicity, 'interview',
           COUNT(*) FILTER (WHERE eligible_interview), COUNT(*) FILTER (WHERE eligible_interview AND passed_interview)
    FROM base GROUP BY ethnicity
    UNION ALL
    SELECT 'ethnicity', ethnicity, 'offer',
           COUNT(*) FILTER (WHERE eligible_offer), COUNT(*) FILTER (WHERE eligible_offer AND passed_offer)
    FROM base GROUP BY ethnicity
    UNION ALL
    SELECT 'ethnicity', ethnicity, 'hire',
           COUNT(*) FILTER (WHERE eligible_hire), COUNT(*) FILTER (WHERE eligible_hire AND passed_hire)
    FROM base GROUP BY ethnicity
),
with_rate AS (
    SELECT *,
        CASE WHEN total_at_risk > 0 THEN passed::double precision / total_at_risk ELSE NULL END AS selection_rate
    FROM stage_stats
),
with_ref AS (
    SELECT *,
        FIRST_VALUE(group_value) OVER (
            PARTITION BY group_attribute, stage ORDER BY selection_rate DESC NULLS LAST
        ) AS reference_group,
        MAX(selection_rate) OVER (PARTITION BY group_attribute, stage) AS reference_selection_rate
    FROM with_rate
)
INSERT INTO hiring_bias.fairness_metrics
    (group_attribute, group_value, stage, total_at_risk, passed, selection_rate, reference_group, reference_selection_rate, adverse_impact_ratio, computed_at)
SELECT
    group_attribute, group_value, stage, total_at_risk, passed, selection_rate, reference_group, reference_selection_rate,
    CASE WHEN reference_selection_rate > 0 THEN selection_rate / reference_selection_rate ELSE NULL END AS adverse_impact_ratio,
    now()
FROM with_ref
ON CONFLICT (group_attribute, group_value, stage) DO UPDATE SET
    total_at_risk = EXCLUDED.total_at_risk,
    passed = EXCLUDED.passed,
    selection_rate = EXCLUDED.selection_rate,
    reference_group = EXCLUDED.reference_group,
    reference_selection_rate = EXCLUDED.reference_selection_rate,
    adverse_impact_ratio = EXCLUDED.adverse_impact_ratio,
    computed_at = EXCLUDED.computed_at;
