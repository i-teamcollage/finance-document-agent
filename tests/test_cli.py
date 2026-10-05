import json
import shutil
from pathlib import Path

from perfect_reader import PerfectReader

from finance_document_agent.cli import main

REPO = Path(__file__).resolve().parents[1]
README = "# Sample\n\n<!-- results:start -->\nnot yet measured\n<!-- results:end -->\n"


def workspace(tmp_path: Path) -> Path:
    shutil.copytree(REPO / "data", tmp_path / "data")
    shutil.copy(REPO / "acceptance.toml", tmp_path / "acceptance.toml")
    (tmp_path / "README.md").write_text(README, encoding="utf-8")
    return tmp_path


def test_record_then_replay_gives_the_same_report_without_a_model(tmp_path):
    root = workspace(tmp_path)
    reader = PerfectReader(root / "data", "test")
    record_code = main(["accept", "--record"], root=root, transport=reader)
    recorded = json.loads((root / "reports" / "acceptance.json").read_text(encoding="utf-8"))
    assert reader.calls == 80
    assert (root / "runs" / "ministral-3-8b" / "calls.jsonl").exists()
    run_info = json.loads((root / "runs" / "ministral-3-8b" / "run.json").read_text(encoding="utf-8"))
    assert run_info["items"] == 80 and run_info["split"] == "test"

    replay_code = main(["accept"], root=root)
    replayed = json.loads((root / "reports" / "acceptance.json").read_text(encoding="utf-8"))
    assert replay_code == record_code
    assert replayed["criteria"] == recorded["criteria"]
    assert replayed["recorded_at"] == run_info["recorded_at"]


def test_review_queue_lists_every_field_sent_to_a_person(tmp_path):
    root = workspace(tmp_path)
    main(["accept", "--record"], root=root, transport=PerfectReader(root / "data", "test"))
    queue = (root / "out" / "test" / "review_queue.csv").read_text(encoding="utf-8").splitlines()
    assert queue[0] == "doc_id,field,value,reason,suggestion"
    assert len(queue) > 1
    result = json.loads((root / "out" / "test" / "t-001.json").read_text(encoding="utf-8"))
    assert set(result["fields"]) == {
        "counterparty",
        "document_number",
        "document_date",
        "due_date",
        "amount",
        "iban",
        "bic",
    }


def test_readme_block_follows_the_report_and_check_mode_detects_drift(tmp_path):
    root = workspace(tmp_path)
    main(["accept", "--record"], root=root, transport=PerfectReader(root / "data", "test"))
    assert main(["readme", "--check"], root=root) == 1
    assert main(["readme"], root=root) == 0
    assert main(["readme", "--check"], root=root) == 0
    assert "Bank details accepted automatically that are correct" in (root / "README.md").read_text(encoding="utf-8")


def test_demo_replays_three_examples(tmp_path):
    root = workspace(tmp_path)
    main(["accept", "--record"], root=root, transport=PerfectReader(root / "data", "test"))
    assert main(["demo"], root=root) == 0


def test_card_counts_fields_in_plain_english():
    from finance_document_agent.checks import FieldResult
    from finance_document_agent.cli import card
    from finance_document_agent.pipeline import DocumentResult

    one = DocumentResult("d", {"iban": FieldResult("iban", "X", "review", ["why"])}, False, 1.0)
    two = DocumentResult(
        "d",
        {"iban": FieldResult("iban", "X", "review", ["why"]), "bic": FieldResult("bic", "Y", "review", ["why"])},
        False,
        1.0,
    )
    assert card("t", one).endswith("goes to a reviewer (1 field)")
    assert card("t", two).endswith("goes to a reviewer (2 fields)")


def test_replay_without_a_stored_run_explains_what_to_do(tmp_path):
    root = workspace(tmp_path)
    assert main(["accept"], root=root) == 2
