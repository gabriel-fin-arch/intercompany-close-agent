"""The README's "Results on the sample data" block has to be what a run produces.

It reruns the close offline on the committed dataset and compares. A failure
means either the code changed what the sample run finds, or someone edited the
figures by hand; regenerate with
`uv run python -m intercompany_close_agent.sample_results --write`.
"""

import difflib

from intercompany_close_agent.sample_results import README, readme_block, render, summarize


def test_readme_sample_results_match_a_fresh_offline_run(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)

    expected = render(summarize())
    actual = readme_block(README.read_text(encoding="utf-8"))

    diff = "\n".join(
        difflib.unified_diff(actual.splitlines(), expected.splitlines(), "README", "fresh run", lineterm="")
    )
    assert actual == expected, f"README's sample results are out of date:\n{diff}"


def test_the_block_reports_the_planted_tie_out_break():
    run = summarize()
    assert run.entities_not_tying == 1
    assert run.for_review + run.auto_resolvable == run.exceptions
