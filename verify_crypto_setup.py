#!/usr/bin/env python3
"""
Quick validation script to verify crypto implementation is complete.
Run this to verify all components are properly installed.
"""

import os
import sys
from pathlib import Path

def check_file_exists(path, description):
    """Check if file exists."""
    if Path(path).exists():
        print(f"✓ {description}")
        return True
    else:
        print(f"✗ {description} - MISSING")
        return False

def check_module_imports():
    """Check if all modules can be imported."""
    modules = [
        ('crypto.artifacts', 'CryptoArtifactStore'),
        ('crypto.universe', 'CryptoUniverse'),
        ('crypto.scheduling', 'DowntimeScheduler'),
        ('crypto.regime', 'CryptoRegimeEngine'),
        ('crypto.strategies', 'CryptoStrategySelector'),
        ('crypto.ml_pipeline', 'MLPipeline'),
        ('broker.kraken', 'KrakenAdapter'),
        ('broker.kraken.paper', 'PaperKrakenSimulator'),
    ]
    
    all_ok = True
    for module_name, class_name in modules:
        try:
            module = __import__(module_name, fromlist=[class_name])
            if hasattr(module, class_name):
                print(f"✓ Import {module_name}.{class_name}")
            else:
                print(f"✗ {class_name} not found in {module_name}")
                all_ok = False
        except ImportError as e:
            print(f"✗ Failed to import {module_name}: {e}")
            all_ok = False
    
    return all_ok

def main():
    """Run validation checks."""
    print("=" * 60)
    print("CRYPTO IMPLEMENTATION VALIDATION")
    print("=" * 60)
    
    # Change to project root
    project_root = Path(__file__).parent
    os.chdir(project_root)
    
    # Add project to path
    sys.path.insert(0, str(project_root))
    
    all_checks = []
    
    # 1. Check directory structure
    print("\n[1] Directory Structure")
    print("-" * 60)
    
    dirs = [
        ('crypto/artifacts', 'Artifact store module'),
        ('crypto/universe', 'Symbol universe module'),
        ('crypto/scheduling', 'Downtime scheduler module'),
        ('crypto/regime', 'Regime detection module'),
        ('crypto/strategies', 'Strategy selection module'),
        ('crypto/ml_pipeline', 'ML pipeline module'),
        ('broker/kraken', 'Kraken broker module'),
        ('config/crypto', 'Crypto config directory'),
        ('tools/crypto', 'Crypto tools directory'),
        ('tests/crypto', 'Crypto tests directory'),
    ]
    
    dir_ok = all(check_file_exists(d, desc) for d, desc in dirs)
    all_checks.append(dir_ok)
    
    # 2. Check source files
    print("\n[2] Source Files")
    print("-" * 60)
    
    files = [
        ('crypto/artifacts/__init__.py', 'Artifact store'),
        ('crypto/universe/__init__.py', 'Symbol universe'),
        ('crypto/scheduling/__init__.py', 'Downtime scheduler'),
        ('crypto/regime/__init__.py', 'Regime engine'),
        ('crypto/strategies/__init__.py', 'Strategy selector'),
        ('crypto/ml_pipeline/__init__.py', 'ML pipeline'),
        ('broker/kraken/__init__.py', 'Kraken adapter'),
        ('broker/kraken/paper.py', 'Paper simulator'),
    ]
    
    files_ok = all(check_file_exists(f, desc) for f, desc in files)
    all_checks.append(files_ok)
    
    # 3. Check config files
    print("\n[3] Configuration Files")
    print("-" * 60)
    
    configs = [
        ('config/crypto/paper.kraken.crypto.global.yaml', 'Paper config'),
        ('config/crypto/live.kraken.crypto.global.yaml', 'Live config'),
    ]
    
    configs_ok = all(check_file_exists(c, desc) for c, desc in configs)
    all_checks.append(configs_ok)
    
    # 4. Check tools
    print("\n[4] Approval Tools")
    print("-" * 60)
    
    tools = [
        ('tools/crypto/validate_model.py', 'Model validation tool'),
        ('tools/crypto/promote_model.py', 'Model promotion tool'),
        ('tools/crypto/rollback_model.py', 'Model rollback tool'),
    ]
    
    tools_ok = all(check_file_exists(t, desc) for t, desc in tools)
    all_checks.append(tools_ok)
    
    # 5. Check test files
    print("\n[5] Test Files")
    print("-" * 60)
    
    tests = [
        ('tests/crypto/test_universe.py', 'Universe tests (10)'),
        ('tests/crypto/test_downtime_scheduler.py', 'Scheduler tests (12)'),
        ('tests/crypto/test_artifact_isolation.py', 'Isolation tests (5)'),
        ('tests/crypto/test_paper_simulator.py', 'Simulator tests (12)'),
        ('tests/crypto/test_model_approval_gates.py', 'Approval tests (8)'),
        ('tests/crypto/test_ml_pipeline.py', 'Pipeline tests (14)'),
        ('tests/crypto/test_integration.py', 'Integration tests (15)'),
    ]
    
    tests_ok = all(check_file_exists(t, desc) for t, desc in tests)
    all_checks.append(tests_ok)
    
    # 6. Check Docker scripts
    print("\n[6] Docker Scripts")
    print("-" * 60)
    
    scripts = [
        ('run_paper_kraken_crypto.sh', 'Paper container runner'),
        ('run_live_kraken_crypto.sh', 'Live container runner'),
    ]
    
    scripts_ok = all(check_file_exists(s, desc) for s, desc in scripts)
    all_checks.append(scripts_ok)
    
    # 7. Check documentation
    print("\n[7] Documentation Files")
    print("-" * 60)
    
    docs = [
        ('CRYPTO_README.md', 'Comprehensive README'),
        ('CRYPTO_TESTING_GUIDE.md', 'Testing guide'),
        ('CRYPTO_DEPLOYMENT_CHECKLIST.md', 'Deployment checklist'),
        ('CRYPTO_IMPLEMENTATION_SUMMARY.md', 'Implementation summary'),
    ]
    
    docs_ok = all(check_file_exists(d, desc) for d, desc in docs)
    all_checks.append(docs_ok)
    
    # 8. Check imports
    print("\n[8] Module Imports")
    print("-" * 60)
    
    imports_ok = check_module_imports()
    all_checks.append(imports_ok)
    
    # 9. Line counts
    print("\n[9] Code Statistics")
    print("-" * 60)
    
    source_files = [
        'crypto/artifacts/__init__.py',
        'crypto/universe/__init__.py',
        'crypto/scheduling/__init__.py',
        'crypto/regime/__init__.py',
        'crypto/strategies/__init__.py',
        'crypto/ml_pipeline/__init__.py',
        'broker/kraken/__init__.py',
        'broker/kraken/paper.py',
    ]
    
    total_lines = 0
    for f in source_files:
        if Path(f).exists():
            with open(f) as file:
                lines = len(file.readlines())
                total_lines += lines
                print(f"✓ {f}: {lines} lines")
    
    print(f"\nTotal source code: {total_lines} lines")
    
    test_files = [
        'tests/crypto/test_universe.py',
        'tests/crypto/test_downtime_scheduler.py',
        'tests/crypto/test_artifact_isolation.py',
        'tests/crypto/test_paper_simulator.py',
        'tests/crypto/test_model_approval_gates.py',
        'tests/crypto/test_ml_pipeline.py',
        'tests/crypto/test_integration.py',
    ]
    
    total_test_lines = 0
    for f in test_files:
        if Path(f).exists():
            with open(f) as file:
                lines = len(file.readlines())
                total_test_lines += lines
                print(f"✓ {f}: {lines} lines")
    
    print(f"\nTotal test code: {total_test_lines} lines")
    
    # Final summary
    print("\n" + "=" * 60)
    
    if all(all_checks):
        print("✓ ALL CHECKS PASSED")
        print("=" * 60)
        print("\nCrypto implementation is complete!")
        print(f"- {len(source_files)} source modules ({total_lines} lines)")
        print(f"- {len(test_files)} test modules ({total_test_lines} lines)")
        print(f"- {len(configs)} configuration files")
        print(f"- {len(tools)} approval tools")
        print(f"- {len(docs)} documentation files")
        print(f"- {len(scripts)} Docker run scripts")
        print("\nNext steps:")
        print("1. Run: pytest tests/crypto/ -v")
        print("2. Check: CRYPTO_README.md for detailed guide")
        print("3. Deploy: Review CRYPTO_DEPLOYMENT_CHECKLIST.md")
        return 0
    else:
        print("✗ SOME CHECKS FAILED")
        print("=" * 60)
        print("\nPlease review the output above and fix missing items.")
        return 1

if __name__ == '__main__':
    sys.exit(main())
