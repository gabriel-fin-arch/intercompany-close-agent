"""A close at the size of a real group, timed.

The sample has 7 entities and 53 ledger lines, which says nothing about
whether the close holds up at the size it's meant for. This generates a
group of a given size (by default 60 entities and 1,500 balances), runs the
close on it offline, rejects every item on the worklist so it finalizes, and
times each step.

The counts follow from the seed, and a test checks them. The times depend
on the machine, which is reported with them.
"""

from __future__ import annotations

import contextlib
import io
import os
import platform
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

from intercompany_close_agent.graph.graph import resume_close, run_close
from intercompany_close_agent.ingest.loaders import load_dataset
from intercompany_close_agent.synthetic.generator import generate

PREPARER = "scale-run"
REVIEWER = "scale-run reviewer"


@dataclass(frozen=True)
class ScaleRun:
    entities: int
    balances: int
    ledger_lines: int
    clean_pairs: int
    exceptions: int
    for_review: int
    not_tying_out: int
    eliminations: int
    load_seconds: float
    to_worklist_seconds: float
    finalize_seconds: float


@contextlib.contextmanager
def _offline() -> Iterator[None]:
    """No API key or model for the duration, whatever the environment says.

    A worklist this size is dozens of model calls, and a timing that
    includes them measures the network, not the close.
    """
    saved = {name: os.environ.pop(name) for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_MODEL") if name in os.environ}
    try:
        yield
    finally:
        os.environ.update(saved)


def machine() -> str:
    processor = platform.processor() or platform.machine()
    return f"{platform.platform()}, {processor}, {os.cpu_count()} CPUs, Python {platform.python_version()}"


def scale_run(
    entity_count: int = 60, pair_count: int = 1500, seed: int = 14, anomaly_rate: float = 0.05
) -> ScaleRun:
    """Generate a group this size, close it offline, and time load, run and finalize."""
    with tempfile.TemporaryDirectory() as tmp, _offline():
        data_dir = Path(tmp)
        with contextlib.redirect_stdout(io.StringIO()):
            generate(
                seed=seed,
                pair_count=pair_count,
                out_dir=data_dir,
                entity_count=entity_count,
                anomaly_rate=anomaly_rate,
            )

        started = perf_counter()
        entities, trial_balance, transactions = load_dataset(data_dir)
        loaded = perf_counter()
        graph, config, result = run_close(
            transactions, trial_balance, entities, thread_id="scale-run", prepared_by=PREPARER
        )
        at_worklist = perf_counter()
        pending = result["__interrupt__"][0].value["pending_review"] if "__interrupt__" in result else []
        final = (
            resume_close(
                graph,
                config,
                [{"reference": item["reference"], "action": "reject", "reviewer": REVIEWER} for item in pending],
            )
            if pending
            else result
        )
        finalized = perf_counter()

    return ScaleRun(
        entities=len(entities),
        balances=pair_count,
        ledger_lines=len(transactions),
        clean_pairs=len(result["clean_pairs"]),
        exceptions=len(result["exceptions"]),
        for_review=len(pending),
        not_tying_out=sum(not v.within_tolerance for v in result["tb_variances"]),
        eliminations=len(final["eliminations"]),
        load_seconds=loaded - started,
        to_worklist_seconds=at_worklist - loaded,
        finalize_seconds=finalized - at_worklist,
    )


def report(run: ScaleRun, seed: int, anomaly_rate: float) -> list[str]:
    """The lines `scale-run` prints: the counts first, then the times and the machine."""
    return [
        f"Group: {run.entities} entities, {run.balances:,} balances, {run.ledger_lines:,} IC ledger lines "
        f"(seed {seed}, anomaly rate {anomaly_rate})",
        f"Found: {run.clean_pairs:,} clean pairs, {run.exceptions} exceptions, {run.for_review} for review; "
        f"entities not tying out: {run.not_tying_out} of {run.entities}",
        f"Booked: {run.eliminations:,} eliminations, with every item on the worklist rejected",
        f"Time: load {run.load_seconds:.2f} s, to the worklist {run.to_worklist_seconds:.2f} s, "
        f"finalize {run.finalize_seconds:.2f} s",
        f"Machine: {machine()}",
        "Offline: rule-based triage, no API calls.",
    ]
