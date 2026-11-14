"""Static checks on the project files: DAG structure, no secrets committed, dbt layout."""
import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_dag_defines_the_expected_tasks():
    source = (ROOT / "airflow" / "dags" / "retail_warehouse_daily.py").read_text(encoding="utf-8")
    ast.parse(source)  # valid Python
    for task_id in ["wait_for_source_files", "ingest_batch", "dbt_build", "reconcile", "export_dashboard_snapshot"]:
        assert f'"{task_id}"' in source, task_id
    assert "retries" in source and "max_active_runs=1" in source


def test_no_real_env_file_is_tracked():
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert ".env" in gitignore
    assert (ROOT / ".env.example").exists()


def test_no_password_written_in_config_files():
    pattern = re.compile(r"password\s*[:=]\s*['\"]?[A-Za-z0-9_]{6,}", re.IGNORECASE)
    for path in [ROOT / "dbt" / "profiles.yml", ROOT / "docker-compose.yml"]:
        for line in path.read_text(encoding="utf-8").splitlines():
            if pattern.search(line):
                # only references to environment variables are allowed
                assert "env_var" in line or "${" in line or "$${" in line, f"{path.name}: {line.strip()}"


def test_every_dbt_model_has_a_comment_header():
    for sql in (ROOT / "dbt" / "models").rglob("*.sql"):
        first = sql.read_text(encoding="utf-8").lstrip()
        assert first.startswith("--") or first.startswith("{{"), sql.name


def test_online_demo_data_is_in_the_repository():
    # the static online dashboard reads this file: without it the demo shows no data
    snapshot = ROOT / "dashboard" / "static" / "data" / "snapshot.json"
    assert snapshot.exists(), "run: python -m dashboard.export_snapshot, then commit the file"
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "data/" not in gitignore, "'data/' would also ignore dashboard/static/data (use '/data/')"
