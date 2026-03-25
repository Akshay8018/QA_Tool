from __future__ import annotations

import contextvars
import logging
import re

request_id_ctx_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")

_SENSITIVE_PATTERN = re.compile(
    r"(?i)\b(password|passwd|token|secret|api[_-]?key|authorization)\b\s*[:=]\s*([^\s,;]+)"
)


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx_var.get()
        return True


class SensitiveDataFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        if not message:
            return True
        redacted = _SENSITIVE_PATTERN.sub(r"\1=<redacted>", message)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.addFilter(RequestIdFilter())
    handler.addFilter(SensitiveDataFilter())
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s [%(name)s] [request_id=%(request_id)s] %(message)s")
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
