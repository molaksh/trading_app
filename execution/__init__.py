"""Execution realism module for Phase G."""

from execution.execution_model import (
    apply_slippage,
    compute_entry_price,
    compute_exit_price,
    check_liquidity,
    compute_slippage_cost,
    ExecutionModel,
)

__all__ = [
    "apply_slippage",
    "compute_entry_price",
    "compute_exit_price",
    "check_liquidity",
    "compute_slippage_cost",
    "ExecutionModel",
]
