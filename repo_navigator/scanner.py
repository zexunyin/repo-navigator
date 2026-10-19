"""Extract deterministic structural facts; never invent semantic descriptions."""

from __future__ import annotations

import ast
import hashlib
import os
import re
import subprocess
from pathlib import Path
from typing import Any

PYTHON_EXTENSIONS = {".py"}
CPP_EXTENSIONS = {".cpp", ".cc", ".cxx", ".hpp", ".hh", ".hxx", ".h"}
SKIP_DIRECTORIES = {
    ".git", ".ai", ".venv", "venv", "__pycache__", ".tox", ".mypy_cache",
    ".pytest_cache", "node_modules", "build", "dist", "vendor", "third_party",
}


class ScanError(Exception):
    """A source file could not be indexed reliably."""


def digest(content: bytes | str) -> str:
    if isinstance(content, str):
        content = content.encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def discover_files(root: Path) -> list[Path]:
    """Prefer Git's ignore rules; fall back to walking non-Git folders."""
    root = root.resolve()
    git_root = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], cwd=root, capture_output=True,
        text=True, check=False,
    ) if _git_available() else None
    if git_root and git_root.returncode == 0 and Path(git_root.stdout.strip()).resolve() == root:
        found = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            cwd=root, capture_output=True, check=False,
        )
        if found.returncode != 0:
            raise ScanError("git ls-files failed; cannot apply ignore rules")
        candidates = [root / os.fsdecode(name) for name in found.stdout.split(b"\0") if name]
    else:
        candidates = []
        for directory, subdirectories, filenames in os.walk(root, followlinks=False):
            subdirectories[:] = sorted(d for d in subdirectories if d not in SKIP_DIRECTORIES)
            candidates.extend(Path(directory) / name for name in filenames)
    supported = PYTHON_EXTENSIONS | CPP_EXTENSIONS
    return sorted(
        (path for path in candidates if path.suffix.lower() in supported
         and path.is_file() and not path.is_symlink()
         and not any(segment in SKIP_DIRECTORIES for segment in path.relative_to(root).parts)),
        key=lambda path: path.relative_to(root).as_posix(),
    )


def _git_available() -> bool:
    from shutil import which
    return which("git") is not None


def _python_symbols(source: str, relative_path: str) -> list[dict[str, Any]]:
    try:
        tree = ast.parse(source, filename=relative_path)
    except SyntaxError as error:
        raise ScanError(f"{relative_path}:{error.lineno}: {error.msg}") from error
    symbols: list[dict[str, Any]] = []

    def visit(container: ast.AST, parents: tuple[str, ...] = (), in_class: bool = False) -> None:
        for node in ast.iter_child_nodes(container):
            if isinstance(node, ast.ClassDef):
                visit(node, (*parents, node.name), in_class=True)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qualified_name = ".".join((*parents, node.name))
                arguments = ast.unparse(node.args)
                signature = f"{node.name}({arguments})"
                start = min([node.lineno, *(decorator.lineno for decorator in node.decorator_list)])
                symbols.append({
                    "id": f"{relative_path}::{qualified_name}",
                    "file": relative_path,
                    "language": "python",
                    "kind": "method" if in_class else "function",
                    "name": node.name,
                    "qualified_name": qualified_name,
                    "signature": signature,
                    "start_line": start,
                    "end_line": node.end_lineno,
                    "source_hash": digest(ast.dump(node, include_attributes=False)),
                })
                visit(node, (*parents, node.name, "<locals>"), in_class=False)
            else:
                # Only look through top-level control blocks, not expression nodes.
                if isinstance(node, (ast.If, ast.Try, ast.With, ast.For, ast.While, ast.Match)):
                    visit(node, parents, in_class)

    visit(tree)
    return symbols


def _cpp_symbols(source: bytes, relative_path: str) -> list[dict[str, Any]]:
    try:
        from tree_sitter import Language, Parser
        import tree_sitter_cpp
    except ImportError as error:
        raise ScanError(
            "C++ parser unavailable. Install: pip install 'tree-sitter>=0.22' tree-sitter-cpp"
        ) from error
    try:
        parser = Parser(Language(tree_sitter_cpp.language()))
        syntax_tree = parser.parse(source)
    except Exception as error:
        raise ScanError(f"Cannot initialize C++ parser for {relative_path}: {error}") from error

    symbols: list[dict[str, Any]] = []

    def node_text(node: Any) -> str:
        return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")

    def find_declarator(node: Any) -> Any | None:
        if node is None:
            return None
        if node.type == "function_declarator":
            return node
        for child in node.named_children:
            candidate = find_declarator(child)
            if candidate is not None:
                return candidate
        return None

    def walk(node: Any, scope: tuple[str, ...] = (), in_class: bool = False) -> None:
        if node.type == "namespace_definition":
            name = node.child_by_field_name("name")
            new_scope = (*scope, node_text(name)) if name is not None else scope
            for child in node.named_children:
                if child is not name:
                    walk(child, new_scope, in_class)
            return
        if node.type in ("class_specifier", "struct_specifier", "union_specifier"):
            name = node.child_by_field_name("name")
            new_scope = (*scope, node_text(name)) if name is not None else scope
            for child in node.named_children:
                if child is not name:
                    walk(child, new_scope, True)
            return
        if node.type == "function_definition":
            declarator = find_declarator(node.child_by_field_name("declarator"))
            if declarator is not None:
                name_node = declarator.child_by_field_name("declarator")
                if name_node is not None:
                    raw_name = node_text(name_node)
                    qualified_name = "::".join((*scope, raw_name))
                    signature = re.sub(r"\s+", " ", node_text(declarator)).strip()
                    symbols.append({
                        "id": f"{relative_path}::{qualified_name}({digest(signature)[:12]})",
                        "file": relative_path,
                        "language": "cpp",
                        "kind": "method" if in_class or "::" in raw_name else "function",
                        "name": raw_name.split("::")[-1],
                        "qualified_name": qualified_name,
                        "signature": signature,
                        "start_line": node.start_point.row + 1,
                        "end_line": node.end_point.row + 1,
                        "source_hash": digest(source[node.start_byte:node.end_byte]),
                    })
            # Do not recurse into function bodies (lambdas aren't standalone symbols).
            return
        for child in node.named_children:
            walk(child, scope, in_class)

    walk(syntax_tree.root_node)
    return symbols


def collect_structure(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    files: list[dict[str, Any]] = []
    symbols: list[dict[str, Any]] = []
    failures: list[str] = []
    for path in discover_files(root):
        relative_path = path.relative_to(root).as_posix()
        try:
            content = path.read_bytes()
            decoded = content.decode("utf-8-sig")
            language = "python" if path.suffix.lower() in PYTHON_EXTENSIONS else "cpp"
            extracted = (
                _python_symbols(decoded, relative_path)
                if language == "python" else _cpp_symbols(content, relative_path)
            )
            files.append({
                "path": relative_path, "language": language,
                "source_hash": digest(content), "symbol_count": len(extracted),
            })
            symbols.extend(extracted)
        except (UnicodeError, OSError, ScanError) as error:
            failures.append(f"{relative_path}: {error}")
    if failures:
        raise ScanError("Scan failed; existing indexes left unchanged:\n" + "\n".join(failures))
    symbols.sort(key=lambda item: (item["file"], item["start_line"], item["id"]))
    ids = [item["id"] for item in symbols]
    if len(ids) != len(set(ids)):
        raise ScanError("Duplicate symbol IDs detected; refusing to write ambiguous index")
    return ({"schema_version": 1, "files": files}, {"schema_version": 1, "symbols": symbols})
