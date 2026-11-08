"""Central configuration for the pipeline.

Every value can be changed with an environment variable (or a .env file),
so nothing is hard-coded in the code and no secret is committed to Git.
"""
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """Very small .env reader (KEY=VALUE lines) so we do not need an extra library.

    Variables already set in the environment always win over the file.
    """
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    # PostgreSQL connection (the warehouse)
    pg_host: str = os.getenv("POSTGRES_HOST", "localhost")
    pg_port: int = int(os.getenv("POSTGRES_PORT", "5433"))
    pg_db: str = os.getenv("POSTGRES_DB", "retail_dw")
    pg_user: str = os.getenv("POSTGRES_USER", "retail")
    pg_password: str = os.getenv("POSTGRES_PASSWORD", "retail")

    # Where the simulated source systems drop their daily files
    landing_dir: Path = Path(os.getenv("LANDING_DIR", str(PROJECT_ROOT / "data" / "landing")))

    # Size of the simulated company
    start_date: date = date.fromisoformat(os.getenv("SIM_START_DATE", "2026-01-01"))
    days: int = int(os.getenv("SIM_DAYS", "90"))
    n_stores: int = int(os.getenv("SIM_STORES", "6"))
    n_products: int = int(os.getenv("SIM_PRODUCTS", "150"))
    n_suppliers: int = int(os.getenv("SIM_SUPPLIERS", "12"))
    seed: int = int(os.getenv("SIM_SEED", "42"))

    # dbt
    dbt_bin: str = os.getenv("DBT_BIN", "dbt")
    dbt_project_dir: Path = Path(os.getenv("DBT_PROJECT_DIR", str(PROJECT_ROOT / "dbt")))
    dbt_target: str = os.getenv("DBT_TARGET", "postgres")

    @property
    def dsn(self) -> str:
        return (
            f"host={self.pg_host} port={self.pg_port} dbname={self.pg_db} "
            f"user={self.pg_user} password={self.pg_password}"
        )


settings = Settings()
