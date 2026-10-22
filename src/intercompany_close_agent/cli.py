"""Command-line interface for the intercompany close agent.

Six commands:
  demo            -- `run` on the committed sample data, always offline
  generate-data   -- regenerate the synthetic dataset
  write-workbook  -- write a folder of CSV inputs as one .xlsx workbook
  run             -- run the close pipeline end to end and print the results
  scale-run       -- generate a group the size of a real one, close it offline, time it
  triage-eval     -- score triage on the labelled and adversarial sets in evals/triage

`run` works with or without an Anthropic API key: with one, triage uses
Claude (DEFAULT_MODEL in triage/llm.py, or ANTHROPIC_MODEL); without, it
falls back to the deterministic rule-based classifier. Either way, the
pipeline halts at human_review for anything that needs a person's judgment
and prints the reviewer worklist -- it never silently books something a
human should see.
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
from intercompany_close_agent.offline import offline
from intercompany_close_agent.policy import DEFAULT_POLICY, ClosePolicy, PolicyError
from intercompany_close_agent.scale import report as scale_report
from intercompany_close_agent.scale import scale_run as run_at_scale
from intercompany_close_agent.synthetic.generator import OUTPUT_DIR as DEFAULT_DATA_DIR
from intercompany_close_agent.synthetic.generator import generate as generate_dataset
from intercompany_close_agent.triage import evaluation
from intercompany_close_agent.triage.llm import model_name

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
    _close(data_dir, policy_file, prepared_by, evidence_dir)


@app.command()
def demo() -> None:
    """The whole close on the committed sample data, offline, whatever is in the environment."""
    # No load_dotenv() here: a .env with a key in it would switch triage to the
    # model, and the demo is the offline run.
    with offline():
        _close(DEFAULT_DATA_DIR, None, None, Path("evidence"))
    typer.echo("")
    typer.echo(
        "That was the committed synthetic dataset, with the rule-based triage. Why each item above "
        "needs a person: docs/human-in-the-loop.md"
    )


def _close(data_dir: Path, policy_file: Path | None, prepared_by: str | None, evidence_dir: Path) -> None:
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

    mode = f"Claude ({model_name()})" if os.environ.get("ANTHROPIC_API_KEY") else "offline rule-based fallback"
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
        pack = write_pack(result, evidence_dir, data_dir)
        typer.echo(f"Evidence pack: {pack}")
        typer.echo(f"Journal to import: {pack / 'journal.csv'}, and for Dynamics 365 {pack / 'journal_d365.csv'}")


@app.command("triage-eval")
def triage_eval(
    set_name: str = typer.Option("labelled", "--set", help="Which set in evals/triage: labelled or adversarial"),
    triage: str = typer.Option("rules", help="rules, or model, which calls the Anthropic API once per case"),
    estimate_only: bool = typer.Option(
        False, "--estimate", help="Print what a model run on the set would cost, without calling the API"
    ),
    save_run: bool = typer.Option(False, "--save", help="Write the run to evals/triage/results/<set>/"),
    sets_dir: Path = typer.Option(evaluation.SETS_DIR, help="Folder with the sets"),
) -> None:
    """Score triage on a set of exceptions with known answers. Exits 1 if any case misses."""
    if set_name not in evaluation.SET_NAMES or triage not in ("rules", "model"):
        typer.echo("--set is labelled or adversarial, and --triage is rules or model.", err=True)
        raise typer.Exit(code=2)
    try:
        case_set = evaluation.load_set(evaluation.set_path(set_name, sets_dir))
        if estimate_only:
            for line in evaluation.estimate(case_set, model_name()).lines(set_name):
                typer.echo(line)
            return
        if triage == "model":
            load_dotenv()
            if not os.environ.get("ANTHROPIC_API_KEY"):
                typer.echo("The model path needs ANTHROPIC_API_KEY; the rules path doesn't.", err=True)
                raise typer.Exit(code=1)
            run = evaluation.evaluate(case_set, evaluation.model_classifier, "model", model_name())
        else:
            run = evaluation.evaluate(case_set, evaluation.rules_classifier, "rules")
    except (OSError, ValueError) as exc:
        typer.echo(f"Cannot run the triage eval: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    for line in run.report():
        typer.echo(line)
    if save_run:
        path = evaluation.results_path(set_name, run.triage, run.model, sets_dir)
        evaluation.save(run, path)
        typer.echo(f"Saved: {path}")
    if run.passed != len(run.cases):
        raise typer.Exit(code=1)


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
