#!/usr/bin/env python3
"""Copy experiment figures and released datasets into the site's public dir.

experiments/<slug>/figures/*      -> site/public/figures/<slug>/
experiments/<slug>/data/public/*  -> site/public/datasets/<slug>/

Synced copies are committed so the Vercel build needs no Python. Only
figures/ and data/public/ are synced — data/raw and data/interim never touch
the site.

Usage: uv run python scripts/sync_site_assets.py [slug ...]
       (no args = sync every experiment)
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENTS = ROOT / "experiments"
SITE_PUBLIC = ROOT / "site" / "public"


def sync(slug: str) -> None:
    exp = EXPERIMENTS / slug
    if not exp.is_dir():
        raise SystemExit(f"no such experiment: {slug}")
    for src_rel, dst_rel in [("figures", f"figures/{slug}"), ("data/public", f"datasets/{slug}")]:
        src = exp / src_rel
        dst = SITE_PUBLIC / dst_rel
        if not src.is_dir() or not any(src.iterdir()):
            continue
        dst.mkdir(parents=True, exist_ok=True)
        n = 0
        for f in src.iterdir():
            if f.is_file() and not f.name.startswith("."):
                shutil.copy2(f, dst / f.name)
                n += 1
        print(f"  {src.relative_to(ROOT)} -> {dst.relative_to(ROOT)} ({n} files)")


def main() -> None:
    slugs = sys.argv[1:] or sorted(
        p.name for p in EXPERIMENTS.iterdir() if p.is_dir() and not p.name.startswith(".")
    )
    for slug in slugs:
        print(slug)
        sync(slug)


if __name__ == "__main__":
    main()
