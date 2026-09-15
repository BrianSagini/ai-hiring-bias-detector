# Power BI Guide

## Status — read this first

A real `.pbip` project exists at `powerbi/HiringBiasDetector.pbip`. Real and complete: 3 tables,
all 11 DAX measures below (0 relationships — deliberate, see below), and **12 real visual objects
across all 4 pages** (see [Visual inventory](#visual-inventory)) — every one binds to an actual
table/column/measure. Page 4's ideal content (audit-model coefficients) still needs a new SQL view
(`hiring_bias.powerbi_audit_coefficients`) that doesn't exist yet, so page 4 uses the fairness
tables instead — real fields, just not the coefficients page originally envisioned.

**Power BI Desktop validation status: NOT VERIFIED.** This project's sibling (Climate Risk) was
confirmed *openable* by Power BI Desktop in one clean, safe test — full authoring ribbon, "Loading
report" state. A second validation attempt on that file captured unrelated content from another
window on this live desktop instead (a focus-tracking failure, not a Power BI issue) — deleted
immediately, never committed — and after that second incident, further screenshot-based validation
was stopped entirely, before reaching this repo specifically. The outer project structure follows
the same pattern already confirmed acceptable; **the visual JSON below was authored to the best
available knowledge of the PBIR schema but was never itself opened in Power BI Desktop.** If you
open this file and something doesn't render, that's real information.

## Data connectivity

Get Data → Database → PostgreSQL database → `localhost:5433` / `analytics` / `analytics_ro`
(password from your `.env`). Mode: **Import**.

## Tables, relationships, measures

Tables: `hiring_bias.powerbi_funnel_summary` (1 row/`role_family`), `powerbi_fairness_summary`,
`powerbi_group_comparison` (1 row/attribute/group/stage each).

**No relationships** — each table is independently sliceable; a bridge relationship via
`role_family` would be artificial (nothing in this data needs that cross-filter), so it's
deliberately left out rather than added "just in case."

```dax
Total Applications = SUM(powerbi_funnel_summary[total_applications])
Total Screened = SUM(powerbi_funnel_summary[reached_screen])
Total Interviewed = SUM(powerbi_funnel_summary[reached_interview])
Total Offered = SUM(powerbi_funnel_summary[reached_offer])
Total Hired = SUM(powerbi_funnel_summary[reached_hire])
Screen Rate = DIVIDE([Total Screened], [Total Applications])
Interview Rate = DIVIDE([Total Interviewed], [Total Screened])
Offer Rate = DIVIDE([Total Offered], [Total Interviewed])
Hire Rate = DIVIDE([Total Hired], [Total Offered])
Overall Selection Rate = DIVIDE([Total Hired], [Total Applications])
Groups Failing 4/5ths Rule = CALCULATE(DISTINCTCOUNT(powerbi_group_comparison[group_value]), powerbi_group_comparison[fails_four_fifths_rule] = TRUE)
```
Selection rate and adverse-impact ratio *per group* are already SQL-computed columns on
`powerbi_group_comparison` — visualize directly, don't re-derive in DAX.

## Design system

Base: near-white `#F7F8FA` background, Segoe UI. This project's accents: primary blue `#2C5F8A`,
secondary teal `#2E8B99`, warning amber `#E8A33D`, critical red `#C0392B` (fairness-threshold
indicator only — never used to color a demographic group itself). Demographic-group colors are
deliberately **neutral, not semantic**: assign a fixed qualitative sequence (Blue `#2C5F8A`,
Purple `#6C4AB6`, Teal `#2E8B99`, Slate `#64748B`) in data order, never by category meaning.

## Visual inventory

Every visual below is a real object in `powerbi/HiringBiasDetector.Report/definition/pages/*/visuals/`.

**Page 1 — Executive Overview**
- Total Applications — Card — `FunnelSummary[Total Applications]`
- Overall Selection Rate — Card — `FunnelSummary[Overall Selection Rate]`
- Hire Rate — Card — `FunnelSummary[Hire Rate]`
- Groups Failing 4/5ths Rule — Card — `GroupComparison[Groups Failing 4/5ths Rule]`
- Applications vs. Hires by Role Family — Clustered column chart — Category `FunnelSummary[role_family]`, Y `FunnelSummary[total_applications]`, `FunnelSummary[reached_hire]`

**Page 2 — Recruitment Funnel**
- Funnel Stage Totals by Role Family — Clustered column chart — Category `FunnelSummary[role_family]`, Y all 5 stage totals
- Funnel Detail — Table — `FunnelSummary[role_family]` + all 5 stage totals

**Page 3 — Fairness & Group Comparison**
- Selection Rate by Group — Clustered column chart — Category `GroupComparison[group_value]`, Y `GroupComparison[selection_rate]`
- Adverse Impact Ratio by Group — Clustered column chart — Category `GroupComparison[group_value]`, Y `GroupComparison[adverse_impact_ratio]`
- Group Comparison Detail — Table — attribute, group, stage, selection rate, adverse-impact ratio, fails-4/5ths flag

**Page 4 — Model & Decision Analysis** *(real fields, but not yet the coefficients page — see Status)*
- Selection Rate Difference vs. Reference Group — Clustered column chart — Category `GroupComparison[group_value]`, Y `GroupComparison[rate_difference]`
- Fairness Detail — Table — `FairnessSummary[group_attribute]`, `[group_value]`, `[stage]`, `[total_at_risk]`, `[passed]`, `[reference_selection_rate]`

**Total: 12 visuals across 4 pages.**

**Never add a per-candidate table or score to this report.**

## Power BI Service publication: BLOCKED

Needs a Power BI account/workspace and an On-premises Data Gateway — neither exists here.
