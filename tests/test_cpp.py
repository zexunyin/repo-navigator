import pytest

from repo_navigator.scanner import _cpp_symbols


def test_cpp_overloads_namespaces_and_class_methods():
    pytest.importorskip("tree_sitter")
    pytest.importorskip("tree_sitter_cpp")
    code = b"""
namespace engine {
class Planner {
public:
    int update(int step) { return step + 1; }
    int update(double step) { return static_cast<int>(step); }
};
int increment(int value) { return value + 1; }
}
"""
    functions = _cpp_symbols(code, "source/planner.cpp")
    assert len(functions) == 3
    assert len({item["id"] for item in functions}) == 3
    assert "engine::Planner::update" in functions[0]["qualified_name"]
    assert any(item["qualified_name"] == "engine::increment" for item in functions)
