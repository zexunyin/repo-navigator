import json
from pathlib import Path

from repo_navigator.cli import main
from repo_navigator.indexer import read_json, write_json


def test_init_scan_review_and_stale_detection(tmp_path: Path, capsys):
    code = tmp_path / "sample.py"
    code.write_text("def total(value: int) -> int:\n    return value + 1\n", encoding="utf-8")
    assert main(["init", str(tmp_path)]) == 0
    assert (tmp_path / "AGENTS.md").exists()
    assert main(["check", str(tmp_path)]) == 1  # Not yet reviewed by an agent
    symbols = read_json(tmp_path / ".ai" / "symbols.json")["symbols"]
    assert len(symbols) == 1
    assert symbols[0]["start_line"] == 1
    assert symbols[0]["qualified_name"] == "total"
    semantics_path = tmp_path / ".ai" / "semantics.json"
    semantics = read_json(semantics_path)
    semantics["entries"][symbols[0]["id"]] = {
        "purpose": "Return the value plus one", "owner": "sample",
        "side_effects": [], "reviewed_hash": symbols[0]["source_hash"],
    }
    write_json(semantics_path, semantics)
    assert main(["scan", str(tmp_path)]) == 0
    assert main(["check", str(tmp_path)]) == 0
    assert "Return the value plus one" in (tmp_path / ".ai" / "INDEX.md").read_text()

    code.write_text("def total(value: int) -> int:\n    return value + 2\n", encoding="utf-8")
    assert main(["check", str(tmp_path)]) == 1
    assert main(["status", str(tmp_path)]) == 1  # Current source differs from saved index
    assert main(["scan", str(tmp_path)]) == 0
    assert main(["status", str(tmp_path)]) == 0  # Index is fresh but semantic review is not
    assert "stale" in capsys.readouterr().out
    assert main(["check", str(tmp_path)]) == 1
    after = read_json(semantics_path)["entries"][symbols[0]["id"]]
    assert after["purpose"] == "Return the value plus one"  # Never overwritten


def test_existing_agent_instructions_preserved(tmp_path: Path):
    (tmp_path / "AGENTS.md").write_text("Custom instructions\n", encoding="utf-8")
    (tmp_path / "example.py").write_text("class A:\n    def m(self):\n        pass\n")
    assert main(["init", str(tmp_path)]) == 0
    assert (tmp_path / "AGENTS.md").read_text() == "Custom instructions\n"
    symbol = read_json(tmp_path / ".ai" / "symbols.json")["symbols"][0]
    assert symbol["qualified_name"] == "A.m"
    assert symbol["kind"] == "method"


def test_nested_functions_and_python_hash_ignore_line_shifts(tmp_path: Path):
    file = tmp_path / "example.py"
    file.write_text("def outer():\n    def inner():\n        return 1\n    return inner()\n")
    assert main(["scan", str(tmp_path)]) == 0
    old = read_json(tmp_path / ".ai" / "symbols.json")["symbols"]
    assert {item["qualified_name"] for item in old} == {"outer", "outer.<locals>.inner"}
    file.write_text("\n\ndef outer():\n    def inner():\n        return 1\n    return inner()\n")
    assert main(["scan", str(tmp_path)]) == 0
    new = read_json(tmp_path / ".ai" / "symbols.json")["symbols"]
    assert {item["id"]: item["source_hash"] for item in new} == {
        item["id"]: item["source_hash"] for item in old
    }
    assert new[0]["start_line"] == 3


def test_ignored_directories_not_indexed(tmp_path: Path):
    (tmp_path / "app.py").write_text("def foo(): pass\n")
    (tmp_path / "build").mkdir()
    (tmp_path / "build" / "generated.py").write_text("def generated(): pass\n")
    assert main(["scan", str(tmp_path)]) == 0
    assert [file["path"] for file in read_json(tmp_path / ".ai" / "files.json")["files"]] == ["app.py"]


def test_invalid_python_does_not_overwrite_existing_index(tmp_path: Path):
    file = tmp_path / "app.py"
    file.write_text("def foo(): return 1\n")
    assert main(["scan", str(tmp_path)]) == 0
    old = (tmp_path / ".ai" / "symbols.json").read_text()
    file.write_text("def broken(\n")
    assert main(["scan", str(tmp_path)]) == 2
    assert (tmp_path / ".ai" / "symbols.json").read_text() == old


def test_removed_symbol_purges_entry_on_scan(tmp_path: Path):
    file = tmp_path / "example.py"
    file.write_text("def vanished(): pass\n")
    assert main(["scan", str(tmp_path)]) == 0
    file.write_text("# gone\n")
    assert main(["scan", str(tmp_path)]) == 0
    assert read_json(tmp_path / ".ai" / "semantics.json")["entries"] == {}
    assert main(["check", str(tmp_path)]) == 0
