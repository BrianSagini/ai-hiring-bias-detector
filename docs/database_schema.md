# Database Schema

Postgres 16, database `analytics`, schema `hiring_bias`. Read-only role `analytics_ro` has
`SELECT` on everything here.

| Table | Grain | Notes |
|---|---|---|
| `candidates` | 1 row/synthetic candidate (20k) | fully synthetic (`is_synthetic`), includes funnel-stage booleans |
| `fairness_metrics` | 1 row/attribute/group/stage | SQL-computed selection rates + four-fifths adverse-impact ratio |
| `audit_model_coefficients` | 1 row/model feature | interpretability only, **never used to score candidates** |
| `powerbi_funnel_summary`, `powerbi_fairness_summary`, `powerbi_group_comparison` | views | pure passthrough/aggregation views for Power BI |

Every fact table has a natural-key primary key, so reruns upsert idempotently rather than
duplicate.
