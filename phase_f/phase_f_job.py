"""
Phase F Job Orchestrator: Execute epistemic intelligence pipeline.

Pipeline: Researcher → Critic → Reviewer → Verdict

This is the main job function that executes the full Phase F pipeline.
Runs independently as a scheduled job, produces verdicts for governance consumption.

Pattern: Mirrors governance/crypto_governance_job.py but for Phase F epistemic pipeline.
"""

import logging
import os
from datetime import datetime, timezone
from typing import Optional, Tuple

from phase_f.fetchers.news_api_fetcher import NewsAPIFetcher
from phase_f.fetchers.news_fetcher_multi_source import MultiSourceNewsFetcher
from phase_f.fetchers.kraken_signals_fetcher import KrakenSignalsFetcher
from phase_f.extractors.claim_extractor import ClaimExtractor
from phase_f.hypothesis_builder import HypothesisBuilder
from phase_f.agents.epistemic_critic import EpistemicCritic
from phase_f.agents.epistemic_reviewer import EpistemicReviewer
from phase_f.persistence import Phase_F_Persistence
from phase_f.safety_checks import SafetyValidator
from phase_f.logging import PhaseFLogger
from config.phase_f_settings import (
    PHASE_F_ENABLED,
    PHASE_F_KILL_SWITCH,
    PHASE_F_MAX_ARTICLES_PER_AGENT,
    PHASE_F_USE_MULTI_SOURCE_FETCHER,
)

logger = logging.getLogger(__name__)


class PhaseFJob:
    """
    Orchestrates Phase F epistemic intelligence pipeline.

    Pipeline stages:
    1. Researcher: Fetch news → Extract claims → Build hypotheses
    2. Critic: Challenge hypotheses → Generate counter-arguments
    3. Reviewer: Compare perspectives → Produce verdict

    All stages are append-only, independent, and read-only with no execution authority.
    """

    def __init__(
        self,
        scope: str = "crypto"
    ):
        """
        Initialize Phase F job.

        Args:
            scope: Scope name (default: "crypto")
        """
        self.scope = scope
        self.persistence = Phase_F_Persistence(root=f"persist/phase_f/{scope}")
        self.safety_validator = SafetyValidator()
        self.logger = PhaseFLogger(scope=scope)

        # Initialize components (all load config from environment)
        # Use multi-source fetcher if enabled, otherwise fall back to NewsAPI
        if PHASE_F_USE_MULTI_SOURCE_FETCHER:
            self.fetcher = MultiSourceNewsFetcher()
            logger.info(f"Using multi-source news fetcher: {self.fetcher.get_enabled_sources()}")
        else:
            self.fetcher = NewsAPIFetcher()
            logger.info("Using single-source NewsAPI fetcher")

        self.kraken_fetcher = KrakenSignalsFetcher()  # Market microstructure source
        self.claim_extractor = ClaimExtractor()
        self.hypothesis_builder = HypothesisBuilder()
        self.critic = EpistemicCritic()
        self.reviewer = EpistemicReviewer()

        logger.info(f"PhaseFJob initialized: scope={scope}")

    def run(self) -> bool:
        """
        Execute full Phase F pipeline.

        Returns:
            True if successful, False otherwise
        """
        if PHASE_F_KILL_SWITCH:
            logger.warning("PHASE_F_KILL_SWITCH enabled. Job aborted.")
            return False

        if not PHASE_F_ENABLED:
            logger.info("PHASE_F_ENABLED=false. Job skipped.")
            return False

        run_id = f"phase_f_run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        logger.info(f"Starting Phase F run: {run_id}")

        # Layer 1: Pipeline logging (structured)
        self.logger.log_run_start(run_id)

        try:
            # Stage 1: Researcher - Fetch & Analyze
            logger.info("Stage 1: Researcher (fetch news, extract claims, build hypotheses)")

            # Fetch articles (method depends on fetcher type)
            if isinstance(self.fetcher, MultiSourceNewsFetcher):
                articles = self.fetcher.fetch_all(limit=PHASE_F_MAX_ARTICLES_PER_AGENT)
            else:
                articles = self.fetcher.fetch_crypto_news(limit=PHASE_F_MAX_ARTICLES_PER_AGENT)

            if not articles:
                logger.warning("No articles fetched. Skipping run.")
                self.logger.log_run_complete(run_id, success=False, error="No articles fetched")
                return False

            all_claims = []
            for article in articles:
                claims = self.claim_extractor.extract_from_article(article)
                all_claims.extend(claims)

            researcher_hypotheses = self.hypothesis_builder.build_hypotheses(all_claims)

            logger.info(f"Stage 1 complete: {len(articles)} articles, {len(all_claims)} claims, {len(researcher_hypotheses)} hypotheses")
            self.logger.log_stage_complete("researcher", {
                "articles_fetched": len(articles),
                "claims_extracted": len(all_claims),
                "hypotheses_generated": len(researcher_hypotheses),
                "data_sources": ["NewsAPI (narrative)"]
            })

            # Stage 1b: Fetch Market Signals (Kraken microstructure)
            logger.info("Stage 1b: Market Signals (fetch Kraken ticker, order book, trades)")
            market_signals = self.kraken_fetcher.get_market_signals("BTC")

            if market_signals:
                logger.info(f"Market signals fetched: {market_signals.get('overall_signal', 'UNKNOWN')}")
                self.logger.log_stage_complete("market_signals", {
                    "symbol": market_signals.get("symbol"),
                    "volume_24h": market_signals.get("ticker", {}).get("volume_24h", 0),
                    "bid_ask_spread": market_signals.get("ticker", {}).get("bid_ask_spread_pct", 0),
                    "order_book_imbalance": market_signals.get("order_book", {}).get("imbalance_ratio", 0),
                    "recent_trades": len(market_signals.get("trades", [])),
                    "overall_signal": market_signals.get("overall_signal", "UNKNOWN")
                })
            else:
                logger.warning("Could not fetch market signals (Kraken API may be unavailable)")

            if not researcher_hypotheses:
                logger.warning("No hypotheses generated. Skipping run.")
                self.logger.log_run_complete(run_id, success=False, error="No hypotheses generated")
                return False

            # Stage 2: Critic - Challenge
            logger.info("Stage 2: Critic (challenge hypotheses)")
            all_challenges = []
            for hypothesis in researcher_hypotheses:
                challenges = self.critic.challenge_hypothesis(hypothesis)
                all_challenges.extend(challenges)

            logger.info(f"Stage 2 complete: {len(all_challenges)} challenges generated")
            self.logger.log_stage_complete("critic", {
                "hypotheses_challenged": len(researcher_hypotheses),
                "challenges_generated": len(all_challenges)
            })

            # Stage 3: Reviewer - Synthesize
            logger.info("Stage 3: Reviewer (produce verdict)")

            # Get current regime from latest daily summary
            current_regime, regime_confidence = self._get_current_regime()

            verdict = self.reviewer.produce_verdict(
                researcher_hypotheses,
                all_challenges,
                current_regime=current_regime,
                current_regime_confidence=regime_confidence
            )

            # Validate verdict
            self.safety_validator.validate_verdict(verdict)

            logger.info(f"Stage 3 complete: verdict={verdict.verdict.value}, regime_confidence={verdict.regime_confidence}")
            self.logger.log_stage_complete("reviewer", {
                "verdict": verdict.verdict.value,
                "regime_confidence": verdict.regime_confidence,
                "narrative_consistency": verdict.narrative_consistency.value
            })

            # Stage 4: Persist verdict
            logger.info("Stage 4: Persisting verdict")
            self.persistence.append_verdict(verdict, run_id)

            # Layer 3: Human audit logging
            self.logger.log_verdict_reasoning(run_id, verdict)

            # Success
            self.logger.log_run_complete(run_id, success=True)
            logger.info(f"Phase F run {run_id} completed successfully. Verdict: {verdict.verdict.value}")
            return True

        except Exception as e:
            logger.error(f"Phase F run {run_id} failed: {e}", exc_info=True)
            self.logger.log_run_complete(run_id, success=False, error=str(e))
            return False

    def _get_current_regime(self) -> Tuple[str, float]:
        """
        Get current regime from daily summaries.

        Returns:
            (regime_name, confidence)
        """
        try:
            from ops_agent.summary_reader import SummaryReader

            reader = SummaryReader()
            latest = reader.get_latest_summary("paper.kraken.crypto.global")

            if latest:
                regime = latest.get("current_regime", "UNKNOWN")
                confidence = latest.get("regime_confidence", 0.5)
                logger.debug(f"Current regime from summaries: {regime} (confidence: {confidence})")
                return (regime, confidence)

        except Exception as e:
            logger.warning(f"Failed to get current regime: {e}")

        return ("UNKNOWN", 0.5)


def run_phase_f_job(scope: str = "crypto") -> bool:
    """
    Top-level function to run Phase F job.

    Used by scheduler and CLI entry points.

    Args:
        scope: Scope name (default: "crypto")

    Returns:
        True if successful, False otherwise
    """
    job = PhaseFJob(scope=scope)
    return job.run()
