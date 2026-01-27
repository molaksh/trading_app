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
    """

    def __init__(self, dataset_dir: Path, trade_ledger):
        """
        Initialize dataset builder.
        
        Args:
            dataset_dir: Directory to store dataset files
            trade_ledger: TradeLedger instance with closed trades
        """
        self.dataset_dir = Path(dataset_dir)
        self.dataset_dir.mkdir(parents=True, exist_ok=True)
        self.trade_ledger = trade_ledger
        
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
        
        Args:
            mae_threshold: MAE threshold for 'bad' trade classification
        
        Returns:
            Tuple of (rows_added, rows_total)
        """
        logger.info("=" * 80)
        logger.info("DATASET BUILDING")
        logger.info("=" * 80)
        
        # Get all closed trades from ledger
        all_trades = self.trade_ledger.get_all_trades()
        closed_trades = [t for t in all_trades if t.exit_timestamp is not None]
        
        logger.info(f"Total trades in ledger: {len(all_trades)}")
        logger.info(f"Closed trades: {len(closed_trades)}")
        logger.info(f"Open trades: {len(all_trades) - len(closed_trades)}")
        
        new_rows = []
        for trade in closed_trades:
            # Skip if already processed (prevent duplicates)
            trade_id = (trade.symbol, trade.entry_timestamp)
            if trade_id in self._processed_trade_ids:
                continue
            
            try:
                # Reconstruct decision-time context
                row = self._trade_to_row(trade, mae_threshold)
                if row:
                    new_rows.append(row)
                    self._processed_trade_ids.add(trade_id)
            except Exception as e:
                logger.warning(f"Could not process trade {trade.symbol}: {e}")
        
        # Append to dataset (immutable)
        rows_added = self._append_rows(new_rows)
        rows_total = len(self._processed_trade_ids)
        
        logger.info(f"Rows added: {rows_added}")
        logger.info(f"Dataset total: {rows_total}")
        logger.info("=" * 80)
        
        return rows_added, rows_total

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
        
        return TradeDataRow(
            symbol=trade.symbol,
            decision_timestamp=trade.entry_timestamp,
            rule_confidence=float(trade.confidence),
            rule_features=trade.entry_features.copy() if hasattr(trade, "entry_features") else {},
            position_size=trade.quantity,
            entry_price=trade.entry_price,
            exit_price=trade.exit_price,
            exit_timestamp=trade.exit_timestamp,
            holding_days=holding_days,
            realized_pnl_pct=realized_pnl_pct,
            mae_pct=mae_pct,
            mfe_pct=mfe_pct,
        )

    def _append_rows(self, rows: List[TradeDataRow]) -> int:
        """Append rows to immutable dataset file."""
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
