"""
Read and parse daily summary JSONL files from paper and live scopes.

Provides immutable access to trading summaries for governance analysis.
"""

import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta


class SummaryReader:
    """Read daily summaries from trading scopes."""

    def __init__(self, logs_base_path: str = "logs"):
        """
        Initialize summary reader.

        Args:
            logs_base_path: Base logs directory (usually 'logs')
        """
        self.logs_base = Path(logs_base_path)

    def get_summary_path(self, scope: str) -> Path:
        """
        Get path to daily_summary.jsonl for a scope.

        Scopes like "live.kraken.crypto.global" map to:
          logs/live_kraken_crypto_global/logs/daily_summary.jsonl

        Args:
            scope: Scope string (e.g., "live.kraken.crypto.global")

        Returns:
            Path to daily_summary.jsonl
        """
        # Convert dots to underscores: "live.kraken.crypto.global" -> "live_kraken_crypto_global"
        scope_dir = scope.replace(".", "_")
        summary_path = self.logs_base / scope_dir / "logs" / "daily_summary.jsonl"
        return summary_path

    def read_summaries(
        self,
        scope: str,
        lookback_days: int = 7
    ) -> List[Dict[str, Any]]:
        """
        Read daily summaries for a scope over lookback period.

        Args:
            scope: Scope string
            lookback_days: Number of days to read (most recent N days)

        Returns:
            List of summary dicts, chronologically ordered
        """
        summary_path = self.get_summary_path(scope)

        if not summary_path.exists():
            return []

        summaries = []
        try:
            with open(summary_path) as f:
                for line in f:
                    if line.strip():
                        summary = json.loads(line)
                        summaries.append(summary)
        except (json.JSONDecodeError, IOError) as e:
            # Log but don't crash - governance should be resilient
            print(f"Warning: Error reading {summary_path}: {e}")
            return []

        # Filter by date range
        if lookback_days > 0:
            cutoff_date = (datetime.now() - timedelta(days=lookback_days)).date()
            summaries = [
                s for s in summaries
                if "date" in s and s["date"] >= str(cutoff_date)
            ]

        return summaries

    def get_latest_summary(self, scope: str) -> Optional[Dict[str, Any]]:
        """
        Get most recent summary for a scope.

        Args:
            scope: Scope string

        Returns:
            Latest summary dict or None if no summaries exist
        """
        summaries = self.read_summaries(scope, lookback_days=30)
        if not summaries:
            return None
        return summaries[-1]  # Last entry is most recent

    def analyze_scan_coverage(self, summaries: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Analyze scan coverage metrics across summaries.

        Args:
            summaries: List of summary dicts

        Returns:
            Dict with scan metrics:
              - total_days: Number of days with data
              - avg_scan_symbols: Average symbols scanned per day
              - never_scanned: Symbols never scanned (empty if AI ranking not available)
              - scan_starvation: Symbols with very few scans
        """
        if not summaries:
            return {
                "total_days": 0,
                "avg_scan_symbols": 0.0,
                "never_scanned": [],
                "scan_starvation": [],
            }

        # Extract AI ranking info if present
        scan_counts = {}
        for summary in summaries:
            if "ai_last_ranking" in summary and summary["ai_last_ranking"]:
                ranking = summary["ai_last_ranking"]
                if "ranked_symbols" in ranking:
                    for symbol in ranking["ranked_symbols"]:
                        scan_counts[symbol] = scan_counts.get(symbol, 0) + 1

        total_days = len(summaries)
        avg_scan_symbols = len(scan_counts) / total_days if total_days > 0 else 0

        # Identify starvation (scanned very few times)
        starvation_threshold = max(1, total_days // 4)  # Less than 25% of days
        scan_starvation = [
            s for s, count in scan_counts.items()
            if count < starvation_threshold
        ]

        return {
            "total_days": total_days,
            "avg_scan_symbols": avg_scan_symbols,
            "never_scanned": [],  # Only populated if data available
            "scan_starvation": scan_starvation,
            "scan_counts": scan_counts,
        }

    def extract_performance_metrics(
        self,
        summaries: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Extract performance metrics from summaries.

        Args:
            summaries: List of summary dicts

        Returns:
            Performance metrics dict
        """
        if not summaries:
            return {
                "total_trades": 0,
                "trades_skipped": 0,
                "total_pnl": 0.0,
                "max_drawdown": 0.0,
                "data_issues": 0,
            }

        total_trades = sum(s.get("trades_taken", 0) for s in summaries)
        trades_skipped = sum(s.get("trades_skipped", 0) for s in summaries)
        total_pnl = sum(s.get("realized_pnl", 0) for s in summaries)
        max_drawdown = min(s.get("max_drawdown", 0) for s in summaries)
        data_issues = sum(s.get("data_issues", 0) for s in summaries)

        return {
            "total_trades": total_trades,
            "trades_skipped": trades_skipped,
            "total_pnl": total_pnl,
            "max_drawdown": max_drawdown,
            "data_issues": data_issues,
        }

    def get_combined_analysis(
        self,
        paper_scope: str,
        live_scope: str,
        lookback_days: int = 7
    ) -> Dict[str, Any]:
        """
        Analyze both paper and live trading summaries.

        Args:
            paper_scope: Paper trading scope
            live_scope: Live trading scope
            lookback_days: Number of days to analyze

        Returns:
            Combined analysis dict
        """
        paper_summaries = self.read_summaries(paper_scope, lookback_days)
        live_summaries = self.read_summaries(live_scope, lookback_days)

        return {
            "paper": {
                "summaries_count": len(paper_summaries),
                "latest": self.get_latest_summary(paper_scope),
                "performance": self.extract_performance_metrics(paper_summaries),
                "scan_analysis": self.analyze_scan_coverage(paper_summaries),
            },
            "live": {
                "summaries_count": len(live_summaries),
                "latest": self.get_latest_summary(live_scope),
                "performance": self.extract_performance_metrics(live_summaries),
                "scan_analysis": self.analyze_scan_coverage(live_summaries),
            },
        }
