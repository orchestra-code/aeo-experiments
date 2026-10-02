#!/usr/bin/env python3
"""Copy experiment figures and released datasets into the site's public dir.

experiments/<slug>/figures/*      -> site/public/figures/<slug>/
  (or experiments/<slug>/results/figures/* when the study keeps them there)
experiments/<slug>/data/public/*  -> site/public/datasets/<slug>/

Synced copies are committed so the Vercel build needs no Python. Only
figures/ and data/public/ are synced — data/raw and data/interim never touch
the site.

Usage: uv run python scripts/sync_site_assets.py [--figures-only] [slug ...]
       (no slugs = sync every experiment; --figures-only skips data/public,
       for a draft whose release checklist is not signed yet)
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENTS = ROOT / "experiments"
SITE_PUBLIC = ROOT / "site" / "public"


def sync(slug: str, figures_only: bool = False) -> None:
    exp = EXPERIMENTS / slug
    if not exp.is_dir():
        raise SystemExit(f"no such experiment: {slug}")
    figures = "figures" if (exp / "figures").is_dir() else "results/figures"
    pairs = [(figures, f"figures/{slug}")]
    if not figures_only:
        pairs.append(("data/public", f"datasets/{slug}"))
    for src_rel, dst_rel in pairs:
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
    args = sys.argv[1:]
    figures_only = "--figures-only" in args
    slugs = [a for a in args if a != "--figures-only"] or sorted(
        p.name for p in EXPERIMENTS.iterdir() if p.is_dir() and not p.name.startswith(".")
    )
    for slug in slugs:
        print(slug)
        sync(slug, figures_only)


if __name__ == "__main__":
    main()
