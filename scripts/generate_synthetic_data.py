"""Thin CLI wrapper around intercompany_close_agent.synthetic.generator.

The generation logic itself moved into the package once the CLI's
`generate-data` command needed to call it too -- this script is kept as a
convenience for `uv run python scripts/generate_synthetic_data.py` and to
avoid breaking anyone's muscle memory.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from intercompany_close_agent.synthetic.generator import OUTPUT_DIR, generate


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42, help="RNG seed (default: 42)")
    parser.add_argument("--pairs", type=int, default=26, help="Number of IC pairs to generate before anomalies")
    parser.add_argument("--out-dir", type=Path, default=OUTPUT_DIR, help="Where to write the CSVs")
    args = parser.parse_args()
    generate(seed=args.seed, pair_count=args.pairs, out_dir=args.out_dir)


if __name__ == "__main__":
    main()
