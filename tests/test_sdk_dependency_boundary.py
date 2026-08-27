from pathlib import Path


def test_sdk_does_not_import_pydantic():
    sdk_root = Path(__file__).parents[1] / "src" / "satellite1"

    offenders = [
        path.relative_to(sdk_root)
        for path in sdk_root.rglob("*.py")
        if "pydantic" in path.read_text(encoding="utf-8")
    ]

    assert offenders == []
