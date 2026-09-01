"""Score AIPVS for the study's domain contrast set, via the real product scorer.

Builds the domain list — every site:-consulted domain plus a seeded random
sample of cited-only pool domains — and drives the spyglasses tsx script
(scratchpad score-aipvs.ts) against the production read replica with the
same credentials scripts/replica_psql.py resolves. Output:
data/raw/aipvs.csv (gitignored).

Sample seed 20260901 (the day this pre-freeze exploration ran; recorded in
the spec's pre-freeze section). Sample size 5,000 — plenty for the
consulted-vs-cited contrast without scoring all ~72k pool domains.

Usage: uv run python experiments/007-site-consultations-observational/pipeline/02b_aipvs.py [tsx_script_path]
"""

from __future__ import annotations

import importlib.util
import random
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

import pandas as pd

EXP = Path(__file__).resolve().parents[1]
REPO = EXP.parents[1]
SPYGLASSES = REPO.parent / "spyglasses"
SEED = 20260901
SAMPLE = 5000

_spec = importlib.util.spec_from_file_location(
    "replica_psql", REPO / "scripts" / "replica_psql.py"
)
replica_psql = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(replica_psql)


def replica_database_url() -> str:
    env = replica_psql.pg_env()
    user = quote(env["PGUSER"], safe="")
    password = quote(env["PGPASSWORD"], safe="")
    return (
        f"postgresql://{user}:{password}@{env['PGHOST']}:{env['PGPORT']}"
        f"/{env['PGDATABASE']}"
    )


def main() -> None:
    tsx_script = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if not tsx_script or not tsx_script.exists():
        raise SystemExit("pass the score-aipvs.ts path as argv[1]")

    features = pd.read_csv(EXP / "data" / "interim" / "features.csv",
                           keep_default_na=False, na_values=[""])
    consulted = sorted(set(features.loc[features["scoped"], "scoped_domain"].dropna()))
    consulted = [d for d in consulted if not d.startswith("*")]

    domains_all = pd.read_csv(EXP / "data" / "raw" / "domains.csv",
                              keep_default_na=False, na_values=[""])
    cited_only = sorted(set(domains_all["domain"]) - set(consulted))
    rng = random.Random(SEED)
    sample = rng.sample(cited_only, min(SAMPLE, len(cited_only)))

    targets = consulted + sample
    in_csv = EXP / "data" / "interim" / "aipvs_targets.csv"
    in_csv.write_text("domain\n" + "\n".join(targets) + "\n")
    out_csv = EXP / "data" / "raw" / "aipvs.csv"
    print(f"{len(consulted):,} consulted + {len(sample):,} sampled cited-only "
          f"= {len(targets):,} to score")

    import os
    env = os.environ.copy()
    env.update(
        DATABASE_URL=replica_database_url(),
        NODE_OPTIONS="--conditions=react-server",
        NODE_ENV="production",
    )
    proc = subprocess.run(
        [str(SPYGLASSES / "tooling" / "scripts" / "node_modules" / ".bin" / "tsx"),
         str(tsx_script), str(in_csv), str(out_csv)],
        cwd=SPYGLASSES,
        env=env,
    )
    if proc.returncode != 0:
        raise SystemExit(f"tsx scorer exited {proc.returncode}")
    scored = pd.read_csv(out_csv)
    print(f"scored {len(scored):,}; tiers:")
    print(scored["tier_label"].value_counts().to_string())


if __name__ == "__main__":
    main()
