import argparse
from pathlib import Path
from enum import Enum
from typing import Any, get_origin, get_args, Literal
from pydantic import BaseModel

def _kebab(name: str) -> str:
    return name.replace("_", "-")

def _base_type(tp: Any) -> tuple[type[Any] | None, dict[str, Any]]:
    """
    Return (argparse_type, extra_kwargs) derived from an annotation.
    Handles Optional[T], Literal[...] and common basic types.
    """
    extra: dict[str, Any] = {}
    origin = get_origin(tp)

    # list/tuple/set[T] → repeated args
    if origin in (tuple, list, set):
        inner = get_args(tp)[0] if get_args(tp) else str
        atype, _ = _base_type(inner)
        extra["nargs"] = "+"
        return (atype or str, extra)

    # Literal[...] → choices
    if origin is Literal:
        choices = list(get_args(tp))
        choices = [c.value if isinstance(c, Enum) else c for c in choices]
        extra["choices"] = choices
        if choices:
            return (type(choices[0]), extra)
        return (str, extra)

    # Union/Optional → first non-None member
    if origin is not None:
        args = [a for a in get_args(tp) if a is not type(None)]  # noqa: E721
        if args:
            return _base_type(args[0])

    # Plain types
    if tp in (str, int, float, bool, Path):
        return (tp, extra)
    if isinstance(tp, type) and issubclass(tp, Enum):
        extra["choices"] = [e.value for e in tp]
        return (str, extra)

    return (str, extra)  # fallback


def add_pydantic_overrides(
    parser: argparse.ArgumentParser,
    model_cls: type[BaseModel],
    *,
    prefix: str,  # e.g. "dac" or ""
    title: str | None = None,
    descriptions: dict[str, str] | None = None,
) -> None:
    """
    Add --<prefix>-<field> flags for each Pydantic field in model_cls.
    Booleans use BooleanOptionalAction with default=None (so "not provided" != False).
    Others default to None (only provided values override).
    """
    descriptions = descriptions or {}
    group_title = title or (f"{prefix.upper()} config overrides" if prefix else "config overrides")
    grp = parser.add_argument_group(group_title)

    def flag_for(fname: str) -> str:
        base = _kebab(fname)
        return f"--{prefix}-{base}" if prefix else f"--{base}"

    for fname, field in model_cls.model_fields.items():
        ann = field.annotation
        help_text = descriptions.get(fname) or (field.description or "")
        dest = f"{prefix}_{fname}" if prefix else fname
        atype, extra = _base_type(ann)

        if atype is bool:
            try:
                grp.add_argument(
                    flag_for(fname),
                    dest=dest,
                    action=argparse.BooleanOptionalAction,
                    default=None,
                    help=help_text,
                )
            except AttributeError:
                # Fallback for very old Python (not needed on 3.11+)
                grp.add_argument(flag_for(fname), dest=dest, action="store_true", default=None, help=help_text)
                noflag = f"--no-{prefix}-{_kebab(fname)}" if prefix else f"--no-{_kebab(fname)}"
                grp.add_argument(noflag, dest=dest, action="store_false")
        else:
            kwargs: dict[str, Any] = {"dest": dest, "default": None}
            if atype is not None:
                kwargs["type"] = atype
            kwargs.update(extra)
            if help_text:
                kwargs["help"] = help_text
            grp.add_argument(flag_for(fname), **kwargs)


def collect_overrides(ns: argparse.Namespace, model_cls: type[BaseModel], *, prefix: str) -> dict[str, Any]:
    """
    Pull only provided overrides (non-None) for the given model.
    Works for both prefixed (e.g. "dac_startup_volume") and unprefixed ("startup_volume").
    """
    out: dict[str, Any] = {}
    for fname in model_cls.model_fields:
        key = f"{prefix}_{fname}" if prefix else fname
        if hasattr(ns, key):
            val = getattr(ns, key)
            if val is not None:
                out[fname] = val
    return out
