from pathlib import Path


def test_public_client_does_not_import_hardware_or_pydantic():
    sdk_root = Path(__file__).parents[1] / "src" / "satellite1"

    offenders = [
        path.relative_to(sdk_root)
        for path in sdk_root.rglob("*.py")
        if any(
            token in path.read_text(encoding="utf-8")
            for token in ("pydantic", "satellite1_hw")
        )
    ]

    assert offenders == []
