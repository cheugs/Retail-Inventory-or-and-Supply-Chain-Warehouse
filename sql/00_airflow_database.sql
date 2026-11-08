-- Separate database for Airflow's own metadata (DAG runs, task states...).
-- Only used by the Docker stack; executed once when the PostgreSQL volume is created.
CREATE DATABASE airflow;
