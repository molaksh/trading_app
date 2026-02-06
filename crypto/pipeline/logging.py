"""
Crypto pipeline logging helpers.

Emits structured logs at each pipeline stage with standard metadata.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Dict, Iterable, Optional

logger = logging.getLogger(__name__)


def log_pipeline_stage(
    stage: str,
    scope: str,
    run_id: str,
    symbols: Iterable[str],
    extra: Optional[Dict] = None,
) -> None:
    """
    Emit a structured pipeline log line.
    """
    payload = {
        "stage": stage,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "scope": scope,
        "run_id": run_id,
        "symbols": list(symbols),
    }
    if extra:
        payload.update(extra)

    logger.info("CRYPTO_PIPELINE %s", json.dumps(payload, sort_keys=True))
