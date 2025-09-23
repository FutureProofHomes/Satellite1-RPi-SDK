# command_spec.py
from __future__ import annotations
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Optional, get_type_hints
import inspect
import functools

@dataclass
class ArgSpec:
    name: str                # canonical param name (function parameter)
    flags: tuple[str, ...]   # argparse flags ("-o","--out") or empty (positional)
    kwargs: dict[str, Any]   # argparse add_argument kwargs

@dataclass
class CommandSpec:
    name: str
    help: str
    aliases: list[str] = field(default_factory=list)
    fn: Callable | None = None
    args: list[ArgSpec] = field(default_factory=list)
    is_async: bool = False
    # Optional api-specific hints:
    returns: str | None = None
    summary: str | None = None
    tags: list[str] = field(default_factory=list)

def _is_async_callable(fn: Callable) -> bool:
    f = fn
    while isinstance(f, functools.partial):
        f = f.func
    if hasattr(f, "__wrapped__"):
        f = inspect.unwrap(f)
    return inspect.iscoroutinefunction(f)

def command(
        name: str | None = None, 
        *, 
        help: str = "", 
        aliases: list[str] | None = None,
        returns:str | None = None, 
        summary: str | None = None, 
        tags: list[str] | None = None
):
    """Annotate a method/function as a command. Stores spec on the callable."""
    def deco(fn: Callable):
        spec = getattr(fn, "_cmd_spec", None)
        if spec is None:
            spec = CommandSpec(
                name=name or fn.__name__.replace("_", "-"),
                help=help,
                aliases=list(aliases or []),
                fn=fn,
                is_async=_is_async_callable(fn),
                summary=summary,
                tags=list(tags or []),
            )
        else:
            # allow @command to be applied multiple times if needed (we’ll merge updates)
            spec = replace(
                spec,
                name=name or spec.name,
                help=help or spec.help,
                aliases=list(aliases or spec.aliases),
                is_async=_is_async_callable(fn),
                summary=summary or spec.summary,
                tags=list(tags or spec.tags),
                fn=fn,
            )
        setattr(fn, "_cmd_spec", spec)
        return fn
    return deco

def arg(*flags: str, **kwargs: Any):
    """
    Attach an argument to the most recent @command.
    If no flags are given, treat as a positional; its name should match a function param.
    """
    def deco(fn: Callable):
        spec: CommandSpec | None = getattr(fn, "_cmd_spec", None)
        if spec is None:
            raise RuntimeError("@arg must be used under a @command")

        if flags:
            # Option: derive canonical name from long flag if you like
            long = next((f for f in flags if f.startswith("--")), None)
            pname = (long or flags[0]).lstrip("-").replace("-", "_")
        else:
            # Positional: infer from function signature (skip 'self'/'cls'), in declared order
            sig = inspect.signature(fn)
            params = [
                p for p in sig.parameters.values()
                if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
                and p.name not in ("self", "cls")
            ]
            used = {a.name for a in spec.args if not a.flags and a.name}
            try:
                pname = next(p.name for p in params if p.name not in used)
            except StopIteration:
                # Fallback: allow override via 'dest', but do NOT leave it in kwargs for argparse
                pname = kwargs.pop("dest", None) or ""

        # Optional: auto-fill type from annotations if not provided and not an action
        if "type" not in kwargs and "action" not in kwargs:
            try:
                hints = get_type_hints(fn)
                if pname and pname in hints:
                    kwargs["type"] = hints[pname]
            except Exception:
                pass

        # If positional, ensure 'dest' is not forwarded to argparse
        if not flags:
            kwargs.pop("dest", None)

        spec.args.append(ArgSpec(name=pname, flags=tuple(flags), kwargs=kwargs))
        setattr(fn, "_cmd_spec", spec)
        return fn
    return deco

def collect_specs(obj: Any) -> list[CommandSpec]:
    """Collect CommandSpec from obj’s callables (instance or module)."""
    specs: list[CommandSpec] = []
    for attr in dir(obj):
        fn = getattr(obj, attr)
        cs: CommandSpec | None = getattr(fn, "_cmd_spec", None)
        if cs and callable(fn):
            # ensure we bind the actual callable we found (e.g., bound method)
            cs.fn = fn
            specs.append(cs)
    return specs