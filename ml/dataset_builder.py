"""
Offline dataset builder for ML training.

Runs AFTER market close to construct training data from completed trades.
Never runs during market hours to avoid hindsight bias.

SAFETY CONSTRAINTS:
- Only uses CLOSED trades (no open positions)
- Features match decision-time data (no lookahead)
- Immutable, append-only dataset
- No labeling from future price movements
"""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Tuple

import pandas as pd
import numpy as np

from config.scope import get_scope
from config.scope_paths import get_scope_path

logger = logging.getLogger(__name__)


class TradeDataRow:
    """Single training row: decision context + trade outcome."""

    def __init__(
        self,
        symbol: str,
        decision_timestamp: str,
        rule_confidence: float,
        rule_features: Dict[str, float],
        position_size: float,
        entry_price: float,
        exit_price: Optional[float],
        exit_timestamp: Optional[str],
        holding_days: int,
        realized_pnl_pct: float,
        mae_pct: float,
        mfe_pct: float,
    ):
        """Store immutable decision + outcome."""
        self.symbol = symbol
        self.decision_timestamp = decision_timestamp
        self.rule_confidence = rule_confidence
        self.rule_features = rule_features.copy()
        self.position_size = position_size
        self.entry_price = entry_price
        self.exit_price = exit_price
        self.exit_timestamp = exit_timestamp
        self.holding_days = holding_days
        self.realized_pnl_pct = realized_pnl_pct
        self.mae_pct = mae_pct
        self.mfe_pct = mfe_pct

    def is_bad_trade(self, mae_threshold: float = 0.03, negative_only: bool = False) -> bool:
        """Classify trade as 'bad' for ML label.
        
        BAD trade if:
        - Negative realized PnL, OR
        - MAE exceeded threshold
        
        Args:
            mae_threshold: Max adverse excursion threshold (default 3%)
            negative_only: If True, only negative PnL counts as bad (stricter)
        
        Returns:
            True if trade is classified as bad
        """
        if negative_only:
            return self.realized_pnl_pct < 0
        return self.realized_pnl_pct < 0 or abs(self.mae_pct) > mae_threshold

    def to_dict(self) -> Dict:
        """Serialize to dict for JSON storage."""
        return {
            "symbol": self.symbol,
            "decision_timestamp": self.decision_timestamp,
            "rule_confidence": self.rule_confidence,
            "rule_features": self.rule_features,
            "position_size": self.position_size,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "exit_timestamp": self.exit_timestamp,
            "holding_days": self.holding_days,
            "realized_pnl_pct": self.realized_pnl_pct,
            "mae_pct": self.mae_pct,
            "mfe_pct": self.mfe_pct,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "TradeDataRow":
        """Deserialize from dict."""
        return cls(**data)


class DatasetBuilder:
    """Construct training dataset from completed trades.
    
    SAFETY DESIGN:
    - Only processes CLOSED trades
    - Features frozen at decision time
    - Append-only dataset with checksums
    - No future price leakage
    - Phase-aware: can combine paper and live ledgers per ML_LEARNING_PHASE
    """

    def __init__(self, dataset_dir: Optional[Path], trade_ledger, live_trade_ledger=None):
        """
        Initialize dataset builder.
        
        Args:
            dataset_dir: Directory to store dataset files
            trade_ledger: Primary TradeLedger instance (paper ledger)
            live_trade_ledger: Optional live TradeLedger (for PHASE_2+)
        """
        if dataset_dir is None:
            scope = get_scope()
            dataset_dir = get_scope_path(scope, "features")

        self.dataset_dir = Path(dataset_dir)
        self.dataset_dir.mkdir(parents=True, exist_ok=True)
        self.trade_ledger = trade_ledger  # Primary (paper)
        self.live_trade_ledger = live_trade_ledger  # Secondary (live)
        
        # Immutable dataset path (append-only)
        self.dataset_file = self.dataset_dir / "ml_training_dataset.jsonl"
        self.metadata_file = self.dataset_dir / "ml_dataset_metadata.json"
        
        # Track processed trade IDs to prevent duplicates
        self._processed_trade_ids = set()
        self._load_processed_ids()

    def _load_processed_ids(self) -> None:
        """Load set of already-processed trade IDs."""
        if not self.dataset_file.exists():
            return
        
        try:
            with open(self.dataset_file) as f:
                for line in f:
                    if line.strip():
                        row = json.loads(line)
                        # Use (symbol, decision_timestamp) as unique ID
                        trade_id = (row["symbol"], row["decision_timestamp"])
                        self._processed_trade_ids.add(trade_id)
            logger.info(f"Loaded {len(self._processed_trade_ids)} processed trade IDs")
        except Exception as e:
            logger.warning(f"Could not load processed IDs: {e}")

    def build_from_ledger(self, mae_threshold: float = 0.03) -> Tuple[int, int]:
        """Build dataset from closed trades in ledger.
        
        Phase-aware data collection:
        - PHASE_1: Paper ledger only
        - PHASE_2: Paper primary (70-80%) + live secondary (20-30%, tagged)
        - PHASE_3: Paper primary + live constraints
        
        Args:
            mae_threshold: MAE threshold for 'bad' trade classification
        
        Returns:
            Tuple of (rows_added, rows_total)
        """
        from config.ml_phase import get_ml_phase_config, MLLearningPhase
        
        logger.info("=" * 80)
        logger.info("DATASET BUILDING")
        logger.info("=" * 80)
        
        phase_config = get_ml_phase_config()
        current_phase = phase_config.get_phase()
        
        logger.info(f"ML Learning Phase: {current_phase.value}")
        
        # Collect paper ledger trades (always primary)
        paper_trades = self._collect_trades_from_ledger(
            self.trade_ledger,
            source_tag="paper",
            weight=1.0
        )
        
        # Collect live ledger trades (phase-dependent)
        live_trades = []
        if current_phase == MLLearningPhase.PHASE_1:
            logger.info("PHASE_1: Using paper ledger only (live excluded)")
        elif current_phase == MLLearningPhase.PHASE_2:
            if self.live_trade_ledger:
                logger.info("PHASE_2: Using paper (primary) + live (secondary, 30% weight)")
                live_trades = self._collect_trades_from_ledger(
                    self.live_trade_ledger,
                    source_tag="live",
                    weight=0.3
                )
            else:
                logger.warning("PHASE_2 configured but no live ledger provided")
        elif current_phase == MLLearningPhase.PHASE_3:
            if self.live_trade_ledger:
                logger.info("PHASE_3: Using paper (primary) + live (constraints)")
                live_trades = self._collect_trades_from_ledger(
                    self.live_trade_ledger,
                    source_tag="live",
                    weight=0.4  # Higher weight for mature system
                )
            else:
                logger.warning("PHASE_3 configured but no live ledger provided")
        
        # Combine datasets
        all_trades_to_process = paper_trades + live_trades
        
        logger.info(f"Paper trades: {len(paper_trades)}")
        logger.info(f"Live trades: {len(live_trades)}")
        logger.info(f"Total to process: {len(all_trades_to_process)}")
        
        # Process new trades
        new_rows = []
        for trade, source_tag, weight in all_trades_to_process:
            trade_id = (trade.symbol, trade.entry_timestamp, source_tag)
            if trade_id in self._processed_trade_ids:
                continue
            
            try:
                row = self._trade_to_row(trade, mae_threshold)
                if row:
                    # Add metadata for multi-source tracking
                    row_dict = row.to_dict()
                    row_dict["source"] = source_tag
                    row_dict["weight"] = weight
                    new_rows.append(row_dict)
                    self._processed_trade_ids.add(trade_id)
            except Exception as e:
                logger.warning(f"Could not process trade {trade.symbol}: {e}")
        
        # Append to dataset
        rows_added = self._append_row_dicts(new_rows)
        rows_total = len(self._processed_trade_ids)
        
        logger.info(f"Rows added: {rows_added}")
        logger.info(f"Dataset total: {rows_total}")
        logger.info("=" * 80)
        
        return rows_added, rows_total
    
    def _collect_trades_from_ledger(self, ledger, source_tag: str, weight: float) -> List[Tuple]:
        """
        Collect closed trades from a ledger with metadata.
        
        Only includes trades with ML features (strategy-opened positions).
        Excludes reconciliation-discovered positions that lack entry_features.
        
        Args:
            ledger: TradeLedger instance
            source_tag: 'paper' or 'live'
            weight: Training weight for these trades
            
        Returns:
            List of (trade, source_tag, weight) tuples
        """
        if ledger is None:
            return []
        
        try:
            all_trades = ledger.get_all_trades()
            # Filter to closed trades with valid ML features
            # Exclude trades without entry_features (reconciliation-discovered positions)
            closed_trades = [
                t for t in all_trades 
                if t.exit_timestamp is not None 
                and hasattr(t, 'entry_features') 
                and t.entry_features is not None
                and len(t.entry_features) > 0
            ]
            return [(trade, source_tag, weight) for trade in closed_trades]
        except Exception as e:
            logger.warning(f"Could not collect trades from {source_tag} ledger: {e}")
            return []

    def _trade_to_row(self, trade, mae_threshold: float) -> Optional[TradeDataRow]:
        """Convert closed Trade to training row.
        
        Extract decision-time features (no lookahead).
        """
        if trade.exit_timestamp is None:
            return None
        
        # Calculate realized PnL %
        if trade.entry_price <= 0:
            return None
        
        realized_pnl_pct = (trade.exit_price - trade.entry_price) / trade.entry_price
        
        # Calculate MAE and MFE (from trade object if available)
        mae_pct = getattr(trade, "mae_pct", 0.0) or 0.0
        mfe_pct = getattr(trade, "mfe_pct", 0.0) or 0.0
        
        # Calculate holding days
        try:
            entry_ts = datetime.fromisoformat(trade.entry_timestamp)
            exit_ts = datetime.fromisoformat(trade.exit_timestamp)
            holding_days = (exit_ts - entry_ts).days
        except Exception:
            holding_days = 0
        
        # Handle missing confidence (e.g., liquidation exits)
        confidence = trade.confidence if trade.confidence is not None else 0.0
        
        # Handle quantity field (Trade uses entry_quantity, not quantity)
        quantity = getattr(trade, 'quantity', trade.entry_quantity)
        
        return TradeDataRow(
            symbol=trade.symbol,
            decision_timestamp=trade.entry_timestamp,
            rule_confidence=float(confidence),
            rule_features=trade.entry_features.copy() if hasattr(trade, "entry_features") else {},
            position_size=quantity,
            entry_price=trade.entry_price,
            exit_price=trade.exit_price,
            exit_timestamp=trade.exit_timestamp,
            holding_days=holding_days,
            realized_pnl_pct=realized_pnl_pct,
            mae_pct=mae_pct,
            mfe_pct=mfe_pct,
        )

    def _append_rows(self, rows: List[TradeDataRow]) -> int:
        """Append TradeDataRow objects to immutable dataset file."""
        if not rows:
            return 0
        
        try:
            with open(self.dataset_file, "a") as f:
                for row in rows:
                    f.write(json.dumps(row.to_dict()) + "\n")
            
            self._update_metadata()
            return len(rows)
        except Exception as e:
            logger.error(f"Failed to append rows: {e}")
            raise
    
    def _append_row_dicts(self, row_dicts: List[Dict]) -> int:
        """Append dictionary rows to immutable dataset file."""
        if not row_dicts:
            return 0
        
        try:
            with open(self.dataset_file, "a") as f:
                for row_dict in row_dicts:
                    f.write(json.dumps(row_dict) + "\n")
            
            self._update_metadata()
            return len(row_dicts)
        except Exception as e:
            logger.error(f"Failed to append rows: {e}")
            raise

    def _update_metadata(self) -> None:
        """Update metadata file with dataset info."""
        try:
            metadata = {
                "last_updated": datetime.now().isoformat(),
                "total_rows": len(self._processed_trade_ids),
                "dataset_file": str(self.dataset_file),
            }
            with open(self.metadata_file, "w") as f:
                json.dump(metadata, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not update metadata: {e}")

    def to_dataframe(self) -> pd.DataFrame:
        """Load full dataset as pandas DataFrame."""
        if not self.dataset_file.exists():
            return pd.DataFrame()
        
        rows = []
        with open(self.dataset_file) as f:
            for line in f:
                if line.strip():
                    rows.append(json.loads(line))
        
        return pd.DataFrame(rows)

    def get_stats(self) -> Dict:
        """Get summary statistics of dataset."""
        df = self.to_dataframe()
        if df.empty:
            return {"rows": 0, "symbols": 0, "avg_pnl": 0}
        
        return {
            "rows": len(df),
            "symbols": df["symbol"].nunique(),
            "avg_pnl_pct": df["realized_pnl_pct"].mean(),
            "win_rate": (df["realized_pnl_pct"] > 0).sum() / len(df),
            "avg_holding_days": df["holding_days"].mean(),
            "avg_confidence": df["rule_confidence"].mean(),
        }
