"""Command-line interface for the intercompany close agent.

Two commands:
  generate-data  -- regenerate the synthetic dataset
  run            -- run the close pipeline end to end and print the results

`run` works with or without an Anthropic API key: with one (and
ANTHROPIC_MODEL set), triage uses Claude; without, it falls back to the
deterministic rule-based classifier. Either way, the pipeline halts at
human_review for anything that needs a person's judgment and prints the
reviewer worklist -- it never silently books something a human should see.
"""

from __future__ import annotations

import csv
import os
from pathlib import Path

import typer
from dotenv import load_dotenv

from intercompany_close_agent.graph.graph import run_close
from intercompany_close_agent.ingest.loaders import load_ic_transactions, load_trial_balance
from intercompany_close_agent.models.entity import Entity
from intercompany_close_agent.synthetic.generator import OUTPUT_DIR as DEFAULT_DATA_DIR
from intercompany_close_agent.synthetic.generator import generate as generate_dataset

app = typer.Typer(help="Intercompany close agent -- IC matching, eliminations, and human-in-the-loop triage.")


def _load_entities(path: Path) -> list[Entity]:
    with path.open(encoding="utf-8") as fh:
        return [Entity(**row) for row in csv.DictReader(fh)]


@app.command("generate-data")
def generate_data(
    seed: int = typer.Option(42, help="RNG seed"),
    pairs: int = typer.Option(26, help="Number of IC pairs to generate before anomalies"),
    out_dir: Path = typer.Option(DEFAULT_DATA_DIR, help="Where to write the CSVs"),
) -> None:
    """Regenerate the synthetic dataset."""
    generate_dataset(seed=seed, pair_count=pairs, out_dir=out_dir)


@app.command()
def run(
    data_dir: Path = typer.Option(
        DEFAULT_DATA_DIR, help="Directory with entities.csv, trial_balance.csv, ic_ledger.csv"
    ),
) -> None:
    """Run the close pipeline end to end and print the results."""
    load_dotenv()

    entities = _load_entities(data_dir / "entities.csv")
    trial_balance = load_trial_balance(data_dir / "trial_balance.csv")
    transactions = load_ic_transactions(data_dir / "ic_ledger.csv")

    model_name = os.environ.get("ANTHROPIC_MODEL")
    llm_configured = bool(os.environ.get("ANTHROPIC_API_KEY")) and bool(model_name)
    mode = f"Claude ({model_name})" if llm_configured else "offline rule-based fallback"
    typer.echo(f"Triage mode: {mode}")
    typer.echo(f"Loaded {len(entities)} entities, {len(transactions)} IC transaction legs")

    _, _, result = run_close(transactions, trial_balance, entities)

    typer.echo("")
    typer.echo("=== Audit trail ===")
    for line in result["audit_trail"]:
        typer.echo(f"  - {line}")

    breaks = [v for v in result.get("tb_variances", []) if not v.within_tolerance]
    if breaks:
        typer.echo("")
        typer.echo(f"=== Control account tie-out: {len(breaks)} entity(ies) do not tie ===")
        for variance in breaks:
            typer.echo(
                f"  {variance.entity_code}: IC subledger {variance.ledger_total} vs "
                f"trial balance {variance.trial_balance_total} (variance {variance.variance})"
            )
        typer.echo("  These are GL-vs-subledger data breaks, not per-balance reconciliation items.")

    if "__interrupt__" in result:
        pending = result["__interrupt__"][0].value["pending_review"]
        typer.echo("")
        typer.echo(f"=== Reviewer worklist ({len(pending)} item(s) need a human decision) ===")
        for item in pending:
            typer.echo(f"  [{item['materiality'].upper()}] {item['reference']} -- {item['exception_type']}")
            typer.echo(f"      net amount: {item['net_amount']}")
            typer.echo(f"      why: {item['detected_reason']}")
            typer.echo(f"      triage (confidence {item['confidence']:.2f}): {item['rationale']}")
        typer.echo("")
        typer.echo("Run the reviewer dashboard to approve, reject or edit these:")
        typer.echo("  uv run streamlit run app/streamlit_app.py")
    else:
        n_eliminations = len(result.get("eliminations", []))
        typer.echo("")
        typer.echo(f"No items needed human review. {n_eliminations} elimination(s) finalized.")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
