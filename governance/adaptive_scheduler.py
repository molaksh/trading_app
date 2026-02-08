#!/usr/bin/env python3
"""
Adaptive Governance Scheduler

Triggers governance proposal generation based on market conditions,
not just a fixed weekly schedule.

Modes:
  NORMAL:    Weekly (default)
  VOLATILE:  2-3x per week (high volatility detected)
  REACTIVE:  On-demand (market event detected)
  EMERGENCY: Daily (crisis detected)
"""

import json
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, List, Tuple


class AdaptiveScheduler:
    """Determine governance frequency based on market conditions."""

    def __init__(self, logs_path: str = "logs"):
        self.logs_path = Path(logs_path)
        self.paper_summaries = self._read_summaries("paper.kraken.crypto.global")
        self.live_summaries = self._read_summaries("live.kraken.crypto.global")

    def _read_summaries(self, scope: str) -> List[Dict[str, Any]]:
        """Read daily summaries for a scope."""
        scope_dir = scope.replace(".", "_")
        summary_file = self.logs_path / scope_dir / "logs" / "daily_summary.jsonl"

        if not summary_file.exists():
            return []

        summaries = []
        try:
            with open(summary_file) as f:
                for line in f:
                    if line.strip():
                        summaries.append(json.loads(line))
        except:
            pass

        return summaries[-7:]  # Last 7 days

    def analyze_market_conditions(self) -> Dict[str, Any]:
        """Analyze current market conditions."""
        analysis = {
            "volatility_level": self._calculate_volatility(),
            "drawdown_level": self._calculate_max_drawdown(),
            "missed_signals_trend": self._analyze_missed_signals(),
            "performance_trend": self._analyze_performance(),
            "data_quality": self._analyze_data_quality(),
        }
        return analysis

    def _calculate_volatility(self) -> str:
        """Calculate volatility level: LOW / MEDIUM / HIGH / EXTREME."""
        if not self.live_summaries:
            return "UNKNOWN"

        drawdowns = [s.get("max_drawdown", 0) for s in self.live_summaries[-3:]]
        avg_drawdown = sum(abs(d) for d in drawdowns) / len(drawdowns) if drawdowns else 0

        if avg_drawdown > 10:
            return "EXTREME"  # > 10% max drawdown
        elif avg_drawdown > 5:
            return "HIGH"  # > 5% max drawdown
        elif avg_drawdown > 2:
            return "MEDIUM"  # > 2% max drawdown
        else:
            return "LOW"

    def _calculate_max_drawdown(self) -> float:
        """Get maximum drawdown from recent data."""
        if not self.live_summaries:
            return 0.0

        return max(abs(s.get("max_drawdown", 0)) for s in self.live_summaries[-3:])

    def _analyze_missed_signals(self) -> str:
        """Analyze trend in missed signals: STABLE / INCREASING / SPIKING."""
        if not self.paper_summaries or len(self.paper_summaries) < 2:
            return "UNKNOWN"

        recent = [s.get("trades_skipped", 0) for s in self.paper_summaries[-3:]]
        older = [s.get("trades_skipped", 0) for s in self.paper_summaries[-6:-3]]

        avg_recent = sum(recent) / len(recent) if recent else 0
        avg_older = sum(older) / len(older) if older else 0

        if avg_recent == 0:
            return "STABLE"

        increase_pct = ((avg_recent - avg_older) / avg_older * 100) if avg_older > 0 else 0

        if increase_pct > 50:
            return "SPIKING"  # > 50% increase
        elif increase_pct > 20:
            return "INCREASING"  # > 20% increase
        else:
            return "STABLE"

    def _analyze_performance(self) -> str:
        """Analyze performance trend: IMPROVING / STABLE / DEGRADING / CRITICAL."""
        if not self.paper_summaries or len(self.paper_summaries) < 2:
            return "UNKNOWN"

        recent_pnl = [s.get("realized_pnl", 0) for s in self.paper_summaries[-3:]]
        older_pnl = [s.get("realized_pnl", 0) for s in self.paper_summaries[-6:-3]]

        avg_recent = sum(recent_pnl) / len(recent_pnl) if recent_pnl else 0
        avg_older = sum(older_pnl) / len(older_pnl) if older_pnl else 0

        if avg_recent < -500:  # Large loss
            return "CRITICAL"
        elif avg_recent < avg_older * 0.7:  # 30% drop
            return "DEGRADING"
        elif avg_recent > avg_older * 1.2:  # 20% gain
            return "IMPROVING"
        else:
            return "STABLE"

    def _analyze_data_quality(self) -> str:
        """Analyze data quality: GOOD / DEGRADED / CRITICAL."""
        if not self.live_summaries:
            return "UNKNOWN"

        data_issues = [s.get("data_issues", 0) for s in self.live_summaries[-3:]]
        recon_issues = [s.get("reconciliation_issues", 0) for s in self.live_summaries[-3:]]

        total_issues = sum(data_issues) + sum(recon_issues)

        if total_issues > 5:
            return "CRITICAL"
        elif total_issues > 2:
            return "DEGRADED"
        else:
            return "GOOD"

    def determine_governance_mode(self) -> Tuple[str, str, int]:
        """Determine governance mode and frequency.

        Returns:
            (mode, reason, hours_until_next_run)
        """
        conditions = self.analyze_market_conditions()

        volatility = conditions["volatility_level"]
        drawdown = conditions["drawdown_level"]
        missed_signals = conditions["missed_signals_trend"]
        performance = conditions["performance_trend"]
        data_quality = conditions["data_quality"]

        # EMERGENCY: Daily governance
        if (
            volatility == "EXTREME"
            or drawdown > 15
            or performance == "CRITICAL"
            or (missed_signals == "SPIKING" and data_quality != "CRITICAL")
        ):
            return (
                "EMERGENCY",
                f"Extreme conditions: volatility={volatility}, drawdown={drawdown:.1f}%, "
                f"performance={performance}",
                24,  # Run daily
            )

        # REACTIVE: Every 2 days
        if (
            volatility == "HIGH"
            or (5 < drawdown <= 15)
            or missed_signals == "INCREASING"
            or performance == "DEGRADING"
        ):
            return (
                "REACTIVE",
                f"Market stress: volatility={volatility}, drawdown={drawdown:.1f}%, "
                f"missed_signals={missed_signals}",
                48,  # Run every 2 days
            )

        # VOLATILE: Every 3 days
        if volatility == "MEDIUM" or (missed_signals == "INCREASING" and data_quality == "GOOD"):
            return (
                "VOLATILE",
                f"Elevated activity: volatility={volatility}, missed_signals={missed_signals}",
                72,  # Run every 3 days
            )

        # NORMAL: Weekly (default)
        return (
            "NORMAL",
            f"Market stable: volatility={volatility}, performance={performance}",
            168,  # Run weekly (7 days)
        )

    def print_status(self) -> None:
        """Print current governance status."""
        conditions = self.analyze_market_conditions()
        mode, reason, hours = self.determine_governance_mode()

        print("\n" + "=" * 80)
        print("ADAPTIVE GOVERNANCE SCHEDULER STATUS")
        print("=" * 80)

        print("\nMarket Conditions:")
        print(f"  Volatility:      {conditions['volatility_level']}")
        print(f"  Max Drawdown:    {conditions['drawdown_level']:.2f}%")
        print(f"  Missed Signals:  {conditions['missed_signals_trend']}")
        print(f"  Performance:     {conditions['performance_trend']}")
        print(f"  Data Quality:    {conditions['data_quality']}")

        print(f"\nGovernance Mode: {mode}")
        print(f"Reason: {reason}")
        print(f"Next run in: {hours} hours ({hours/24:.1f} days)")

        print("\nMode Meanings:")
        print("  NORMAL:    Weekly (calm markets)")
        print("  VOLATILE:  Every 3 days (elevated activity)")
        print("  REACTIVE:  Every 2 days (market stress)")
        print("  EMERGENCY: Daily (crisis mode)")

        print("\n" + "=" * 80)


def main():
    scheduler = AdaptiveScheduler()
    scheduler.print_status()


if __name__ == "__main__":
    main()
