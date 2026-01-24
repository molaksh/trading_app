"""
Dataset builder: aggregates feature snapshots across symbols and saves to disk.
Ensures deterministic ordering, reproducibility, and leak-free data.
"""

import logging
import os
from pathlib import Path
from typing import Optional, List
import pandas as pd
from datetime import datetime
from config.settings import (
    DATASET_OUTPUT_DIR,
    DATASET_FILE_FORMAT,
    LOOKBACK_DAYS,
    LOG_LEVEL,
    LOG_FORMAT,
    LOG_DATE_FORMAT,
)
from data.price_loader import load_price_data
from dataset.feature_snapshot import create_feature_snapshots, validate_snapshots

logger = logging.getLogger(__name__)


class DatasetBuilder:
    """
    Build and save ML-ready dataset from feature snapshots.
    
    Workflow:
    1. Load price data for each symbol
    2. Create feature snapshots (no lookahead)
    3. Aggregate across symbols
    4. Validate leak-free and reproducible
    5. Save to disk (CSV or Parquet)
    """
    
    def __init__(self, output_dir: str = DATASET_OUTPUT_DIR, file_format: str = DATASET_FILE_FORMAT):
        """
        Initialize dataset builder.
        
        Parameters
        ----------
        output_dir : str
            Directory to save dataset files
        file_format : str
            Format for saving ('csv' or 'parquet')
        """
        self.output_dir = Path(output_dir)
        self.file_format = file_format.lower()
        
        # Validate file format
        if self.file_format not in ['csv', 'parquet']:
            raise ValueError(f"Invalid file_format: {self.file_format}. Must be 'csv' or 'parquet'")
        
        # Create output directory if it doesn't exist
        self.output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Output directory: {self.output_dir.absolute()}")
    
    def build_dataset(
        self,
        symbols: List[str],
        lookback_days: int = LOOKBACK_DAYS
    ) -> Optional[pd.DataFrame]:
        """
        Build dataset from symbols.
        
        Parameters
        ----------
        symbols : list
            List of ticker symbols to process
        lookback_days : int
            Number of trading days to load for each symbol
        
        Returns
        -------
        pd.DataFrame or None
            Aggregated dataset with all snapshots, or None if no valid data
        """
        logger.info("=" * 90)
        logger.info(f"Building ML Dataset | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("=" * 90)
        logger.info(f"Symbols: {len(symbols)}, Lookback: {lookback_days} days, Format: {self.file_format}")
        
        all_snapshots = []
        failed_symbols = []
        
        for i, symbol in enumerate(symbols):
            logger.info(f"[{i+1:2d}/{len(symbols)}] Processing {symbol}")
            
            try:
                # Load price data
                price_df = load_price_data(symbol, lookback_days)
                if price_df is None or price_df.empty:
                    logger.warning(f"  Failed to load price data for {symbol}")
                    failed_symbols.append(symbol)
                    continue
                
                # Create feature snapshots
                snapshots_df = create_feature_snapshots(price_df, symbol)
                if snapshots_df is None or snapshots_df.empty:
                    logger.warning(f"  No valid snapshots for {symbol}")
                    failed_symbols.append(symbol)
                    continue
                
                # Validate snapshots
                if not validate_snapshots(snapshots_df):
                    logger.warning(f"  Snapshots failed validation for {symbol}")
                    failed_symbols.append(symbol)
                    continue
                
                all_snapshots.append(snapshots_df)
                logger.info(f"  ✓ {len(snapshots_df)} snapshots")
            
            except Exception as e:
                logger.error(f"  Exception: {type(e).__name__}: {e}")
                failed_symbols.append(symbol)
                continue
        
        # Aggregate snapshots
        if len(all_snapshots) == 0:
            logger.error("No valid snapshots created for any symbol")
            return None
        
        logger.info(f"Aggregating {len(all_snapshots)} symbol snapshots...")
        dataset = pd.concat(all_snapshots, ignore_index=True)
        
        # Sort deterministically: by date, then by symbol
        dataset = dataset.sort_values(['date', 'symbol']).reset_index(drop=True)
        
        logger.info("=" * 90)
        logger.info("DATASET SUMMARY")
        logger.info("=" * 90)
        logger.info(f"Total rows:              {len(dataset)}")
        logger.info(f"Symbols processed:       {len(all_snapshots)}")
        logger.info(f"Failed symbols:          {len(failed_symbols)}")
        if failed_symbols:
            logger.info(f"  {', '.join(failed_symbols[:5])}" + 
                       (f" (and {len(failed_symbols) - 5} more)" if len(failed_symbols) > 5 else ""))
        
        logger.info(f"Date range:              {dataset['date'].min()} to {dataset['date'].max()}")
        logger.info(f"Unique symbols:          {dataset['symbol'].nunique()}")
        
        # Label distribution
        label_counts = dataset['label'].value_counts().sort_index()
        label_pct = (dataset['label'].value_counts(normalize=True).sort_index() * 100)
        logger.info(f"\nLabel distribution:")
        for label, count in label_counts.items():
            logger.info(f"  Label {label}: {count:7d} ({label_pct[label]:5.1f}%)")
        
        # Confidence distribution
        logger.info(f"\nConfidence distribution:")
        conf_counts = dataset['confidence'].value_counts().sort_index()
        for conf, count in conf_counts.items():
            logger.info(f"  Confidence {conf}: {count:7d}")
        
        logger.info("=" * 90)
        
        return dataset
    
    def save_dataset(self, dataset: pd.DataFrame, name: str = "trading_dataset") -> Optional[str]:
        """
        Save dataset to disk in specified format.
        
        Parameters
        ----------
        dataset : pd.DataFrame
            Dataset to save
        name : str
            Filename prefix (without extension)
        
        Returns
        -------
        str or None
            Path to saved file, or None if save fails
        """
        if dataset is None or dataset.empty:
            logger.error("Cannot save empty dataset")
            return None
        
        try:
            # Create filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{name}_{timestamp}.{self.file_format}"
            filepath = self.output_dir / filename
            
            logger.info(f"Saving dataset to {filepath}")
            
            if self.file_format == 'parquet':
                dataset.to_parquet(filepath, index=False, compression='snappy')
            else:  # csv
                dataset.to_csv(filepath, index=False)
            
            logger.info(f"✓ Dataset saved: {filepath}")
            return str(filepath)
        
        except Exception as e:
            logger.error(f"Failed to save dataset: {type(e).__name__}: {e}")
            return None
    
    def build_and_save(
        self,
        symbols: List[str],
        lookback_days: int = LOOKBACK_DAYS,
        name: str = "trading_dataset"
    ) -> Optional[str]:
        """
        Build and save dataset in one call.
        
        Parameters
        ----------
        symbols : list
            List of symbols to process
        lookback_days : int
            Number of days to load per symbol
        name : str
            Dataset filename prefix
        
        Returns
        -------
        str or None
            Path to saved dataset, or None if failed
        """
        # Build dataset
        dataset = self.build_dataset(symbols, lookback_days)
        if dataset is None:
            logger.error("Dataset building failed")
            return None
        
        # Save dataset
        filepath = self.save_dataset(dataset, name)
        
        return filepath


def build_dataset_pipeline(symbols: List[str], lookback_days: int = LOOKBACK_DAYS) -> Optional[str]:
    """
    Convenience function to build and save dataset.
    
    Parameters
    ----------
    symbols : list
        List of symbols to process
    lookback_days : int
        Number of days to load
    
    Returns
    -------
    str or None
        Path to saved dataset file, or None if failed
    """
    builder = DatasetBuilder()
    return builder.build_and_save(symbols, lookback_days)
