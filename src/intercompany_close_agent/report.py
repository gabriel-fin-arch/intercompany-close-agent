"""A static HTML report of the sample close, for GitHub Pages.

`python -m intercompany_close_agent.cli report --out site` runs the close
offline on the committed dataset (the run `demo` prints), then resumes it with
no reviewer decisions, so finalize books exactly what it books before anyone
has looked: the clean pairs and the auto-resolved exceptions. The worklist
items stay unbooked, as they would. One self-contained index.html; CI publishes
it on every push to main.
"""

from __future__ import annotations

import html
from collections.abc import Collection
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from intercompany_close_agent.graph.graph import resume_close, run_close
from intercompany_close_agent.ingest.loaders import load_dataset
from intercompany_close_agent.models.entity import Entity
from intercompany_close_agent.models.ledger import ICTransaction
from intercompany_close_agent.offline import offline
from intercompany_close_agent.sample_results import bullets, summary_of
from intercompany_close_agent.synthetic.generator import OUTPUT_DIR
from intercompany_close_agent.triage.models import TriageClassification

REPO = "https://github.com/gabriel-fin-arch/intercompany-close-agent"


@dataclass
class CloseReport:
    entities: list[Entity]
    transactions: list[ICTransaction]
    paused: dict  # the run as it stops at human_review
    final: dict  # the same run resumed with no decisions


def build(data_dir: Path = OUTPUT_DIR) -> CloseReport:
    entities, trial_balance, transactions = load_dataset(data_dir)
    with offline():
        graph, config, paused = run_close(
            transactions, trial_balance, entities, prepared_by="example preparer", thread_id="static-report"
        )
        final = resume_close(graph, config, []) if "__interrupt__" in paused else paused
    return CloseReport(entities, transactions, paused, final)


def _e(value: object) -> str:
    return html.escape(str(value))


def _money(value: Decimal | None) -> str:
    return "n/a" if value is None else f"{value:,.2f}"


def _table(head: list[str], rows: list[list[str]], numeric: Collection[int] = ()) -> str:
    th = "".join(f'<th class="num">{_e(h)}</th>' if i in numeric else f"<th>{_e(h)}</th>" for i, h in enumerate(head))
    body = "".join(
        "<tr>" + "".join(f'<td class="num">{c}</td>' if i in numeric else f"<td>{c}</td>" for i, c in enumerate(r))
        + "</tr>"
        for r in rows
    )
    return f"<table><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table>"


def render(report: CloseReport, commit: str | None = None) -> str:
    paused, final = report.paused, report.final
    summary = summary_of(report.entities, report.transactions, paused)
    pending = paused["__interrupt__"][0].value["pending_review"] if "__interrupt__" in paused else []
    triage = {t.reference: t for t in paused["triage_results"]}
    auto = [
        e for e in paused["exceptions"] if triage[e.reference].classification == TriageClassification.AUTO_RESOLVABLE
    ]

    built = "Built by <code>python -m intercompany_close_agent.cli report</code>"
    if commit:
        built += f' from commit <a href="{REPO}/commit/{_e(commit)}"><code>{_e(commit[:7])}</code></a>'

    tie_out = _table(
        ["Entity", "IC subledger", "Trial balance", "Variance", ""],
        [
            [
                _e(v.entity_code),
                _money(v.ledger_total),
                _money(v.trial_balance_total),
                _money(v.variance),
                "ties" if v.within_tolerance else '<span class="bad">does not tie</span>',
            ]
            for v in paused["tb_variances"]
        ],
        numeric={1, 2, 3},
    )
    worklist = _table(
        ["Reference", "Type", "Materiality", "Net amount", "Why it was raised", "Triage (rules)"],
        [
            [
                f"<code>{_e(p['reference'])}</code>",
                _e(p["exception_type"]),
                _e(p["materiality"]),
                _money(Decimal(p["net_amount"])) if p["net_amount"] is not None else "n/a: different currencies",
                _e(p["detected_reason"]),
                _e(p["rationale"]),
            ]
            for p in pending
        ],
        numeric={3},
    )
    auto_rows = _table(
        ["Reference", "Type", "Net amount", "Triage (rules)"],
        [
            [f"<code>{_e(e.reference)}</code>", _e(e.exception_type.value), _money(e.net_amount),
             _e(triage[e.reference].rationale)]
            for e in auto
        ],
        numeric={2},
    )
    pairs = _table(
        ["Reference", "Entity", "Counterparty", "Amount", "Currency"],
        [
            [f"<code>{_e(a.reference)}</code>", _e(a.entity_code), _e(a.counterparty_code), _money(a.amount),
             _e(a.currency)]
            for a, _b in paused["clean_pairs"]
        ],
        numeric={3},
    )
    eliminations = _table(
        ["Reference", "Entity", "Account", "Debit", "Credit"],
        [
            [
                f"<code>{_e(elim.reference)}</code>",
                _e(line.entity_code),
                _e(line.account_code),
                _money(line.amount) if line.line_type.value == "debit" else "",
                _money(line.amount) if line.line_type.value == "credit" else "",
            ]
            for elim in final.get("eliminations", [])
            for line in elim.lines
        ],
        numeric={3, 4},
    )
    trail = "".join(f"<li>{_e(line)}</li>" for line in final["audit_trail"])
    findings = "".join(f"<li>{_e(b)}</li>" for b in bullets(summary))
    n_elims = len(final.get("eliminations", []))

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>intercompany-close-agent: the sample close</title>
<style>
  body {{ font: 15px/1.5 -apple-system, "Segoe UI", Helvetica, Arial, sans-serif; color: #1b1f23; margin: 0; }}
  .sheet {{ max-width: 1100px; margin: 0 auto; padding: 2rem 1.5rem 4rem; }}
  h1 {{ font-size: 1.6rem; margin: 0 0 .3rem; }}
  h2 {{ font-size: 1.15rem; margin: 2.2rem 0 .4rem; border-bottom: 1px solid #d9dde1; padding-bottom: .25rem; }}
  .lede, .note {{ color: #5b6570; }}
  .note {{ background: #f6f7f8; border: 1px solid #d9dde1; padding: .6rem .8rem; border-radius: 4px; }}
  table {{ border-collapse: collapse; width: 100%; font-size: .86rem; margin-top: .4rem; }}
  th, td {{ text-align: left; vertical-align: top; padding: .35rem .5rem; border-bottom: 1px solid #e6e9ec; }}
  th {{ background: #f6f7f8; }}
  .num {{ text-align: right; white-space: nowrap; font-variant-numeric: tabular-nums; }}
  .bad {{ color: #a02020; font-weight: 600; }}
  code {{ font-size: .85em; }}
  footer {{ margin-top: 3rem; padding-top: 1rem; border-top: 1px solid #d9dde1; font-size: .8rem; color: #5b6570; }}
  a {{ color: inherit; }}
</style>
</head>
<body>
<div class="sheet">
<h1>The sample close</h1>
<p class="lede">What <a href="{REPO}">intercompany-close-agent</a> does with its committed sample data: the
control-account tie-out, the matching, triage, the reviewer worklist and the eliminations booked before
anyone has reviewed anything.</p>
<p class="note">Synthetic data: {summary.entities} fictional entities, none real, {summary.legs} intercompany legs.
Offline run with the rule-based triage; no model was called. {built}.</p>

<h2>What the run found</h2>
<ul>{findings}</ul>

<h2>Control-account tie-out</h2>
<p class="lede">Each entity's intercompany subledger against its control accounts on the trial balance, before
anything is matched.</p>
{tie_out}

<h2>Reviewer worklist ({len(pending)})</h2>
<p class="lede">Exceptions that need a person. Nothing here is booked until a reviewer approves, rejects or
edits it, in the dashboard (<code>uv run streamlit run app/streamlit_app.py</code>).</p>
{worklist}

<h2>Proposed for auto-elimination ({len(auto)})</h2>
{auto_rows}

<h2>Pairs that matched clean ({summary.clean_pairs})</h2>
<p class="lede">One row per pair, from the first leg.</p>
{pairs}

<h2>Eliminations booked before any review ({n_elims})</h2>
<p class="lede">The clean pairs and the auto-resolved exceptions; the worklist items are not in here.</p>
{eliminations}

<h2>Audit trail</h2>
<ul>{trail}</ul>

<footer>Generated from the code at <a href="{REPO}">{REPO}</a>. Why each worklist item needs a person:
<a href="{REPO}/blob/main/docs/human-in-the-loop.md">docs/human-in-the-loop.md</a>.</footer>
</div>
</body>
</html>
"""


def write(out_dir: Path, data_dir: Path = OUTPUT_DIR, commit: str | None = None) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / "index.html"
    target.write_bytes(render(build(data_dir), commit).encode("utf-8"))
    return target
