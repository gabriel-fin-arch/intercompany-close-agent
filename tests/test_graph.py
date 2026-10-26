"""End-to-end tests for the close pipeline graph, offline (no ANTHROPIC_API_KEY).

Exercises the real interrupt/resume cycle against LangGraph's checkpointer --
not mocked -- so these tests double as a guard against LangGraph API drift.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from intercompany_close_agent.graph.graph import build_graph, resume_close, run_close
from intercompany_close_agent.ingest.loaders import load_ic_transactions, load_trial_balance
from intercompany_close_agent.models.exception import ExceptionType
from intercompany_close_agent.models.review import ReviewAction
from intercompany_close_agent.policy import ClosePolicy

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "synthetic"

# Two different people: finalize refuses a decision by whoever prepared the run.
PREPARER = "Ana Ruiz"
REVIEWER = "Ben Okafor"


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

    _, _, result = run_close(transactions, trial_balance, entities, thread_id="test-thread-1", prepared_by=PREPARER)

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

    graph, config, result = run_close(
        transactions, trial_balance, entities, thread_id="test-thread-2", prepared_by=PREPARER
    )
    assert "__interrupt__" in result

    pending = result["__interrupt__"][0].value["pending_review"]
    decisions = [
        {
            "reference": item["reference"],
            "reviewer": REVIEWER,
            "action": ReviewAction.APPROVE.value,
            "reviewer_note": "test approval",
        }
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

    graph, config, result = run_close(
        transactions, trial_balance, entities, thread_id="test-thread-3", prepared_by=PREPARER
    )
    pending = result["__interrupt__"][0].value["pending_review"]

    # reject the first one, approve the rest
    decisions = []
    for i, item in enumerate(pending):
        action = ReviewAction.REJECT.value if i == 0 else ReviewAction.APPROVE.value
        decisions.append(
            {"reference": item["reference"], "reviewer": REVIEWER, "action": action, "reviewer_note": "test"}
        )

    final = resume_close(graph, config, decisions)

    rejected_reference = pending[0]["reference"]
    eliminated_references = {e.reference for e in final["eliminations"]}
    assert rejected_reference not in eliminated_references


def test_approving_a_missing_counterparty_with_an_amount_books_it(monkeypatch):
    """A one-legged exception can only be booked if the reviewer supplies the amount."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)

    entities, trial_balance, transactions = _load_real_data()
    graph, config, result = run_close(
        transactions, trial_balance, entities, thread_id="test-thread-5", prepared_by=PREPARER
    )

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
                    "reviewer": REVIEWER,
                    "action": ReviewAction.APPROVE.value,
                    "reviewer_note": "confirmed with the affiliate",
                    "override_amount": "5000.00",
                }
            )
        else:
            decisions.append(
                {"reference": item["reference"], "reviewer": REVIEWER, "action": ReviewAction.REJECT.value}
            )

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
    graph, config, result = run_close(
        transactions, trial_balance, entities, thread_id="test-thread-neg-override", prepared_by=PREPARER
    )

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
                    "reviewer": REVIEWER,
                    "action": ReviewAction.EDIT.value,
                    "reviewer_note": "fat-fingered a negative",
                    "override_amount": "-5000.00",
                }
            )
        else:
            decisions.append(
                {"reference": item["reference"], "reviewer": REVIEWER, "action": ReviewAction.REJECT.value}
            )

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
    graph, config, result = run_close(
        transactions, trial_balance, entities, thread_id="test-thread-6", prepared_by=PREPARER
    )

    one_legged = {exc.reference for exc in result["exceptions"] if len(exc.legs) == 1}
    target = sorted(one_legged)[0]

    pending = result["__interrupt__"][0].value["pending_review"]
    decisions = [
        {"reference": item["reference"], "reviewer": REVIEWER, "action": ReviewAction.APPROVE.value} for item in pending
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
    _, _, result = run_close(transactions, trial_balance, entities, thread_id="test-serde", prepared_by=PREPARER)

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
    graph, config, result = run_close(
        transactions, trial_balance, entities, thread_id="test-thread-currency-1", prepared_by=PREPARER
    )
    assert "__interrupt__" in result

    currency_mismatches = {
        exc.reference for exc in result["exceptions"] if exc.exception_type == ExceptionType.CURRENCY_MISMATCH
    }
    assert currency_mismatches, "fixture dataset should contain a currency mismatch"

    pending = result["__interrupt__"][0].value["pending_review"]
    assert any(item["reference"] in currency_mismatches and item["net_amount"] is None for item in pending)

    decisions = [
        {
            "reference": item["reference"],
            "reviewer": REVIEWER,
            "action": ReviewAction.APPROVE.value,
            "reviewer_note": "test",
        }
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
    graph, config, result = run_close(
        transactions, trial_balance, entities, thread_id="test-thread-currency-2", prepared_by=PREPARER
    )

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
                    "reviewer": REVIEWER,
                    "action": ReviewAction.EDIT.value,
                    "reviewer_note": "converted at the confirmed month-end rate",
                    "override_amount": "50000.00",
                }
            )
        else:
            decisions.append(
                {"reference": item["reference"], "reviewer": REVIEWER, "action": ReviewAction.REJECT.value}
            )

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
    graph, config, result = run_close(
        transactions, trial_balance, entities, thread_id="test-thread-7", prepared_by=PREPARER
    )

    sign_mismatch_refs = {
        exc.reference for exc in result["exceptions"] if exc.exception_type == ExceptionType.SIGN_MISMATCH
    }
    assert sign_mismatch_refs, "the synthetic dataset should contain at least one sign mismatch"

    pending = result["__interrupt__"][0].value["pending_review"]
    pending_refs = {item["reference"] for item in pending}
    assert sign_mismatch_refs.issubset(pending_refs)

    decisions = [
        {
            "reference": item["reference"],
            "reviewer": REVIEWER,
            "action": ReviewAction.APPROVE.value,
            "reviewer_note": "test approval",
        }
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
    graph, config, result = run_close(
        transactions, trial_balance, entities, thread_id="test-thread-9", prepared_by=PREPARER
    )
    assert "__interrupt__" in result

    amount_mismatches = [exc for exc in result["exceptions"] if exc.exception_type == ExceptionType.AMOUNT_MISMATCH]
    target_exc = next((exc for exc in amount_mismatches if abs(exc.legs[0].amount) != abs(exc.legs[1].amount)), None)
    assert target_exc is not None, "fixture dataset should contain an amount mismatch with a genuine residual"
    payable_leg = next(leg for leg in target_exc.legs if leg.amount < 0)

    pending = result["__interrupt__"][0].value["pending_review"]
    decisions = [
        {
            "reference": item["reference"],
            "reviewer": REVIEWER,
            "action": ReviewAction.APPROVE.value,
            "reviewer_note": "test",
        }
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
    _, _, result = run_close(transactions, trial_balance, entities, thread_id="test-thread-4", prepared_by=PREPARER)

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
    graph, config, result = run_close(
        transactions, trial_balance, entities, thread_id="test-thread-tolerance", prepared_by=PREPARER
    )
    off_by_a_little = [(a, b) for a, b in result["clean_pairs"] if a.amount + b.amount != 0]
    assert off_by_a_little, "fixture dataset should contain a clean pair that nets to within tolerance, not zero"
    leg_a, leg_b = off_by_a_little[0]
    payable = leg_a if leg_a.amount < 0 else leg_b

    pending = result["__interrupt__"][0].value["pending_review"]
    final = resume_close(
        graph, config, [{"reference": item["reference"], "reviewer": REVIEWER, "action": "reject"} for item in pending]
    )

    assert any(
        leg_a.reference in entry and "within tolerance" in entry and payable.entity_code in entry
        for entry in final["audit_trail"]
    )


def _pending(result) -> list[dict]:
    return result["__interrupt__"][0].value["pending_review"]


def _offline(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)


def test_the_audit_trail_opens_with_the_preparer_and_the_policy(monkeypatch):
    _offline(monkeypatch)
    entities, trial_balance, transactions = _load_real_data()

    _, _, result = run_close(transactions, trial_balance, entities, thread_id="test-trail", prepared_by=" Ana  Ruiz ")

    assert result["audit_trail"][:2] == [
        "prepared by Ana Ruiz",
        "policy (built-in defaults): materiality threshold 5000.00; matching tolerance the larger of "
        "1.00 and 0.01% of the larger leg; tie-out tolerance 1.00",
    ]


def test_a_run_needs_someone_to_have_prepared_it(monkeypatch):
    _offline(monkeypatch)
    entities, trial_balance, transactions = _load_real_data()

    with pytest.raises(ValueError, match="prepared_by is required"):
        run_close(transactions, trial_balance, entities, thread_id="test-no-preparer", prepared_by="  ")


def test_a_decision_needs_someone_to_have_made_it(monkeypatch):
    _offline(monkeypatch)
    entities, trial_balance, transactions = _load_real_data()
    graph, config, result = run_close(
        transactions, trial_balance, entities, thread_id="test-no-reviewer", prepared_by=PREPARER
    )

    with pytest.raises(ValidationError, match="reviewer"):
        resume_close(graph, config, [{"reference": item["reference"], "action": "reject"} for item in _pending(result)])


def test_an_approval_names_who_gave_it(monkeypatch):
    """The README says the audit trail shows what was eliminated and approved
    by whom. Until decisions carried a reviewer, it showed only that someone
    had."""
    _offline(monkeypatch)
    entities, trial_balance, transactions = _load_real_data()
    graph, config, result = run_close(
        transactions, trial_balance, entities, thread_id="test-named-approval", prepared_by=PREPARER
    )
    target = "RECHARGE-2025-1000"
    decisions = [
        {
            "reference": item["reference"],
            "reviewer": REVIEWER,
            "action": "approve" if item["reference"] == target else "reject",
        }
        for item in _pending(result)
    ]

    final = resume_close(graph, config, decisions)

    [approved] = [e for e in final["eliminations"] if e.reference == target]
    assert f"human-approved (approve) by {REVIEWER}" in approved.narrative
    assert f"received {len(decisions)} human review decisions from {REVIEWER}" in final["audit_trail"]


def test_the_preparer_cannot_approve_what_the_run_books(monkeypatch):
    """Segregation of duties, enforced where the booking happens rather than
    only in the dashboard: an approval from the preparer, however the name is
    capitalised or spaced, books nothing and says why."""
    _offline(monkeypatch)
    entities, trial_balance, transactions = _load_real_data()
    graph, config, result = run_close(
        transactions, trial_balance, entities, thread_id="test-segregation", prepared_by=PREPARER
    )
    target = "RECHARGE-2025-1000"
    decisions = [
        {
            "reference": item["reference"],
            "reviewer": "  ana   RUIZ " if item["reference"] == target else REVIEWER,
            "action": "approve" if item["reference"] == target else "reject",
        }
        for item in _pending(result)
    ]

    final = resume_close(graph, config, decisions)

    assert target not in {e.reference for e in final["eliminations"]}
    assert any(
        entry.startswith(f"{target}: approve by ana   RUIZ, who prepared this run; not booked")
        for entry in final["audit_trail"]
    )


def test_the_example_policy_file_is_the_default_close(monkeypatch):
    """examples/policy.toml spells out the defaults, so running with it has to
    give exactly the close that running without a policy gives."""
    _offline(monkeypatch)
    entities, trial_balance, transactions = _load_real_data()
    example = ClosePolicy.from_toml(Path(__file__).resolve().parent.parent / "examples" / "policy.toml")

    _, _, without = run_close(transactions, trial_balance, entities, thread_id="test-default-1", prepared_by=PREPARER)
    _, _, with_example = run_close(
        transactions, trial_balance, entities, thread_id="test-default-2", prepared_by=PREPARER, policy=example
    )

    def outcome(result):
        return (
            [(a.reference, b.reference) for a, b in result["clean_pairs"]],
            [(e.reference, e.exception_type, e.materiality) for e in result["exceptions"]],
            [item["reference"] for item in _pending(result)],
            [(v.entity_code, v.within_tolerance) for v in result["tb_variances"]],
        )

    assert outcome(without) == outcome(with_example)
    assert (len(without["clean_pairs"]), len(without["exceptions"]), len(_pending(without))) == (11, 18, 16)


def test_a_higher_materiality_threshold_sends_less_to_a_person(monkeypatch):
    """LOAN-INT-2025-1022 is a timing gap on a balance of 142,472.27. Above the
    default threshold it goes to a reviewer; under a 200,000 one it is
    auto-resolved like any immaterial timing gap."""
    _offline(monkeypatch)
    entities, trial_balance, transactions = _load_real_data()
    target = "LOAN-INT-2025-1022"

    _, _, default = run_close(transactions, trial_balance, entities, thread_id="test-mat-1", prepared_by=PREPARER)
    _, _, loose = run_close(
        transactions,
        trial_balance,
        entities,
        thread_id="test-mat-2",
        prepared_by=PREPARER,
        policy=ClosePolicy(materiality_threshold=Decimal("200000")),
    )

    assert target in {item["reference"] for item in _pending(default)}
    assert target not in {item["reference"] for item in _pending(loose)}
    assert len(_pending(loose)) == len(_pending(default)) - 1


def test_the_tolerance_floor_moves_the_tie_out_and_the_matching_together(monkeypatch):
    """US01's control account is off by 2,536.01 and LOAN-INT-2025-1019's legs
    by 1,156.76. A floor of 3,000 absorbs both: the tie-out uses the same floor
    as matching, by design."""
    _offline(monkeypatch)
    entities, trial_balance, transactions = _load_real_data()

    _, _, result = run_close(
        transactions,
        trial_balance,
        entities,
        thread_id="test-floor",
        prepared_by=PREPARER,
        policy=ClosePolicy(amount_tolerance_floor=Decimal("3000")),
    )

    assert all(v.within_tolerance for v in result["tb_variances"])
    assert "LOAN-INT-2025-1019" in {a.reference for a, _ in result["clean_pairs"]}
    assert "LOAN-INT-2025-1019" not in {e.reference for e in result["exceptions"]}


def _close_two_entities(monkeypatch, legs: list[tuple[str, str, str, str]], thread: str, decide=None):
    """A close of two made-up entities on the given legs, resumed with decide(item) if it pauses."""
    from datetime import date

    from intercompany_close_agent.models.entity import Entity
    from intercompany_close_agent.models.ledger import ICTransaction

    _offline(monkeypatch)
    entities = [Entity(code=code, name=code, region="US", local_currency="USD") for code in ("A", "B")]
    transactions = [
        ICTransaction(
            entity_code=entity,
            counterparty_code=counterparty,
            reference=reference,
            amount=Decimal(amount),
            transaction_date=date(2026, 9, 30),
        )
        for entity, counterparty, reference, amount in legs
    ]
    graph, config, result = run_close(transactions, [], entities, thread_id=thread, prepared_by=PREPARER)
    if "__interrupt__" in result and decide:
        result = resume_close(graph, config, [decide(item) for item in _pending(result)])
    return result


def _approve(item: dict) -> dict:
    return {"reference": item["reference"], "action": "approve", "reviewer": REVIEWER}


@pytest.mark.parametrize("zero_first", [True, False])
def test_a_clean_pair_with_a_zero_leg_closes_and_reports_what_it_leaves(monkeypatch, zero_first: bool):
    """One leg at zero and the other inside the tolerance is a clean pair with
    nothing to eliminate on the receivable side. It used to crash the whole
    close when the zero came second, and leave the payable unreported when it
    came first."""
    legs = [("A", "B", "Z", "0.00"), ("B", "A", "Z", "-0.50")]
    result = _close_two_entities(monkeypatch, legs if zero_first else legs[::-1], f"zero-{zero_first}")

    assert result["eliminations"] == []
    assert any("Z: matched within tolerance" in entry and "B's control account keeps -0.50" in entry
               for entry in result["audit_trail"])


def test_an_approved_mismatch_with_a_zero_receivable_is_not_booked_at_zero(monkeypatch):
    legs = [("A", "B", "Z", "0.00"), ("B", "A", "Z", "-6000.00")]
    result = _close_two_entities(monkeypatch, legs, "zero-approve", _approve)

    assert result["eliminations"] == []
    assert any("Z: approved but not booked" in entry and "receivable side is zero" in entry
               for entry in result["audit_trail"])


def test_an_approved_self_dealing_entry_against_one_entity_is_not_booked(monkeypatch):
    """Both legs booked by A against A: approving it would debit and credit A,
    the entry docs/human-in-the-loop.md names as this exception's danger."""
    legs = [("A", "A", "S", "500.00"), ("A", "A", "S", "-500.00")]
    result = _close_two_entities(monkeypatch, legs, "self", _approve)

    assert result["eliminations"] == []
    assert any("S: approved but not booked" in entry and "debit and credit A itself" in entry
               for entry in result["audit_trail"])
