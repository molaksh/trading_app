"""
Smart responder using OpenAI for conversational ops questions.

Falls back to OpenAI for questions that don't match predefined intents.
Uses existing data readers to provide context about trading system state.
"""

import json
import logging
import os
import requests
from typing import Optional, Dict, Any
from pathlib import Path

from ops_agent.summary_reader import SummaryReader
from ops_agent.positions_reader import PositionsReader
from ops_agent.errors_reader import ErrorsReader
from ops_agent.observability_reader import ObservabilityReader

logger = logging.getLogger(__name__)


class SmartResponder:
    """Use OpenAI to answer arbitrary questions about the trading system."""

    def __init__(self, logs_root: str = "logs"):
        self.api_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.base_url = os.getenv("OPENAI_API_BASE_URL", "https://api.openai.com/v1")
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        
        # Data readers for context
        self.summary_reader = SummaryReader(logs_root)
        self.positions_reader = PositionsReader(logs_root)
        self.errors_reader = ErrorsReader(logs_root)
        self.obs_reader = ObservabilityReader(logs_root)
        
        self.enabled = bool(self.api_key)

    def answer(self, question: str, scope: Optional[str] = None) -> Optional[str]:
        """
        Answer arbitrary question about the trading system using OpenAI.
        
        Args:
            question: User's question
            scope: Optional scope to filter context (e.g., 'live_kraken_crypto_global')
        
        Returns:
            Response from OpenAI, or None if disabled/error
        """
        if not self.enabled:
            logger.warning("SmartResponder disabled: OPENAI_API_KEY not set")
            return None

        try:
            # Gather system context
            context = self._build_context(scope)
            
            # Build prompt
            system_prompt = self._build_system_prompt()
            context_str = json.dumps(context, indent=2, default=str)
            
            # Call OpenAI
            logger.debug(f"SmartResponder | question={question[:50]}... scope={scope}")
            response = self._call_openai(system_prompt, context_str, question)
            
            if response:
                logger.info(f"SmartResponder | answered: {len(response)} chars")
            
            return response
            
        except Exception as e:
            logger.error(f"SmartResponder error: {e}", exc_info=True)
            return None

    def _build_context(self, scope: Optional[str]) -> Dict[str, Any]:
        """Build context about current trading system state."""
        context = {
            "timestamp": str(__import__('datetime').datetime.utcnow().isoformat()),
            "scopes": {},
        }
        
        # If scope specified, focus on that; otherwise include all
        scopes_to_check = [scope] if scope else [
            "live_kraken_crypto_global",
            "paper_kraken_crypto_global",
            "live_alpaca_swing_us",
            "paper_alpaca_swing_us",
        ]
        
        for s in scopes_to_check:
            scope_data = {}
            
            # Latest summary
            summary = self.summary_reader.get_latest_summary(s)
            if summary:
                scope_data["summary"] = {
                    "regime": getattr(summary, 'regime', 'UNKNOWN'),
                    "trades_executed": summary.trades_executed,
                    "realized_pnl": summary.realized_pnl,
                    "max_drawdown": summary.max_drawdown,
                    "data_issues": summary.data_issues,
                }
            
            # Holdings
            try:
                holdings = self.positions_reader.get_open_positions(s)
                if holdings:
                    # Convert dict to list format for JSON serialization
                    positions_list = [
                        {
                            "symbol": symbol,
                            "quantity": position.get("quantity") or position.get("entry_quantity", 0),
                            "entry_price": position.get("entry_price", 0),
                            "current_price": position.get("current_price", 0),
                        }
                        for symbol, position in list(holdings.items())[:5]
                    ]
                    scope_data["holdings"] = {
                        "count": len(holdings),
                        "positions": positions_list,
                    }
            except Exception as e:
                logger.debug(f"Error getting holdings for {s}: {e}")
                pass
            
            # Recent errors
            try:
                errors = self.errors_reader.get_recent_errors(s, limit=3)
                if errors:
                    scope_data["recent_errors"] = [
                        {"type": e.get("type"), "message": e.get("message")} 
                        for e in errors
                    ]
            except Exception:
                pass
            
            # Observability
            try:
                obs = self.obs_reader.get_snapshot(s)
                if obs:
                    scope_data["observability"] = {
                        "trading_active": obs.trading_active,
                        "blocks": obs.blocks,
                    }
            except Exception:
                pass
            
            if scope_data:
                context["scopes"][s] = scope_data
        
        return context

    def _build_system_prompt(self) -> str:
        """Build system prompt for OpenAI."""
        return """You are an expert trading system assistant. You help users understand the state of their automated trading system.

Guidelines:
- Be concise and direct
- Use data provided in context
- Focus on factual information from the system state
- If asked about trading decisions, explain the system's regime-based approach
- Always mention relevant scopes (live_kraken_crypto_global, paper_kraken_crypto_global, etc.)
- Be aware of risk management - the system prioritizes capital preservation
- Don't speculate about future markets - stick to current system state"""

    def _call_openai(self, system_prompt: str, context: str, question: str) -> Optional[str]:
        """Call OpenAI API and return response."""
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "system", "content": f"Current system state:\n{context}"},
                {"role": "user", "content": question},
            ],
            "temperature": 0.3,
            "max_tokens": 500,
        }
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        
        try:
            resp = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=10,
            )
            resp.raise_for_status()
            
            data = resp.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            
            return content if content else None
            
        except requests.RequestException as e:
            logger.error(f"OpenAI API error: {e}")
            return None


def get_smart_responder(logs_root: str = "logs") -> SmartResponder:
    """Convenience function."""
    return SmartResponder(logs_root)
