"""
AI Advisor (Phase B) - Read-only universe ranking.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone, date
from pathlib import Path
from typing import Dict, Any, Optional, List

import requests

from config.crypto_scheduler_settings import (
    AI_ADVISOR_ENABLED,
    AI_MAX_CALLS_PER_DAY,
    AI_RANKING_INTERVAL_HOURS,
)
from config.scope import get_scope
from config.scope_paths import get_scope_path
from config.crypto.loader import load_crypto_config
from core.data.providers.kraken_provider import KrakenMarketDataProvider, KrakenOHLCConfig
from crypto.features import build_execution_features
from crypto.scope_guard import validate_crypto_universe_symbols
from runtime.observability import get_observability

logger = logging.getLogger(__name__)

_DEFAULT_ALLOWLIST = ["BTC", "ETH", "SOL", "LINK", "AVAX"]
_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "universe_ranking_phase_a.txt"


class AIAdvisor:
    """
    Stateless AI advisor for universe ranking.
    """

    def __init__(self) -> None:
        self.api_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.base_url = os.getenv("OPENAI_API_BASE_URL", "https://api.openai.com/v1")
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    def rank_universe(self, symbol_features: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        prompt = _PROMPT_PATH.read_text()
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are a careful, compliant assistant."},
                {"role": "user", "content": prompt},
                {
                    "role": "user",
                    "content": "FEATURES_JSON:\n" + json.dumps(symbol_features, sort_keys=True),
                },
            ],
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        }

        logger.info(
            "AI_ADVISOR_API_CALL | url=%s model=%s",
            f"{self.base_url}/chat/completions",
            self.model,
        )

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        resp = requests.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        parsed = json.loads(content)
        return {
            "parsed": parsed,
            "raw": content,
            "response_id": data.get("id"),
            "model": data.get("model", self.model),
        }


class AIAdvisorRunner:
    def __init__(self) -> None:
        self._last_call_time: Optional[datetime] = None
        self._last_success_time: Optional[datetime] = None
        self._last_error: Optional[str] = None
        self._calls_today: int = 0
        self._last_call_date: Optional[str] = None
        self._last_ranking: Optional[List[str]] = None
        self._last_reasoning: Optional[str] = None

    def _reset_if_new_day(self) -> None:
        today = date.today().isoformat()
        if self._last_call_date != today:
            self._last_call_date = today
            self._calls_today = 0

    def _within_interval(self) -> bool:
        if self._last_call_time is None:
            return False
        delta = (datetime.now(timezone.utc) - self._last_call_time).total_seconds()
        return delta < max(1, AI_RANKING_INTERVAL_HOURS) * 3600

    def get_ranked_symbols(self, default_symbols: List[str]) -> List[str]:
        if self._last_ranking and _valid_ranking(self._last_ranking, default_symbols):
            return list(self._last_ranking)
        return list(default_symbols)

    def validate_scheduler_decision(self, trigger: str) -> None:
        self._reset_if_new_day()

        logger.info(
            "AI_ADVISOR_RANKING_TRIGGERED | trigger=%s ts=%s calls_today=%s",
            trigger,
            datetime.now(timezone.utc).isoformat(),
            self._calls_today,
        )

        if not AI_ADVISOR_ENABLED:
            logger.info(
                "AI_ADVISOR_RANKING_SKIPPED | trigger=%s ts=%s calls_today=%s reason=disabled",
                trigger,
                datetime.now(timezone.utc).isoformat(),
                self._calls_today,
            )
            return

        if self._within_interval():
            logger.info(
                "AI_ADVISOR_RANKING_SKIPPED | trigger=%s ts=%s calls_today=%s reason=interval_limit",
                trigger,
                datetime.now(timezone.utc).isoformat(),
                self._calls_today,
            )
            return

        if self._calls_today >= AI_MAX_CALLS_PER_DAY:
            logger.info(
                "AI_ADVISOR_RANKING_SKIPPED | trigger=%s ts=%s calls_today=%s reason=max_calls_reached",
                trigger,
                datetime.now(timezone.utc).isoformat(),
                self._calls_today,
            )
            return

        logger.info(
            "AI_ADVISOR_RANKING_SKIPPED | trigger=%s ts=%s calls_today=%s reason=validation_mode_no_call",
            trigger,
            datetime.now(timezone.utc).isoformat(),
            self._calls_today,
        )

    def trigger_ranking_from_market_data(self, trigger: str) -> Optional[Dict[str, Any]]:
        self._reset_if_new_day()

        logger.info(
            "AI_ADVISOR_RANKING_TRIGGERED | trigger=%s ts=%s calls_today=%s",
            trigger,
            datetime.now(timezone.utc).isoformat(),
            self._calls_today,
        )

        if not AI_ADVISOR_ENABLED:
            logger.info(
                "AI_ADVISOR_RANKING_SKIPPED | trigger=%s ts=%s calls_today=%s reason=disabled",
                trigger,
                datetime.now(timezone.utc).isoformat(),
                self._calls_today,
            )
            return None

        if self._within_interval():
            logger.info(
                "AI_ADVISOR_RANKING_SKIPPED | trigger=%s ts=%s calls_today=%s reason=interval_limit",
                trigger,
                datetime.now(timezone.utc).isoformat(),
                self._calls_today,
            )
            return None

        if self._calls_today >= AI_MAX_CALLS_PER_DAY:
            logger.info(
                "AI_ADVISOR_RANKING_SKIPPED | trigger=%s ts=%s calls_today=%s reason=max_calls_reached",
                trigger,
                datetime.now(timezone.utc).isoformat(),
                self._calls_today,
            )
            return None

        symbol_features = _build_ai_features_from_market_data()
        if symbol_features is None:
            self._last_error = "feature_build_failed"
            logger.error(
                "AI_ADVISOR_RANKING_FAILED | trigger=%s ts=%s calls_today=%s error=%s",
                trigger,
                datetime.now(timezone.utc).isoformat(),
                self._calls_today,
                self._last_error,
            )
            get_observability().record_ai_error(self._last_error)
            return None
        return self.rank_with_ai(symbol_features, trigger)

    def rank_with_ai(self, symbol_features: Dict[str, Dict[str, Any]], trigger: str) -> Optional[Dict[str, Any]]:
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            self._last_error = "missing_api_key"
            logger.error(
                "AI_ADVISOR_RANKING_FAILED | trigger=%s ts=%s calls_today=%s error=%s",
                trigger,
                datetime.now(timezone.utc).isoformat(),
                self._calls_today,
                self._last_error,
            )
            get_observability().record_ai_error(self._last_error)
            return None

        advisor = AIAdvisor()
        observability = get_observability()
        self._last_call_time = datetime.now(timezone.utc)
        self._calls_today += 1
        observability.record_ai_attempt(self._calls_today, self._last_call_time)

        try:
            logger.info(
                "AI_ADVISOR_REQUEST | trigger=%s ts=%s symbols=%s",
                trigger,
                datetime.now(timezone.utc).isoformat(),
                ",".join(sorted(symbol_features.keys())),
            )
            result = advisor.rank_universe(symbol_features)
            parsed = result.get("parsed", {})
            ranked = parsed.get("ranked_symbols", [])
            reasoning = parsed.get("reasoning", "")

            allowlist = _get_allowlist(load_crypto_config(get_scope()))
            normalized = _normalize_ranked_symbols(ranked, allowlist)
            if normalized is None:
                self._last_error = "invalid_symbols"
                logger.error(
                    "AI_ADVISOR_RANKING_FAILED | trigger=%s ts=%s calls_today=%s error=%s",
                    trigger,
                    datetime.now(timezone.utc).isoformat(),
                    self._calls_today,
                    self._last_error,
                )
                observability.record_ai_error(self._last_error)
                return None

            self._last_success_time = datetime.now(timezone.utc)
            self._last_error = None
            self._last_ranking = list(normalized)
            self._last_reasoning = reasoning
            observability.record_ai_success(self._last_success_time, normalized, reasoning)

            logger.info(
                "AI_ADVISOR_RESPONSE | trigger=%s ts=%s response_id=%s model=%s raw=%s",
                trigger,
                self._last_success_time.isoformat(),
                result.get("response_id") or "NONE",
                result.get("model") or "UNKNOWN",
                result.get("raw", ""),
            )

            logger.info(
                "AI_ADVISOR_REASONING | trigger=%s ts=%s reasoning=%s",
                trigger,
                self._last_success_time.isoformat(),
                reasoning,
            )

            _write_ai_call_log(
                {
                    "ts": self._last_success_time.isoformat(),
                    "trigger": trigger,
                    "response_id": result.get("response_id"),
                    "model": result.get("model"),
                    "symbols": sorted(symbol_features.keys()),
                    "ranked_symbols": normalized,
                    "reasoning": reasoning,
                    "raw_response": result.get("raw", ""),
                }
            )

            logger.info(
                "AI_ADVISOR_RANKING_SUCCESS | trigger=%s ts=%s calls_today=%s ranked_symbols=%s",
                trigger,
                self._last_success_time.isoformat(),
                self._calls_today,
                ",".join(normalized),
            )
            return {"ranked_symbols": normalized, "reasoning": reasoning}
        except Exception as e:
            self._last_error = str(e)
            logger.error(
                "AI_ADVISOR_RANKING_FAILED | trigger=%s ts=%s calls_today=%s error=%s",
                trigger,
                datetime.now(timezone.utc).isoformat(),
                self._calls_today,
                self._last_error,
            )
            observability.record_ai_error(self._last_error)
            _write_ai_call_log(
                {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "trigger": trigger,
                    "response_id": None,
                    "model": advisor.model,
                    "symbols": sorted(symbol_features.keys()),
                    "ranked_symbols": None,
                    "reasoning": None,
                    "raw_response": None,
                    "error": self._last_error,
                }
            )
            return None


def _write_ai_call_log(payload: Dict[str, Any]) -> None:
    try:
        scope = get_scope()
        logs_dir = Path(get_scope_path(scope, "logs"))
        logs_dir.mkdir(parents=True, exist_ok=True)
        log_path = logs_dir / "ai_advisor_calls.jsonl"
        with log_path.open("a") as f:
            f.write(json.dumps(payload) + "\n")
    except Exception as e:
        logger.error("AI_ADVISOR_LOG_WRITE_FAILED | error=%s", e)


def _get_allowlist(crypto_config: Dict[str, Any]) -> List[str]:
    allowlist = crypto_config.get("UNIVERSE_ALLOWLIST") or crypto_config.get("CRYPTO_UNIVERSE")
    if not allowlist:
        allowlist = _DEFAULT_ALLOWLIST
    return validate_crypto_universe_symbols(allowlist)


def _normalize_ranked_symbols(ranked: Any, allowlist: List[str]) -> Optional[List[str]]:
    if not isinstance(ranked, list):
        return None
    allowed_set = set(allowlist)
    seen = set()
    filtered = []
    for symbol in ranked:
        if symbol in allowed_set and symbol not in seen:
            filtered.append(symbol)
            seen.add(symbol)
    for symbol in allowlist:
        if symbol not in seen:
            filtered.append(symbol)
            seen.add(symbol)
    if len(filtered) != len(allowlist):
        return None
    return filtered


def _valid_ranking(ranked: List[str], allowlist: List[str]) -> bool:
    if not isinstance(ranked, list) or len(ranked) != len(allowlist):
        return False
    ranked_set = set(ranked)
    return ranked_set == set(allowlist)


def _build_ai_features_from_market_data() -> Optional[Dict[str, Dict[str, Any]]]:
    scope = get_scope()
    crypto_config = load_crypto_config(scope)
    canonical = _get_allowlist(crypto_config)

    execution_interval = str(crypto_config.get("EXECUTION_CANDLE_INTERVAL", "5m"))
    if execution_interval != "5m":
        logger.error(
            "AI_ADVISOR_RANKING_FAILED | reason=invalid_execution_interval interval=%s",
            execution_interval,
        )
        return None

    execution_lookback = int(crypto_config.get("EXECUTION_LOOKBACK_BARS", 500))
    enable_cache = bool(crypto_config.get("ENABLE_OHLC_CACHE", True))
    max_staleness = crypto_config.get("MAX_OHLC_STALENESS_SECONDS", None)
    if isinstance(max_staleness, str) and max_staleness.strip().lower() == "auto":
        max_staleness = None

    provider = KrakenMarketDataProvider(
        scope=scope,
        config=KrakenOHLCConfig(
            interval=execution_interval,
            enable_ws=bool(crypto_config.get("ENABLE_WS_MARKETDATA", False)),
            cache_enabled=enable_cache,
            max_staleness_seconds=max_staleness,
        ),
    )

    features: Dict[str, Dict[str, Any]] = {}
    for symbol in canonical:
        bars = provider.fetch_ohlcv(symbol, execution_lookback)
        if bars is None or bars.empty:
            logger.error("AI_ADVISOR_RANKING_FAILED | reason=missing_data symbol=%s", symbol)
            return None
        try:
            ctx = build_execution_features(symbol, bars)
        except Exception as e:
            logger.error("AI_ADVISOR_RANKING_FAILED | reason=feature_error symbol=%s error=%s", symbol, e)
            return None

        ctx_dict = ctx.__dict__
        features[symbol] = {
            "timestamp_utc": _format_ai_timestamp(ctx_dict.get("timestamp_utc")),
            "close": ctx_dict.get("close"),
            "sma_20": ctx_dict.get("sma_20"),
            "sma_50": ctx_dict.get("sma_50"),
            "sma_200": ctx_dict.get("sma_200"),
            "trend_strength": ctx_dict.get("trend_strength"),
            "momentum": ctx_dict.get("momentum"),
            "atr_pct": ctx_dict.get("atr_pct"),
            "bb_width": ctx_dict.get("bb_width"),
            "volume_ratio": ctx_dict.get("volume_ratio"),
            "distance_from_sma20_pct": ctx_dict.get("distance_from_sma20_pct"),
            "rsi_14": ctx_dict.get("rsi_14"),
        }

    return features


def _format_ai_timestamp(value) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    try:
        return datetime.fromisoformat(str(value)).isoformat()
    except Exception:
        return None


_AI_RUNNER: Optional[AIAdvisorRunner] = None


def get_ai_runner() -> AIAdvisorRunner:
    global _AI_RUNNER
    if _AI_RUNNER is None:
        _AI_RUNNER = AIAdvisorRunner()
    return _AI_RUNNER
