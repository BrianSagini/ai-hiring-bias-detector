"""AI Hiring Bias Detector -- synthetic data generation + fairness analysis.

100% SYNTHETIC DATA. No real applicant, employer, or hiring data is used
anywhere in this project. Real anonymized hiring-funnel datasets with
protected-attribute labels are either not freely redistributable or carry
licensing/ethical constraints incompatible with a public portfolio repo
(see docs/data_sources.md) -- a parameterized generator is used instead,
with a documented, adjustable bias-injection mechanism so the fairness
metrics computed downstream have real signal to detect.

This module (and the dashboard built on it) is a FAIRNESS AUDIT tool. It
does not and must not decide who should be hired -- see
docs/methodology_hiring_bias.md, "Ethical constraints" section.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from shared.database import bulk_upsert_dataframe, get_engine, upsert_dataframe
from shared.validation import validate_dataframe

EVIDENCE_DIR = os.path.join(os.path.dirname(__file__), "docs", "evidence")

RNG_SEED = 42
N_CANDIDATES = 20_000

GENDERS = ["Woman", "Man", "Non-binary"]
GENDER_P = [0.47, 0.49, 0.04]
ETHNICITIES = ["Group A", "Group B", "Group C", "Group D"]
ETHNICITY_P = [0.55, 0.18, 0.17, 0.10]
EDUCATION = ["High School", "Bachelor's", "Master's", "PhD"]
EDUCATION_P = [0.15, 0.5, 0.27, 0.08]
ROLE_FAMILIES = ["Engineering", "Sales", "Operations", "Design", "Data/Analytics"]
SOURCES = ["Referral", "Job Board", "University Recruiting", "Direct Apply", "Recruiter Outreach"]

# --- Documented bias injection ------------------------------------------------
# Applied as a MULTIPLIER on an otherwise qualification-driven pass
# probability at each funnel stage. 1.0 = no injected bias. These values
# are deliberately synthetic and exaggerated versus most real-world
# measured gaps, so the fairness metrics below have unambiguous signal to
# detect in a demo. See docs/methodology_hiring_bias.md.
STAGE_BIAS_MULTIPLIER = {
    # stage: {group_column: {group_value: multiplier}}
    "screen": {"gender": {"Woman": 0.90, "Non-binary": 0.85}},
    "interview": {"ethnicity": {"Group C": 0.80, "Group D": 0.75}},
    "offer": {"gender": {"Woman": 0.88}},
}

RAW_DIR = os.path.join(os.path.dirname(__file__), "data_raw")


def generate_candidates(n: int = N_CANDIDATES, seed: int = RNG_SEED) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({
        "candidate_id": [f"C{100000+i}" for i in range(n)],
        "gender": rng.choice(GENDERS, n, p=GENDER_P),
        "ethnicity": rng.choice(ETHNICITIES, n, p=ETHNICITY_P),
        "education_level": rng.choice(EDUCATION, n, p=EDUCATION_P),
        "years_experience": np.clip(rng.gamma(shape=2.5, scale=2.2, size=n), 0, 30).round(1),
        "role_family": rng.choice(ROLE_FAMILIES, n),
        "application_source": rng.choice(SOURCES, n),
        "application_date": pd.to_datetime("2025-01-01") + pd.to_timedelta(rng.integers(0, 365, n), unit="D"),
    })
    df["is_synthetic"] = True
    return df


def _qualification_score(df: pd.DataFrame) -> np.ndarray:
    """A synthetic 'ground-truth' qualification signal (0-1), used to drive
    genuinely qualification-based funnel progression before bias is layered
    on top -- without this, injected bias would be the *only* signal, which
    would make the audit trivial rather than realistic (real qualification
    noise coexisting with bias)."""
    edu_score = df["education_level"].map({"High School": 0.2, "Bachelor's": 0.5, "Master's": 0.75, "PhD": 0.9})
    exp_score = np.clip(df["years_experience"] / 15, 0, 1)
    return (0.5 * edu_score + 0.5 * exp_score).to_numpy()


def _apply_stage(
    df: pd.DataFrame, passed_so_far: np.ndarray, base_pass_rate: float, stage: str, rng: np.random.Generator
) -> np.ndarray:
    qual = _qualification_score(df)
    prob = base_pass_rate * (0.4 + 0.6 * qual)  # qualification pushes prob toward/away from base rate
    for group_col, multipliers in STAGE_BIAS_MULTIPLIER.get(stage, {}).items():
        for group_value, mult in multipliers.items():
            mask = df[group_col] == group_value
            prob = np.where(mask, prob * mult, prob)
    prob = np.clip(prob, 0, 1)
    draw = rng.random(len(df))
    return passed_so_far & (draw < prob)


def run_funnel(candidates: pd.DataFrame, seed: int = RNG_SEED) -> pd.DataFrame:
    rng = np.random.default_rng(seed + 1)
    n = len(candidates)
    applied = np.ones(n, dtype=bool)
    screened = _apply_stage(candidates, applied, base_pass_rate=0.55, stage="screen", rng=rng)
    interviewed = _apply_stage(candidates, screened, base_pass_rate=0.50, stage="interview", rng=rng)
    offered = _apply_stage(candidates, interviewed, base_pass_rate=0.45, stage="offer", rng=rng)
    hired = _apply_stage(candidates, offered, base_pass_rate=0.85, stage="hire", rng=rng)

    out = candidates.copy()
    out["reached_screen"] = screened
    out["reached_interview"] = interviewed
    out["reached_offer"] = offered
    out["reached_hire"] = hired
    out["qualification_score"] = _qualification_score(candidates).round(3)
    return out


def validate_funnel(df: pd.DataFrame):
    report = validate_dataframe(
        df,
        required_columns=["candidate_id", "gender", "ethnicity", "reached_screen", "reached_interview", "reached_offer", "reached_hire"],
        not_null_columns=["candidate_id", "gender", "ethnicity"],
        allowed_values={"gender": set(GENDERS), "ethnicity": set(ETHNICITIES)},
    )
    # Funnel must be monotonic: can't reach a later stage without every earlier one.
    non_monotonic = (
        (df["reached_hire"] & ~df["reached_offer"])
        | (df["reached_offer"] & ~df["reached_interview"])
        | (df["reached_interview"] & ~df["reached_screen"])
    )
    report.invalid_row_indices |= set(df.index[non_monotonic])
    report.valid_rows = report.total_rows - len(report.invalid_row_indices)
    return report


def load_candidates(df: pd.DataFrame) -> int:
    return bulk_upsert_dataframe(df, schema="hiring_bias", table="candidates", key_columns=["candidate_id"])


def compute_and_load_fairness_metrics() -> int:
    from shared.database import get_engine, run_sql_file

    sql_path = os.path.join(os.path.dirname(__file__), "sql", "002_fairness_metrics.sql")
    run_sql_file(sql_path)
    engine = get_engine()
    with engine.connect() as conn:
        return int(conn.exec_driver_sql("SELECT COUNT(*) FROM hiring_bias.fairness_metrics").scalar())


AUDIT_FEATURE_COLUMNS = ["gender", "ethnicity", "education_level", "years_experience", "role_family", "application_source"]
AUDIT_CATEGORICAL_COLUMNS = ["gender", "ethnicity", "education_level", "role_family", "application_source"]
AUDIT_MODEL_NAME = "logistic_regression_audit"
AUDIT_TEST_SIZE = 0.2
AUDIT_CV_FOLDS = 5
AUDIT_CALIBRATION_BINS = 10


def _build_audit_features(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Shared feature build for both the bootstrap-CI audit model below and
    evaluate_audit_model() -- one source of truth for what goes into the
    audit model, not two parallel encodings that could quietly drift apart."""
    from sklearn.preprocessing import StandardScaler

    features = pd.get_dummies(
        df[AUDIT_FEATURE_COLUMNS], columns=AUDIT_CATEGORICAL_COLUMNS, drop_first=True,
    )
    feature_names = features.columns.tolist()
    X = StandardScaler().fit_transform(features.astype(float))
    y = df["reached_hire"].astype(int).to_numpy()
    return X, y, feature_names


def train_and_load_audit_model() -> int:
    """Interpretable logistic-regression AUDIT model: which features
    correlate with reaching 'hire', reported as coefficients + bootstrap
    confidence intervals for interpretability. NEVER used to score or
    decide on real/new candidates -- see docs/methodology.md.
    """
    from sklearn.linear_model import LogisticRegression

    from shared.database import get_engine

    engine = get_engine()
    df = pd.read_sql("SELECT * FROM hiring_bias.candidates", engine)
    X, y, feature_names = _build_audit_features(df)

    rng = np.random.default_rng(RNG_SEED)
    boot_coefs = []
    for _ in range(200):
        idx = rng.integers(0, len(X), len(X))
        model = LogisticRegression(max_iter=1000)
        model.fit(X[idx], y[idx])
        boot_coefs.append(model.coef_[0])
    boot_coefs = np.array(boot_coefs)

    result = pd.DataFrame({
        "feature": feature_names,
        "coef_mean": boot_coefs.mean(axis=0).round(4),
        "coef_ci_low": np.percentile(boot_coefs, 2.5, axis=0).round(4),
        "coef_ci_high": np.percentile(boot_coefs, 97.5, axis=0).round(4),
    })
    upsert_dataframe(result, schema="hiring_bias", table="audit_model_coefficients", key_columns=["feature"])
    return len(result)


def _calibration_table(y_true: np.ndarray, y_proba: np.ndarray, n_bins: int = AUDIT_CALIBRATION_BINS) -> list[dict]:
    """Equal-width reliability-diagram bins over [0, 1], with real per-bin
    counts -- computed by hand rather than sklearn's calibration_curve so
    calibration_bins reflects exactly what gets plotted (bin edges, n_in_bin
    included), not a re-derived approximation of it. Bins with zero points
    are skipped rather than written as a misleading 0/0."""
    bin_edges = np.linspace(0, 1, n_bins + 1)
    bin_idx = np.clip(np.digitize(y_proba, bin_edges, right=True) - 1, 0, n_bins - 1)
    rows = []
    for b in range(n_bins):
        mask = bin_idx == b
        n = int(mask.sum())
        if n == 0:
            continue
        rows.append({
            "bin_index": b,
            "bin_lower": float(bin_edges[b]),
            "bin_upper": float(bin_edges[b + 1]),
            "mean_predicted_prob": float(y_proba[mask].mean()),
            "observed_hire_rate": float(y_true[mask].mean()),
            "n_in_bin": n,
        })
    return rows


def evaluate_audit_model() -> dict:
    """Deepens the interpretability-only audit model above with the parts
    that matter for trusting a fairness tool, not just an accuracy number:
    does its accuracy hold up across folds (stratified K-fold, since the
    ~10% hire rate is real class imbalance) rather than one lucky split;
    is its predicted P(hire) actually reliable at face value for every
    protected group, not just overall (calibration); and are the
    selection-rate gaps hiring_bias.fairness_metrics already flags real
    given the sample size, or plausibly noise (chi-square significance).
    Same feature build as train_and_load_audit_model() via
    _build_audit_features() -- not a parallel reimplementation. NEVER used
    to score or decide on real/new candidates -- see docs/methodology.md.
    """
    from scipy.stats import chi2_contingency
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import f1_score, precision_score, recall_score, roc_auc_score
    from sklearn.model_selection import StratifiedKFold, train_test_split

    from shared.database import get_engine

    engine = get_engine()
    df = pd.read_sql("SELECT * FROM hiring_bias.candidates", engine).reset_index(drop=True)
    X, y, feature_names = _build_audit_features(df)
    groups = df[["gender", "ethnicity"]]
    computed_at = datetime.now(timezone.utc)

    # --- 1. Single held-out split: a model_evaluation row in the same
    # shape every other project's ML table already uses. ---
    X_train, X_test, y_train, y_test, _, groups_test = train_test_split(
        X, y, groups, test_size=AUDIT_TEST_SIZE, random_state=RNG_SEED, stratify=y,
    )
    model = LogisticRegression(max_iter=1000)
    model.fit(X_train, y_train)
    proba_test = model.predict_proba(X_test)[:, 1]
    pred_test = (proba_test >= 0.5).astype(int)

    eval_row = pd.DataFrame([{
        "model_name": AUDIT_MODEL_NAME,
        "precision": float(precision_score(y_test, pred_test, zero_division=0)),
        "recall": float(recall_score(y_test, pred_test, zero_division=0)),
        "f1": float(f1_score(y_test, pred_test, zero_division=0)),
        "roc_auc": float(roc_auc_score(y_test, proba_test)),
        "threshold": 0.5,
        "computed_at": computed_at,
    }])
    upsert_dataframe(eval_row, schema="hiring_bias", table="model_evaluation", key_columns=["model_name"])

    # --- 2. Stratified K-fold CV: report variance across folds, not just
    # the mean -- a fairness-audit model whose accuracy swings a lot fold
    # to fold is itself a reason to trust it less. ---
    skf = StratifiedKFold(n_splits=AUDIT_CV_FOLDS, shuffle=True, random_state=RNG_SEED)
    fold_rows = []
    for fold_idx, (train_idx, val_idx) in enumerate(skf.split(X, y)):
        fold_model = LogisticRegression(max_iter=1000)
        fold_model.fit(X[train_idx], y[train_idx])
        fold_proba = fold_model.predict_proba(X[val_idx])[:, 1]
        fold_pred = (fold_proba >= 0.5).astype(int)
        fold_rows.append({
            "model_name": AUDIT_MODEL_NAME,
            "fold_number": fold_idx,
            "roc_auc": float(roc_auc_score(y[val_idx], fold_proba)),
            "precision": float(precision_score(y[val_idx], fold_pred, zero_division=0)),
            "recall": float(recall_score(y[val_idx], fold_pred, zero_division=0)),
            "f1": float(f1_score(y[val_idx], fold_pred, zero_division=0)),
            "computed_at": computed_at,
        })
    cv_df = pd.DataFrame(fold_rows)
    upsert_dataframe(cv_df, schema="hiring_bias", table="cv_fold_results", key_columns=["model_name", "fold_number"])

    # --- 3. Calibration: overall + per protected group, on the held-out
    # test split's real predictions (never train, never CV). ---
    calibration_rows = []
    groups_test = groups_test.reset_index(drop=True)
    overall_bins = _calibration_table(y_test, proba_test)
    for row in overall_bins:
        calibration_rows.append({"model_name": AUDIT_MODEL_NAME, "group_attribute": "overall", "group_value": "overall", "computed_at": computed_at, **row})
    for attr in ["gender", "ethnicity"]:
        for value in groups_test[attr].unique():
            mask = (groups_test[attr] == value).to_numpy()
            # Skip groups too small in this one test split for a stable
            # bin-by-bin curve rather than write noisy near-empty bins.
            if mask.sum() < AUDIT_CALIBRATION_BINS * 2:
                continue
            for row in _calibration_table(y_test[mask], proba_test[mask]):
                calibration_rows.append({"model_name": AUDIT_MODEL_NAME, "group_attribute": attr, "group_value": value, "computed_at": computed_at, **row})
    calibration_df = pd.DataFrame(calibration_rows)
    upsert_dataframe(
        calibration_df, schema="hiring_bias", table="calibration_bins",
        key_columns=["model_name", "group_attribute", "group_value", "bin_index"],
    )

    # --- 4. Statistical significance of the fairness_metrics selection-rate
    # gaps: chi-square test of independence per group/stage row already
    # computed in SQL, not re-derived here. ---
    n_sig_rows = compute_fairness_significance_tests()

    save_audit_model_evidence(cv_df=cv_df, calibration_df=calibration_df)

    return {
        "model_evaluation": eval_row.to_dict(orient="records")[0],
        "cv_roc_auc_mean": float(cv_df["roc_auc"].mean()),
        "cv_roc_auc_std": float(cv_df["roc_auc"].std()),
        "cv_f1_mean": float(cv_df["f1"].mean()),
        "cv_f1_std": float(cv_df["f1"].std()),
        "calibration_rows": len(calibration_df),
        "significance_rows": n_sig_rows,
        "test_rows": int(len(y_test)),
    }


def compute_fairness_significance_tests() -> int:
    """Chi-square test of independence (2x2: this group's passed/not-passed
    counts vs. the reference group's) for every hiring_bias.fairness_metrics
    row -- is the selection-rate gap the four-fifths ratio already flags
    statistically significant given the sample size, or plausibly noise?
    Chi-square, not a permutation test: every group/stage cell here has
    from several dozen to several thousand candidates, comfortably large
    enough for the chi-square approximation to hold -- a permutation test
    would converge on the same p-value at far higher compute cost, not a
    different one, at this sample size."""
    from shared.database import get_engine

    engine = get_engine()
    metrics = pd.read_sql("SELECT * FROM hiring_bias.fairness_metrics", engine)
    computed_at = datetime.now(timezone.utc)

    rows = []
    for (attr, stage), sub in metrics.groupby(["group_attribute", "stage"]):
        ref_name = sub["reference_group"].iloc[0]
        ref_row = sub[sub["group_value"] == ref_name]
        if ref_row.empty or ref_row["total_at_risk"].iloc[0] in (0, None):
            continue
        ref_total = int(ref_row["total_at_risk"].iloc[0])
        ref_passed = int(ref_row["passed"].iloc[0])
        for _, row in sub.iterrows():
            if row["total_at_risk"] in (0, None):
                continue
            total, passed = int(row["total_at_risk"]), int(row["passed"])
            table = [[passed, total - passed], [ref_passed, ref_total - ref_passed]]
            chi2, p, _, _ = chi2_contingency_safe(table)
            rows.append({
                "group_attribute": attr, "group_value": row["group_value"], "stage": stage,
                "reference_group": ref_name, "test_name": "chi_square_2x2",
                "chi2_statistic": chi2, "p_value": p,
                "significant_at_05": bool(p is not None and p < 0.05),
                "computed_at": computed_at,
            })
    result = pd.DataFrame(rows)
    upsert_dataframe(
        result, schema="hiring_bias", table="fairness_significance_tests",
        key_columns=["group_attribute", "group_value", "stage"],
    )
    return len(result)


def chi2_contingency_safe(table: list[list[int]]) -> tuple[float | None, float | None, int | None, np.ndarray | None]:
    """chi2_contingency raises on a degenerate table (a zero row/column --
    e.g. a group with 0% or 100% selection rate, which does happen in a
    small stage x group cell). Comparing a group to itself (identical rows)
    is also degenerate in a different way: scipy still returns chi2=0,
    p=1.0 for that case, which is the correct trivial answer, not an error."""
    from scipy.stats import chi2_contingency

    arr = np.array(table)
    if (arr.sum(axis=0) == 0).any() or (arr.sum(axis=1) == 0).any():
        return None, None, None, None
    chi2, p, dof, expected = chi2_contingency(arr, correction=True)
    return float(chi2), float(p), int(dof), expected


def save_audit_model_evidence(*, cv_df: pd.DataFrame, calibration_df: pd.DataFrame) -> None:
    """Calibration reliability diagram (overall + per protected group), the
    cross-validation fold-score distribution, and the significance-test
    p-values against the 0.05 line -- real images from this actual run."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    os.makedirs(EVIDENCE_DIR, exist_ok=True)

    # Calibration curve. Zoomed to the actual data range rather than the
    # full [0, 1] axis -- with a ~2% hire rate every predicted probability
    # sits under 0.2, so a full-scale axis squeezes every point into one
    # illegible corner and hides the calibration this plot exists to show.
    axis_max = max(0.25, float(calibration_df[["mean_predicted_prob", "observed_hire_rate"]].to_numpy().max()) * 1.2)
    fig, ax = plt.subplots(figsize=(7, 6))
    ax.plot([0, axis_max], [0, axis_max], "k--", alpha=0.3, label="perfectly calibrated")
    colors = {"overall": "#1b1b1b"}
    palette = ["#2a6f97", "#e07a5f", "#6a994e", "#bc4749", "#264653", "#f2a541"]
    color_i = 0
    for (attr, value), sub in calibration_df.groupby(["group_attribute", "group_value"]):
        sub = sub.sort_values("bin_index")
        key = f"{attr}={value}" if attr != "overall" else "overall"
        if key not in colors:
            colors[key] = palette[color_i % len(palette)]
            color_i += 1
        style = dict(marker="o", linewidth=2.5 if attr == "overall" else 1.3, alpha=1.0 if attr == "overall" else 0.75)
        ax.plot(sub["mean_predicted_prob"], sub["observed_hire_rate"], color=colors[key], label=key, **style)
    ax.set_xlim(0, axis_max)
    ax.set_ylim(0, axis_max)
    ax.set_xlabel("Mean predicted P(hire) in bin")
    ax.set_ylabel("Observed hire rate in bin")
    ax.set_title(f"Calibration: {AUDIT_MODEL_NAME}, held-out test split")
    ax.legend(loc="upper left", fontsize=8, ncol=2)
    fig.tight_layout()
    fig.savefig(os.path.join(EVIDENCE_DIR, "hiring_calibration_curve.png"), dpi=150)
    plt.close(fig)

    # CV fold-score distribution.
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    for ax, metric in zip(axes, ["roc_auc", "f1"]):
        ax.plot(cv_df["fold_number"], cv_df[metric], marker="o", color="#2a6f97")
        ax.axhline(cv_df[metric].mean(), color="#e07a5f", linestyle="--", label=f"mean = {cv_df[metric].mean():.3f}")
        ax.fill_between(
            cv_df["fold_number"], cv_df[metric].mean() - cv_df[metric].std(), cv_df[metric].mean() + cv_df[metric].std(),
            color="#e07a5f", alpha=0.12, label=f"+/-1 std = {cv_df[metric].std():.3f}",
        )
        ax.set_xlabel("Fold")
        ax.set_ylabel(metric)
        ax.set_title(f"{AUDIT_CV_FOLDS}-fold CV: {metric}")
        ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(EVIDENCE_DIR, "hiring_cv_score_distribution.png"), dpi=150)
    plt.close(fig)

    # Significance-test p-values. Plotted as -log10(p), not raw p, and
    # excluding a group compared against itself (trivially p=1.0, not a
    # real test) -- on a raw-p linear axis the most significant (smallest-p)
    # bars are a few p-value-wide slivers near zero and are effectively
    # invisible; -log10(p) makes the significant results the TALL bars,
    # which is the point of the plot.
    from shared.database import get_engine
    sig = pd.read_sql(
        "SELECT group_attribute, group_value, stage, p_value FROM hiring_bias.fairness_significance_tests "
        "WHERE p_value IS NOT NULL AND group_value != reference_group ORDER BY p_value",
        get_engine(),
    )
    if not sig.empty:
        sig["label"] = sig["group_attribute"] + ":" + sig["group_value"] + "@" + sig["stage"]
        sig["neg_log10_p"] = -np.log10(np.clip(sig["p_value"], 1e-300, 1.0))
        sig = sig.sort_values("neg_log10_p")  # most significant at the top of a horizontal barh
        fig, ax = plt.subplots(figsize=(8, max(4, 0.28 * len(sig))))
        bar_colors = ["#bc4749" if p < 0.05 else "#6a994e" for p in sig["p_value"]]
        ax.barh(sig["label"], sig["neg_log10_p"], color=bar_colors)
        ax.axvline(-np.log10(0.05), color="black", linestyle="--", alpha=0.6, label="p = 0.05")
        ax.set_xlabel("-log10(p-value), chi-square vs. reference group (higher = more significant)")
        ax.set_title("Fairness gap significance by group / stage")
        ax.legend(fontsize=8, loc="lower right")
        fig.tight_layout()
        fig.savefig(os.path.join(EVIDENCE_DIR, "hiring_significance_tests.png"), dpi=150)
        plt.close(fig)
