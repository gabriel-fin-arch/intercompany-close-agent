"""recalc/ic_recalc.sql, the accountant's own recalculation, reconciled against the pipeline.

recalc/ holds Gabriel's independent recalculation of the sample close in plain
SQL; recalc/README.md says what it checks and who writes it, and nothing here
writes to it. This runs that SQL in DuckDB, runs the close offline on the same
three CSVs, and compares the two, one by one:

- the tie-out, per entity: subledger total, trial balance total, variance and
  whether it breaks
- the matching, per reference: clean or exception, and the exception type
  when the recalculation gives one
- the amount the clean pairs eliminate

Any difference fails the check. Neither side is adjusted to make it pass: the
entity or reference that differs is investigated by hand, and if it looks like
a defect in the pipeline, an issue is opened (#54). CI runs it on every push
and pull request; locally,

    uv run python -m intercompany_close_agent.recalc_check
"""

from __future__ import annotations

import contextlib
import sys
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from intercompany_close_agent.eliminations.engine import build_eliminations
from intercompany_close_agent.graph.graph import run_close
from intercompany_close_agent.ingest.loaders import load_dataset
from intercompany_close_agent.models.elimination import JournalLineType
from intercompany_close_agent.offline import offline

ROOT = Path(__file__).resolve().parents[2]
SQL = ROOT / "recalc" / "ic_recalc.sql"
# Where the SQL reads its CSVs from, relative to the repository root.
DATA_DIR = ROOT / "data" / "synthetic"


@dataclass(frozen=True)
class TieOut:
    ledger_total: Decimal
    tb_total: Decimal
    variance: Decimal
    is_break: bool


@dataclass(frozen=True)
class Pair:
    outcome: str  # "clean" or "exception", the contract in #54
    exception_type: str | None  # None for a clean pair, or when the recalculation gives no type


@dataclass(frozen=True)
class Figures:
    """One side's answer, in the shape of the three views #54 fixed."""

    tieout: dict[str, TieOut]
    pairs: dict[str, Pair]
    eliminated: Decimal


@dataclass(frozen=True)
class Difference:
    where: str
    recalc: object
    pipeline: object


def from_recalc(sql: Path = SQL) -> Figures:
    """Run the SQL as recalc/README.md does, from the repository root, and read its three views."""
    import duckdb  # a dev dependency: only this check needs it

    con = duckdb.connect()
    with contextlib.chdir(ROOT):
        con.execute(sql.read_text(encoding="utf-8"))
    tieout = {
        entity: TieOut(ledger, tb, variance, is_break)
        for entity, ledger, tb, variance, is_break in con.execute(
            "SELECT entity_code, ledger_total, tb_total, variance, is_break FROM recalc_tieout"
        ).fetchall()
    }
    # outcome is the contract; the type is an extra column the recalculation may or may not have.
    columns = {row[0] for row in con.execute("DESCRIBE recalc_pairs").fetchall()}
    exception_type = "exception_type" if "exception_type" in columns else "NULL"
    pairs = {
        reference: Pair(outcome, kind)
        for reference, outcome, kind in con.execute(
            f"SELECT reference, outcome, {exception_type} FROM recalc_pairs"
        ).fetchall()
    }
    row = con.execute("SELECT total_eliminated_clean_pairs FROM recalc_eliminated").fetchone()
    eliminated = row[0] if row and row[0] is not None else Decimal("0")
    return Figures(tieout, pairs, eliminated)


def from_pipeline(data_dir: Path = DATA_DIR) -> Figures:
    """The same figures from an offline close: triage doesn't touch them, so no key is needed or used."""
    entities, trial_balance, transactions = load_dataset(data_dir)
    with offline():
        _, _, result = run_close(
            transactions, trial_balance, entities, prepared_by="recalc check", thread_id="recalc-check"
        )
    tieout = {
        v.entity_code: TieOut(v.ledger_total, v.trial_balance_total, v.variance, not v.within_tolerance)
        for v in result["tb_variances"]
    }
    pairs = {leg.reference: Pair("clean", None) for leg, _ in result["clean_pairs"]}
    pairs |= {exc.reference: Pair("exception", exc.exception_type.value) for exc in result["exceptions"]}
    # What the close books for the clean pairs: finalize builds their entries with this same call.
    eliminated = sum(
        (
            line.amount
            for elimination in build_eliminations(result["clean_pairs"])
            for line in elimination.lines
            if line.line_type == JournalLineType.DEBIT
        ),
        Decimal("0"),
    )
    return Figures(tieout, pairs, eliminated)


def differences(recalc: Figures, pipeline: Figures) -> list[Difference]:
    """Every entity, reference and total where the two sides don't say the same thing."""
    found: list[Difference] = []
    for entity in sorted(recalc.tieout.keys() | pipeline.tieout.keys()):
        mine, theirs = recalc.tieout.get(entity), pipeline.tieout.get(entity)
        if mine is None or theirs is None:
            found.append(Difference(f"tie-out, {entity}", _presence(mine), _presence(theirs)))
            continue
        for field in ("ledger_total", "tb_total", "variance", "is_break"):
            if getattr(mine, field) != getattr(theirs, field):
                found.append(Difference(f"tie-out, {entity}, {field}", getattr(mine, field), getattr(theirs, field)))
    for reference in sorted(recalc.pairs.keys() | pipeline.pairs.keys()):
        pair, other = recalc.pairs.get(reference), pipeline.pairs.get(reference)
        if pair is None or other is None:
            found.append(Difference(f"pairs, {reference}", _presence(pair), _presence(other)))
        elif pair.outcome != other.outcome:
            found.append(Difference(f"pairs, {reference}, outcome", pair.outcome, other.outcome))
        elif pair.exception_type is not None and pair.exception_type != other.exception_type:
            found.append(Difference(f"pairs, {reference}, exception type", pair.exception_type, other.exception_type))
    if recalc.eliminated != pipeline.eliminated:
        found.append(Difference("eliminated, clean pairs", recalc.eliminated, pipeline.eliminated))
    return found


def _presence(value: object) -> str:
    return "missing" if value is None else "present"


def _show(value: object) -> str:
    return f"{value:,}" if isinstance(value, Decimal) else str(value)


def report(recalc: Figures, pipeline: Figures, found: list[Difference]) -> list[str]:
    """Markdown: the headline figures side by side, then every difference, or a line saying there are none."""

    def breaks(side: Figures) -> str:
        return ", ".join(f"{e} {t.variance:,}" for e, t in sorted(side.tieout.items()) if t.is_break) or "none"

    def count(side: Figures, outcome: str) -> int:
        return sum(1 for p in side.pairs.values() if p.outcome == outcome)

    rows = [
        ("Entities in the tie-out", len(recalc.tieout), len(pipeline.tieout)),
        ("Entities that break", breaks(recalc), breaks(pipeline)),
        ("References", len(recalc.pairs), len(pipeline.pairs)),
        ("Clean pairs", count(recalc, "clean"), count(pipeline, "clean")),
        ("Exceptions", count(recalc, "exception"), count(pipeline, "exception")),
        ("Eliminated, clean pairs", f"{recalc.eliminated:,}", f"{pipeline.eliminated:,}"),
    ]
    lines = [
        "## recalc/ic_recalc.sql against the pipeline",
        "",
        "| | recalc/ic_recalc.sql | pipeline, offline run |",
        "|---|---:|---:|",
        *(f"| {name} | {mine} | {theirs} |" for name, mine, theirs in rows),
        "",
    ]
    if not found:
        lines.append(
            f"No differences: {len(pipeline.tieout)} entities, {len(pipeline.pairs)} references "
            "and the eliminated total, compared one by one."
        )
        return lines
    lines += [
        f"**{len(found)} difference(s).** Investigate each by hand; neither side gets adjusted to make this pass.",
        "",
        "| Where | recalc/ic_recalc.sql | pipeline |",
        "|---|---|---|",
        *(f"| {d.where} | {_show(d.recalc)} | {_show(d.pipeline)} |" for d in found),
    ]
    return lines


def main() -> None:
    recalc, pipeline = from_recalc(), from_pipeline()
    found = differences(recalc, pipeline)
    print("\n".join(report(recalc, pipeline, found)))
    if found:
        sys.exit(1)


if __name__ == "__main__":
    main()
