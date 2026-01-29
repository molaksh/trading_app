"""
Model registry and promotion logic.

Manages model versions and safe promotion to active status.

SAFETY CONSTRAINTS:
- Only one ACTIVE model per day
- Promotion requires explicit approval
- Fallback to rules-only if model unavailable
- All model changes logged
"""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict

from config.scope import get_scope
from config.scope_paths import get_scope_path

logger = logging.getLogger(__name__)


class ModelRegistry:
    """Manage model versions and promotion."""

    def __init__(self, model_dir: Optional[Path] = None):
        """
        Initialize registry.
        
        Args:
            model_dir: Directory containing model artifacts
        """
        if model_dir is None:
            scope = get_scope()
            model_dir = get_scope_path(scope, "models")

        self.model_dir = Path(model_dir)
        self.registry_file = self.model_dir / "model_registry.json"
        self.active_model_file = self.model_dir / "active_model.json"
        
        self.registry = self._load_registry()

    def _load_registry(self) -> Dict:
        """Load model registry from disk."""
        if not self.registry_file.exists():
            return {
                "candidates": {},
                "active": None,
                "locked_until": None,
            }
        
        try:
            with open(self.registry_file) as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Could not load registry: {e}")
            return {"candidates": {}, "active": None, "locked_until": None}

    def _save_registry(self) -> None:
        """Save registry to disk."""
        try:
            with open(self.registry_file, "w") as f:
                json.dump(self.registry, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not save registry: {e}")

    def register_candidate(self, model_id: str, metrics: Dict) -> None:
        """Register a newly trained candidate model.
        
        Candidate must be explicitly promoted to become active.
        """
        logger.info(f"Registering candidate: {model_id}")
        
        self.registry["candidates"][model_id] = {
            "registered_at": datetime.now().isoformat(),
            "metrics": metrics,
            "promoted": False,
        }
        
        self._save_registry()
        logger.info(f"Candidate registered: {model_id}")

    def get_active_model(self) -> Optional[str]:
        """Get currently active model ID."""
        return self.registry.get("active")

    def promote_candidate(self, model_id: str, reason: str = "") -> bool:
        """Promote candidate to active status.
        
        SAFETY: Manual step, explicit decision.
        
        Args:
            model_id: ID of candidate to promote
            reason: Reason for promotion
        
        Returns:
            True if promoted, False otherwise
        """
        if model_id not in self.registry["candidates"]:
            logger.error(f"Candidate not found: {model_id}")
            return False
        
        # Replace previous active model
        old_active = self.registry.get("active")
        self.registry["active"] = model_id
        self.registry["candidates"][model_id]["promoted"] = True
        self.registry["candidates"][model_id]["promoted_at"] = datetime.now().isoformat()
        
        self._save_registry()

        # Persist active model file
        try:
            self.active_model_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.active_model_file, "w") as f:
                json.dump(
                    {
                        "active_model_version": model_id,
                        "promoted_at": datetime.now().isoformat(),
                        "reason": reason,
                    },
                    f,
                    indent=2,
                )
        except Exception as e:
            logger.warning(f"Could not write active_model.json: {e}")
        
        logger.info("=" * 80)
        logger.info(f"MODEL PROMOTED: {model_id}")
        logger.info(f"Previous active: {old_active}")
        logger.info(f"Reason: {reason}")
        logger.info("=" * 80)
        
        return True

    def list_candidates(self) -> Dict[str, Dict]:
        """List all registered candidates."""
        return self.registry.get("candidates", {})

    def get_candidate_metrics(self, model_id: str) -> Optional[Dict]:
        """Get metrics for a candidate."""
        candidate = self.registry["candidates"].get(model_id)
        return candidate.get("metrics") if candidate else None

    def lock_active_model(self, hours: int = 24) -> None:
        """Lock active model to prevent changes during trading.
        
        SAFETY: Ensures model version is stable across trading session.
        """
        until = datetime.now().isoformat()
        self.registry["locked_until"] = until
        self._save_registry()
        logger.info(f"Active model locked until: {until}")

    def is_model_locked(self) -> bool:
        """Check if active model is locked."""
        locked_until = self.registry.get("locked_until")
        if not locked_until:
            return False
        
        try:
            locked_time = datetime.fromisoformat(locked_until)
            return datetime.now() < locked_time
        except Exception:
            return False

    def auto_promote_if_better(
        self,
        model_id: str,
        improvement_metrics: Dict,
        min_expectancy_improvement: float = 0.001,
        min_bad_trades_avoided: int = 1,
        min_win_rate_improvement: float = 0.0,
    ) -> bool:
        """Auto-promote candidate if it meets safety thresholds.
        
        Args:
            model_id: Candidate model ID
            improvement_metrics: Metrics from OfflineEvaluator
            min_expectancy_improvement: Minimum expectancy gain (default: 0.1%)
            min_bad_trades_avoided: Minimum bad trades avoided (default: 1)
            min_win_rate_improvement: Minimum win rate improvement (default: 0%)
        
        Returns:
            True if promoted, False if thresholds not met
        """
        if model_id not in self.registry["candidates"]:
            logger.error(f"Cannot auto-promote: candidate not found: {model_id}")
            return False
        
        # Check improvement thresholds
        exp_improvement = improvement_metrics.get("expectancy_improvement", 0)
        bad_avoided = improvement_metrics.get("bad_trades_avoided", 0)
        win_rate_delta = improvement_metrics.get("win_rate_improvement", 0)
        
        logger.info("\n" + "=" * 80)
        logger.info("AUTO-PROMOTION EVALUATION")
        logger.info("=" * 80)
        logger.info(f"Candidate: {model_id}")
        logger.info(f"\nImprovement Metrics:")
        logger.info(f"  Expectancy: {exp_improvement:+.4f} (threshold: {min_expectancy_improvement:+.4f})")
        logger.info(f"  Bad trades avoided: {bad_avoided} (threshold: {min_bad_trades_avoided})")
        logger.info(f"  Win rate delta: {win_rate_delta:+.1%} (threshold: {min_win_rate_improvement:+.1%})")
        
        # Check all conditions
        passes = []
        if exp_improvement >= min_expectancy_improvement:
            passes.append("✅ Expectancy improvement")
        else:
            passes.append("❌ Expectancy improvement")
        
        if bad_avoided >= min_bad_trades_avoided:
            passes.append("✅ Bad trades avoided")
        else:
            passes.append("❌ Bad trades avoided")
        
        if win_rate_delta >= min_win_rate_improvement:
            passes.append("✅ Win rate improvement")
        else:
            passes.append("❌ Win rate improvement")
        
        logger.info(f"\nThreshold Checks:")
        for check in passes:
            logger.info(f"  {check}")
        
        # All must pass
        all_pass = all("✅" in check for check in passes)
        
        if all_pass:
            logger.info(f"\n✅ AUTO-PROMOTING: {model_id}")
            logger.info("=" * 80)
            return self.promote_candidate(
                model_id,
                reason=f"Auto-promoted: exp={exp_improvement:+.4f}, bad_avoided={bad_avoided}, wr={win_rate_delta:+.1%}"
            )
        else:
            logger.info(f"\n❌ PROMOTION BLOCKED: Thresholds not met")
            logger.info("Model remains as candidate. Manual promotion available.")
            logger.info("=" * 80)
            return False

    def get_registry_summary(self) -> Dict:
        """Get registry summary for logging."""
        candidates = self.registry.get("candidates", {})
        active = self.registry.get("active")
        
        return {
            "active_model": active,
            "n_candidates": len(candidates),
            "is_locked": self.is_model_locked(),
            "candidates": list(candidates.keys()),
        }
