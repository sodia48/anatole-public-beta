from pathlib import Path
import ast


def test_python_syntax():
    root = Path(__file__).resolve().parents[1]
    for path in root.rglob("*.py"):
        if ".venv" in path.parts:
            continue
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
