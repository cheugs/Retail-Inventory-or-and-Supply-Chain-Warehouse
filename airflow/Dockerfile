# Airflow image with the pipeline dependencies.
# dbt is installed in its own virtual environment (/opt/dbt_venv) so that its
# dependencies never conflict with Airflow's.
FROM apache/airflow:2.10.4-python3.12

USER root
RUN python -m venv /opt/dbt_venv \
    && /opt/dbt_venv/bin/pip install --no-cache-dir "dbt-core==1.9.4" "dbt-postgres==1.9.0" \
    && chown -R airflow: /opt/dbt_venv
USER airflow

# numpy and pandas pinned with the official Airflow constraints (no version conflict),
# then the PostgreSQL driver used by the pipeline
RUN pip install --no-cache-dir numpy pandas \
      --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-2.10.4/constraints-3.12.txt" \
    && pip install --no-cache-dir "psycopg[binary]==3.2.3"
