"""The "Results on the sample data" block in the README, computed from a run.

The figures in that block are never typed by hand: `render(summarize())` runs
the close pipeline offline on the committed dataset and writes the Markdown the
README holds between the sample-results markers. tests/test_readme_results.py
fails if the README and a fresh run disagree; after a deliberate change,

    uv run python -m intercompany_close_agent.sample_results --write

rewrites the block.
"""

from __future__ import annotations

import argparse
import textwrap
from dataclasses import dataclass
from pathlib import Path

from intercompany_close_agent.graph.graph import run_close
from intercompany_close_agent.ingest.loaders import load_dataset
from intercompany_close_agent.offline import offline
from intercompany_close_agent.synthetic.generator import OUTPUT_DIR
from intercompany_close_agent.triage.models import TriageClassification

README = Path(__file__).resolve().parents[2] / "README.md"
START = "<!-- sample-results:start -->"
END = "<!-- sample-results:end -->"


@dataclass(frozen=True)
class SampleRun:
    entities: int
    legs: int
    clean_pairs: int
    exceptions: int
    exception_types: int
    for_review: int
    auto_resolvable: int
    auto_resolvable_kinds: tuple[str, ...]
    entities_not_tying: int


def summarize(data_dir: Path = OUTPUT_DIR) -> SampleRun:
    entities, trial_balance, transactions = load_dataset(data_dir)
    with offline():  # the README shows the offline run, whatever key is in the environment
        _, _, result = run_close(
            transactions, trial_balance, entities, prepared_by="example preparer", thread_id="readme-results"
        )
    exceptions = result["exceptions"]
    classes = [t.classification for t in result["triage_results"]]
    auto = {t.reference for t in result["triage_results"] if t.classification == TriageClassification.AUTO_RESOLVABLE}
    # The rule fallback auto-resolves only amount and timing differences, below
    # materiality, between two interfaced entities (triage/rules.py).
    kinds = sorted({_KIND[e.exception_type.value] for e in exceptions if e.reference in auto})
    return SampleRun(
        entities=len(entities),
        legs=len(transactions),
        clean_pairs=len(result["clean_pairs"]),
        exceptions=len(exceptions),
        exception_types=len({e.exception_type for e in exceptions}),
        for_review=classes.count(TriageClassification.NEEDS_HUMAN_JUDGMENT),
        auto_resolvable=classes.count(TriageClassification.AUTO_RESOLVABLE),
        auto_resolvable_kinds=tuple(kinds),
        entities_not_tying=sum(1 for v in result["tb_variances"] if not v.within_tolerance),
    )


_KIND = {"amount_mismatch": "amount", "timing_gap": "timing"}


def render(run: SampleRun) -> str:
    kinds = " or ".join(run.auto_resolvable_kinds)
    rest = (
        f" The other {run.auto_resolvable} are {kinds} differences below materiality between interfaced "
        "entities, proposed for auto-elimination."
        if run.auto_resolvable
        else ""
    )
    fails = "fails" if run.entities_not_tying == 1 else "fail"
    intro = (
        f"**Results on the sample data** (synthetic: {run.entities} entities, {run.legs} intercompany legs; "
        "the tests rerun the close offline and fail if these figures change):"
    )
    bullets = [
        f"{run.clean_pairs} pairs match clean, and {run.exceptions} balances become exceptions, "
        f"of {run.exception_types} different types.",
        f"{run.for_review} of the {run.exceptions} go to a reviewer.{rest}",
        f"{run.entities_not_tying} of {run.entities} entities {fails} the control-account tie-out, "
        "a break the sample data plants on purpose.",
    ]
    # Wrapped like the rest of the README.
    wrap = textwrap.TextWrapper(width=78, break_on_hyphens=False, break_long_words=False)
    lines = wrap.wrap(intro) + [""]
    for b in bullets:
        wrap.initial_indent, wrap.subsequent_indent = "- ", "  "
        lines += wrap.wrap(b)
    return "\n".join(lines)


def readme_block(text: str) -> str:
    """The text between the markers, without the blank lines around it."""
    head, sep, rest = text.partition(START)
    body, sep2, _ = rest.partition(END)
    if not sep or not sep2:
        raise ValueError(f"README has no {START} ... {END} block")
    return body.strip("\n")


def write_readme(block: str, path: Path = README) -> None:
    raw = path.read_bytes().decode("utf-8")
    eol = "\r\n" if "\r\n" in raw else "\n"
    text = raw.replace("\r\n", "\n")
    head, _, rest = text.partition(START)
    _, _, tail = rest.partition(END)
    new = f"{head}{START}\n{block}\n{END}{tail}"
    path.write_bytes(new.replace("\n", eol).encode("utf-8"))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write", action="store_true", help="rewrite the block in README.md")
    args = parser.parse_args(argv)
    block = render(summarize())
    if args.write:
        write_readme(block)
    print(block)


if __name__ == "__main__":
    main()
