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

import numpy as np
import pandas as pd

from shared.database import bulk_upsert_dataframe, upsert_dataframe
from shared.validation import validate_dataframe

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


def train_and_load_audit_model() -> int:
    """Interpretable logistic-regression AUDIT model: which features
    correlate with reaching 'hire', reported as coefficients + bootstrap
    confidence intervals for interpretability. NEVER used to score or
    decide on real/new candidates -- see docs/methodology_hiring_bias.md.
    """
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler

    from shared.database import get_engine

    engine = get_engine()
    df = pd.read_sql("SELECT * FROM hiring_bias.candidates", engine)

    features = pd.get_dummies(
        df[["gender", "ethnicity", "education_level", "years_experience", "role_family", "application_source"]],
        columns=["gender", "ethnicity", "education_level", "role_family", "application_source"],
        drop_first=True,
    )
    feature_names = features.columns.tolist()
    X = StandardScaler().fit_transform(features.astype(float))
    y = df["reached_hire"].astype(int).to_numpy()

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
