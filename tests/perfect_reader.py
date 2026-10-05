"""A stand-in model for tests: it copies exactly what is printed, scan errors included.

It answers from the answer key, so it measures what the checks allow, not what a model can read.
"""

import json
import re
from pathlib import Path

CONFUSIONS = {
    "0": "O",
    "O": "0",
    "1": "l",
    "l": "1",
    "I": "1",
    "5": "S",
    "S": "5",
    "8": "B",
    "B": "8",
    "2": "Z",
    "Z": "2",
}


def _pattern(printed: str) -> str:
    parts = []
    for ch in printed:
        if ch == " ":
            parts.append(r"[ \u00a0\u202f]+")
        elif ch in CONFUSIONS:
            parts.append("[" + re.escape(ch + CONFUSIONS[ch]) + "]")
        else:
            parts.append(re.escape(ch))
    return "".join(parts)


class PerfectReader:
    def __init__(self, data_dir: Path, split: str):
        self.by_text = {}
        for line in (data_dir / split / "labels.jsonl").read_text(encoding="utf-8").splitlines():
            label = json.loads(line)
            text = (data_dir / split / label["file"]).read_text(encoding="utf-8")
            self.by_text[text] = label
        self.calls = 0

    def __call__(self, request):
        self.calls += 1
        user = request["messages"][-1]["content"]
        text = user.split("<<<\n", 1)[1].rsplit("\n>>>", 1)[0]
        label = self.by_text[text]
        answer = {}
        for field, printed in label["printed"].items():
            match = re.search(_pattern(printed), text)
            quote = match.group(0) if match else None
            truth = label["fields"][field]
            if field == "amount":
                answer[field] = {"value": truth["value"], "currency": truth["currency"], "quote": quote}
            elif field in ("document_date", "due_date"):
                answer[field] = {"value": truth, "quote": quote}
            else:
                answer[field] = {
                    "value": re.sub(r"\s+", "", quote) if field in ("iban", "bic") and quote else quote,
                    "quote": quote,
                }
        return {
            "content": json.dumps(answer, ensure_ascii=False),
            "tool_calls": [],
            "prompt_tokens": 1500,
            "output_tokens": 220,
        }
