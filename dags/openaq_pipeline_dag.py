from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator

# Default arguments cho DAG
default_args = {
    "owner": "airflow",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}


def run_extract_task(**kwargs):
    from src.pipeline import OpenAQPipeline
    execution_date = kwargs.get("ds")  # YYYY-MM-DD
    pipeline = OpenAQPipeline()
    res = pipeline.run_extract(target_date=execution_date)
    # Day ket qua vao XCom
    kwargs["ti"].xcom_push(key="extract_res", value=res)


def run_transform_task(**kwargs):
    from src.pipeline import OpenAQPipeline
    ti = kwargs["ti"]
    extract_res = ti.xcom_pull(key="extract_res", task_ids="extract_openaq_data")
    if not extract_res:
        raise ValueError("Khong tim thay ket qua tu task extract!")

    pipeline = OpenAQPipeline()
    processed_key = pipeline.run_transform(
        s3_measurements_key=extract_res["measurements_key"],
        target_date=extract_res["date"],
    )
    ti.xcom_push(key="processed_key", value=processed_key)


def run_load_task(**kwargs):
    from src.pipeline import OpenAQPipeline
    ti = kwargs["ti"]
    processed_key = ti.xcom_pull(key="processed_key", task_ids="transform_openaq_data")
    pipeline = OpenAQPipeline()
    load_res = pipeline.run_load(s3_processed_key=processed_key)
    print("Ket qua Load:", load_res)


with DAG(
    dag_id="openaq_etl_daily_pipeline",
    default_args=default_args,
    description="Pipeline thu thap, xu ly va nap du lieu chat luong khong khi OpenAQ hang ngay vao DWH",
    schedule_interval="0 2 * * *",  # 2:00 AM UTC hang ngay
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["openaq", "etl", "air_quality", "data_warehouse"],
) as dag:

    extract_task = PythonOperator(
        task_id="extract_openaq_data",
        python_callable=run_extract_task,
        provide_context=True,
    )

    transform_task = PythonOperator(
        task_id="transform_openaq_data",
        python_callable=run_transform_task,
        provide_context=True,
    )

    load_task = PythonOperator(
        task_id="load_into_data_warehouse",
        python_callable=run_load_task,
        provide_context=True,
    )

    # Dependency flow: Extract -> Transform -> Load
    extract_task >> transform_task >> load_task
