"""
Offline evaluation of ML model performance vs rules-only baseline.

Runs AFTER market close to compare:
1. Rules-only trading
2. Rules + ML risk filtering

SAFETY: Never runs during trading hours.
"""

import logging
from typing import Dict, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class OfflineEvaluator:
    """Compare rules-only vs rules+ML performance."""

    def __init__(self, dataset_builder, trainer):
        """
        Initialize evaluator.
        
        Args:
            dataset_builder: DatasetBuilder with closed trades
            trainer: OfflineTrainer with trained model
        """
        self.dataset_builder = dataset_builder
        self.trainer = trainer

    def evaluate(
        self,
        risk_threshold: float = 0.5,
        mae_threshold: float = 0.03,
    ) -> Dict:
        """Evaluate model against baseline.
        
        Args:
            risk_threshold: ML probability threshold for blocking trades
            mae_threshold: MAE threshold for 'bad' classification
        
        Returns:
            Evaluation results dict
        """
        logger.info("=" * 80)
        logger.info("OFFLINE EVALUATION")
        logger.info("=" * 80)
        
        # Load dataset
        df = self.dataset_builder.to_dataframe()
        
        if df.empty or self.trainer.model is None:
            logger.warning("Cannot evaluate: dataset empty or model not trained")
            return {}
        
        # Classify trades
        df["is_bad"] = df.apply(
            lambda row: 1 if row["realized_pnl_pct"] < 0 or abs(row["mae_pct"]) > mae_threshold else 0,
            axis=1
        )
        
        # Get ML risk scores
        ml_scores = []
        for _, row in df.iterrows():
            features = row["rule_features"] if isinstance(row["rule_features"], dict) else {}
            score = self.trainer.predict_risk(features)
            ml_scores.append(score if score is not None else 0.5)
        
        df["ml_risk_score"] = ml_scores
        df["ml_blocked"] = df["ml_risk_score"] > risk_threshold
        
        # Baseline: rules-only (all trades)
        baseline_metrics = self._compute_metrics(df, "RULES-ONLY", use_ml_filter=False)
        
        # With ML filtering
        ml_metrics = self._compute_metrics(df, "RULES + ML FILTER", use_ml_filter=True)
        
        # Summary
        logger.info("\n" + "=" * 80)
        logger.info("COMPARISON: Rules-Only vs Rules+ML")
        logger.info("=" * 80)
        
        self._print_comparison(baseline_metrics, ml_metrics)
        
        logger.info("=" * 80)
        
        return {
            "baseline": baseline_metrics,
            "with_ml": ml_metrics,
            "improvement": self._compute_improvement(baseline_metrics, ml_metrics),
        }

    def _compute_metrics(self, df: pd.DataFrame, label: str, use_ml_filter: bool = False) -> Dict:
        """Compute trading metrics for a scenario."""
        if use_ml_filter:
            subset = df[~df["ml_blocked"]].copy()
        else:
            subset = df.copy()
        
        if len(subset) == 0:
            return {
                "label": label,
                "n_trades": 0,
                "bad_trades": 0,
                "good_trades": 0,
                "win_rate": 0,
                "expectancy": 0,
                "avg_pnl": 0,
                "std_pnl": 0,
            }
        
        bad_count = (subset["is_bad"] == 1).sum()
        good_count = (subset["is_bad"] == 0).sum()
        pnl_values = subset["realized_pnl_pct"]
        
        return {
            "label": label,
            "n_trades": len(subset),
            "bad_trades": int(bad_count),
            "good_trades": int(good_count),
            "win_rate": float(good_count / len(subset)) if len(subset) > 0 else 0,
            "expectancy": float(pnl_values.mean()),
            "avg_pnl": float(pnl_values.mean()),
            "std_pnl": float(pnl_values.std()),
            "max_drawdown": float(pnl_values.min()),
            "best_trade": float(pnl_values.max()),
        }

    def _print_comparison(self, baseline: Dict, with_ml: Dict) -> None:
        """Print side-by-side comparison."""
        logger.info(f"\n{'Metric':<25} {'Rules-Only':<20} {'Rules+ML':<20}")
        logger.info("-" * 65)
        logger.info(f"{'Trade Count':<25} {baseline['n_trades']:<20} {with_ml['n_trades']:<20}")
        logger.info(f"{'Bad Trades':<25} {baseline['bad_trades']:<20} {with_ml['bad_trades']:<20}")
        logger.info(f"{'Win Rate':<25} {baseline['win_rate']:.1%}{'':<13} {with_ml['win_rate']:.1%}")
        logger.info(f"{'Expectancy':<25} {baseline['expectancy']:+.3f}{'':<14} {with_ml['expectancy']:+.3f}")
        logger.info(f"{'Avg PnL %':<25} {baseline['avg_pnl']:+.2%}{'':<14} {with_ml['avg_pnl']:+.2%}")
        logger.info(f"{'Std Dev':<25} {baseline['std_pnl']:.3f}{'':<14} {with_ml['std_pnl']:.3f}")
        logger.info(f"{'Max Drawdown':<25} {baseline['max_drawdown']:+.2%}{'':<14} {with_ml['max_drawdown']:+.2%}")

    def _compute_improvement(self, baseline: Dict, with_ml: Dict) -> Dict:
        """Compute improvement metrics."""
        bad_reduction = baseline["bad_trades"] - with_ml["bad_trades"]
        trade_reduction = baseline["n_trades"] - with_ml["n_trades"]
        
        return {
            "bad_trades_avoided": int(bad_reduction),
            "trades_filtered": int(trade_reduction),
            "expectancy_improvement": float(with_ml["expectancy"] - baseline["expectancy"]),
            "win_rate_improvement": float(with_ml["win_rate"] - baseline["win_rate"]),
            "drawdown_improvement": float(with_ml["max_drawdown"] - baseline["max_drawdown"]),
        }
