"""Run the sql/ extracts against the prod read replica → data/raw/*.csv.

READ-ONLY: connects via scripts/replica_psql.pg_env (forces
default_transaction_read_only=on; replica verified in recovery). Each .sql
file's comment header is stripped and its single SELECT is wrapped in
server-side ``COPY (...) TO STDOUT (FORMAT csv, HEADER)`` — no \\copy
one-liner contortions, no server file access.

Raw extracts are gitignored and contain customer query text / identity
context — they never leave data/raw/.

Usage: uv run python experiments/007-site-consultations-observational/pipeline/00_extract.py [name ...]
       (names default to: extract context citations)
"""

import importlib.util
import subprocess
import sys
import time
from pathlib import Path

EXP = Path(__file__).resolve().parents[1]
REPO = EXP.parents[1]

_spec = importlib.util.spec_from_file_location(
    "replica_psql", REPO / "scripts" / "replica_psql.py"
)
replica_psql = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(replica_psql)

STATEMENT_TIMEOUT_S = 600


def sql_body(path: Path) -> str:
    lines = [l for l in path.read_text().splitlines() if not l.lstrip().startswith("--")]
    body = "\n".join(lines).strip().rstrip(";")
    if not body.upper().startswith("SELECT"):
        raise SystemExit(f"{path}: expected a single SELECT")
    return body


def run_extract(name: str, env: dict) -> None:
    sql = sql_body(EXP / "sql" / f"{name}.sql")
    out = EXP / "data" / "raw" / f"{name}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    command = (
        f"SET statement_timeout = '{STATEMENT_TIMEOUT_S}s';\n"
        f"COPY ({sql}) TO STDOUT (FORMAT csv, HEADER);"
    )
    started = time.time()
    with out.open("wb") as f:
        proc = subprocess.run(
            ["psql", "-X", "-q", "-v", "ON_ERROR_STOP=1", "-c", command],
            env=env,
            stdout=f,
        )
    if proc.returncode != 0:
        raise SystemExit(f"{name}: psql exited {proc.returncode}")
    n_rows = sum(1 for _ in out.open()) - 1
    print(f"{name}: {n_rows:,} rows, {out.stat().st_size / 1e6:.1f} MB, "
          f"{time.time() - started:.0f}s -> {out}")


def main() -> None:
    names = sys.argv[1:] or ["extract", "context", "citations"]
    env = replica_psql.pg_env()
    for name in names:
        run_extract(name, env)


if __name__ == "__main__":
    main()
