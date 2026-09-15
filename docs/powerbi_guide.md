# Power BI Guide

## Status — read this first

A real `.pbip` project exists at `powerbi/HiringBiasDetector.pbip`. Real and complete: 3 tables,
all 11 DAX measures below (0 relationships — deliberate, see below), **20 real visual objects
across all 4 pages** (16 data visuals + a header/footer text box per page — see
[Visual inventory](#visual-inventory)), a custom theme (`HiringBiasTheme.json`, wired into
`report.json`), and accent colors applied only to compliance-indicator metrics, never to
demographic groups (see Design system). Page 4's ideal content (audit-model coefficients) still
needs a new SQL view (`hiring_bias.powerbi_audit_coefficients`) that doesn't exist yet, so page 4
uses the fairness tables instead — real fields, just not the coefficients page originally
envisioned.

**Power BI Desktop validation status: FULLY VERIFIED. All 4 pages confirmed rendering correctly
with real data, real colors, in Power BI Desktop** (see `docs/evidence/page1_executive_overview.png`
through `page4_model_decision_analysis.png`).

The root causes behind the original round-2 bugs (blank charts, no titles, a literal `\$`, wrong
date format, maps disabled for the tenant) were found on the sibling Climate Risk project and
fixed identically here — see Climate's `docs/powerbi_guide.md` for that diagnostic account. This
project's own file was then independently reopened in Desktop, where it first failed to load
entirely with "Your report has issues that could not be resolved" — `report.json`'s
`themeCollection.baseTheme.reportVersionAtImport` was a bare string (`"5.55"`) instead of the
required `{visual, report, page}` object. Fixed to match Climate's shape.

After that fix, the file loaded but every chart Y-field bound as a raw, unaggregated `Column`
reference rendered as a completely empty plot area — no bars, no error shown. Fixed by wrapping
each affected field in Desktop's own confirmed `Aggregation` shape
(`field.Aggregation.Expression.Column` + `Function`) or, where an exact-match DAX measure existed
(`Total Applications`, `Total Screened`, `Total Interviewed`, `Total Offered`, `Total Hired`),
pointing the field at that measure instead. Selection-rate/adverse-impact-ratio/rate-difference
charts use `Function: 1` (Average) on the raw column deliberately — the guide's own instruction not
to re-derive an already-SQL-computed rate in DAX still holds; the Average wrapper exists only to
satisfy the chart's aggregation requirement, and is a no-op given one row per category.

**Round 5 (this one)**: tightened every page's layout to a dense 16px-margin/14px-gutter grid, and
fixed the canvas background and card accent colors — `visualStyles.*.*.outspace` doesn't actually
control the page canvas (confirmed via Desktop's own theme customizer; the real property is
`visualStyles.page.*.background`), and cards need `objects.labels[0].properties.color`, not
`dataPoint` (confirmed via Desktop's own save after setting a card's color through Format →
Callout value → Color). `report.json` was also rebuilt from Climate's proven-correct structure
(older schema version and a missing base-theme resourcePackage entry, both silently tolerated
until this round's newer theme feature tripped a hard load error). All 4 pages reopened and
confirmed rendering correctly.

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

## Design system — now actually applied, not just documented

Segoe UI. Accents: primary blue `#2C5F8A`, secondary teal `#2E8B99`, warning amber `#E8A33D`,
critical red `#C0392B` (fairness-threshold indicator only — never used to color a demographic
group itself). The theme's `dataColors` sequence leads with the neutral qualitative group
sequence (Blue, Purple `#6C4AB6`, Teal, Slate `#64748B`) precisely so any chart that ends up
color-differentiating by group falls back to those, not amber/red, by construction.

**Background**: a pale blue-tinted canvas `#D8E7F2` behind white visual containers. Set via
`HiringBiasTheme.json`'s `visualStyles.page.*.background` — **not** `outspace`, which doesn't
control the canvas (see Status above for how that was confirmed).

**Per-visual accent colors**: applied *only* to compliance-indicator metrics, never to a
demographic group — Groups Failing 4/5ths Rule card, Adverse Impact Ratio by Group, and Selection
Rate Difference vs. Reference Group → warning amber (all bars in a uniform amber, since the metric
itself is the thing being flagged, not any one group). Selection Rate by Group and the funnel
charts are left theme-driven, using the neutral group sequence above — no group is ever singled
out in red/green. The amber card uses `objects.labels[0].properties.color` (not `dataPoint` — see
Status above); the amber charts use each chart's own `dataPoint.defaultColor`.

**Header/footer**: every page gets a themed header and footer as real `textbox` visuals,
including a synthetic-data disclosure in the header badge.

**Layout**: a standard dense grid — 16px canvas margin, 14px gutter between visuals, visuals
resized to fill their row/column exactly. Before this pass, pages covered 78–83% of the canvas by
visual area; after, 87–88%.

## Visual inventory

Every visual below is a real object in `powerbi/HiringBiasDetector.Report/definition/pages/*/visuals/`.

**Page 1 — Executive Overview**
- Total Applications — Card — `FunnelSummary[Total Applications]`
- Overall Selection Rate — Card — `FunnelSummary[Overall Selection Rate]`
- Hire Rate — Card — `FunnelSummary[Hire Rate]`
- Groups Failing 4/5ths Rule — Card — `GroupComparison[Groups Failing 4/5ths Rule]`
- Applications vs. Hires by Role Family — Clustered column chart — Category `FunnelSummary[role_family]`, Y `FunnelSummary[Total Applications]`, `FunnelSummary[Total Hired]`

**Page 2 — Recruitment Funnel**
- Funnel Stage Totals by Role Family — Clustered column chart — Category `FunnelSummary[role_family]`, Y all 5 stage-total measures
- Funnel Detail — Table — `FunnelSummary[role_family]` + all 5 stage totals

**Page 3 — Fairness & Group Comparison**
- Selection Rate by Group — Clustered column chart — Category `GroupComparison[group_value]`, Y `GroupComparison[selection_rate]` (Average aggregation)
- Adverse Impact Ratio by Group — Clustered column chart — Category `GroupComparison[group_value]`, Y `GroupComparison[adverse_impact_ratio]` (Average aggregation)
- Group Comparison Detail — Table — attribute, group, stage, selection rate, adverse-impact ratio, fails-4/5ths flag

**Page 4 — Model & Decision Analysis** *(real fields, but not yet the coefficients page — see Status)*
- Selection Rate Difference vs. Reference Group — Clustered column chart — Category `GroupComparison[group_value]`, Y `GroupComparison[rate_difference]` (Average aggregation)
- Fairness Detail — Table — `FairnessSummary[group_attribute]`, `[group_value]`, `[stage]`, `[total_at_risk]`, `[passed]`, `[reference_selection_rate]`

**Total: 20 visuals across 4 pages** (12 data visuals + a header and footer text box per page).

**Never add a per-candidate table or score to this report.**

## Power BI Service publication: BLOCKED

Needs a Power BI account/workspace and an On-premises Data Gateway — neither exists here.
