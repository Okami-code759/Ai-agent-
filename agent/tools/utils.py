"""Small utilities: exact maths and the current date/time."""
from __future__ import annotations

import ast
import math
import operator
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from . import ToolError, tool

_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod,
    ast.Pow: operator.pow, ast.USub: operator.neg, ast.UAdd: operator.pos,
}
_NAMES = {k: getattr(math, k) for k in dir(math) if not k.startswith("_")}
_NAMES.update(abs=abs, round=round, min=min, max=max)


def _eval(node):
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        left, right = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > 10_000:
            raise ToolError("Exponent too large.")
        return _OPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.operand))
    if isinstance(node, ast.Name) and node.id in _NAMES and not callable(_NAMES[node.id]):
        return _NAMES[node.id]
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and callable(_NAMES.get(node.func.id)):
        return _NAMES[node.func.id](*[_eval(a) for a in node.args])
    raise ToolError("Unsupported expression. Use numbers, + - * / // % **, and math functions.")


@tool("calculate", "Evaluate a maths expression exactly, e.g. 'sqrt(2) * 10**3' or 'log(100, 10)'.",
      {"expression": {"type": "string"}}, ci=True)
def calculate(ctx, expression: str) -> str:
    try:
        return str(_eval(ast.parse(expression, mode="eval")))
    except SyntaxError:
        raise ToolError("Invalid expression syntax.")
    except (ValueError, ZeroDivisionError, OverflowError, TypeError) as e:
        raise ToolError(f"Maths error: {e}")


@tool("current_datetime", "Get the current date and time, optionally in a timezone like 'Australia/Melbourne'.",
      {"timezone": {"type": "string"}}, required=[], ci=True)
def current_datetime(ctx, timezone: str = "") -> str:
    try:
        now = datetime.now(ZoneInfo(timezone)) if timezone else datetime.now().astimezone()
    except (ZoneInfoNotFoundError, ValueError):
        raise ToolError(f"Unknown timezone '{timezone}'.")
    return now.strftime("%A %d %B %Y, %H:%M:%S %Z (UTC%z)")
