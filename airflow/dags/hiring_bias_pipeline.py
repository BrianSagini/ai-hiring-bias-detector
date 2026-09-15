"""AI Hiring Bias Detector -- Airflow DAG.

100% synthetic recruitment-funnel data (see
projects/03_ai_hiring_bias_detector/pipeline.py for the generator and its
documented, adjustable bias-injection mechanism) -> validate -> load ->
SQL fairness metrics (selection rates, 4/5ths-rule adverse impact ratio)
-> interpretable audit-model coefficients -> data-quality check.

This pipeline is a FAIRNESS AUDIT tool. It does not decide who should be
hired -- see docs/methodology_hiring_bias.md.
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
    def create_powerbi_views(_metrics_rows: int, _model_rows: int) -> None:
        from shared.database import run_sql_file
        run_sql_file(os.path.join(os.path.dirname(pipeline.__file__), "sql", "003_powerbi_views.sql"))

    @task
    def data_quality_check(_views_done: None) -> None:
        engine = get_engine()
        with engine.connect() as conn:
            total = conn.exec_driver_sql("SELECT COUNT(*) FROM hiring_bias.candidates").scalar()
            non_monotonic = conn.exec_driver_sql(
                "SELECT COUNT(*) FROM hiring_bias.candidates "
                "WHERE (reached_hire AND NOT reached_offer) OR (reached_offer AND NOT reached_interview) "
                "OR (reached_interview AND NOT reached_screen)"
            ).scalar()
        if total == 0:
            raise ValueError("hiring_bias.candidates is empty after load")
        if non_monotonic:
            raise ValueError(f"{non_monotonic} candidates have a non-monotonic funnel")

    cfg = validate_config()
    schema = ensure_schema()
    funnel_path = generate_and_run_funnel()
    loaded = validate_and_load(funnel_path)
    metrics = compute_fairness_metrics(loaded)
    model = train_audit_model(loaded)
    views = create_powerbi_views(metrics, model)
    dq = data_quality_check(views)

    cfg >> schema >> funnel_path >> loaded >> [metrics, model] >> views >> dq
