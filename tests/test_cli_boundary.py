from pathlib import Path


def test_cli_does_not_import_direct_hardware_or_configuration():
    cli_root = Path(__file__).parents[1] / "src" / "satellite1_cli"
    forbidden = ("satellite1.", "pydantic", "tomllib", "config_load")

    offenders = [
        path.relative_to(cli_root)
        for path in cli_root.rglob("*.py")
        if any(token in path.read_text(encoding="utf-8") for token in forbidden)
    ]

    assert offenders == []
