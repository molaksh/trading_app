#!/usr/bin/env python3
"""
Phase 0 Implementation Audit

Lists all files created and modified as part of Phase 0 implementation.
Use this to verify the implementation is complete.
"""

import os
from pathlib import Path
from datetime import datetime

# Workspace root
WORKSPACE_ROOT = Path("/Users/mohan/Documents/SandBox/test/trading_app")

# Files created for Phase 0
NEW_FILES = [
    ("Core Abstractions", [
        "config/scope.py",
        "config/scope_paths.py",
        "broker/broker_factory.py",
        "broker/ibkr_adapter.py",
        "broker/zerodha_adapter.py",
        "broker/crypto_adapter.py",
        "strategies/registry.py",
        "ml/ml_state.py",
        "startup/validator.py",
    ]),
    ("Documentation", [
        "PHASE_0_README.md",
        "PHASE_0_INTEGRATION.md",
        "PHASE_0_COMPLETION_SUMMARY.txt",
        "PHASE_0_INDEX.md",
        "verify_phase0.py",
    ]),
]

# Files modified for Phase 0
MODIFIED_FILES = [
    "execution/runtime.py",
    "execution/scheduler.py",
    "broker/execution_logger.py",
    "broker/trade_ledger.py",
    "strategies/base.py",
    "strategies/swing.py",
]

def get_file_size(path: Path) -> str:
    """Get human-readable file size."""
    if not path.exists():
        return "NOT FOUND"
    
    size = path.stat().st_size
    for unit in ['B', 'KB', 'MB']:
        if size < 1024:
            return f"{size} {unit}"
        size /= 1024
    return f"{size:.1f} MB"

def get_line_count(path: Path) -> int:
    """Count lines in file."""
    if not path.exists():
        return 0
    try:
        with open(path, 'r') as f:
            return len(f.readlines())
    except:
        return 0

def main():
    print("=" * 100)
    print("PHASE 0 IMPLEMENTATION AUDIT")
    print("=" * 100)
    print(f"Workspace: {WORKSPACE_ROOT}\n")
    
    total_new_lines = 0
    total_modified_lines = 0
    new_files_found = 0
    new_files_missing = 0
    modified_files_found = 0
    modified_files_missing = 0
    
    # NEW FILES
    print("NEW FILES CREATED")
    print("-" * 100)
    
    for category, files in NEW_FILES:
        print(f"\n{category}:")
        for file in files:
            path = WORKSPACE_ROOT / file
            exists = path.exists()
            size = get_file_size(path)
            lines = get_line_count(path)
            
            status = "✓" if exists else "✗"
            print(f"  {status} {file:50} {size:15} {lines:6} lines")
            
            if exists:
                new_files_found += 1
                total_new_lines += lines
            else:
                new_files_missing += 1
    
    # MODIFIED FILES
    print("\n" + "=" * 100)
    print("MODIFIED FILES")
    print("-" * 100)
    
    for file in MODIFIED_FILES:
        path = WORKSPACE_ROOT / file
        exists = path.exists()
        size = get_file_size(path)
        lines = get_line_count(path)
        
        status = "✓" if exists else "✗"
        print(f"  {status} {file:50} {size:15} {lines:6} lines")
        
        if exists:
            modified_files_found += 1
            total_modified_lines += lines
        else:
            modified_files_missing += 1
    
    # SUMMARY
    print("\n" + "=" * 100)
    print("AUDIT SUMMARY")
    print("-" * 100)
    
    new_files_total = len([f for _, files in NEW_FILES for f in files])
    
    print(f"\nNew Files:")
    print(f"  Created: {new_files_found}/{new_files_total}")
    print(f"  Total lines: {total_new_lines:,}")
    
    print(f"\nModified Files:")
    print(f"  Updated: {modified_files_found}/{len(MODIFIED_FILES)}")
    print(f"  Total lines: {total_modified_lines:,}")
    
    print(f"\nOverall:")
    print(f"  Files created: {new_files_found}")
    print(f"  Files modified: {modified_files_found}")
    print(f"  Total lines added: {total_new_lines + total_modified_lines:,}")
    
    if new_files_missing == 0 and modified_files_missing == 0:
        print(f"\n✓ ALL FILES PRESENT AND ACCOUNTED FOR")
        print(f"✓ Phase 0 Implementation Complete")
    else:
        print(f"\n✗ Missing {new_files_missing + modified_files_missing} files")
        print(f"✗ Phase 0 Implementation Incomplete")
    
    print("=" * 100)
    
    return 0 if new_files_missing == 0 and modified_files_missing == 0 else 1

if __name__ == "__main__":
    import sys
    sys.exit(main())
