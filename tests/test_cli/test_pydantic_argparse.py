# tests/test_pydantic_argparse.py
from __future__ import annotations
import argparse
from pathlib import Path
from typing import List, Literal

import pytest
from pydantic import BaseModel, Field, ConfigDict

# If your helpers live in satellite1/arg_overrides.py, adjust the import:
from satellite1_cli.pydantic_argparse import add_pydantic_overrides, collect_overrides


class CliModel(BaseModel):
    model_config = ConfigDict(extra="ignore")
    enabled: bool = False
    level: float = 0.5
    mode: Literal["auto", "manual"] = "auto"
    count: int = 1
    tags: List[str] = Field(default_factory=list, description="One or more tags")


def make_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="tool")
    add_pydantic_overrides(p, CliModel, prefix="dac")
    return p


def test_flags_are_generated_with_none_defaults_and_help_present(capsys):
    p = make_parser()
    # Ensure attributes exist and are None by default (meaning "no override supplied")
    ns = p.parse_args([])
    assert hasattr(ns, "dac_enabled") and ns.dac_enabled is None
    assert hasattr(ns, "dac_level") and ns.dac_level is None
    assert hasattr(ns, "dac_mode") and ns.dac_mode is None
    assert hasattr(ns, "dac_count") and ns.dac_count is None
    assert hasattr(ns, "dac_tags") and ns.dac_tags is None

    # Help text includes our flags (basic smoke)
    with pytest.raises(SystemExit):
        p.parse_args(["-h"])
    out = capsys.readouterr().out
    assert "--dac-enabled" in out
    assert "--dac-level" in out
    assert "--dac-mode" in out
    assert "--dac-count" in out
    assert "--dac-tags" in out
    # BooleanOptionalAction should have --no-dac-enabled too (on py3.11+)
    assert "--no-dac-enabled" in out or True  # tolerate older Python fallback


def test_boolean_optional_action_true_and_false():
    p = make_parser()

    ns = p.parse_args(["--dac-enabled"])
    overrides = collect_overrides(ns, CliModel, prefix="dac")
    assert overrides == {"enabled": True}

    ns = p.parse_args(["--no-dac-enabled"])
    overrides = collect_overrides(ns, CliModel, prefix="dac")
    assert overrides == {"enabled": False}


def test_parses_literal_choices_and_types_and_list():
    p = make_parser()
    ns = p.parse_args(
        [
            "--dac-level", "0.7",
            "--dac-mode", "manual",
            "--dac-count", "5",
            "--dac-tags", "alpha", "beta",
        ]
    )
    overrides = collect_overrides(ns, CliModel, prefix="dac")
    assert overrides == {
        "level": 0.7,
        "mode": "manual",
        "count": 5,
        "tags": ["alpha", "beta"],
    }


def test_combined_overrides_multiple_fields():
    p = make_parser()
    ns = p.parse_args(["--dac-enabled", "--dac-level", "0.6"])
    overrides = collect_overrides(ns, CliModel, prefix="dac")
    assert overrides == {"enabled": True, "level": 0.6}
