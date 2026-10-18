"""Command-line interface for the intercompany close agent.

Four commands:
  generate-data   -- regenerate the synthetic dataset
  write-workbook  -- write a folder of CSV inputs as one .xlsx workbook
  run             -- run the close pipeline end to end and print the results
  scale-run       -- generate a group the size of a real one, close it offline, time it

`run` works with or without an Anthropic API key: with one (and
ANTHROPIC_MODEL set), triage uses Claude; without, it falls back to the
deterministic rule-based classifier. Either way, the pipeline halts at
human_review for anything that needs a person's judgment and prints the
reviewer worklist -- it never silently books something a human should see.
"""

from __future__ import annotations

import getpass
import os
from pathlib import Path

import typer
from dotenv import load_dotenv

from intercompany_close_agent.evidence import write_pack
from intercompany_close_agent.graph.graph import run_close
from intercompany_close_agent.ingest.loaders import DataLoadError, load_dataset
from intercompany_close_agent.ingest.workbook import write_workbook
from intercompany_close_agent.policy import DEFAULT_POLICY, ClosePolicy, PolicyError
from intercompany_close_agent.scale import report as scale_report
from intercompany_close_agent.scale import scale_run as run_at_scale
from intercompany_close_agent.synthetic.generator import OUTPUT_DIR as DEFAULT_DATA_DIR
from intercompany_close_agent.synthetic.generator import generate as generate_dataset

app = typer.Typer(help="Intercompany close agent -- IC matching, eliminations, and human-in-the-loop triage.")


@app.command("generate-data")
def generate_data(
    seed: int = typer.Option(14, help="RNG seed"),
    pairs: int = typer.Option(26, help="Number of IC pairs to generate before anomalies"),
    out_dir: Path = typer.Option(DEFAULT_DATA_DIR, help="Where to write the CSVs"),
    entities: int = typer.Option(7, help="Number of legal entities; 7 is the committed sample's group"),
    anomaly_rate: float = typer.Option(0.35, help="Share of balances broken on purpose"),
) -> None:
    """Regenerate the synthetic dataset."""
    generate_dataset(seed=seed, pair_count=pairs, out_dir=out_dir, entity_count=entities, anomaly_rate=anomaly_rate)


@app.command("write-workbook")
def write_workbook_command(
    data_dir: Path = typer.Option(DEFAULT_DATA_DIR, help="Folder with the three CSVs"),
    out: Path = typer.Option(Path("examples/close_template.xlsx"), help="The workbook to write"),
) -> None:
    """Write a folder of CSV inputs as one .xlsx workbook that `run` can read."""
    typer.echo(f"wrote {write_workbook(data_dir, out)}")


@app.command("scale-run")
def scale_run(
    entities: int = typer.Option(60, help="Number of legal entities in the group"),
    pairs: int = typer.Option(1500, help="Number of IC balances, two ledger lines each before anomalies"),
    seed: int = typer.Option(14, help="RNG seed"),
    anomaly_rate: float = typer.Option(0.05, help="Share of balances broken on purpose"),
) -> None:
    """Generate a group of this size, close it offline, and time each step."""
    result = run_at_scale(entity_count=entities, pair_count=pairs, seed=seed, anomaly_rate=anomaly_rate)
    for line in scale_report(result, seed, anomaly_rate):
        typer.echo(line)


@app.command()
def run(
    data_dir: Path = typer.Option(
        DEFAULT_DATA_DIR,
        "--data-dir",
        "--data",
        help="Folder with entities.csv, trial_balance.csv and ic_ledger.csv, or an .xlsx workbook "
        "with sheets of those names (see examples/close_template.xlsx)",
    ),
    policy_file: Path | None = typer.Option(
        None,
        "--policy",
        help="TOML file with the materiality threshold and tolerances (see examples/policy.toml). "
        "Without one, the built-in defaults apply.",
    ),
    prepared_by: str | None = typer.Option(
        None, help="Who is preparing this close, for the audit trail. Defaults to your login name."
    ),
    evidence_dir: Path = typer.Option(
        Path("evidence"), help="Where a run that finalizes writes its evidence pack, one folder per run."
    ),
) -> None:
    """Run the close pipeline end to end and print the results."""
    load_dotenv()

    try:
        entities, trial_balance, transactions = load_dataset(data_dir)
        policy = ClosePolicy.from_toml(policy_file) if policy_file else DEFAULT_POLICY
    except (DataLoadError, PolicyError) as exc:
        typer.echo(f"Cannot run the close: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    preparer = _login_name() if prepared_by is None else prepared_by
    if not preparer.strip():
        typer.echo("Cannot run the close: --prepared-by can't be blank.", err=True)
        raise typer.Exit(code=1)

    model_name = os.environ.get("ANTHROPIC_MODEL")
    llm_configured = bool(os.environ.get("ANTHROPIC_API_KEY")) and bool(model_name)
    mode = f"Claude ({model_name})" if llm_configured else "offline rule-based fallback"
    typer.echo(f"Triage mode: {mode}")
    typer.echo(f"Loaded {len(entities)} entities, {len(transactions)} IC transaction legs")

    _, _, result = run_close(transactions, trial_balance, entities, prepared_by=preparer, policy=policy)

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
            net_amount = item["net_amount"] or "n/a -- different currencies, no FX rate to net"
            typer.echo(f"      net amount: {net_amount}")
            typer.echo(f"      why: {item['detected_reason']}")
            typer.echo(f"      triage (confidence {item['confidence']:.2f}): {item['rationale']}")
        typer.echo("")
        typer.echo("Run the reviewer dashboard to approve, reject or edit these:")
        typer.echo("  uv run streamlit run app/streamlit_app.py")
        typer.echo("The close finalizes, and writes its evidence pack, once every item has a decision.")
    else:
        n_eliminations = len(result.get("eliminations", []))
        typer.echo("")
        typer.echo(f"No items needed human review. {n_eliminations} elimination(s) finalized.")
        typer.echo(f"Evidence pack: {write_pack(result, evidence_dir, data_dir)}")


def _login_name() -> str:
    try:
        return getpass.getuser()
    except (KeyError, OSError) as exc:
        typer.echo("Cannot tell who is running this; pass --prepared-by.", err=True)
        raise typer.Exit(code=1) from exc


def main() -> None:
    app()


if __name__ == "__main__":
    main()
