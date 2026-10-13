"""End-to-end tests for the close pipeline graph, offline (no ANTHROPIC_API_KEY).

Exercises the real interrupt/resume cycle against LangGraph's checkpointer --
not mocked -- so these tests double as a guard against LangGraph API drift.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from intercompany_close_agent.graph.graph import build_graph, resume_close, run_close
from intercompany_close_agent.ingest.loaders import load_ic_transactions, load_trial_balance
from intercompany_close_agent.models.exception import ExceptionType
from intercompany_close_agent.models.review import ReviewAction

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "synthetic"


def _load_real_data():
    entities_path = DATA_DIR / "entities.csv"
    import csv

    from intercompany_close_agent.models.entity import Entity

    with entities_path.open(encoding="utf-8") as fh:
        entities = [Entity(**row) for row in csv.DictReader(fh)]

    transactions = load_ic_transactions(DATA_DIR / "ic_ledger.csv")
    trial_balance = load_trial_balance(DATA_DIR / "trial_balance.csv")
    return entities, trial_balance, transactions


def test_run_pauses_for_human_review_on_real_dataset(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)

    entities, trial_balance, transactions = _load_real_data()

    _, _, result = run_close(transactions, trial_balance, entities, thread_id="test-thread-1")

    # the synthetic dataset has real exceptions in it (missing-counterparty,
    # amount-mismatch, ...), so this run should hit the interrupt
    assert "__interrupt__" in result
    pending = result["__interrupt__"][0].value["pending_review"]
    assert len(pending) > 0
    assert result["exceptions"]
    assert result["triage_results"]


def test_resume_with_decisions_produces_final_eliminations(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)

    entities, trial_balance, transactions = _load_real_data()

    graph, config, result = run_close(transactions, trial_balance, entities, thread_id="test-thread-2")
    assert "__interrupt__" in result

    pending = result["__interrupt__"][0].value["pending_review"]
    decisions = [
        {"reference": item["reference"], "action": ReviewAction.APPROVE.value, "reviewer_note": "test approval"}
        for item in pending
    ]

    final = resume_close(graph, config, decisions)

    assert "__interrupt__" not in final
    assert "eliminations" in final
    assert len(final["eliminations"]) > 0
    assert any("finalized" in entry for entry in final["audit_trail"])


def test_rejecting_a_decision_excludes_it_from_eliminations(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)

    entities, trial_balance, transactions = _load_real_data()

    graph, config, result = run_close(transactions, trial_balance, entities, thread_id="test-thread-3")
    pending = result["__interrupt__"][0].value["pending_review"]

    # reject the first one, approve the rest
    decisions = []
    for i, item in enumerate(pending):
        action = ReviewAction.REJECT.value if i == 0 else ReviewAction.APPROVE.value
        decisions.append({"reference": item["reference"], "action": action, "reviewer_note": "test"})

    final = resume_close(graph, config, decisions)

    rejected_reference = pending[0]["reference"]
    eliminated_references = {e.reference for e in final["eliminations"]}
    assert rejected_reference not in eliminated_references


def test_approving_a_missing_counterparty_with_an_amount_books_it(monkeypatch):
    """A one-legged exception can only be booked if the reviewer supplies the amount."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)

    entities, trial_balance, transactions = _load_real_data()
    graph, config, result = run_close(transactions, trial_balance, entities, thread_id="test-thread-5")

    one_legged = {exc.reference for exc in result["exceptions"] if len(exc.legs) == 1}
    assert one_legged, "the synthetic dataset should contain at least one missing counterparty"
    target = sorted(one_legged)[0]

    pending = result["__interrupt__"][0].value["pending_review"]
    decisions = []
    for item in pending:
        if item["reference"] == target:
            decisions.append(
                {
                    "reference": target,
                    "action": ReviewAction.APPROVE.value,
                    "reviewer_note": "confirmed with the affiliate",
                    "override_amount": "5000.00",
                }
            )
        else:
            decisions.append({"reference": item["reference"], "action": ReviewAction.REJECT.value})

    final = resume_close(graph, config, decisions)

    booked = {e.reference for e in final["eliminations"]}
    assert target in booked

    elimination = next(e for e in final["eliminations"] if e.reference == target)
    assert all(line.amount == Decimal("5000.00") for line in elimination.lines)
    assert "confirmed with the affiliate" in elimination.narrative


def test_approving_with_a_non_positive_override_is_not_booked(monkeypatch):
    """The reviewer's amount is free text from the dashboard. A negative would
    book a direction-inverted entry and a zero would clear nothing, so a
    fat-fingered amount must degrade to an unbooked worklist item with a
    reason in the audit trail -- not crash the resume, and not book garbage."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)

    entities, trial_balance, transactions = _load_real_data()
    graph, config, result = run_close(transactions, trial_balance, entities, thread_id="test-thread-neg-override")

    one_legged = {exc.reference for exc in result["exceptions"] if len(exc.legs) == 1}
    assert one_legged, "the synthetic dataset should contain at least one missing counterparty"
    target = sorted(one_legged)[0]

    pending = result["__interrupt__"][0].value["pending_review"]
    decisions = []
    for item in pending:
        if item["reference"] == target:
            decisions.append(
                {
                    "reference": target,
                    "action": ReviewAction.EDIT.value,
                    "reviewer_note": "fat-fingered a negative",
                    "override_amount": "-5000.00",
                }
            )
        else:
            decisions.append({"reference": item["reference"], "action": ReviewAction.REJECT.value})

    final = resume_close(graph, config, decisions)

    booked = {e.reference for e in final["eliminations"]}
    assert target not in booked
    assert any(
        target in entry and "must be a positive number" in entry for entry in final["audit_trail"]
    )


def test_approving_a_missing_counterparty_without_an_amount_is_not_booked(monkeypatch):
    """Approval alone isn't enough when there's no amount to book."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)

    entities, trial_balance, transactions = _load_real_data()
    graph, config, result = run_close(transactions, trial_balance, entities, thread_id="test-thread-6")

    one_legged = {exc.reference for exc in result["exceptions"] if len(exc.legs) == 1}
    target = sorted(one_legged)[0]

    pending = result["__interrupt__"][0].value["pending_review"]
    decisions = [
        {"reference": item["reference"], "action": ReviewAction.APPROVE.value}
        for item in pending
    ]

    final = resume_close(graph, config, decisions)

    booked = {e.reference for e in final["eliminations"]}
    assert target not in booked
    # and the audit trail says why, rather than the item silently vanishing
    assert any(target in entry and "not booked automatically" in entry for entry in final["audit_trail"])


def test_every_checkpointed_type_is_declared_to_the_serializer(monkeypatch):
    """Types that land in a checkpoint have to be declared, or resume breaks.

    LangGraph currently allows anything and only warns; a future release
    blocks it, which would break resume -- the one path a reviewer depends
    on. Asserting on the configuration rather than on the warning, because
    the warning is emitted once per process and any earlier test swallows it.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)

    allowlist = build_graph().checkpointer.serde._allowed_msgpack_modules
    assert allowlist is not True, "an explicit allowlist is the point; True means 'allow anything'"

    # Walk a real paused state and check nothing in it is missing from the list.
    entities, trial_balance, transactions = _load_real_data()
    _, _, result = run_close(transactions, trial_balance, entities, thread_id="test-serde")

    declared = {name for _module, name in allowlist}
    seen: set[str] = set()

    def walk(value):
        if isinstance(value, list | tuple | set):
            for item in value:
                walk(item)
        elif isinstance(value, dict):
            for item in value.values():
                walk(item)
        elif type(value).__module__.startswith("intercompany_close_agent"):
            seen.add(type(value).__name__)
            if hasattr(value, "__dict__"):
                walk(vars(value))

    walk({k: v for k, v in result.items() if k != "__interrupt__"})

    assert seen, "the paused state should contain our own types"
    assert seen <= declared, f"undeclared in _CHECKPOINTED_TYPES: {sorted(seen - declared)}"


def test_currency_mismatch_approved_without_an_override_is_not_booked(monkeypatch):
    """Legs in different currencies have no FX rate to net them. Approving
    alone (no reviewer-supplied amount) mustn't book at either leg's own,
    currency-ambiguous amount -- that would apply exactly the implicit 1:1
    rate this exception type exists to refuse."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)

    entities, trial_balance, transactions = _load_real_data()
    graph, config, result = run_close(transactions, trial_balance, entities, thread_id="test-thread-currency-1")
    assert "__interrupt__" in result

    currency_mismatches = {
        exc.reference for exc in result["exceptions"] if exc.exception_type == ExceptionType.CURRENCY_MISMATCH
    }
    assert currency_mismatches, "fixture dataset should contain a currency mismatch"

    pending = result["__interrupt__"][0].value["pending_review"]
    assert any(item["reference"] in currency_mismatches and item["net_amount"] is None for item in pending)

    decisions = [
        {"reference": item["reference"], "action": ReviewAction.APPROVE.value, "reviewer_note": "test"}
        for item in pending
    ]
    final = resume_close(graph, config, decisions)

    booked = {e.reference for e in final["eliminations"]}
    assert not (currency_mismatches & booked)
    for ref in currency_mismatches:
        assert any(
            ref in entry and "not booked automatically" in entry and "currencies" in entry
            for entry in final["audit_trail"]
        )


def test_currency_mismatch_with_an_override_amount_is_booked(monkeypatch):
    """Edit is the one path that can book a currency mismatch: the reviewer
    supplies the amount, already converted to the reporting currency."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)

    entities, trial_balance, transactions = _load_real_data()
    graph, config, result = run_close(transactions, trial_balance, entities, thread_id="test-thread-currency-2")

    target = next(
        exc.reference for exc in result["exceptions"] if exc.exception_type == ExceptionType.CURRENCY_MISMATCH
    )

    pending = result["__interrupt__"][0].value["pending_review"]
    decisions = []
    for item in pending:
        if item["reference"] == target:
            decisions.append(
                {
                    "reference": target,
                    "action": ReviewAction.EDIT.value,
                    "reviewer_note": "converted at the confirmed month-end rate",
                    "override_amount": "50000.00",
                }
            )
        else:
            decisions.append({"reference": item["reference"], "action": ReviewAction.REJECT.value})

    final = resume_close(graph, config, decisions)

    booked = {e.reference for e in final["eliminations"]}
    assert target in booked
    elimination = next(e for e in final["eliminations"] if e.reference == target)
    assert all(line.amount == Decimal("50000.00") for line in elimination.lines)
    assert "converted at the confirmed month-end rate" in elimination.narrative


def test_sign_mismatch_never_auto_resolves_and_is_never_booked_on_approval(monkeypatch):
    """A sign-flip (both legs booked on the same side) is a real bug in the
    synthetic dataset (see anomaly_sign_flip). It should always land in the
    reviewer worklist, and approving it still shouldn't produce an
    elimination -- there's no unambiguous receivable/payable pair to build
    one from, so it needs offline resolution rather than a booking."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)

    entities, trial_balance, transactions = _load_real_data()
    graph, config, result = run_close(transactions, trial_balance, entities, thread_id="test-thread-7")

    sign_mismatch_refs = {
        exc.reference for exc in result["exceptions"] if exc.exception_type == ExceptionType.SIGN_MISMATCH
    }
    assert sign_mismatch_refs, "the synthetic dataset should contain at least one sign mismatch"

    pending = result["__interrupt__"][0].value["pending_review"]
    pending_refs = {item["reference"] for item in pending}
    assert sign_mismatch_refs.issubset(pending_refs)

    decisions = [
        {"reference": item["reference"], "action": ReviewAction.APPROVE.value, "reviewer_note": "test approval"}
        for item in pending
    ]
    final = resume_close(graph, config, decisions)

    booked = {e.reference for e in final["eliminations"]}
    assert not (sign_mismatch_refs & booked)
    for ref in sign_mismatch_refs:
        assert any(ref in entry and "not booked automatically" in entry for entry in final["audit_trail"])


def test_finalize_surfaces_a_control_account_residual_left_by_an_elimination(monkeypatch):
    """An amount_mismatch exception's two legs don't net to zero -- that's
    the whole reason it's an exception. Eliminating it books at the
    receivable leg's own amount, which leaves the payable entity's control
    account short (or over) by whatever didn't net -- that has to show up
    in the audit trail, not disappear. Finds a real one in the shipped
    dataset rather than hardcoding a reference, so this doesn't silently
    stop testing anything the next time the dataset is regenerated."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)

    entities, trial_balance, transactions = _load_real_data()
    graph, config, result = run_close(transactions, trial_balance, entities, thread_id="test-thread-9")
    assert "__interrupt__" in result

    amount_mismatches = [exc for exc in result["exceptions"] if exc.exception_type == ExceptionType.AMOUNT_MISMATCH]
    target_exc = next(
        (exc for exc in amount_mismatches if abs(exc.legs[0].amount) != abs(exc.legs[1].amount)), None
    )
    assert target_exc is not None, "fixture dataset should contain an amount mismatch with a genuine residual"
    payable_leg = next(leg for leg in target_exc.legs if leg.amount < 0)

    pending = result["__interrupt__"][0].value["pending_review"]
    decisions = [
        {"reference": item["reference"], "action": ReviewAction.APPROVE.value, "reviewer_note": "test"}
        for item in pending
    ]
    final = resume_close(graph, config, decisions)

    assert target_exc.reference in {e.reference for e in final["eliminations"]}
    assert any(
        target_exc.reference in entry and "unexplained residual" in entry and payable_leg.entity_code in entry
        for entry in final["audit_trail"]
    )


def test_missing_counterparty_never_auto_resolves(monkeypatch):
    """Sanity check on the taxonomy: a missing-counterparty exception in the
    real dataset should always show up in pending_review, never be silently
    auto-eliminated."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)

    entities, trial_balance, transactions = _load_real_data()
    _, _, result = run_close(transactions, trial_balance, entities, thread_id="test-thread-4")

    missing_counterparty_refs = {
        exc.reference for exc in result["exceptions"] if exc.exception_type == ExceptionType.MISSING_COUNTERPARTY
    }
    assert missing_counterparty_refs, "fixture dataset should contain a missing counterparty"

    pending_refs = {item["reference"] for item in result["__interrupt__"][0].value["pending_review"]}
    assert missing_counterparty_refs.issubset(pending_refs)


def test_finalize_records_what_a_within_tolerance_clean_pair_leaves_behind(monkeypatch):
    """A clean pair only has to net to within tolerance, not to zero, and its
    elimination books the receivable leg's amount on both sides. Whatever the
    payable side was off by stays in that entity's control account, and the
    audit trail is where a reviewer has to be able to find it."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)

    entities, trial_balance, transactions = _load_real_data()
    graph, config, result = run_close(transactions, trial_balance, entities, thread_id="test-thread-tolerance")
    off_by_a_little = [(a, b) for a, b in result["clean_pairs"] if a.amount + b.amount != 0]
    assert off_by_a_little, "fixture dataset should contain a clean pair that nets to within tolerance, not zero"
    leg_a, leg_b = off_by_a_little[0]
    payable = leg_a if leg_a.amount < 0 else leg_b

    pending = result["__interrupt__"][0].value["pending_review"]
    final = resume_close(graph, config, [{"reference": item["reference"], "action": "reject"} for item in pending])

    assert any(
        leg_a.reference in entry and "within tolerance" in entry and payable.entity_code in entry
        for entry in final["audit_trail"]
    )
