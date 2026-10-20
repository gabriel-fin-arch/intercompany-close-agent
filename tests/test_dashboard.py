"""The reviewer dashboard, run headless with Streamlit's own test harness.

The graph tests cover what each decision books. These cover what the page
sends as a decision, which is where an item nobody had looked at once became
an approval, and who the page says prepared and reviewed the close.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "app" / "streamlit_app.py"
DATA_DIR = ROOT / "data" / "synthetic"
EXAMPLE_POLICY = ROOT / "examples" / "policy.toml"

PREPARER = "Ana Ruiz"
REVIEWER = "Ben Okafor"


def _field(elements, label: str):
    return next(element for element in elements if element.label == label)


def _start(monkeypatch, prepared_by: str = PREPARER, policy: str = "") -> AppTest:
    # Empty rather than unset: the app calls load_dotenv(), which leaves a
    # variable that is already set alone, so a local .env can't put the test
    # on the live model.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("ANTHROPIC_MODEL", "")

    app = AppTest.from_file(str(APP), default_timeout=60)
    app.run()
    _field(app.sidebar.text_input, "Synthetic data directory").set_value(str(DATA_DIR))
    _field(app.sidebar.text_input, "Prepared by").set_value(prepared_by)
    _field(app.sidebar.text_input, "Policy file").set_value(policy)
    _field(app.sidebar.button, "Run close pipeline").click().run()
    return app


@pytest.fixture
def dashboard(monkeypatch) -> AppTest:
    """The dashboard with the sample close run and paused at the worklist."""
    app = _start(monkeypatch)

    assert "__interrupt__" in app.session_state["result"]
    return app


def _decisions(app: AppTest) -> dict:
    return {radio.key.removeprefix("action_"): radio for radio in app.radio if radio.label == "Decision"}


def _submit(app: AppTest, reviewer: str = REVIEWER) -> None:
    _field(app.text_input, "Reviewer").set_value(reviewer)
    _field(app.button, "Submit decisions").click().run()


def _reject_all(app: AppTest) -> None:
    for radio in _decisions(app).values():
        radio.set_value("reject")


def test_every_item_starts_with_no_decision(dashboard: AppTest):
    pending = dashboard.session_state["result"]["__interrupt__"][0].value["pending_review"]
    decisions = _decisions(dashboard)

    assert len(decisions) == len(pending) > 0
    assert all(radio.value is None for radio in decisions.values())


def test_an_untouched_worklist_is_not_submitted(dashboard: AppTest):
    """Every item used to start on approve, so one click on the sample data
    booked four eliminations as human-approved, three of them types that are
    never auto-resolved, with an audit trail that read as if someone had
    decided."""
    count = len(_decisions(dashboard))

    _submit(dashboard)

    assert "final" not in dashboard.session_state
    [error] = dashboard.error
    assert f"No decision yet for {count} item(s)" in error.value
    assert "RECHARGE-2025-1000" in error.value


def test_one_undecided_item_holds_back_the_rest(dashboard: AppTest):
    decisions = _decisions(dashboard)
    *decided, last = decisions
    for reference in decided:
        decisions[reference].set_value("reject")

    _submit(dashboard)

    assert "final" not in dashboard.session_state
    [error] = dashboard.error
    assert f"No decision yet for 1 item(s): {last}." in error.value


def test_a_decision_the_reviewer_picked_is_booked_in_their_name(dashboard: AppTest):
    for reference, radio in _decisions(dashboard).items():
        radio.set_value("approve" if reference == "RECHARGE-2025-1000" else "reject")

    _submit(dashboard)

    final = dashboard.session_state["final"]
    approved = [e for e in final["eliminations"] if "human-approved" in e.narrative]
    assert [e.reference for e in approved] == ["RECHARGE-2025-1000"]
    assert f"by {REVIEWER}" in approved[0].narrative
    assert [s.value for s in dashboard.success] == ["Close finalized."]


def test_the_close_does_not_run_until_someone_says_who_prepared_it(monkeypatch):
    app = _start(monkeypatch, prepared_by="  ")

    assert "result" not in app.session_state
    [error] = app.error
    assert "Prepared by" in error.value


def test_the_worklist_is_not_submitted_without_a_reviewer(dashboard: AppTest):
    _reject_all(dashboard)

    _submit(dashboard, reviewer=" ")

    assert "final" not in dashboard.session_state
    [error] = dashboard.error
    assert "Enter who is reviewing" in error.value


def test_the_preparer_cannot_review_the_worklist(dashboard: AppTest):
    """Finalize refuses a preparer's approval on its own; the page says so
    before anything is submitted, however the name is typed."""
    _reject_all(dashboard)

    _submit(dashboard, reviewer="ana  RUIZ")

    assert "final" not in dashboard.session_state
    [error] = dashboard.error
    assert f"{PREPARER} prepared this run" in error.value


def test_the_policy_file_field_sets_the_policy_and_the_trail_says_which(monkeypatch):
    app = _start(monkeypatch, policy=str(EXAMPLE_POLICY))

    trail = app.session_state["result"]["audit_trail"]
    assert trail[0] == f"prepared by {PREPARER}"
    assert trail[1].startswith(f"policy ({EXAMPLE_POLICY}): materiality threshold 5000.00;")


def test_a_policy_file_the_close_cannot_use_stops_the_run(monkeypatch, tmp_path: Path):
    bad = tmp_path / "policy.toml"
    bad.write_text("materiality_threshold = -5\n", encoding="utf-8")

    app = _start(monkeypatch, policy=str(bad))

    assert "result" not in app.session_state
    [error] = app.error
    assert error.value.startswith("Cannot run the close:")
    assert "materiality_threshold" in error.value
