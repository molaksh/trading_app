"""
INDIA RULES-ONLY BASELINE REPORT
==================================

Generate baseline performance report after N days of observation logging.

PURPOSE:
  - Quantify rules-only performance (before any ML changes)
  - Establish baseline for comparison
  - Identify rejection patterns and failure modes
  - Document confidence distribution and risk behavior
  - Create audit trail for validation process

INPUT:
  - India observation JSONL logs (from monitoring/india_observation_log.py)
  - Date range (default: all available observations)
  
OUTPUT:
  - Markdown report: reports/india_rules_baseline_{date}.md
  - CSV summary: reports/india_rules_baseline_{date}.csv
  
REPORT SECTIONS:
  1. Summary: Overall metrics (win rate, avg return, Sharpe, drawdown)
  2. Signals: How many generated, accepted, rejected (and why)
  3. Trades: Execution rate, average confidence of executed vs rejected
  4. Risk: Portfolio heat over time, max drawdown, volatility
  5. Confidence: Distribution of confidence scores
  6. Rejections: Breakdown of rejection reasons (risk vs confidence)
  7. Symbols: Top performers and worst performers

USAGE:
  from reports.india_rules_baseline import IndiaRulesBaseline
  
  reporter = IndiaRulesBaseline()
  
  # Generate baseline report after 20 trading days
  reporter.generate_report(min_days=20)
"""

import json
import csv
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Tuple
import statistics


class IndiaRulesBaseline:
    """
    Generate baseline performance report for India rules-only validation phase.
    
    Safety Features:
    - Requires minimum N days of data before generating report
    - Immutable report output (timestamped, not overwritten)
    - Clear markdown documentation
    - CSV export for external analysis
    """
    
    def __init__(self, log_dir: str = "logs/india_observations", 
                 report_dir: str = "reports"):
        """
        Initialize baseline report generator.
        
        Args:
            log_dir: Directory with observation JSONL files
            report_dir: Directory for output reports
        """
        self.log_dir = Path(log_dir)
        self.report_dir = Path(report_dir)
        self.report_dir.mkdir(parents=True, exist_ok=True)
    
    def _load_observations(self, days: int = None) -> List[Dict[str, Any]]:
        """Load all observation records (optionally limit to last N days)."""
        if not self.log_dir.exists():
            return []
        
        observations = []
        jsonl_files = sorted(self.log_dir.glob("*.jsonl"))
        
        if days:
            jsonl_files = jsonl_files[-days:]
        
        for filepath in jsonl_files:
            with open(filepath, "r") as f:
                for line in f:
                    if line.strip():
                        observations.append(json.loads(line))
        
        return observations
    
    def _calculate_metrics(self, observations: List[Dict]) -> Dict[str, Any]:
        """Calculate summary metrics from observations."""
        if not observations:
            return {}
        
        total_days = len(observations)
        
        # Aggregate counters
        total_signals = sum(o.get("signals_generated", 0) for o in observations)
        total_signals_rejected = sum(o.get("signals_rejected", 0) for o in observations)
        total_trades = sum(o.get("trades_executed", 0) for o in observations)
        total_rejected_risk = sum(o.get("trades_rejected_risk", 0) for o in observations)
        total_rejected_confidence = sum(o.get("trades_rejected_confidence", 0) for o in observations)
        
        # Confidence analysis
        executed_confidences = [o.get("avg_confidence_executed", 0) for o in observations 
                               if o.get("trades_executed", 0) > 0]
        rejected_confidences = [o.get("avg_confidence_rejected", 0) for o in observations 
                               if o.get("signals_rejected", 0) > 0]
        
        # Return metrics
        returns = [o.get("daily_return_pct", 0) for o in observations]
        drawdowns = [o.get("max_drawdown_pct", 0) for o in observations]
        portfolio_heats = [o.get("portfolio_heat_pct", 0) for o in observations]
        
        # Calculate win days vs loss days
        winning_days = sum(1 for r in returns if r > 0)
        losing_days = sum(1 for r in returns if r < 0)
        win_rate = winning_days / total_days if total_days > 0 else 0
        
        # Calculate performance
        total_return = sum(returns)
        avg_return = statistics.mean(returns) if returns else 0
        max_drawdown = max(drawdowns) if drawdowns else 0
        avg_heat = statistics.mean(portfolio_heats) if portfolio_heats else 0
        
        return {
            "total_trading_days": total_days,
            "winning_days": winning_days,
            "losing_days": losing_days,
            "win_rate_pct": round(win_rate * 100, 2),
            "total_return_pct": round(total_return, 2),
            "avg_daily_return_pct": round(avg_return, 4),
            "max_drawdown_pct": round(max_drawdown, 2),
            "avg_portfolio_heat_pct": round(avg_heat, 2),
            
            "total_signals_generated": total_signals,
            "total_signals_rejected": total_signals_rejected,
            "signal_acceptance_rate_pct": round(
                ((total_signals - total_signals_rejected) / total_signals * 100) 
                if total_signals > 0 else 0, 2
            ),
            
            "total_trades_executed": total_trades,
            "total_rejected_risk": total_rejected_risk,
            "total_rejected_confidence": total_rejected_confidence,
            
            "avg_confidence_executed": round(statistics.mean(executed_confidences), 4) 
                if executed_confidences else 0,
            "avg_confidence_rejected": round(statistics.mean(rejected_confidences), 4) 
                if rejected_confidences else 0,
        }
    
    def generate_report(self, min_days: int = 20) -> Tuple[str, str]:
        """
        Generate baseline report if enough observation days available.
        
        Args:
            min_days: Minimum observation days required (default 20)
            
        Returns:
            Tuple of (markdown_filepath, csv_filepath) if successful, else (None, None)
            
        Raises:
            ValueError: If insufficient observation data
        """
        observations = self._load_observations()
        
        if len(observations) < min_days:
            raise ValueError(
                f"Insufficient observation data. Have {len(observations)} days, "
                f"need {min_days}. Run rules-only trading for {min_days - len(observations)} "
                f"more days before generating baseline report."
            )
        
        metrics = self._calculate_metrics(observations)
        
        # Generate report timestamp
        report_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        md_filename = f"india_rules_baseline_{report_timestamp}.md"
        csv_filename = f"india_rules_baseline_{report_timestamp}.csv"
        
        md_path = self.report_dir / md_filename
        csv_path = self.report_dir / csv_filename
        
        # Generate markdown report
        self._write_markdown_report(md_path, metrics, observations)
        
        # Generate CSV summary
        self._write_csv_report(csv_path, metrics)
        
        print(f"[INDIA] Baseline report generated:")
        print(f"  Markdown: {md_path}")
        print(f"  CSV: {csv_path}")
        
        return str(md_path), str(csv_path)
    
    def _write_markdown_report(self, filepath: Path, metrics: Dict, 
                               observations: List[Dict]) -> None:
        """Write markdown baseline report."""
        with open(filepath, "w") as f:
            f.write("# India Rules-Only Baseline Report\n\n")
            f.write(f"**Generated**: {datetime.now().isoformat()}\n")
            f.write(f"**Validation Phase**: RULES_ONLY_MODE (ML disabled)\n")
            f.write(f"**Observation Period**: {metrics.get('total_trading_days')} trading days\n\n")
            
            # Summary Section
            f.write("## 1. Performance Summary\n\n")
            f.write("| Metric | Value |\n")
            f.write("|--------|-------|\n")
            f.write(f"| Trading Days | {metrics.get('total_trading_days')} |\n")
            f.write(f"| Winning Days | {metrics.get('winning_days')} |\n")
            f.write(f"| Losing Days | {metrics.get('losing_days')} |\n")
            f.write(f"| Win Rate | {metrics.get('win_rate_pct')}% |\n")
            f.write(f"| Total Return | {metrics.get('total_return_pct')}% |\n")
            f.write(f"| Avg Daily Return | {metrics.get('avg_daily_return_pct')}% |\n")
            f.write(f"| Max Drawdown | {metrics.get('max_drawdown_pct')}% |\n")
            f.write(f"| Avg Portfolio Heat | {metrics.get('avg_portfolio_heat_pct')}% |\n\n")
            
            # Signal Analysis
            f.write("## 2. Signal Analysis\n\n")
            f.write("| Metric | Count |\n")
            f.write("|--------|-------|\n")
            f.write(f"| Signals Generated | {metrics.get('total_signals_generated')} |\n")
            f.write(f"| Signals Rejected | {metrics.get('total_signals_rejected')} |\n")
            f.write(f"| Signal Acceptance Rate | {metrics.get('signal_acceptance_rate_pct')}% |\n\n")
            
            # Trade Execution
            f.write("## 3. Trade Execution\n\n")
            f.write("| Metric | Count |\n")
            f.write("|--------|-------|\n")
            f.write(f"| Trades Executed | {metrics.get('total_trades_executed')} |\n")
            f.write(f"| Rejected (Risk) | {metrics.get('total_rejected_risk')} |\n")
            f.write(f"| Rejected (Confidence) | {metrics.get('total_rejected_confidence')} |\n\n")
            
            # Confidence Analysis
            f.write("## 4. Confidence Distribution\n\n")
            f.write("| Metric | Score |\n")
            f.write("|--------|-------|\n")
            f.write(f"| Avg Confidence (Executed) | {metrics.get('avg_confidence_executed')} |\n")
            f.write(f"| Avg Confidence (Rejected) | {metrics.get('avg_confidence_rejected')} |\n\n")
            
            # Validation Status
            f.write("## 5. Validation Status\n\n")
            f.write("- **Phase**: RULES_ONLY_MODE\n")
            f.write("- **ML Status**: DISABLED (rules-based confidence only)\n")
            f.write("- **Baseline**: ESTABLISHED (ready for ML validation)\n")
            f.write("- **Next Step**: Run `--run-india-ml-validation` to enable ML comparison\n\n")
            
            # Recommendations
            f.write("## 6. Recommendations\n\n")
            f.write("Based on baseline performance:\n\n")
            
            if metrics.get('win_rate_pct', 0) > 50:
                f.write("✓ Win rate > 50% - Rules performance acceptable\n")
            else:
                f.write("⚠ Win rate < 50% - Review signal selection logic\n")
            
            if metrics.get('max_drawdown_pct', 0) < 10:
                f.write("✓ Max drawdown < 10% - Risk management effective\n")
            else:
                f.write("⚠ Max drawdown > 10% - Consider tighter position sizing\n")
            
            if metrics.get('avg_portfolio_heat_pct', 0) < 20:
                f.write("✓ Portfolio heat < 20% - Conservative positioning\n")
            else:
                f.write("⚠ Portfolio heat > 20% - May need tighter stops\n")
            
            f.write("\n---\n")
            f.write("*This baseline was established using rules-only trading (ML disabled).*\n")
            f.write("*Future ML models will be evaluated against this baseline.*\n")
    
    def _write_csv_report(self, filepath: Path, metrics: Dict) -> None:
        """Write CSV summary report."""
        with open(filepath, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Metric", "Value"])
            for key, value in sorted(metrics.items()):
                writer.writerow([key, value])
