import json

from test_checks import GOOD, REFS, TEXT

from finance_document_agent.extract import SCHEMA, build_messages
from finance_document_agent.llm import LLM
from finance_document_agent.pipeline import process
from finance_document_agent.rules import find_candidates
from finance_document_agent.schema import validate


class ScriptedModel:
    def __init__(self, *answers):
        self.answers = list(answers)
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        return {"content": self.answers.pop(0), "tool_calls": [], "prompt_tokens": 900, "output_tokens": 160}


def llm_with(tmp_path, *answers):
    model = ScriptedModel(*answers)
    return LLM(mode="live", runs_root=tmp_path, num_ctx=8192, transport=model), model


def test_the_schema_accepts_a_complete_answer():
    assert validate(GOOD, SCHEMA) is GOOD


def test_the_prompt_carries_the_document_and_the_rule_findings():
    messages = build_messages(TEXT, find_candidates(TEXT))
    assert messages[0]["role"] == "system"
    assert "Ostrander Freight Group SA" in messages[0]["content"]
    assert TEXT in messages[1]["content"]
    assert "IBAN-like strings: DE89370400440532013000" in messages[1]["content"]


def test_a_provable_document_goes_straight_through(tmp_path):
    llm, model = llm_with(tmp_path, json.dumps(GOOD))
    result = process("doc-1", TEXT, llm, REFS)
    assert result.straight_through
    assert model.requests[0]["format"] == SCHEMA


def test_an_unreadable_answer_sends_every_field_to_a_person(tmp_path):
    llm, _ = llm_with(tmp_path, "not json", "still not json")
    result = process("doc-2", TEXT, llm, REFS)
    assert not result.straight_through
    assert all(field.status == "review" for field in result.fields.values())
    assert result.error is not None
