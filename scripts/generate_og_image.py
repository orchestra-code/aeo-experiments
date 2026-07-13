#!/usr/bin/env python3
"""Generate a brand OG card end to end: prompt -> Replicate -> branded WEBP.

Calls an image model on Replicate (default google/nano-banana-2) at 21:9,
downloads the result, then cover-crops to 1200x630 and stamps the gold
isotype via aeo_research.make_og_image.

Prompt convention (write the subject to match the article; no words in art):
    "An abstract image representing <subject>. Blue palette with copper
     accents. No words are in the image."

Token: reads REPLICATE_API_TOKEN from the environment, or from --env-file
(e.g. your spyglasses checkout's .env.local). The token is never written to
committed files.

Usage:
    uv run python scripts/generate_og_image.py DST.webp \
        --prompt "An abstract image representing ... No words are in the image." \
        --env-file /path/to/spyglasses/.env.local \
        --source-out experiments/<slug>/hero-source.jpg
"""

from __future__ import annotations

import argparse
import os
import tempfile
import urllib.request
from pathlib import Path

from aeo_research.og_image import make_og_image

MODEL = "google/nano-banana-2"


def load_token(env_file: str | None) -> str:
    tok = os.environ.get("REPLICATE_API_TOKEN")
    if tok:
        return tok
    if env_file:
        for line in Path(env_file).read_text().splitlines():
            if line.strip().startswith("REPLICATE_API_TOKEN="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit(
        "No REPLICATE_API_TOKEN. Set it in the environment or pass --env-file "
        "pointing at a dotenv that defines it (e.g. spyglasses/.env.local)."
    )


def output_to_bytes(out) -> bytes:
    """Pull image bytes from whatever shape replicate.run returns."""
    if isinstance(out, (list, tuple)):
        return output_to_bytes(out[0])
    if hasattr(out, "read"):  # replicate FileOutput
        return out.read()
    if isinstance(out, str):  # URL
        with urllib.request.urlopen(out) as r:
            return r.read()
    if hasattr(out, "url"):
        with urllib.request.urlopen(out.url) as r:
            return r.read()
    raise RuntimeError(f"Unexpected Replicate output type: {type(out)!r}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("dst", help="output .webp (1200x630, branded)")
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--aspect-ratio", default="21:9")
    ap.add_argument("--env-file", default=None)
    ap.add_argument("--source-out", default=None,
                    help="also keep the raw generated image here (for reproducibility)")
    ap.add_argument("--logo-frac", type=float, default=0.062)
    a = ap.parse_args()

    import replicate

    client = replicate.Client(api_token=load_token(a.env_file))
    print(f"  generating via {a.model} ({a.aspect_ratio}) ...")
    output = client.run(
        a.model,
        input={
            "prompt": a.prompt,
            "resolution": "1K",
            "image_input": [],
            "aspect_ratio": a.aspect_ratio,
            "image_search": False,
            "google_search": False,
            "output_format": "jpg",
        },
    )
    raw = output_to_bytes(output)

    if a.source_out:
        src_path = Path(a.source_out)
        src_path.parent.mkdir(parents=True, exist_ok=True)
        src_path.write_bytes(raw)
    else:
        tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        tmp.write(raw)
        tmp.close()
        src_path = Path(tmp.name)

    out = make_og_image(src_path, a.dst, logo_width_frac=a.logo_frac)
    print(f"  {out}  (1200x630 WEBP)")
    if a.source_out:
        print(f"  source kept at {src_path}")


if __name__ == "__main__":
    main()
