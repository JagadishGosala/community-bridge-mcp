import logging
import sys


def setup(level: int = logging.INFO) -> None:
    """Send all logging to stderr; stdout carries only MCP JSON-RPC (REQ-29)."""
    logging.basicConfig(
        stream=sys.stderr, level=level, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
