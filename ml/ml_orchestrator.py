"""
Offline ML orchestrator - runs after market close.

Coordinates:
1. Dataset building from closed trades
2. Model training
3. Offline evaluation
4. Candidate registration

SAFETY: Never runs during market hours.
"""

import logging
from pathlib import Path
from typing import Optional, Dict

logger = logging.getLogger(__name__)


class OfflineMLOrchestrator:
    """Orchestrate offline ML workflow after market close."""

    def __init__(
        self,
        dataset_builder,
        trainer,
        evaluator,
        registry,
    ):
        """
        Initialize orchestrator.
        
        Args:
            dataset_builder: DatasetBuilder
            trainer: OfflineTrainer
            evaluator: OfflineEvaluator
            registry: ModelRegistry
        """
        self.dataset_builder = dataset_builder
        self.trainer = trainer
        self.evaluator = evaluator
        self.registry = registry

    def run_offline_ml_cycle(
        self,
        force_train: bool = False,
        auto_promote: bool = True,
        min_expectancy_improvement: float = 0.001,
        min_bad_trades_avoided: int = 1,
        min_win_rate_improvement: float = 0.0,
    ) -> Optional[Dict]:
        """Run complete offline ML cycle after market close.
        
        SAFETY: Only runs after market close (scheduler responsibility).
        
        Steps:
        1. Build dataset from closed trades
        2. Train new model (if dataset large enough)
        3. Evaluate new model vs baseline
        4. Register candidate
        5. Auto-promote if thresholds met (optional)
        
        Args:
            force_train: Force training even on small dataset (testing only)
            auto_promote: Enable automatic promotion (default: True)
            min_expectancy_improvement: Min expectancy gain for auto-promotion (default: 0.1%)
            min_bad_trades_avoided: Min bad trades avoided (default: 1)
            min_win_rate_improvement: Min win rate improvement (default: 0%)
        
        Returns:
            Results dict or None
        """
        logger.info("\n")
        logger.info("╔" + "=" * 78 + "╗")
        logger.info("║" + " OFFLINE ML CYCLE (POST-MARKET-CLOSE)".center(78) + "║")
        logger.info("╚" + "=" * 78 + "╝")
        
        # Step 1: Build dataset
        rows_added, rows_total = self.dataset_builder.build_from_ledger()
        
        # Step 2: Train (skip if dataset too small)
        train_result = self.trainer.train(force=force_train)
        if train_result is None:
            logger.info("Training skipped (dataset too small)")
            return None
        
        # Step 3: Evaluate
        eval_result = self.evaluator.evaluate()
        
        if not eval_result:
            logger.warning("Evaluation failed")
            return None
        
        # Step 4: Register candidate
        model_id = train_result["model_id"]
        self.registry.register_candidate(model_id, train_result)
        
        # Step 5: Auto-promote if enabled and thresholds met
        promoted = False
        if auto_promote:
            improvement_metrics = eval_result.get("improvement", {})
            promoted = self.registry.auto_promote_if_better(
                model_id,
                improvement_metrics,
                min_expectancy_improvement=min_expectancy_improvement,
                min_bad_trades_avoided=min_bad_trades_avoided,
                min_win_rate_improvement=min_win_rate_improvement,
            )
        
        # Log summary
        logger.info("\n" + "=" * 80)
        logger.info("OFFLINE ML CYCLE COMPLETE")
        logger.info("=" * 80)
        logger.info(f"New candidate: {model_id}")
        if promoted:
            logger.info(f"Status: ✅ AUTO-PROMOTED to ACTIVE")
        else:
            logger.info(f"Status: Registered as candidate (not promoted)")
        logger.info(f"Previous active: {self.registry.get_active_model()}")
        logger.info("=" * 80)
        
        return {
            "model_id": model_id,
            "promoted": promoted,
            "training": train_result,
            "evaluation": eval_result,
            "registry": self.registry.get_registry_summary(),
        }

    def maybe_load_active_model(self) -> bool:
        """Load active model for trading (called at startup).
        
        SAFETY: Read-only during trading hours.
        If load fails, falls back to rules-only trading.
        
        Returns:
            True if model loaded, False = fallback to rules-only
        """
        active_id = self.registry.get_active_model()
        
        if not active_id:
            logger.info("No active model. Using rules-only trading.")
            return False
        
        if self.trainer.load_model(active_id):
            logger.info(f"Loaded active model: {active_id}")
            # Lock model for trading session
            self.registry.lock_active_model()
            return True
        else:
            logger.warning(f"Failed to load model {active_id}. Falling back to rules-only.")
            return False
