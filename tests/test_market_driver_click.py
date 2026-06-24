import ast
from pathlib import Path


def _load_resolver():
    path = (
        Path(__file__).resolve().parents[1]
        / "screens"
        / "15_Market_Drivers.py"
    )
    tree = ast.parse(path.read_text(encoding="utf-8"))
    function_node = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "resolve_clicked_sector"
    )
    module = ast.Module(body=[function_node], type_ignores=[])
    namespace = {}
    exec(compile(module, str(path), "exec"), namespace)
    return namespace["resolve_clicked_sector"]


def test_sector_click_from_y_value():
    resolver = _load_resolver()
    sectors = ["Energy", "Materials", "Financials"]

    result = resolver(
        [{"x": 0.7, "y": "Materials", "pointIndex": 1}],
        sectors,
    )

    assert result == "Materials"


def test_sector_click_from_point_index_fallback():
    resolver = _load_resolver()
    sectors = ["Energy", "Materials", "Financials"]

    result = resolver(
        [{"x": 0.7, "pointIndex": 2}],
        sectors,
    )

    assert result == "Financials"
