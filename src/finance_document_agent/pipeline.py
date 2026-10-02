"""One document from text to decision: rules, one model call, then the checks."""

from __future__ import annotations

from dataclasses import dataclass

from .checks import FieldResult, References, check_document, unreadable
from .extract import extract
from .llm import LLM, InvalidOutput
from .rules import find_candidates


@dataclass
class DocumentResult:
    doc_id: str
    fields: dict[str, FieldResult]
    straight_through: bool
    seconds: float
    error: str | None = None

    @property
    def review_count(self) -> int:
        return sum(field.status == "review" for field in self.fields.values())


def process(doc_id: str, text: str, llm: LLM, refs: References) -> DocumentResult:
    candidates = find_candidates(text)
    try:
        reply = extract(llm, text, candidates, label=doc_id)
    except InvalidOutput as error:
        fields = unreadable("the model's answer could not be read")
        return DocumentResult(doc_id, fields, False, 0.0, str(error))
    fields = check_document(text, reply.data, refs)
    straight_through = all(field.status == "auto" for field in fields.values())
    return DocumentResult(doc_id, fields, straight_through, reply.seconds)
