"""Run psql against PROD_REPLICA_URL from .env.local — READ-ONLY analysis only.

The URL's password may contain unencoded special characters (@ ! *), which
breaks naive URL parsing — so this splits the authority on the LAST '@'
(hostnames cannot contain one) and hands psql the pieces via PG* environment
variables. Credentials are never printed.

Also forces a read-only session: options=-c default_transaction_read_only=on.

Usage:
  uv run python scripts/replica_psql.py -c "SELECT 1;"
  uv run python scripts/replica_psql.py -f experiments/007-.../sql/counts.sql
"""

import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote

_REPO = Path(__file__).resolve().parents[1]
#: First hit wins. The spyglasses entry is the pooler-host form the
#: clone-prod-to-preview script uses; Supabase replicas connect through the
#: pooler with a replica-scoped username — the UI's db.<ref>-rr-* hostname is
#: not publicly resolvable.
ENV_FILES = [_REPO / ".env.local", _REPO.parent / "spyglasses" / ".env.local"]


def load_url() -> tuple[str, str | None]:
    """(pooler url, replica tenant id or None).

    A db.<ref>-rr-*.supabase.co entry is the dashboard's direct form —
    IPv6-only, unreachable without an IPv6 route — but its hostname carries
    the replica id (<ref>-rr-...), which the pooler routes by when embedded
    in the username. So that entry is mined for the id and the connection
    itself goes through the pooler-form URL.
    """
    replica_id = None
    for env_file in ENV_FILES:
        if not env_file.exists():
            continue
        for line in env_file.read_text().splitlines():
            if line.strip().startswith("PROD_REPLICA_URL="):
                url = line.split("=", 1)[1].strip().strip('"').strip("'")
                host = url.rpartition("@")[2].partition(":")[0].partition("/")[0]
                if host.startswith("db.") and "-rr-" in host:
                    replica_id = host[len("db."):].partition(".")[0]
                    print(f"{env_file}: db.*-rr-* host is IPv6-only — "
                          f"harvested replica id {replica_id}", file=sys.stderr)
                    continue
                print(f"using PROD_REPLICA_URL from {env_file}", file=sys.stderr)
                return url, replica_id
    raise SystemExit(f"No usable PROD_REPLICA_URL in {ENV_FILES}")


def main() -> None:
    # Optional: --tenant <id> rewrites the pooler username's tenant suffix
    # (postgres.<ref> -> postgres.<id>). Supabase read replicas are routed by
    # the pooler via a replica-suffixed tenant id; the db.<ref>-rr-* host is
    # IPv6-only and unreachable without an IPv6 route.
    tenant = None
    argv = sys.argv[1:]
    if argv and argv[0] == "--tenant":
        tenant = argv[1]
        del argv[:2]
    sys.argv[1:] = argv

    url, harvested_tenant = load_url()
    tenant = tenant or harvested_tenant
    scheme, _, rest = url.partition("://")
    if scheme not in ("postgres", "postgresql"):
        raise SystemExit(f"PROD_REPLICA_URL has unexpected scheme {scheme!r}")
    authority, _, path = rest.partition("/")
    userinfo, sep, hostport = authority.rpartition("@")
    if not sep:
        raise SystemExit("PROD_REPLICA_URL has no credentials part")
    user, _, password = userinfo.partition(":")
    host, _, port = hostport.partition(":")
    dbname = (path.split("?")[0] or "postgres")
    if tenant:
        base, dot, _ref = user.partition(".")
        user = f"{base}{dot}{tenant}" if dot else user
        print(f"tenant override -> user {base}.{tenant}", file=sys.stderr)

    env = os.environ.copy()
    env.update(
        PGHOST=host,
        PGPORT=port or "5432",
        PGUSER=unquote(user),
        PGPASSWORD=unquote(password),
        PGDATABASE=unquote(dbname),
        # Belt and braces: this tool exists for read-only analysis.
        PGOPTIONS="-c default_transaction_read_only=on",
    )
    raise SystemExit(
        subprocess.run(["psql", "-X", *sys.argv[1:]], env=env).returncode
    )


if __name__ == "__main__":
    main()
