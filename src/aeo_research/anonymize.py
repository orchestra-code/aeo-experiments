"""Release gate for published datasets.

Public datasets contain derived features only. This module is the *technical*
enforcement of docs/data-policy.md — the human checklist in
templates/release-checklist.md still applies on top.

Hard rules enforced here:
- Explicit allow-list: only columns you name (with a description) are written.
- Deny-list: column names matching customer-data patterns are refused even if
  allow-listed — the gate errs on the side of not shipping.
- Content scans: string cells are scanned for Prisma cuid identifiers and for
  long free text (which is how prompt/response text sneaks out inside an
  innocuously named column).
- Grouping keys are pseudonymized to sequential per-release codes.
- The datasheet states row counts as "rows evaluated in this study" — never
  as, or alongside, any database total.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pandas as pd


class ReleaseError(RuntimeError):
    """A dataset failed the release gate. Do not work around this."""


#: Case-insensitive substrings that may never appear in a released column name.
FORBIDDEN_SUBSTRINGS = [
    "execution",
    "property",
    "organization",
    "org_id",
    "customer",
    "account",
    "user",
    "email",
    "prompt",
    "query",
    "fanout",
    "fan_out",
    "answer",
    "response",
    "summary",
    "markdown",
    "content_md",
    "embedding",
]

#: Prisma cuid: "c" + 24 lowercase base36 chars.
CUID_PATTERN = re.compile(r"\bc[a-z0-9]{24}\b")

#: Cells longer than this are treated as free text (potential proprietary
#: content) unless the column is explicitly marked as a public fact.
MAX_TEXT_LEN = 200


@dataclass
class ColumnSpec:
    name: str
    description: str
    #: Set True only for columns whose values are verifiably public facts
    #: (e.g. a YouTube category name). Exempts the long-text scan, not the
    #: cuid scan.
    public_fact: bool = False


@dataclass
class Datasheet:
    title: str
    dataset_slug: str
    study: str
    license: str = "CC BY 4.0"
    notes: list[str] = field(default_factory=list)


def pseudonymize(series: pd.Series, prefix: str) -> pd.Series:
    """Map distinct values to sequential ``{prefix}_0001`` codes (first-appearance order)."""
    mapping: dict = {}
    for v in series:
        if pd.notna(v) and v not in mapping:
            mapping[v] = f"{prefix}_{len(mapping) + 1:04d}"
    return series.map(mapping)


def _check_column_names(specs: list[ColumnSpec]) -> None:
    for spec in specs:
        lowered = spec.name.lower()
        for bad in FORBIDDEN_SUBSTRINGS:
            if bad in lowered:
                raise ReleaseError(
                    f"Column '{spec.name}' matches forbidden pattern '{bad}'. "
                    "Derived features only — see docs/data-policy.md."
                )


def _scan_values(df: pd.DataFrame, specs: list[ColumnSpec]) -> None:
    by_name = {s.name: s for s in specs}
    for col in df.columns:
        if not pd.api.types.is_object_dtype(df[col]) and not isinstance(
            df[col].dtype, pd.StringDtype
        ):
            continue
        values = df[col].dropna().astype(str)
        hits = values[values.str.contains(CUID_PATTERN, regex=True)]
        if len(hits):
            raise ReleaseError(
                f"Column '{col}' contains cuid-like identifiers "
                f"(e.g. {hits.iloc[0][:40]!r}). Pseudonymize before release."
            )
        if not by_name[col].public_fact:
            long = values[values.str.len() > MAX_TEXT_LEN]
            if len(long):
                raise ReleaseError(
                    f"Column '{col}' contains free text >{MAX_TEXT_LEN} chars. "
                    "If these values are verifiably public facts, mark the "
                    "column public_fact=True; otherwise it does not ship."
                )


def release_dataset(
    df: pd.DataFrame,
    columns: list[ColumnSpec],
    outdir: str | Path,
    datasheet: Datasheet,
) -> dict[str, Path]:
    """Validate and write ``<slug>.csv`` + ``<slug>.datasheet.md``.

    Raises ReleaseError on any violation; writes nothing in that case.
    """
    outdir = Path(outdir)
    names = [c.name for c in columns]

    missing = [n for n in names if n not in df.columns]
    if missing:
        raise ReleaseError(f"Allow-listed columns missing from frame: {missing}")

    _check_column_names(columns)
    out = df[names].copy()
    _scan_values(out, columns)

    outdir.mkdir(parents=True, exist_ok=True)
    csv_path = outdir / f"{datasheet.dataset_slug}.csv"
    md_path = outdir / f"{datasheet.dataset_slug}.datasheet.md"

    out.to_csv(csv_path, index=False)

    lines = [
        f"# {datasheet.title}",
        "",
        f"- **Study:** {datasheet.study}",
        f"- **Rows:** {len(out):,} (citations evaluated in this study)",
        f"- **License:** {datasheet.license}",
        f"- **Released:** {date.today().isoformat()}",
        "",
        "This dataset contains derived features only. It does not include any",
        "customer prompts, AI responses, fan-out queries, or customer",
        "identifiers, and it says nothing about the overall size of the",
        "Spyglasses database.",
        "",
        "## Columns",
        "",
        "| Column | Description |",
        "|---|---|",
    ]
    lines += [f"| `{c.name}` | {c.description} |" for c in columns]
    if datasheet.notes:
        lines += ["", "## Notes", ""] + [f"- {n}" for n in datasheet.notes]
    md_path.write_text("\n".join(lines) + "\n")

    return {"csv": csv_path, "datasheet": md_path}
