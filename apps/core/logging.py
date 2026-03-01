import json
import logging
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    def format(self, record):
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        request = getattr(record, "request", None)
        if request is not None:
            payload["path"] = getattr(request, "path", "")
            payload["method"] = getattr(request, "method", "")

        return json.dumps(payload, ensure_ascii=True)
