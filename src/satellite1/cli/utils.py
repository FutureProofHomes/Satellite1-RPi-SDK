# cfg_argparse.py
from __future__ import annotations
import argparse, json
from pathlib import Path
from typing import Any, get_origin, get_args, Literal
from pydantic import BaseModel
from pydantic.fields import FieldInfo
import tomllib

def _base0_int(s: str) -> int:
    return int(s, 0)

def _str2bool(s: str) -> bool:
    s = s.lower()
    if s in ("1","true","t","yes","y","on"): return True
    if s in ("0","false","f","no","n","off"): return False
    raise argparse.ArgumentTypeError(f"Not a boolean: {s!r}")

def _add_scalar_arg(g: argparse._ArgumentGroup, flag: str, ftype: Any, finfo: FieldInfo) -> None:
    import enum
    from argparse import BooleanOptionalAction, SUPPRESS

    kwargs = dict(help=finfo.description or "", default=SUPPRESS)
    origin = get_origin(ftype)

    if ftype is bool:
        g.add_argument(flag, action=BooleanOptionalAction, **kwargs)
    elif origin is None and isinstance(ftype, type) and issubclass(ftype, enum.Enum):
        choices = [e.value for e in ftype]  # pass enum values
        g.add_argument(flag, choices=choices, **kwargs)
    elif origin is None and ftype is int:
        g.add_argument(flag, type=_base0_int, **kwargs)
    elif origin is None and ftype is float:
        g.add_argument(flag, type=float, **kwargs)
    elif origin is None and ftype is str:
        g.add_argument(flag, type=str, **kwargs)
    elif origin is Literal:
        choices = list(get_args(ftype))
        g.add_argument(flag, choices=choices, **kwargs)
    else:
        # fallback: accept JSON and let Pydantic coerce
        g.add_argument(flag, type=str, metavar="JSON", **kwargs)

def _parse_kv_to_dict(spec: str) -> dict[str, Any]:
    """
    Accept 'k=v,k2=v2' OR a raw JSON object. Values auto-coerce 0/1/true/false and 0x.. ints.
    """
    spec = spec.strip()
    if spec.startswith("{"):
        return json.loads(spec)
    out: dict[str, Any] = {}
    for tok in filter(None, (t.strip() for t in spec.split(","))):
        if "=" not in tok:
            raise argparse.ArgumentTypeError(f"Bad token (expected k=v): {tok!r}")
        k, v = (x.strip() for x in tok.split("=", 1))
        low = v.lower()
        if low in ("true","false","1","0","yes","no","on","off"):
            out[k] = _str2bool(v)
        else:
            try:
                out[k] = _base0_int(v)
            except ValueError:
                out[k] = v
    return out

def load_toml_first(paths: list[Path]) -> dict:
    for p in paths:
        if p.is_file():
            with p.open("rb") as f:
                return tomllib.load(f) or {}
    return {}

def deep_merge(a: dict, b: dict) -> dict:
    out = dict(a)
    for k, v in b.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def add_model_to_argparse(
    parser: argparse.ArgumentParser,
    model_cls: type[BaseModel],
    *,
    prefix: str = "",
) -> None:
    """
    Recursively add flags for a Pydantic model. Nested models become sub-groups.
    List[SubModel] fields become repeatable --<prefix>-<field> flags accepting k=v pairs.
    """
    # group for this prefix
    title = " ".join(part for part in prefix.replace("__","-").split("-") if part) or "Config"
    group = parser.add_argument_group(title)

    for name, field in model_cls.model_fields.items():
        finfo: FieldInfo = field
        ftype = field.annotation
        flag = f"--{(prefix + name).replace('_','-').replace('__','-')}"
        origin = get_origin(ftype)

        # nested model
        if isinstance(field.annotation, type) and issubclass(field.annotation, BaseModel):
            add_model_to_argparse(parser, field.annotation, prefix=prefix + name + "__")
            continue

        # list of submodels
        if origin in (list, list | None,):
            (item_type,) = get_args(ftype) or (Any,)
            if isinstance(item_type, type) and issubclass(item_type, BaseModel):
                group.add_argument(
                    flag, action="append", default=argparse.SUPPRESS, metavar="k=v[,k2=v2...]",
                    type=_parse_kv_to_dict,
                    help=(finfo.description or "") + " (repeatable; accepts k=v or JSON)",
                )
                continue

        # scalar
        _add_scalar_arg(group, flag, ftype, finfo)

def namespace_to_updates(ns: argparse.Namespace) -> dict[str, Any]:
    """
    Turn provided args into a nested dict by splitting dest names on '__'.
    Only includes flags the user set (thanks to SUPPRESS defaults).
    """
    def set_in(d: dict, path: list[str], val: Any) -> None:
        cur = d
        for p in path[:-1]:
            cur = cur.setdefault(p, {})
        cur[path[-1]] = val

    updates: dict[str, Any] = {}
    for dest, val in vars(ns).items():
        # argparse converts '--pcm5122-i2c-addr' to dest 'pcm5122_i2c_addr'
        path = dest.split("_")  # we used __ to mark nesting, but underscores are fine here
        set_in(updates, path, val)
    return updates
