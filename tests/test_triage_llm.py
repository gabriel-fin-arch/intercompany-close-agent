"""Tests for the parts of the LLM triage module that don't require a live call."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from intercompany_close_agent.models.entity import Entity
from intercompany_close_agent.models.exception import ExceptionType, ICException, Materiality
from intercompany_close_agent.models.ledger import ICTransaction
from intercompany_close_agent.triage.llm import (
    DEFAULT_MODEL,
    MAX_TOKENS,
    _build_chain,
    _describe,
    triage_exception,
    triage_measured,
)
from intercompany_close_agent.triage.models import TriageClassification, TriageJudgment


def _exc() -> ICException:
    legs = [
        ICTransaction(
            entity_code="US01",
            counterparty_code="DE01",
            reference="REF-1",
            amount=Decimal("1000.00"),
            transaction_date=date(2025, 9, 30),
        ),
        ICTransaction(
            entity_code="DE01",
            counterparty_code="US01",
            reference="REF-1",
            amount=Decimal("-950.00"),
            transaction_date=date(2025, 9, 30),
        ),
    ]
    return ICException(
        reference="REF-1",
        exception_type=ExceptionType.AMOUNT_MISMATCH,
        legs=legs,
        net_amount=Decimal("50.00"),
        materiality=Materiality.LOW,
        detected_reason="test fixture",
    )


def test_describe_includes_the_key_facts():
    description = _describe(_exc())
    assert "REF-1" in description
    assert "amount_mismatch" in description
    assert "US01" in description
    assert "DE01" in description


def test_describe_flags_a_manually_loaded_entity():
    entities = {
        "US01": Entity(code="US01", name="US", region="US", local_currency="USD", interfaced=True),
        "DE01": Entity(code="DE01", name="DE", region="EMEA", local_currency="EUR", interfaced=False),
    }
    description = _describe(_exc(), entities)
    assert "manually_loaded_entities: DE01" in description


def _chat_models(chain) -> list[ChatAnthropic]:
    bound = [getattr(step, "bound", step) for step in chain.steps]
    return [model for model in bound if isinstance(model, ChatAnthropic)]


def test_build_chain_uses_the_pinned_model_unless_one_is_named(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "not-a-real-key")
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    pinned = _chat_models(_build_chain())

    monkeypatch.setenv("ANTHROPIC_MODEL", "some-model")
    named = _chat_models(_build_chain())

    assert [model.model for model in pinned] == [DEFAULT_MODEL]
    assert [model.model for model in named] == ["some-model"]


def test_build_chain_caps_the_answer_length(monkeypatch):
    """Left alone, langchain-anthropic asks for the model's maximum output,
    128,000 tokens on Opus 5.5, and a cost estimate has no useful ceiling."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "not-a-real-key")
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)

    assert [model.max_tokens for model in _chat_models(_build_chain())] == [MAX_TOKENS]


def test_build_chain_constructs_a_runnable_chain(monkeypatch):
    """The prompt/model/parser wiring is built without ever calling the API."""
    monkeypatch.setenv("ANTHROPIC_MODEL", "some-model")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "not-a-real-key")

    chain = _build_chain()

    assert hasattr(chain, "invoke")


def test_build_chain_asks_for_the_apis_own_structured_output(monkeypatch):
    """Opus 5.5 doesn't accept a forced tool call, so the default
    function_calling method leaves the tool optional and fails whenever the
    model answers without it. json_schema constrains the answer itself."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "not-a-real-key")
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)

    bindings = [step for step in _build_chain().steps if hasattr(step, "kwargs")]

    assert [binding.kwargs["output_config"]["format"]["type"] for binding in bindings] == ["json_schema"]
    assert all("tools" not in binding.kwargs for binding in bindings)


def test_a_measured_call_reads_the_answer_after_the_thinking_and_the_usage(monkeypatch):
    """The real chain, with the request to the API replaced: Opus 5.5 thinks
    before it answers, so the JSON comes in a text block after a thinking one."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "not-a-real-key")
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    answer = AIMessage(
        content=[
            {"type": "thinking", "thinking": "", "signature": "sig"},
            {
                "type": "text",
                "text": '{"classification": "needs_human_judgment", "confidence": 0.8, "rationale": "material"}',
            },
        ],
        usage_metadata={
            "input_tokens": 900,
            "output_tokens": 300,
            "total_tokens": 1200,
            "input_token_details": {"cache_read": 0, "cache_creation": 0},
        },
    )

    def generate(self, messages, stop=None, run_manager=None, **kwargs):
        assert kwargs["output_config"]["format"]["type"] == "json_schema"
        return ChatResult(generations=[ChatGeneration(message=answer)])

    monkeypatch.setattr(ChatAnthropic, "_generate", generate)

    result, call = triage_measured(_exc())

    assert (result.reference, result.classification) == ("REF-1", TriageClassification.NEEDS_HUMAN_JUDGMENT)
    assert (call.model, call.input_tokens, call.output_tokens) == (DEFAULT_MODEL, 900, 300)
    # 900 input tokens at USD 4 and 300 output at USD 20, per million
    assert str(call.cost_usd) == "0.009600"


def test_build_chain_leaves_temperature_at_the_default(monkeypatch):
    """Claude 4.7 and later return a 400 for any non-default temperature, so
    setting one would break the live path on every current model."""
    monkeypatch.setenv("ANTHROPIC_MODEL", "some-model")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "not-a-real-key")

    chat_models = _chat_models(_build_chain())
    assert chat_models, "no ChatAnthropic in the chain"
    assert all(model.temperature is None for model in chat_models)


def test_triage_exception_maps_the_model_judgment_onto_the_reference(monkeypatch):
    """Exercises the real function body with a stubbed chain, so the LLM path
    is covered end to end without a network call."""
    captured = {}

    class FakeChain:
        def invoke(self, payload):
            captured["payload"] = payload
            return TriageJudgment(
                classification=TriageClassification.NEEDS_HUMAN_JUDGMENT,
                confidence=0.42,
                rationale="model says look at this one",
            )

    monkeypatch.setattr("intercompany_close_agent.triage.llm._build_chain", lambda: FakeChain())

    result = triage_exception(_exc())

    assert result.reference == "REF-1"  # set by our code, not echoed by the model
    assert result.confidence == 0.42
    assert result.rationale == "model says look at this one"
    assert "amount_mismatch" in captured["payload"]["exception_details"]


def test_triage_exception_accepts_a_plain_dict_from_the_model(monkeypatch):
    """Structured output can come back as a dict rather than a model instance."""

    class DictChain:
        def invoke(self, payload):
            return {
                "classification": "auto_resolvable",
                "confidence": 0.9,
                "rationale": "immaterial",
            }

    monkeypatch.setattr("intercompany_close_agent.triage.llm._build_chain", lambda: DictChain())

    result = triage_exception(_exc())

    assert result.classification == TriageClassification.AUTO_RESOLVABLE
    assert result.reference == "REF-1"
