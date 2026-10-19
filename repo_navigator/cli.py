"""repo-nav: portable repository navigation from source code."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .indexer import inspect, scan, write_text_if_changed
from .scanner import ScanError
from .templates import AGENT_INSTRUCTIONS, ARCHITECTURE


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="repo-nav", description="AI-readable repository indexes")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("init", "scan", "status", "check"):
        command = commands.add_parser(name)
        command.add_argument("path", nargs="?", default=".", help="Repository root (default: .)")
    args = parser.parse_args(argv)
    root = Path(args.path).resolve()
    if not root.is_dir():
        parser.error(f"Directory does not exist: {root}")

    try:
        if args.command == "init":
            for path, contents in (
                (root / "AGENTS.md", AGENT_INSTRUCTIONS),
                (root / ".ai" / "architecture.md", ARCHITECTURE),
            ):
                if not path.exists():
                    write_text_if_changed(path, contents)
                    print(f"Created {path.relative_to(root)}")
                else:
                    print(f"Preserved existing {path.relative_to(root)}")
        if args.command in ("init", "scan"):
            files, symbols, _ = scan(root)
            print(f"Indexed {len(files['files'])} files and {len(symbols['symbols'])} symbols")
            print("Next: repo-nav status .")
            return 0

        problems, counts, pending = inspect(root)
        print(
            f"Symbols: {sum(counts.values())} | verified: {counts['verified']} | "
            f"missing: {counts['missing']} | stale: {counts['stale']}"
        )
        for problem in problems:
            print(f"INDEX: {problem}")
        if args.command == "status":
            for symbol in pending:
                print(f"  [{symbol['status']}] {symbol['id']} ({symbol['start_line']})")
            return 1 if problems else 0
        if pending:
            print("Definitions need review. See: repo-nav status .")
        if problems or pending:
            print("CHECK FAILED")
            return 1
        print("CHECK PASSED")
        return 0
    except (OSError, ValueError, ScanError) as error:
        print(f"repo-nav: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
