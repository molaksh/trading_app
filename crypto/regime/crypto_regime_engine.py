"""
Crypto regime engine - PRODUCTION IMPLEMENTATION.

Detects market regime based on 4H candle metrics:
- Realized volatility (annualized)
- Trend strength (SMA slopes)
- Drawdown severity

TIMEFRAME: 4H candles ONLY (no 5m contamination)
OUTPUT: {RISK_ON, NEUTRAL, RISK_OFF, PANIC}
DETERMINISTIC: Same candles → same regime
"""

import logging
from enum import Enum
from typing import Dict, Optional
from dataclasses import dataclass

from crypto.features.regime_features import RegimeFeatureContext

logger = logging.getLogger(__name__)


class MarketRegime(Enum):
    """Market regime classification."""
    RISK_ON = "risk_on"          # Bull market, low volatility, uptrend
    NEUTRAL = "neutral"           # Sideways, moderate volatility
    RISK_OFF = "risk_off"         # Bear market, high volatility, downtrend
    PANIC = "panic"               # Crash, extreme volatility, severe drawdown


@dataclass
class RegimeThresholds:
    """Configurable thresholds for regime detection."""
    # Volatility thresholds (annualized %)
    vol_low: float = 30.0  # Below this = low vol
    vol_high: float = 60.0  # Above this = high vol
    vol_extreme: float = 100.0  # Above this = extreme vol
    
    # Trend thresholds (SMA slope % per period)
    trend_pos: float = 0.5  # Above this = uptrend
    trend_neg: float = -0.5  # Below this = downtrend
    trend_strong_neg: float = -2.0  # Below this = strong downtrend
    
    # Drawdown thresholds (%)
    drawdown_mild: float = -5.0  # Above this = mild drawdown
    drawdown_moderate: float = -15.0  # Below this = moderate drawdown
    drawdown_severe: float = -30.0  # Below this = severe drawdown
    
    # Hysteresis (consecutive confirmations needed for regime change)
    hysteresis_count: int = 2


@dataclass
class RegimeSignal:
    """Regime analysis result."""
    regime: MarketRegime
    previous_regime: Optional[MarketRegime]
    regime_changed: bool
    
    # Scores
    volatility: float  # Annualized volatility
    trend_slope: float  # SMA slope
    drawdown: float  # Current drawdown %
    
    # Confidence
    confidence: float  # 0.0-1.0
    
    # Rationale
    rationale: str
    
    # Metadata
    timestamp_utc: str
    symbol: str
    confirmations: int  # Consecutive periods in this regime


class CryptoRegimeEngine:
    """
    Analyzes 4H market conditions and determines trading regime.
    
    DETERMINISTIC: Same input features → same regime output
    CONFIGURABLE: All thresholds loaded from config
    HYSTERESIS: Requires N consecutive confirmations to change regime
    """
    
    def __init__(self, thresholds: RegimeThresholds = None):
        """
        Initialize regime engine with configurable thresholds.
        
        Args:
            thresholds: RegimeThresholds or None (uses defaults)
        """
        self.thresholds = thresholds or RegimeThresholds()
        self.current_regime: Optional[MarketRegime] = None
        self.confirmation_counter = 0
        self.pending_regime: Optional[MarketRegime] = None
        
        logger.info("CryptoRegimeEngine initialized (REAL IMPLEMENTATION)")
        logger.info(f"  Volatility thresholds: low={self.thresholds.vol_low}%, high={self.thresholds.vol_high}%, extreme={self.thresholds.vol_extreme}%")
        logger.info(f"  Trend thresholds: pos={self.thresholds.trend_pos}%, neg={self.thresholds.trend_neg}%, strong_neg={self.thresholds.trend_strong_neg}%")
        logger.info(f"  Drawdown thresholds: mild={self.thresholds.drawdown_mild}%, moderate={self.thresholds.drawdown_moderate}%, severe={self.thresholds.drawdown_severe}%")
        logger.info(f"  Hysteresis: {self.thresholds.hysteresis_count} consecutive confirmations required")
    
    def analyze(self, regime_features: RegimeFeatureContext) -> RegimeSignal:
        """
        Analyze 4H features and determine regime with hysteresis.
        
        Args:
            regime_features: RegimeFeatureContext from 4H candles
        
        Returns:
            RegimeSignal with regime classification and rationale
        """
        # Extract metrics
        vol = regime_features.realized_volatility_20
        trend = regime_features.trend_sma_slope_50
        drawdown = regime_features.drawdown_pct
        
        # Determine raw regime (before hysteresis)
        raw_regime, rationale = self._classify_regime(vol, trend, drawdown)
        
        # Apply hysteresis
        previous_regime = self.current_regime
        regime_changed = False
        
        if self.current_regime is None:
            # First call - initialize immediately
            self.current_regime = raw_regime
            self.confirmation_counter = 1
            regime_changed = True
        elif raw_regime == self.current_regime:
            # Same regime - reset pending
            self.pending_regime = None
            self.confirmation_counter += 1
        elif raw_regime == self.pending_regime:
            # Continued confirmation of pending regime
            self.confirmation_counter += 1
            if self.confirmation_counter >= self.thresholds.hysteresis_count:
                # Regime change confirmed
                previous_regime = self.current_regime
                self.current_regime = raw_regime
                self.pending_regime = None
                self.confirmation_counter = 1
                regime_changed = True
        else:
            # New pending regime
            self.pending_regime = raw_regime
            self.confirmation_counter = 1
        
        # Calculate confidence based on how clear the signals are
        confidence = self._calculate_confidence(vol, trend, drawdown)
        
        return RegimeSignal(
            regime=self.current_regime,
            previous_regime=previous_regime,
            regime_changed=regime_changed,
            volatility=vol,
            trend_slope=trend,
            drawdown=drawdown,
            confidence=confidence,
            rationale=rationale,
            timestamp_utc=regime_features.timestamp_utc.isoformat(),
            symbol=regime_features.symbol,
            confirmations=self.confirmation_counter,
        )
    
    def _classify_regime(self, vol: float, trend: float, drawdown: float) -> tuple:
        """
        Classify regime based on thresholds.
        
        Priority order: PANIC > RISK_OFF > RISK_ON > NEUTRAL
        """
        t = self.thresholds
        
        # PANIC: Severe drawdown alone OR (extreme volatility + strong downtrend)
        if (drawdown <= t.drawdown_severe or
            (vol >= t.vol_extreme and trend <= t.trend_strong_neg)):
            return (MarketRegime.PANIC, 
                   f"PANIC: drawdown={drawdown:.1f}%, vol={vol:.1f}%, trend={trend:.2f}%")
        
        # RISK_OFF: Moderate drawdown OR high volatility OR downtrend
        if (drawdown <= t.drawdown_moderate or 
            vol >= t.vol_high or 
            trend <= t.trend_neg):
            return (MarketRegime.RISK_OFF,
                   f"RISK_OFF: drawdown={drawdown:.1f}%, vol={vol:.1f}%, trend={trend:.2f}%")
        
        # RISK_ON: Low volatility + uptrend + mild drawdown
        if (vol <= t.vol_low and 
            trend >= t.trend_pos and 
            drawdown >= t.drawdown_mild):
            return (MarketRegime.RISK_ON,
                   f"RISK_ON: vol={vol:.1f}% (low), trend={trend:.2f}% (up), drawdown={drawdown:.1f}% (mild)")
        
        # NEUTRAL: Everything else
        return (MarketRegime.NEUTRAL,
               f"NEUTRAL: vol={vol:.1f}%, trend={trend:.2f}%, drawdown={drawdown:.1f}%")
    
    def _calculate_confidence(self, vol: float, trend: float, drawdown: float) -> float:
        """
        Calculate confidence in regime classification.
        
        Higher confidence when signals are far from thresholds.
        """
        # Simple heuristic: normalize distances from thresholds
        # This is a placeholder - could be improved with more sophisticated logic
        confidence = min(1.0, 0.5 + abs(trend) / 10.0)
        return confidence
    
    def get_current_regime(self) -> Optional[MarketRegime]:
        """Get the current confirmed regime."""
        return self.current_regime
    
    def reset(self):
        """Reset regime state (for testing or reinitialization)."""
        self.current_regime = None
        self.confirmation_counter = 0
        self.pending_regime = None
        logger.info("Regime engine reset")
