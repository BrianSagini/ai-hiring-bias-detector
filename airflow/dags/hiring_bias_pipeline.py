"""AI Hiring Bias Detector -- Airflow DAG.

100% synthetic recruitment-funnel data (see
projects/03_ai_hiring_bias_detector/pipeline.py for the generator and its
documented, adjustable bias-injection mechanism) -> validate -> load ->
SQL fairness metrics (selection rates, 4/5ths-rule adverse impact ratio)
-> interpretable audit-model coefficients -> stratified-K-fold audit-model
evaluation (cross-validation, per-group calibration, chi-square
significance testing of the fairness-metric gaps) -> data-quality check.

This pipeline is a FAIRNESS AUDIT tool. It does not decide who should be
hired -- see docs/methodology.md.
"""
from __future__ import annotations

import os
import tempfile
from datetime import timedelta

import pandas as pd
import pendulum
from airflow.sdk import DAG, task

import pipeline
from shared.database import get_engine

TMP = tempfile.gettempdir()

with DAG(
    dag_id="hiring_bias_pipeline",
    description="Generate synthetic recruitment funnel data, compute fairness metrics and an interpretable audit model",
    schedule="@daily",
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    default_args={
        "retries": 2,
        "retry_delay": timedelta(minutes=1),
        "execution_timeout": timedelta(minutes=20),
    },
    tags=["hiring", "fairness", "project-03"],
) as dag:

    @task
    def validate_config() -> bool:
        assert pipeline.N_CANDIDATES > 0
        assert set(pipeline.STAGE_BIAS_MULTIPLIER.keys()) <= {"screen", "interview", "offer", "hire"}
        return True

    @task
    def ensure_schema() -> None:
        from shared.database import run_sql_file
        run_sql_file(os.path.join(os.path.dirname(pipeline.__file__), "sql", "001_schema.sql"))

    @task
    def generate_and_run_funnel() -> str:
        candidates = pipeline.generate_candidates()
        funnel = pipeline.run_funnel(candidates)
        path = os.path.join(TMP, "hiring_bias_funnel.parquet")
        funnel.to_parquet(path)
        return path

    @task
    def validate_and_load(funnel_path: str) -> int:
        df = pd.read_parquet(funnel_path)
        report = pipeline.validate_funnel(df)
        report.raise_if_invalid(max_invalid_ratio=0.0)
        return pipeline.load_candidates(df)

    @task
    def compute_fairness_metrics(_rows_loaded: int) -> int:
        return pipeline.compute_and_load_fairness_metrics()

    @task
    def train_audit_model(_rows_loaded: int) -> int:
        return pipeline.train_and_load_audit_model()

    @task
    def evaluate_audit_model(_metrics_rows: int, _coef_rows: int) -> dict:
        return pipeline.evaluate_audit_model()

    @task
    def create_powerbi_views(_model_rows: int, _evaluation: dict) -> None:
        from shared.database import run_sql_file
        run_sql_file(os.path.join(os.path.dirname(pipeline.__file__), "sql", "003_powerbi_views.sql"))

    @task
    def data_quality_check(_views_done: None) -> None:
        import logging
        import statistics

        engine = get_engine()
        with engine.connect() as conn:
            total = conn.exec_driver_sql("SELECT COUNT(*) FROM hiring_bias.candidates").scalar()
            non_monotonic = conn.exec_driver_sql(
                "SELECT COUNT(*) FROM hiring_bias.candidates "
                "WHERE (reached_hire AND NOT reached_offer) OR (reached_offer AND NOT reached_interview) "
                "OR (reached_interview AND NOT reached_screen)"
            ).scalar()
            eval_row = conn.exec_driver_sql(
                "SELECT precision, roc_auc FROM hiring_bias.model_evaluation WHERE model_name = %(m)s",
                {"m": pipeline.AUDIT_MODEL_NAME},
            ).first()
            cv_rows = conn.exec_driver_sql(
                "SELECT roc_auc FROM hiring_bias.cv_fold_results WHERE model_name = %(m)s",
                {"m": pipeline.AUDIT_MODEL_NAME},
            ).all()
            sig_rows = conn.exec_driver_sql(
                "SELECT p_value FROM hiring_bias.fairness_significance_tests"
            ).all()
        if total == 0:
            raise ValueError("hiring_bias.candidates is empty after load")
        if non_monotonic:
            raise ValueError(f"{non_monotonic} candidates have a non-monotonic funnel")

        # Same kind of implausibility floor as Fraud's ROC-AUC >= 0.5 check --
        # a fairness-audit model that can't beat random chance at ranking
        # candidates isn't safe to draw any fairness conclusion from.
        if eval_row is None or eval_row.roc_auc is None or eval_row.roc_auc < 0.5:
            raise ValueError(f"{pipeline.AUDIT_MODEL_NAME} ROC-AUC ({eval_row}) is no better than random -- investigate")
        if len(cv_rows) != pipeline.AUDIT_CV_FOLDS:
            raise ValueError(f"expected {pipeline.AUDIT_CV_FOLDS} cv_fold_results rows, got {len(cv_rows)}")
        cv_aucs = [r.roc_auc for r in cv_rows]
        if any(a is None or a < 0.5 for a in cv_aucs):
            raise ValueError(f"at least one CV fold's ROC-AUC is at/below random chance: {cv_aucs}")
        # p-values are a probability -- a value outside [0, 1] means the
        # chi-square computation itself is broken, not a real result.
        bad_p = [p for (p,) in sig_rows if p is not None and not (0.0 <= p <= 1.0)]
        if bad_p:
            raise ValueError(f"fairness_significance_tests has out-of-range p-values: {bad_p}")

        # The audit model beating random chance is required above; it beating
        # a *useful* precision/recall at the default 0.5 threshold is not --
        # with only a ~2% overall hire rate, predicted P(hire) can (and did,
        # in this run) never cross 0.5 for anyone, which is a real property
        # of this funnel's compounding stage-by-stage attrition, not a bug.
        # Log it loudly every run rather than let a silent 0/0/0 pass unnoticed.
        cv_mean, cv_std = statistics.mean(cv_aucs), statistics.pstdev(cv_aucs)
        if eval_row.precision == 0:
            logging.warning(
                "%s: precision/recall/F1 are all 0 at the default 0.5 threshold (max predicted P(hire) "
                "never reaches 0.5 given the ~2%% hire rate) -- ROC-AUC %.4f (single split), CV mean "
                "%.4f +/- %.4f across %d folds still shows real ranking signal. See docs/model_card.md.",
                pipeline.AUDIT_MODEL_NAME, eval_row.roc_auc, cv_mean, cv_std, len(cv_aucs),
            )
        else:
            logging.info(
                "%s: ROC-AUC %.4f (single split), CV mean %.4f +/- %.4f across %d folds.",
                pipeline.AUDIT_MODEL_NAME, eval_row.roc_auc, cv_mean, cv_std, len(cv_aucs),
            )

    cfg = validate_config()
    schema = ensure_schema()
    funnel_path = generate_and_run_funnel()
    loaded = validate_and_load(funnel_path)
    metrics = compute_fairness_metrics(loaded)
    coefs = train_audit_model(loaded)
    evaluation = evaluate_audit_model(metrics, coefs)
    views = create_powerbi_views(coefs, evaluation)
    dq = data_quality_check(views)

    cfg >> schema >> funnel_path >> loaded >> [metrics, coefs]
    [metrics, coefs] >> evaluation >> views >> dq
