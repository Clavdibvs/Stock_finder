"""Logging con redazione automatica dei segreti."""
from __future__ import annotations

import logging
import re

SECRET_PATTERNS = [
    re.compile(r"(api[_-]?key|token|secret|password|authorization)\s*[=:]\s*\S+", re.I),
    re.compile(r"Bearer\s+[A-Za-z0-9._\-]+"),
    re.compile(r"sk-[A-Za-z0-9\-_]{8,}"),
    re.compile(r"/bot\d+:[A-Za-z0-9_\-]+"),  # token Telegram negli URL
]


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        for pattern in SECRET_PATTERNS:
            msg = pattern.sub("[REDACTED]", msg)
        record.msg = msg
        record.args = ()
        return True


def setup_logging(debug: bool = False) -> None:
    level = logging.DEBUG if debug else logging.INFO
    handler = logging.StreamHandler()
    handler.addFilter(RedactingFilter())
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers = [handler]
