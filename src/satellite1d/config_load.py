"""TOML loading for daemon-owned machine configuration."""

from __future__ import annotations
from pathlib import Path
from typing import Any, Mapping, TypeVar, Iterable
import tomllib
from pydantic import BaseModel

DEFAULT_CONF = Path("/etc/satellite1.conf")

DEFAULT_PATHS = [
    Path.home() / ".config" / "satellite1" / "config.toml",
    Path("/etc/satellite1.conf"),
]


T = TypeVar("T", bound=BaseModel)


def _first_existing(paths: Iterable[Path]) -> Path | None:
    for p in paths:
        try:
            if p.exists():
                return p
        except Exception:
            # e.g., HOME not set; ignore and continue
            pass
    return None


def _read_toml(path: Path | None) -> Mapping[str, Any]:
    if not path or not path.exists():
        return {}
    with path.open("rb") as f:
        return tomllib.load(f)


def _pick_section(raw: Mapping[str, Any], groups: tuple[str, ...]) -> Mapping[str, Any]:
    # Try declared groups in order. A missing named group must not receive
    # unrelated TOML tables, but ungrouped top-level settings remain supported.
    for g in groups:
        sec: Any = raw
        for part in g.split("."):
            if not isinstance(sec, Mapping):
                break
            sec = sec.get(part)
        if isinstance(sec, dict):
            return sec
    if not groups:
        return raw
    return {key: value for key, value in raw.items() if not isinstance(value, Mapping)}


def load_from_toml(
    model_cls: type[T],
    *,
    config_path: Path | None = None,
    overrides: Mapping[str, Any] | None = None,
) -> T:
    """
     Precedence: CLI overrides > file section > model defaults.

    If config_path is None, the first existing file from DEFAULT_PATHS is used.
    If model_cls defines CONF_GROUPS = ('line_out_dac',) (or multiple names),
    we select that TOML table; for a single name, both snake and kebab
    variants are tried (e.g. 'line_out_dac' and 'line-out-dac'). If no named
    section exists, only top-level non-table keys are used.
    """
    cfg = config_path if config_path else _first_existing(DEFAULT_PATHS)
    raw = _read_toml(cfg)
    groups = getattr(model_cls, "CONF_GROUPS", ())
    # auto-accept a dashed/snake alias if only a single group was provided
    if not groups:
        groups = ()
    elif len(groups) == 1:
        g = groups[0]
        alias = g.replace("_", "-") if "_" in g else g.replace("-", "_")
        groups = (g, alias) if alias != g else (g,)
    section = _pick_section(raw, groups)

    if overrides:
        section = {**section, **{k: v for k, v in overrides.items() if v is not None}}

    return model_cls.model_validate(section)
