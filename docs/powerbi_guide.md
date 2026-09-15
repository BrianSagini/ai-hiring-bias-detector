# Power BI Guide

## Status — read this first

A real `.pbip` project exists at `powerbi/HiringBiasDetector.pbip`, generated programmatically —
**never opened in Power BI Desktop, so not validated.** Real and complete: 3 tables, all 11 DAX
measures below (0 relationships — deliberate, see below). Placeholder: 4 report pages exist,
named correctly, zero visuals. Page 4 additionally needs a new SQL view
(`hiring_bias.powerbi_audit_coefficients`, exposing `audit_model_coefficients`) before it can be
built — not yet added.

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

## Pages

1. **Executive Overview** — cards for every funnel-rate measure above plus Groups Failing 4/5ths
   Rule (amber/red if >0); a prominent synthetic-data banner.
2. **Recruitment Funnel** — a funnel/stepped-bar chart of the five stage totals; `role_family`
   slicer (the only breakdown dimension this dataset has).
3. **Fairness & Group Comparison** — selection rate by group/stage; adverse-impact ratio with a
   reference line at 0.8; red/amber formatting only where `fails_four_fifths_rule` is true.
4. **Model & Decision Analysis** — *(needs the new view above first)* audit-model coefficients
   with confidence intervals; text disclaimer that this model was never used to score candidates.

**Never add a per-candidate table or score to this report.**

## Power BI Service publication: BLOCKED

Needs a Power BI account/workspace and an On-premises Data Gateway — neither exists here.
