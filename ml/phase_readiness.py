"""
ML Phase Readiness Evaluator.

CRITICAL RULES:
- RECOMMEND-ONLY: Never auto-promotes phases
- Runs OFFLINE in PAPER container after market close
- Outputs phase_readiness.json with recommendations
- Human reviews and manually updates config if they agree

This module helps humans make informed phase promotion decisions.
It NEVER acts automatically.
"""

import json
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict

from config.scope import get_scope
from config.scope_paths import get_scope_path
from config.ml_phase import MLLearningPhase, get_ml_phase_config

logger = logging.getLogger(__name__)


@dataclass
class PhaseReadinessMetrics:
    """Metrics used to evaluate phase readiness."""
    
    # Trade counts
    total_paper_trades: int = 0
    total_live_trades: int = 0
    
    # Performance comparison
    paper_win_rate: float = 0.0
    live_win_rate: float = 0.0
    win_rate_delta: float = 0.0  # live - paper
    
    paper_avg_return: float = 0.0
    live_avg_return: float = 0.0
    return_delta: float = 0.0  # live - paper
    
    paper_sharpe: float = 0.0
    live_sharpe: float = 0.0
    
    paper_max_drawdown: float = 0.0
    live_max_drawdown: float = 0.0
    drawdown_delta: float = 0.0  # live - paper
    
    # Execution quality
    avg_slippage_pct: float = 0.0
    slippage_stability: float = 0.0  # Low std = stable
    
    # Operational health
    reconciliation_error_count: int = 0
    consecutive_stable_days: int = 0
    emergency_halt_count: int = 0
    
    # Time metrics
    days_since_live_launch: int = 0
    last_evaluation_date: Optional[str] = None


@dataclass
class PhaseReadinessRecommendation:
    """Phase promotion recommendation (informational only)."""
    
    current_phase: str
    recommended_next_phase: Optional[str]
    confidence: str  # "LOW", "MEDIUM", "HIGH"
    should_promote: bool
    reasons: List[str]
    blockers: List[str]
    metrics: PhaseReadinessMetrics
    timestamp: str
    recommendation_only: bool = True  # Always True (never auto-promotes)
    
    def to_dict(self) -> Dict:
        """Serialize to dict."""
        result = asdict(self)
        result["metrics"] = asdict(self.metrics)
        return result


class PhaseReadinessEvaluator:
    """
    Evaluate ML phase promotion readiness.
    
    CRITICAL: This is RECOMMEND-ONLY. Never auto-promotes.
    
    Runs in PAPER container after market close.
    Outputs recommendations for human review.
    """
    
    def __init__(self, paper_ledger=None, live_ledger=None):
        """
        Initialize evaluator.
        
        Args:
            paper_ledger: Paper trading ledger
            live_ledger: Live trading ledger (if exists)
        """
        self.paper_ledger = paper_ledger
        self.live_ledger = live_ledger
        
        scope = get_scope()
        state_dir = get_scope_path(scope, "state")
        self.readiness_file = state_dir / "phase_readiness.json"
        
        self.phase_config = get_ml_phase_config()
        self.current_phase = self.phase_config.get_phase()
    
    def evaluate(self) -> PhaseReadinessRecommendation:
        """
        Evaluate phase promotion readiness.
        
        Returns:
            PhaseReadinessRecommendation (informational only)
        """
        logger.info("=" * 80)
        logger.info("ML PHASE READINESS EVALUATION")
        logger.info("=" * 80)
        logger.info(f"Current Phase: {self.current_phase.value}")
        logger.info("")
        logger.info("NOTE: This is a RECOMMENDATION ONLY.")
        logger.info("      Phase changes require MANUAL config update + restart.")
        logger.info("=" * 80)
        
        # Collect metrics
        metrics = self._collect_metrics()
        
        # Evaluate readiness for next phase
        recommendation = self._evaluate_readiness(metrics)
        
        # Persist recommendation
        self._save_recommendation(recommendation)
        
        # Log summary
        self._log_recommendation(recommendation)
        
        return recommendation
    
    def _collect_metrics(self) -> PhaseReadinessMetrics:
        """Collect metrics from paper and live ledgers."""
        metrics = PhaseReadinessMetrics()
        
        # Paper ledger metrics
        if self.paper_ledger:
            paper_trades = [t for t in self.paper_ledger.get_all_trades() if t.exit_timestamp]
            metrics.total_paper_trades = len(paper_trades)
            
            if paper_trades:
                paper_returns = [(t.exit_price - t.entry_price) / t.entry_price for t in paper_trades]
                metrics.paper_win_rate = sum(1 for r in paper_returns if r > 0) / len(paper_returns)
                metrics.paper_avg_return = sum(paper_returns) / len(paper_returns)
                
                # Simple drawdown calc (max cumulative loss)
                cumulative = 0
                max_cumulative = 0
                max_drawdown = 0
                for ret in paper_returns:
                    cumulative += ret
                    max_cumulative = max(max_cumulative, cumulative)
                    drawdown = max_cumulative - cumulative
                    max_drawdown = max(max_drawdown, drawdown)
                metrics.paper_max_drawdown = max_drawdown
        
        # Live ledger metrics
        if self.live_ledger:
            live_trades = [t for t in self.live_ledger.get_all_trades() if t.exit_timestamp]
            metrics.total_live_trades = len(live_trades)
            
            if live_trades:
                live_returns = [(t.exit_price - t.entry_price) / t.entry_price for t in live_trades]
                metrics.live_win_rate = sum(1 for r in live_returns if r > 0) / len(live_returns)
                metrics.live_avg_return = sum(live_returns) / len(live_returns)
                
                # Drawdown calc
                cumulative = 0
                max_cumulative = 0
                max_drawdown = 0
                for ret in live_returns:
                    cumulative += ret
                    max_cumulative = max(max_cumulative, cumulative)
                    drawdown = max_cumulative - cumulative
                    max_drawdown = max(max_drawdown, drawdown)
                metrics.live_max_drawdown = max_drawdown
        
        # Deltas
        metrics.win_rate_delta = metrics.live_win_rate - metrics.paper_win_rate
        metrics.return_delta = metrics.live_avg_return - metrics.paper_avg_return
        metrics.drawdown_delta = metrics.live_max_drawdown - metrics.paper_max_drawdown
        
        metrics.last_evaluation_date = datetime.now().isoformat()
        
        return metrics
    
    def _evaluate_readiness(self, metrics: PhaseReadinessMetrics) -> PhaseReadinessRecommendation:
        """
        Evaluate if system is ready for next phase.
        
        Args:
            metrics: Collected metrics
            
        Returns:
            Recommendation (INFORMATIONAL ONLY)
        """
        reasons = []
        blockers = []
        should_promote = False
        confidence = "LOW"
        next_phase = None
        
        if self.current_phase == MLLearningPhase.PHASE_1:
            # PHASE_1 → PHASE_2 criteria
            next_phase = "PHASE_2"
            
            # Criteria for PHASE_2 promotion
            if metrics.total_live_trades >= 100:
                reasons.append(f"✓ Sufficient live trades ({metrics.total_live_trades} >= 100)")
            else:
                blockers.append(f"✗ Need more live trades ({metrics.total_live_trades} < 100)")
            
            if metrics.reconciliation_error_count == 0:
                reasons.append("✓ No reconciliation errors")
            else:
                blockers.append(f"✗ Reconciliation errors detected: {metrics.reconciliation_error_count}")
            
            if metrics.consecutive_stable_days >= 15:
                reasons.append(f"✓ Stable operation ({metrics.consecutive_stable_days} days)")
            else:
                blockers.append(f"✗ Need more stable days ({metrics.consecutive_stable_days} < 15)")
            
            if abs(metrics.win_rate_delta) <= 0.1:  # Within 10%
                reasons.append(f"✓ Live vs paper win rates aligned (delta: {metrics.win_rate_delta:.1%})")
            else:
                blockers.append(f"⚠ Large win rate delta: {metrics.win_rate_delta:.1%}")
            
            if metrics.live_max_drawdown <= 1.5 * metrics.paper_max_drawdown:
                reasons.append("✓ Live drawdown within expected range")
            else:
                blockers.append("✗ Live drawdown exceeds expected range")
            
            # Decision
            if len(blockers) == 0:
                should_promote = True
                confidence = "HIGH"
            elif len(blockers) <= 2:
                confidence = "MEDIUM"
            
        elif self.current_phase == MLLearningPhase.PHASE_2:
            # PHASE_2 → PHASE_3 criteria
            next_phase = "PHASE_3"
            
            if metrics.total_live_trades >= 500:
                reasons.append(f"✓ Extensive live history ({metrics.total_live_trades} trades)")
            else:
                blockers.append(f"✗ Need more live trades ({metrics.total_live_trades} < 500)")
            
            if metrics.consecutive_stable_days >= 60:
                reasons.append(f"✓ Long-term stability ({metrics.consecutive_stable_days} days)")
            else:
                blockers.append(f"✗ Need more stable days ({metrics.consecutive_stable_days} < 60)")
            
            if metrics.emergency_halt_count == 0:
                reasons.append("✓ No emergency halts")
            else:
                blockers.append(f"✗ Emergency halts detected: {metrics.emergency_halt_count}")
            
            # Decision
            if len(blockers) == 0:
                should_promote = True
                confidence = "HIGH"
            elif len(blockers) <= 1:
                confidence = "MEDIUM"
        
        elif self.current_phase == MLLearningPhase.PHASE_3:
            # Already at mature phase
            next_phase = None
            reasons.append("✓ Already at mature phase (PHASE_3)")
            confidence = "N/A"
        
        return PhaseReadinessRecommendation(
            current_phase=self.current_phase.value,
            recommended_next_phase=next_phase,
            confidence=confidence,
            should_promote=should_promote,
            reasons=reasons,
            blockers=blockers,
            metrics=metrics,
            timestamp=datetime.now().isoformat(),
            recommendation_only=True,
        )
    
    def _save_recommendation(self, recommendation: PhaseReadinessRecommendation) -> None:
        """Save recommendation to file."""
        try:
            self.readiness_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.readiness_file, "w") as f:
                json.dump(recommendation.to_dict(), f, indent=2)
            logger.info(f"Recommendation saved: {self.readiness_file}")
        except Exception as e:
            logger.warning(f"Could not save recommendation: {e}")
    
    def _log_recommendation(self, recommendation: PhaseReadinessRecommendation) -> None:
        """Log recommendation summary."""
        logger.info("")
        logger.info("=" * 80)
        logger.info("PHASE READINESS RECOMMENDATION")
        logger.info("=" * 80)
        logger.info(f"Current Phase:     {recommendation.current_phase}")
        logger.info(f"Recommended Next:  {recommendation.recommended_next_phase or 'None (already mature)'}")
        logger.info(f"Confidence:        {recommendation.confidence}")
        logger.info(f"Should Promote:    {'YES' if recommendation.should_promote else 'NO'}")
        logger.info("")
        
        if recommendation.reasons:
            logger.info("REASONS FOR PROMOTION:")
            for reason in recommendation.reasons:
                logger.info(f"  {reason}")
        
        if recommendation.blockers:
            logger.info("")
            logger.info("BLOCKERS:")
            for blocker in recommendation.blockers:
                logger.info(f"  {blocker}")
        
        logger.info("")
        logger.info("KEY METRICS:")
        logger.info(f"  Paper trades:    {recommendation.metrics.total_paper_trades}")
        logger.info(f"  Live trades:     {recommendation.metrics.total_live_trades}")
        logger.info(f"  Win rate delta:  {recommendation.metrics.win_rate_delta:.2%} (live - paper)")
        logger.info(f"  Stable days:     {recommendation.metrics.consecutive_stable_days}")
        logger.info("")
        logger.info("⚠ THIS IS A RECOMMENDATION ONLY")
        logger.info("  → Human must review and decide")
        logger.info("  → To promote: update ML_LEARNING_PHASE config + restart paper container")
        logger.info("  → System will NEVER auto-promote")
        logger.info("=" * 80)
