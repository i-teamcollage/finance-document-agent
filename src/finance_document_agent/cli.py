"""Command line.

python -m finance_document_agent demo              three examples from the stored run
python -m finance_document_agent accept            the acceptance test on the test split
python -m finance_document_agent accept --record   run it live on Ollama and store the run
python -m finance_document_agent run FILE          read one document live
python -m finance_document_agent readme            refresh the results table in README.md
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import sys
from datetime import date
from pathlib import Path

from .acceptance import (
    evaluate,
    load_criteria,
    report_dict,
    results_block,
    terminal_table,
    update_readme,
    write_reports,
)
from .banking import BankDirectory
from .checks import References
from .llm import DEFAULT_MODEL, LLM, ModelUnavailable, ReplayMiss, machine_description, ollama_info, run_dir_name
from .metrics import score
from .pipeline import DocumentResult, process
from .vendors import VendorMaster

ROOT = Path(__file__).resolve().parents[2]
TITLE = "Finance document agent: acceptance test"
NUM_CTX = 8192
LANGUAGES = {"en": "English", "fr": "French", "de": "German"}


class Workspace:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.data = self.root / "data"
        self.reports = self.root / "reports"
        self.readme = self.root / "README.md"
        self.acceptance = self.root / "acceptance.toml"

    def runs_root(self, split: str) -> Path:
        return self.root / "runs" if split == "test" else self.root / "runs" / split

    def out(self, split: str) -> Path:
        return self.root / "out" / split

    def labels(self, split: str) -> list[dict]:
        lines = (self.data / split / "labels.jsonl").read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines if line.strip()]

    def text(self, split: str, label: dict) -> str:
        return (self.data / split / label["file"]).read_text(encoding="utf-8")

    def references(self) -> References:
        return References(
            BankDirectory.from_csv(self.data / "reference" / "banks.csv"),
            VendorMaster.from_csv(self.data / "reference" / "vendors.csv"),
        )


def _mode(args: argparse.Namespace) -> str:
    if getattr(args, "record", False):
        return "record"
    if getattr(args, "live", False):
        return "live"
    return os.environ.get("AGENT_MODE", "replay")


def _run_split(ws: Workspace, split: str, llm: LLM) -> tuple[list[dict], dict[str, DocumentResult]]:
    refs, labels, results = ws.references(), ws.labels(split), {}
    for number, label in enumerate(labels, start=1):
        result = process(label["id"], ws.text(split, label), llm, refs)
        results[label["id"]] = result
        if llm.mode != "replay":
            outcome = "straight through" if result.straight_through else f"{result.review_count} field(s) to review"
            print(f"  [{number:>3}/{len(labels)}] {label['id']}  {outcome:<24} {result.seconds:6.1f} s", flush=True)
    return labels, results


def _field_json(field) -> dict:
    return {
        "value": field.value,
        "status": field.status,
        "reasons": field.reasons,
        "quote": field.quote,
        "suggestion": field.suggestion,
    }


def _write_outputs(ws: Workspace, split: str, results: dict[str, DocumentResult]) -> None:
    out = ws.out(split)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for doc_id, result in results.items():
        record = {
            "doc_id": doc_id,
            "straight_through": result.straight_through,
            "fields": {name: _field_json(field) for name, field in result.fields.items()},
        }
        (out / f"{doc_id}.json").write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        for name, field in result.fields.items():
            if field.status == "review":
                value = json.dumps(field.value, ensure_ascii=False) if isinstance(field.value, dict) else field.value
                rows.append([doc_id, name, value or "", "; ".join(field.reasons), field.suggestion or ""])
    with open(out / "review_queue.csv", "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["doc_id", "field", "value", "reason", "suggestion"])
        writer.writerows(rows)


def _run_info_path(ws: Workspace, split: str, model: str) -> Path:
    return ws.runs_root(split) / run_dir_name(model) / "run.json"


def _write_run_info(ws: Workspace, split: str, llm: LLM, results: dict[str, DocumentResult], local_model: bool) -> None:
    seconds = [result.seconds for result in results.values()]
    info = {
        "recorded_at": date.today().isoformat(),
        "model": llm.model,
        **(ollama_info(llm.model) if local_model else {}),
        "machine": machine_description(),
        "split": split,
        "items": len(results),
        "median_seconds_per_item": round(statistics.median(seconds), 2) if seconds else None,
        "item_seconds": {doc_id: result.seconds for doc_id, result in results.items()},
    }
    path = _run_info_path(ws, split, llm.model)
    path.write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")


def cmd_accept(args: argparse.Namespace, ws: Workspace, transport=None) -> int:
    mode = _mode(args)
    llm = LLM(model=args.model, mode=mode, runs_root=ws.runs_root(args.split), num_ctx=NUM_CTX, transport=transport)
    if mode == "record":
        llm.start_recording()
    print(f"Acceptance test, {args.split} split, model {args.model}, mode {mode}")
    try:
        labels, results = _run_split(ws, args.split, llm)
    except (ReplayMiss, ModelUnavailable) as error:
        print(f"\n{error}", file=sys.stderr)
        return 2
    _write_outputs(ws, args.split, results)
    if mode == "record":
        _write_run_info(ws, args.split, llm, results, local_model=transport is None)
    info_path = _run_info_path(ws, args.split, args.model)
    info = json.loads(info_path.read_text(encoding="utf-8")) if mode != "live" and info_path.exists() else {}

    measures, details = score(labels, results)
    outcomes = evaluate(load_criteria(ws.acceptance), measures)
    seconds = [result.seconds for result in results.values() if result.seconds]
    meta = {
        "title": TITLE,
        "split": args.split,
        "items": len(labels),
        "model": args.model,
        "machine": info.get("machine") or machine_description(),
        "recorded_at": info.get("recorded_at"),
        "ollama_version": info.get("ollama_version"),
        "model_digest": info.get("model_digest"),
        "median_seconds_per_item": round(statistics.median(seconds), 1) if seconds else None,
    }
    report = report_dict(outcomes, meta)
    write_reports(report, ws.reports if args.split == "test" else ws.reports / args.split, details)
    print()
    print(terminal_table(outcomes))
    print(f"\n{'PASSED' if report['passed'] else 'FAILED'}: details in {ws.reports}/acceptance.md")
    return 0 if report["passed"] else 1


def _show(value) -> str:
    if isinstance(value, dict):
        return f"{value.get('value')} {value.get('currency') or ''}".strip()
    return "-" if value in (None, "") else str(value)


def card(title: str, result: DocumentResult) -> str:
    lines = [title]
    for name, field in result.fields.items():
        status = "accepted" if field.status == "auto" else f"to review: {field.reasons[0]}"
        lines.append(f"  {name:<16} {_show(field.value):<34} {status}")
    count = result.review_count
    verdict = (
        "paid without anyone touching it"
        if result.straight_through
        else f"goes to a reviewer ({count} field{'' if count == 1 else 's'})"
    )
    lines.append(f"  -> {verdict}")
    return "\n".join(lines)


def _title(label: dict) -> str:
    kind = label["type"].replace("_", " ")
    return f"{label['id']}  {kind} in {LANGUAGES[label['language']]}, {'scanned' if label['scan'] else 'clean'}"


def cmd_demo(args: argparse.Namespace, ws: Workspace, transport=None) -> int:
    llm = LLM(model=args.model, mode=_mode(args), runs_root=ws.runs_root("test"), num_ctx=NUM_CTX, transport=transport)
    try:
        labels, results = _run_split(ws, "test", llm)
    except (ReplayMiss, ModelUnavailable) as error:
        print(error, file=sys.stderr)
        return 2
    picks = [
        next((label for label in labels if results[label["id"]].straight_through), None),
        next((label for label in labels if any(f.suggestion for f in results[label["id"]].fields.values())), None),
        next((label for label in labels if label["trap"]), None),
    ]
    for label in filter(None, picks):
        print(card(_title(label), results[label["id"]]))
        if label["trap"]:
            print(f"  (this is a trap document: {label['trap'].replace('_', ' ')})")
        print()
    return 0


def cmd_run(args: argparse.Namespace, ws: Workspace, transport=None) -> int:
    mode = "replay" if args.replay else "live"
    llm = LLM(model=args.model, mode=mode, runs_root=ws.runs_root("test"), num_ctx=NUM_CTX, transport=transport)
    path = Path(args.file)
    try:
        result = process(path.stem, path.read_text(encoding="utf-8"), llm, ws.references())
    except (ReplayMiss, ModelUnavailable) as error:
        print(error, file=sys.stderr)
        return 2
    print(card(path.name, result))
    return 0


def cmd_readme(args: argparse.Namespace, ws: Workspace, transport=None) -> int:
    report = json.loads((ws.reports / "acceptance.json").read_text(encoding="utf-8"))
    changed = update_readme(ws.readme, results_block(report), check=args.check)
    if args.check:
        print("README results are out of date: run `make readme`" if changed else "README results are up to date")
        return 1 if changed else 0
    print("README results updated" if changed else "README results already up to date")
    return 0


def main(argv: list[str] | None = None, *, root: Path = ROOT, transport=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m finance_document_agent", description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    model = os.environ.get("AGENT_MODEL", DEFAULT_MODEL)
    for name in ("demo", "accept"):
        command = commands.add_parser(name)
        command.add_argument("--live", action="store_true", help="ask the model instead of the stored run")
        command.add_argument("--record", action="store_true", help="ask the model and store the run")
        command.add_argument("--model", default=model)
        if name == "accept":
            command.add_argument("--split", default="test", choices=["test", "practice"])
    run = commands.add_parser("run")
    run.add_argument("file")
    run.add_argument("--replay", action="store_true")
    run.add_argument("--model", default=model)
    readme = commands.add_parser("readme")
    readme.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    handler = {"demo": cmd_demo, "accept": cmd_accept, "run": cmd_run, "readme": cmd_readme}[args.command]
    return handler(args, Workspace(root), transport)
