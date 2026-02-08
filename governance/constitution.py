"""
Constitutional rules for Phase C governance.

Hard-coded, non-bypassable rules enforced by the Auditor agent.
"""

import re
from typing import List, Tuple

# Allowed proposal types
ALLOWED_PROPOSAL_TYPES = [
    "ADD_SYMBOLS",
    "REMOVE_SYMBOLS",
    "ADJUST_RULE",
    "ADJUST_THRESHOLD",
]

# Forbidden proposal types
FORBIDDEN_PROPOSAL_TYPES = [
    "EXECUTE_TRADE",
    "MODIFY_POSITION",
    "BYPASS_RISK",
    "DISABLE_SAFETY",
    "OVERRIDE_RULE",
]

# Forbidden language that indicates auto-execution
FORBIDDEN_LANGUAGE_PATTERNS = [
    r"\bexecute\b",
    r"\bauto[-]?apply\b",
    r"\bbypass\b",
    r"\boverride\b",
    r"\bforce\b",
    r"\bdisable\b",
    r"\bskip\b",
    r"\binject\b",
]

# Valid symbol patterns (uppercase alphanumeric, no special chars except dash)
VALID_SYMBOL_PATTERN = re.compile(r"^[A-Z][A-Z0-9-]*$")

# Limits
MAX_SYMBOLS_ADDED_PER_PROPOSAL = 5
MAX_SYMBOLS_REMOVED_PER_PROPOSAL = 3
MAX_PROPOSAL_SIZE = 10


def validate_proposal_type(proposal_type: str) -> Tuple[bool, str]:
    """
    Validate proposal_type field.

    Args:
        proposal_type: The proposed type

    Returns:
        (is_valid, error_message)
    """
    if proposal_type in FORBIDDEN_PROPOSAL_TYPES:
        return False, f"Proposal type '{proposal_type}' is forbidden by constitution"

    if proposal_type not in ALLOWED_PROPOSAL_TYPES:
        allowed = ", ".join(ALLOWED_PROPOSAL_TYPES)
        return False, f"Proposal type '{proposal_type}' not allowed. Allowed: {allowed}"

    return True, ""


def validate_non_binding(non_binding: bool) -> Tuple[bool, str]:
    """
    Validate non_binding flag.

    Constitutional requirement: proposals must NEVER be binding.
    """
    if non_binding is not True:
        return False, "Constitutional violation: non_binding must be True (proposals are never auto-applied)"
    return True, ""


def validate_symbols(symbols: List[str]) -> Tuple[bool, str]:
    """
    Validate symbol names.

    Args:
        symbols: List of symbols

    Returns:
        (is_valid, error_message)
    """
    if not symbols:
        return False, "symbols list cannot be empty"

    if len(symbols) > MAX_PROPOSAL_SIZE:
        return False, f"symbols list too large: {len(symbols)} > {MAX_PROPOSAL_SIZE}"

    for symbol in symbols:
        if not isinstance(symbol, str):
            return False, f"Symbol must be string, got {type(symbol)}: {symbol}"

        if not VALID_SYMBOL_PATTERN.match(symbol):
            return False, f"Invalid symbol format: '{symbol}' (must be uppercase, e.g., 'BTC', 'ETH-USD')"

    return True, ""


def validate_symbol_count_by_type(
    proposal_type: str,
    symbols: List[str]
) -> Tuple[bool, str]:
    """
    Validate symbol counts based on proposal type.

    Args:
        proposal_type: Type of proposal
        symbols: Affected symbols

    Returns:
        (is_valid, error_message)
    """
    if proposal_type == "ADD_SYMBOLS":
        if len(symbols) > MAX_SYMBOLS_ADDED_PER_PROPOSAL:
            return False, (
                f"Too many symbols to add: {len(symbols)} > {MAX_SYMBOLS_ADDED_PER_PROPOSAL}. "
                f"Make multiple proposals."
            )

    elif proposal_type == "REMOVE_SYMBOLS":
        if len(symbols) > MAX_SYMBOLS_REMOVED_PER_PROPOSAL:
            return False, (
                f"Too many symbols to remove: {len(symbols)} > {MAX_SYMBOLS_REMOVED_PER_PROPOSAL}. "
                f"Make multiple proposals."
            )

    return True, ""


def validate_no_forbidden_language(text: str) -> Tuple[bool, str]:
    """
    Validate that text doesn't contain forbidden execution/automation language.

    Args:
        text: Text to check

    Returns:
        (is_valid, error_message)
    """
    text_lower = text.lower()

    for pattern in FORBIDDEN_LANGUAGE_PATTERNS:
        if re.search(pattern, text_lower):
            match = re.search(pattern, text_lower)
            return False, (
                f"Proposal contains forbidden language: '{match.group()}' "
                f"(proposals must not include execution/automation directives)"
            )

    return True, ""


def validate_proposal(proposal: dict) -> Tuple[bool, List[str]]:
    """
    Validate proposal against constitutional rules.

    This is the main entry point for constitutional validation.
    Returns all violations found, not just the first one.

    Args:
        proposal: Proposal dict

    Returns:
        (passed, list_of_violations)
    """
    violations = []

    # Check proposal_type
    if "proposal_type" in proposal:
        valid, msg = validate_proposal_type(proposal["proposal_type"])
        if not valid:
            violations.append(msg)

    # Check non_binding
    if "non_binding" in proposal:
        valid, msg = validate_non_binding(proposal["non_binding"])
        if not valid:
            violations.append(msg)

    # Check symbols
    if "symbols" in proposal:
        valid, msg = validate_symbols(proposal["symbols"])
        if not valid:
            violations.append(msg)

        # Check count limits
        if valid and "proposal_type" in proposal:
            valid2, msg2 = validate_symbol_count_by_type(
                proposal["proposal_type"],
                proposal["symbols"]
            )
            if not valid2:
                violations.append(msg2)

    # Check for forbidden language
    for field in ["rationale", "risk_notes"]:
        if field in proposal:
            valid, msg = validate_no_forbidden_language(proposal[field])
            if not valid:
                violations.append(msg)

    passed = len(violations) == 0
    return passed, violations
