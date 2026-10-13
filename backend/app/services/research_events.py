"""Emit safe progress inside a graph, while keeping direct node calls usable."""

from langgraph.config import get_stream_writer


def emit_progress(event: dict) -> None:
    try:
        writer = get_stream_writer()
    except RuntimeError:
        return
    writer(event)
