"""Per-turn trace collection.

Processors record what happened while handling a message (classifier decision,
which agent ran, tool calls, notable events) into ``data["trace"]``. The trace
is persisted as the ``context`` field of each assistant message doc so admins
can debug a conversation at per-message level.
"""

import json

# Cap individual trace payloads so message docs stay well under Mongo's doc limit.
_MAX_FIELD_CHARS = 6000


def _compact(value, limit: int = _MAX_FIELD_CHARS):
    """Return value as-is when small; truncate to a string when it is too large."""
    if value is None or isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, str):
        return value if len(value) <= limit else value[:limit] + "…[truncated]"
    try:
        dumped = json.dumps(value, default=str)
    except Exception:
        return _compact(str(value), limit)
    if len(dumped) <= limit:
        return value
    return dumped[:limit] + "…[truncated]"


def get_trace(data: dict) -> dict:
    """Get (or initialise) the trace dict for this turn."""
    return data.setdefault("trace", {"tool_calls": [], "events": []})


def set_agent(data: dict, agent: str, model: str | None = None) -> None:
    """Record which agent handled this turn and the model it used."""
    trace = get_trace(data)
    trace["agent"] = agent
    if model:
        trace["model"] = model


def record_classifier(data: dict, category: str, raw_response, model: str) -> None:
    """Record the classifier's routing decision."""
    get_trace(data)["classifier"] = {
        "category": category,
        "raw_response": _compact(raw_response),
        "model": model,
    }


def record_tool_call(data: dict, tool: str, arguments, output) -> None:
    """Record a tool invocation made by an agent (input and output)."""
    get_trace(data)["tool_calls"].append(
        {
            "tool": tool,
            "input": _compact(arguments),
            "output": _compact(output),
        }
    )


def record_event(data: dict, event: str, **details) -> None:
    """Record a notable non-LLM event (routing shortcut, QR scan, checkout step...)."""
    entry = {"event": event}
    for key, value in details.items():
        entry[key] = _compact(value)
    get_trace(data)["events"].append(entry)
