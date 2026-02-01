"""
Quick demo: Train ML model and compare to rule-based approach.

This script:
1. Loads the existing ML dataset
2. Trains a LogisticRegression model (70% train, 30% test, time-safe)
3. Runs backtest with rule-based confidence
4. Runs backtest with ML-derived confidence
5. Prints comparison table

Run with: python3 ml_demo.py
"""

import logging
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

from universe.symbols import SYMBOLS
from ml.train_model import train_and_evaluate
from ml.evaluate import evaluate_ml_vs_rules


def main():
    """Run complete ML validation experiment."""
    
    # Find latest dataset
    data_dir = Path("./data")
    csv_files = sorted(data_dir.glob("ml_dataset_*.csv"))
    
    if not csv_files:
        logger.error("No ML dataset found.")
        logger.error("Run: python3 main.py (with BUILD_DATASET=True)")
        return
    
    dataset_path = str(csv_files[-1])
    logger.info(f"Using dataset: {dataset_path}")
    
    # Step 1: Train model (70% train, 30% test, time-safe split)
    logger.info("\n" + "=" * 100)
    logger.info("STEP 1: Train ML Model")
    logger.info("=" * 100)
    
    result = train_and_evaluate(
        dataset_path,
        include_confidence=False,  # Don't use rule-based confidence as feature
        train_ratio=0.7,
    )
    
    model = result["model"]
    scaler = result["scaler"]
    features = result["features"]
    metrics = result["metrics"]
    
    logger.info(f"\nModel trained successfully:")
    logger.info(f"  Test Accuracy: {metrics['accuracy']:.2%}")
    logger.info(f"  Test Precision: {metrics['precision']:.2%}")
    logger.info(f"  Test Recall: {metrics['recall']:.2%}")
    logger.info(f"  Test F1: {metrics['f1']:.2%}")
    
    # Step 2: Compare on backtests
    logger.info("\n" + "=" * 100)
    logger.info("STEP 2: Compare Rules vs ML on Historical Backtest")
    logger.info("=" * 100)
    
    rule_metrics, ml_metrics = evaluate_ml_vs_rules(
        SYMBOLS,
        model,
        scaler,
        features,
        include_confidence=False,
    )
    
    # Summary
    logger.info("\n" + "=" * 100)
    logger.info("CONCLUSION")
    logger.info("=" * 100)
    
    rule_win_rate = rule_metrics["win_rate"]
    ml_win_rate = ml_metrics["win_rate"]
    
    if ml_win_rate > rule_win_rate:
        improvement = (ml_win_rate - rule_win_rate) / rule_win_rate * 100
        logger.info(f"✓ ML improves win rate by {improvement:.1f}%")
    else:
        decline = (rule_win_rate - ml_win_rate) / rule_win_rate * 100
        logger.warning(f"✗ ML decreases win rate by {decline:.1f}%")
    
    rule_ret = rule_metrics["avg_return"]
    ml_ret = ml_metrics["avg_return"]
    
    if ml_ret > rule_ret:
        improvement = (ml_ret - rule_ret) / abs(rule_ret) * 100 if rule_ret != 0 else 0
        logger.info(f"✓ ML improves avg return by {improvement:.1f}%")
    else:
        decline = (rule_ret - ml_ret) / abs(rule_ret) * 100 if rule_ret != 0 else 0
        logger.warning(f"✗ ML decreases avg return by {decline:.1f}%")


if __name__ == "__main__":
    main()
