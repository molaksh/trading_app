#!/usr/bin/env python3
"""
Documentation Hygiene Guard

Enforces single-source-of-truth documentation policy:
1. All documentation must be in DOCUMENTATION.md only
2. New documentation MUST be prepended to the top (under "Latest Updates")
3. No new .md files allowed (except DOCUMENTATION.md and README.md)
4. This guard runs as a pre-commit hook

Exit codes:
  0 = all checks pass
  1 = violations found
"""

import re
import sys
import subprocess
from pathlib import Path


def get_git_diff(staged_only=True):
    """Get list of changed files from git."""
    cmd = ['git', 'diff', '--name-only']
    if staged_only:
        cmd.append('--cached')
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return result.stdout.strip().split('\n') if result.stdout.strip() else []
    except subprocess.CalledProcessError as e:
        print(f"Error running git diff: {e}")
        return []


def check_new_md_files(changed_files):
    """Check if any new .md files (other than allowed ones) are being added."""
    allowed_files = {'DOCUMENTATION.md', 'README.md'}
    violations = []
    
    for filepath in changed_files:
        if not filepath.endswith('.md'):
            continue
        
        # Check if it's a newly added file (not just modified)
        try:
            # If file doesn't exist in HEAD, it's new
            result = subprocess.run(
                ['git', 'ls-tree', '-r', 'HEAD', filepath],
                capture_output=True,
                text=True
            )
            is_new = result.returncode != 0
        except:
            is_new = True  # Assume new if can't check
        
        if is_new and filepath not in allowed_files:
            violations.append(f"New .md file not allowed: {filepath}")
    
    return violations


def check_documentation_md_format():
    """Check that DOCUMENTATION.md has proper structure."""
    doc_path = Path('DOCUMENTATION.md')
    
    if not doc_path.exists():
        return ["DOCUMENTATION.md does not exist"]
    
    content = doc_path.read_text()
    violations = []
    
    # Check for required sections
    if '## 🔔 Latest Updates' not in content:
        violations.append("DOCUMENTATION.md missing '## 🔔 Latest Updates' section")
    
    if '## 📚 Historical Record' not in content:
        violations.append("DOCUMENTATION.md missing '## 📚 Historical Record' section")
    
    # Warn if new entries might not be at top
    # (This is a soft check since we can't easily parse the structure)
    
    return violations


def check_documentation_md_prepended():
    """Check that new content in DOCUMENTATION.md is prepended, not appended."""
    # Get the diff for DOCUMENTATION.md
    try:
        result = subprocess.run(
            ['git', 'diff', '--cached', 'DOCUMENTATION.md'],
            capture_output=True,
            text=True,
            check=True
        )
        diff = result.stdout
    except subprocess.CalledProcessError:
        return []  # File not staged, skip check
    
    violations = []
    
    # Check if additions are in the "Latest Updates" section (near top)
    # vs the "Historical Record" section (bottom)
    lines = diff.split('\n')
    
    additions_in_historical = False
    additions_in_latest = False
    current_section = None
    
    for line in lines:
        if line.startswith('@@'):
            # Extract line numbers to determine section
            match = re.search(r'\+(\d+)', line)
            if match:
                line_num = int(match.group(1))
                # Rough heuristic: if additions are after line 100, likely in Historical
                if line_num > 200:
                    current_section = 'historical'
                else:
                    current_section = 'latest'
        
        if line.startswith('+') and not line.startswith('+++'):
            if '## 🔔 Latest Updates' in line or '### ' in line:
                additions_in_latest = True
            if '## 📚 Historical Record' in line:
                additions_in_historical = True
    
    # Soft warning: only if clearly appending to bottom
    if additions_in_historical and not additions_in_latest:
        violations.append(
            "⚠️  New documentation may be appended instead of prepended. "
            "Ensure new entries are under '## 🔔 Latest Updates' section at the TOP."
        )
    
    return violations


def main():
    """Run all documentation hygiene checks."""
    all_violations = []
    
    print("🔍 Running documentation hygiene checks...")
    print()
    
    # Check 1: No new .md files
    changed_files = get_git_diff(staged_only=True)
    violations = check_new_md_files(changed_files)
    if violations:
        all_violations.extend(violations)
        print("❌ New .md file check:")
        for v in violations:
            print(f"   {v}")
        print()
    else:
        print("✅ New .md file check passed")
    
    # Check 2: DOCUMENTATION.md structure
    violations = check_documentation_md_format()
    if violations:
        all_violations.extend(violations)
        print("❌ DOCUMENTATION.md format check:")
        for v in violations:
            print(f"   {v}")
        print()
    else:
        print("✅ DOCUMENTATION.md format check passed")
    
    # Check 3: Prepending (soft warning)
    violations = check_documentation_md_prepended()
    if violations:
        print("⚠️  Prepending check (warning):")
        for v in violations:
            print(f"   {v}")
        print()
    else:
        print("✅ Prepending check passed")
    
    print()
    if all_violations:
        print(f"❌ {len(all_violations)} violation(s) found")
        return 1
    else:
        print("✅ All documentation hygiene checks passed")
        return 0


if __name__ == '__main__':
    sys.exit(main())
