"""
Tests for crypto ML orchestration gating and safety.

CRITICAL: Verifies that ML training is truthful:
- Skips with no trades
- Logs correct outcomes
- Never logs COMPLETED without actual work
"""

import json
import logging
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from crypto_main import _task_ml_training
from execution.runtime import build_paper_trading_runtime
from runtime.environment_guard import TradingEnvironment


@pytest.fixture
def empty_trade_ledger(tmp_path):
    """Fixture: empty trade ledger (no trades)."""
    ledger_path = tmp_path / "ledger"
    ledger_path.mkdir()
    trades_file = ledger_path / "trades.jsonl"
    trades_file.write_text("")  # Empty file
    return trades_file


@pytest.fixture
def mock_runtime(tmp_path, empty_trade_ledger):
    """Fixture: mock runtime with empty trade ledger."""
    runtime = MagicMock()
    runtime.trade_ledger.get_all_trades.return_value = []
    return runtime


class TestCryptoMLOrchestrationGating:
    """Test ML training gating logic."""
    
    def test_ml_training_skips_with_no_trades(self, caplog, mock_runtime):
        """
        CRITICAL TEST: ML training must skip when ledger is empty.
        
        Expected behavior:
        - Returns cleanly
        - Logs ML_TRAINING_SKIPPED with reason=no_trades_available
        - Does NOT log ML_TRAINING_COMPLETED
        - No ML orchestrator code is called
        """
        with caplog.at_level(logging.INFO):
            with patch('crypto_main.get_environment_guard') as mock_guard:
                with patch('crypto_main.build_paper_trading_runtime', return_value=mock_runtime):
                    mock_guard_instance = MagicMock()
                    mock_guard_instance.environment = TradingEnvironment.PAPER
                    mock_guard.return_value = mock_guard_instance
                    
                    result = _task_ml_training(runtime=mock_runtime)
        
        # Assertions
        assert result is mock_runtime, "Should return runtime unchanged"
        
        # Check logs for correct outcome
        log_text = caplog.text
        assert "ML_TRAINING_SKIPPED" in log_text, "Should log SKIPPED event"
        assert "no_trades_available" in log_text, "Should cite empty ledger"
        assert "trade_count=0" in log_text, "Should show 0 trades"
        assert "ML_TRAINING_COMPLETED" not in log_text, "Should NOT log fake completion"
        assert "feature extraction" not in log_text, "Should not log placeholder messages"
    
    def test_ml_training_logs_correct_events_sequence(self, caplog):
        """Verify event sequence when trades exist but ML not implemented."""
        mock_runtime = MagicMock()
        mock_runtime.trade_ledger.get_all_trades.return_value = [
            {"id": "trade_1", "status": "CLOSED"}
        ]
        mock_runtime._get_ml_orchestrator.side_effect = NotImplementedError("ML not ready")
        
        with caplog.at_level(logging.INFO):
            with patch('crypto_main.get_environment_guard') as mock_guard:
                with patch('crypto_main.build_paper_trading_runtime', return_value=mock_runtime):
                    mock_guard_instance = MagicMock()
                    mock_guard_instance.environment = TradingEnvironment.PAPER
                    mock_guard.return_value = mock_guard_instance
                    
                    result = _task_ml_training(runtime=mock_runtime)
        
        log_text = caplog.text
        assert "ML_TRAINING_SKIPPED" in log_text, "Should skip due to not implemented"
        assert "ml_orchestrator_not_implemented" in log_text, "Should cite reason"
        assert "trade_count=1" in log_text, "Should show trade count"
        assert "ML_TRAINING_COMPLETED" not in log_text, "Should NOT fake completion"
    
    def test_ml_training_logs_start_and_completion_when_successful(self, caplog):
        """Verify START→COMPLETED sequence when ML actually runs."""
        mock_runtime = MagicMock()
        mock_runtime.trade_ledger.get_all_trades.return_value = [
            {"id": "trade_1", "status": "CLOSED"},
            {"id": "trade_2", "status": "CLOSED"},
        ]
        
        mock_orchestrator = MagicMock()
        mock_orchestrator.run_offline_ml_cycle.return_value = {
            "model_version": "v_2026_02_06_001",
            "metrics": {"accuracy": 0.72}
        }
        mock_runtime._get_ml_orchestrator.return_value = mock_orchestrator
        
        with caplog.at_level(logging.INFO):
            with patch('crypto_main.get_environment_guard') as mock_guard:
                with patch('crypto_main.build_paper_trading_runtime', return_value=mock_runtime):
                    mock_guard_instance = MagicMock()
                    mock_guard_instance.environment = TradingEnvironment.PAPER
                    mock_guard.return_value = mock_guard_instance
                    
                    result = _task_ml_training(runtime=mock_runtime)
        
        log_text = caplog.text
        assert "ML_TRAINING_START" in log_text, "Should log START event"
        assert "trade_count=2" in log_text, "Should show trade count"
        assert "ML_TRAINING_COMPLETED" in log_text, "Should log completion (not fake)"
        assert "v_2026_02_06_001" in log_text, "Should cite model version"
    
    def test_ml_training_disabled_in_live_mode(self, caplog, mock_runtime):
        """Verify ML training is blocked in live mode."""
        with caplog.at_level(logging.INFO):
            with patch('crypto_main.get_environment_guard') as mock_guard:
                mock_guard_instance = MagicMock()
                mock_guard_instance.environment = TradingEnvironment.LIVE
                mock_guard.return_value = mock_guard_instance
                
                result = _task_ml_training(runtime=mock_runtime)
        
        log_text = caplog.text
        assert "ML training disabled in live mode" in log_text
        assert "ML_TRAINING_SKIPPED" not in log_text  # No explicit skip, just warning
    
    def test_ml_training_handles_orchestrator_exception_gracefully(self, caplog):
        """Verify exception handling logs ML_TRAINING_FAILED and doesn't crash."""
        mock_runtime = MagicMock()
        mock_runtime.trade_ledger.get_all_trades.return_value = [{"id": "trade_1"}]
        
        mock_orchestrator = MagicMock()
        mock_orchestrator.run_offline_ml_cycle.side_effect = ValueError("Corrupt data")
        mock_runtime._get_ml_orchestrator.return_value = mock_orchestrator
        
        with caplog.at_level(logging.ERROR):
            with patch('crypto_main.get_environment_guard') as mock_guard:
                with patch('crypto_main.build_paper_trading_runtime', return_value=mock_runtime):
                    mock_guard_instance = MagicMock()
                    mock_guard_instance.environment = TradingEnvironment.PAPER
                    mock_guard.return_value = mock_guard_instance
                    
                    result = _task_ml_training(runtime=mock_runtime)
        
        log_text = caplog.text
        assert "ML_TRAINING_FAILED" in log_text, "Should log failure event"
        assert "Corrupt data" in log_text, "Should cite exception"
        assert result is mock_runtime, "Should return runtime even on failure"


class TestCryptoMLOrchestrationNoDeadCode:
    """Verify no commented-out or fake code remains."""
    
    def test_no_placeholder_feature_extraction_logs(self, caplog):
        """Ensure placeholder 'feature extraction' message is removed."""
        mock_runtime = MagicMock()
        mock_runtime.trade_ledger.get_all_trades.return_value = []
        
        with caplog.at_level(logging.INFO):
            with patch('crypto_main.get_environment_guard') as mock_guard:
                with patch('crypto_main.build_paper_trading_runtime', return_value=mock_runtime):
                    mock_guard_instance = MagicMock()
                    mock_guard_instance.environment = TradingEnvironment.PAPER
                    mock_guard.return_value = mock_guard_instance
                    
                    _task_ml_training(runtime=mock_runtime)
        
        # Placeholder message should be gone
        assert "feature extraction" not in caplog.text.lower()
        assert "running" not in caplog.text or "ML_TRAINING" in caplog.text


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
