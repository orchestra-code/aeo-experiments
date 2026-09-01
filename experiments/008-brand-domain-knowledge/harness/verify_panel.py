"""Panel validity check (spec Audit D, run at freeze and recorded).

For every BrandEntry: fetch https://{true_domain} (redirects followed) and
report the HTTP status and the final host. A true_domain that fails to
resolve, or lands on a different registrable host, needs fixing BEFORE the
panel freezes. Tier-C old_domains get the same probe so 'stale' scoring is
grounded in what those hosts actually do today.

Usage: uv run python experiments/008-brand-domain-knowledge/harness/verify_panel.py
"""

from __future__ import annotations

import concurrent.futures as cf
import importlib.util
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

EXP = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("brands", EXP / "pipeline" / "brands.py")
brands = importlib.util.module_from_spec(spec)
spec.loader.exec_module(brands)

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")


def probe(domain: str) -> tuple[str, str]:
    req = urllib.request.Request(f"https://{domain}", headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return str(resp.status), urlsplit(resp.url).hostname or "?"
    except urllib.error.HTTPError as e:
        return f"HTTP {e.code}", urlsplit(e.url or "").hostname or domain
    except Exception as e:  # noqa: BLE001
        return type(e).__name__, "-"


def strip_www(host: str) -> str:
    return host.removeprefix("www.")


def main() -> None:
    jobs: list[tuple[str, str, str]] = []
    for b in brands.DRAFT_PANEL:
        jobs.append((b.canonical, "true", b.true_domain))
        for old in b.old_domains:
            jobs.append((b.canonical, "old", old))

    with cf.ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(lambda j: (*j, *probe(j[2])), jobs))

    problems = 0
    for canonical, kind, domain, status, final in results:
        landed = strip_www(final)
        ok = status.startswith("2") and (
            kind == "old" or landed == domain or landed.endswith("." + domain)
        )
        flag = "" if ok else "  <-- CHECK"
        if not ok and kind == "true":
            problems += 1
        print(f"{canonical:12} {kind:5} {domain:22} -> {status:12} {landed}{flag}")
    print(f"\n{problems} true_domain problem(s)")


if __name__ == "__main__":
    main()
