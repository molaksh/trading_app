"""
PHASE H BEHAVIORAL VALIDATION
Pre-Paper-Trading Sign-Off Review

Tests whether Phase H actually protects from slow, silent failure.
Focuses on real behavior under stress, not code aesthetics.

5 Validation Dimensions:
1. Confidence Distribution Monitor - Can it detect signal quality degradation?
2. Performance-by-Confidence Monitor - Can it track per-tier performance?
3. Feature Drift Monitor - Can it detect market regime changes?
4. System Guard - Can it actually disable ML sizing safely?
5. Behavioral Stress Test - Would it survive real failure modes?
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

from monitoring import SystemGuard


# ==============================================================================
# BEHAVIORAL VALIDATION FRAMEWORK
# ==============================================================================

class BehavioralValidator:
    """
    Tests Phase H under realistic stress conditions.
    Validates actual behavior, not just code correctness.
    """
    
    def __init__(self):
        self.guard = SystemGuard()
        self.guard.initialize_feature_drift_monitor(
            ["momentum", "volatility", "volume_ratio", "atr_pct"]
        )
        self.results = []
        self.failures = []
        self.current_date = datetime.now()
    
    def log_result(self, test_name: str, passed: bool, message: str):
        """Log a test result."""
        status = "✅ PASS" if passed else "❌ FAIL"
        self.results.append({
            "test": test_name,
            "passed": passed,
            "message": message,
            "status": status
        })
        print(f"{status} | {test_name}: {message}")
        if not passed:
            self.failures.append((test_name, message))
    
    # ==========================================================================
    # VALIDATION 1: CONFIDENCE DISTRIBUTION MONITOR
    # ==========================================================================
    
    def test_confidence_distribution_detection(self):
        """
        Test: Can it detect when signal quality degrades?
        
        Reality: Confidence inflation (too many high-confidence signals)
        often precedes performance collapse by 1-2 weeks.
        """
        print("\n" + "=" * 70)
        print("TEST 1: CONFIDENCE DISTRIBUTION MONITOR")
        print("=" * 70)
        
        # Phase 1: Normal operation (baseline)
        print("\n→ Phase 1: Normal confidence distribution (baseline)")
        for day in range(30):
            # Normal distribution: mostly 2-3, some 4, rare 5
            for _ in range(15):
                conf = np.random.choice([1, 2, 3, 4, 5], p=[0.05, 0.30, 0.40, 0.20, 0.05])
                date = pd.Timestamp(self.current_date + timedelta(days=day))
                self.guard.add_signal(conf, date)
        
        self.guard.update_daily_snapshots()
        baseline_summary = self.guard.confidence_monitor.get_summary()
        baseline_conf5_pct = 0.05  # Expected: ~5% at confidence 5
        
        print(f"  Baseline: ~{baseline_conf5_pct*100:.0f}% confidence 5 signals")
        
        # Phase 2: Confidence inflation (warning sign)
        print("\n→ Phase 2: Confidence inflation (ML degradation symptom)")
        for day in range(10):
            # INFLATION: 30-40% at confidence 5 (RED FLAG)
            for _ in range(20):
                conf = np.random.choice([1, 2, 3, 4, 5], p=[0.05, 0.10, 0.30, 0.25, 0.30])
                date = pd.Timestamp(self.current_date + timedelta(days=30 + day))
                self.guard.add_signal(conf, date)
        
        self.guard.update_daily_snapshots()
        anomaly_check = self.guard.confidence_monitor.check_for_anomalies(pd.Timestamp.now())
        
        has_anomaly = anomaly_check.get("has_anomaly", False)
        self.log_result(
            "Confidence Inflation Detection",
            has_anomaly,
            f"Inflation detected: {has_anomaly} (should be True)"
        )
        
        # What "good" looks like
        print("\n  ✓ Good behavior: Sudden spike in confidence 5 triggers alert")
        print("  ✓ Would log: 'CONFIDENCE_ANOMALY: Inflation detected'")
        
        # Red flag
        if not has_anomaly:
            print("  🚨 RED FLAG: Confidence doubled but nothing logged!")
    
    # ==========================================================================
    # VALIDATION 2: PERFORMANCE-BY-CONFIDENCE MONITOR
    # ==========================================================================
    
    def test_performance_by_confidence_degradation(self):
        """
        Test: Can it detect when high-confidence trades stop working?
        
        Reality: ML often fails at extremes (confidence 4-5) first.
        If your system doesn't detect this, you're flying blind.
        """
        print("\n" + "=" * 70)
        print("TEST 2: PERFORMANCE-BY-CONFIDENCE MONITOR")
        print("=" * 70)
        
        # Phase 1: Normal performance (all tiers profitable)
        print("\n→ Phase 1: Normal performance (baseline)")
        trade_count = 50
        for i in range(trade_count):
            conf = i % 5 + 1  # Distribute across all 5 confidence levels
            # Normal: 55% win rate across all tiers
            pnl = 100 if np.random.random() < 0.55 else -80
            self.guard.add_trade(conf, 100.0, 101.0 if pnl > 0 else 99.0, 1.0)
        
        baseline_metrics = self.guard.performance_monitor.get_summary()
        print(f"  Baseline: 55% win rate expected across tiers")
        for tier, metrics in baseline_metrics["tiers"].items():
            if metrics["count"] > 0:
                print(f"    Tier {tier}: {metrics.get('win_rate', 0):.1%} win rate ({metrics['count']} trades)")
        
        # Phase 2: ML FAILS AT TOP (confidence 4-5 collapse)
        print("\n→ Phase 2: ML fails at high confidence (CRITICAL FAILURE)")
        for i in range(30):
            conf = np.random.choice([4, 5])  # Only top tier
            # COLLAPSE: 25% win rate at confidence 4-5 (disaster)
            pnl = 100 if np.random.random() < 0.25 else -100
            self.guard.add_trade(conf, 100.0, 101.0 if pnl > 0 else 99.0, 1.0)
        
        # Check for degradation
        degradation_result = self.guard.performance_monitor.check_all_tiers()
        has_degradation = degradation_result.get("has_degradation", False)
        
        self.log_result(
            "Top-Tier Performance Degradation Detection",
            has_degradation,
            f"Degradation detected: {has_degradation} (should be True)"
        )
        
        # Verify we can see the problem
        current_metrics = self.guard.performance_monitor.get_summary()
        print(f"\n  Current performance:")
        for tier in [4, 5]:
            tier_metrics = current_metrics["tiers"].get(tier, {})
            if tier_metrics.get("count", 0) > 0:
                print(f"    Tier {tier}: {tier_metrics.get('win_rate', 0):.1%} (BROKEN!)")
        
        # What "good" looks like
        print("\n  ✓ Good behavior: 25% win rate at tier 4-5 triggers alert")
        print("  ✓ Would log: 'PERFORMANCE_DEGRADATION: Tier 4-5 failed'")
        
        # Red flag
        if not has_degradation:
            print("  🚨 RED FLAG: Confidence 4-5 trades collapsed but system didn't notice!")
    
    # ==========================================================================
    # VALIDATION 3: FEATURE DRIFT MONITOR
    # ==========================================================================
    
    def test_feature_drift_detection(self):
        """
        Test: Can it detect market regime changes?
        
        Reality: ATR spikes, volume dries up, pullback patterns break.
        These are early warnings before performance collapse.
        """
        print("\n" + "=" * 70)
        print("TEST 3: FEATURE DRIFT MONITOR")
        print("=" * 70)
        
        # Phase 1: Stable regime (baseline)
        print("\n→ Phase 1: Stable market regime (baseline)")
        baseline_momentum = np.random.normal(0.5, 0.1, 250)  # 250-day baseline
        baseline_volatility = np.random.normal(0.02, 0.005, 250)
        
        for i, (mom, vol) in enumerate(zip(baseline_momentum, baseline_volatility)):
            date = datetime.now() + timedelta(days=i)
            self.guard.add_features({
                "momentum": mom,
                "volatility": vol,
                "volume_ratio": 1.2 + np.random.normal(0, 0.1),
                "atr_pct": 0.025 + np.random.normal(0, 0.005),
            }, pd.Timestamp(date))
        
        self.guard.feature_drift_monitor.compute_baseline_stats()
        print(f"  Baseline momentum: {np.mean(baseline_momentum):.3f} ± {np.std(baseline_momentum):.3f}")
        print(f"  Baseline volatility: {np.mean(baseline_volatility):.4f} ± {np.std(baseline_volatility):.4f}")
        
        # Phase 2: REGIME SHIFT (market breaks)
        print("\n→ Phase 2: Market regime shift (volatility spike)")
        shifted_momentum = np.random.normal(1.5, 0.1, 60)  # SHIFTED 2 std devs away
        shifted_volatility = np.random.normal(0.05, 0.005, 60)  # 2.5x normal vol
        
        for i, (mom, vol) in enumerate(zip(shifted_momentum, shifted_volatility)):
            date = datetime.now() + timedelta(days=250 + i)
            self.guard.add_features({
                "momentum": mom,
                "volatility": vol,
                "volume_ratio": 0.6 + np.random.normal(0, 0.1),  # Volume dried up
                "atr_pct": 0.08 + np.random.normal(0, 0.01),  # ATR exploded
            }, pd.Timestamp(date))
        
        drift_result = self.guard.feature_drift_monitor.detect_drift()
        has_drift = drift_result.get("has_drift", False)
        
        self.log_result(
            "Feature Drift Detection",
            has_drift,
            f"Drift detected: {has_drift} (should be True)"
        )
        
        if has_drift:
            print(f"\n  Drifted features:")
            for drift in drift_result.get("drifts", []):
                print(f"    {drift['feature']}: Z-score = {drift['z_score']:.1f}")
        
        # What "good" looks like
        print("\n  ✓ Good behavior: Volatility 2.5x normal → alert")
        print("  ✓ Would log: 'FEATURE_DRIFT: Volatility regime changed'")
        
        # Red flag
        if not has_drift:
            print("  🚨 RED FLAG: Market regime completely shifted but system didn't notice!")
    
    # ==========================================================================
    # VALIDATION 4: SYSTEM GUARD - PROTECTION MECHANISM
    # ==========================================================================
    
    def test_system_guard_auto_protection(self):
        """
        Test: Can the system actually disable ML sizing?
        
        Reality: Protection is useless if it doesn't work.
        This tests the core survival mechanism.
        """
        print("\n" + "=" * 70)
        print("TEST 4: SYSTEM GUARD - AUTO-PROTECTION MECHANISM")
        print("=" * 70)
        
        # Fresh guard for clean state
        guard = SystemGuard(auto_protection_enabled=True)
        
        print("\n→ Initial state")
        initial_status = guard.get_status()
        print(f"  protection_active: {initial_status['protection_active']} (should be False)")
        print(f"  ml_sizing_enabled: {initial_status['ml_sizing_enabled']} (should be True)")
        
        test1_passed = (
            initial_status['protection_active'] == False and
            initial_status['ml_sizing_enabled'] == True
        )
        self.log_result(
            "Initial Guard State",
            test1_passed,
            "Protection starts off, ML sizing on"
        )
        
        # Trigger protection
        print("\n→ Simulating degradation (3 consecutive alerts)")
        for _ in range(3):
            guard.add_signal(5, 0.5)
        guard.update_daily_snapshots()
        result = guard.check_degradation()
        
        if result.get("should_trigger_protection"):
            guard.trigger_auto_protection("Simulated degradation")
        
        protected_status = guard.get_status()
        print(f"  protection_active: {protected_status['protection_active']} (should be True)")
        print(f"  ml_sizing_enabled: {protected_status['ml_sizing_enabled']} (should be False)")
        
        test2_passed = (
            protected_status['protection_active'] == True and
            protected_status['ml_sizing_enabled'] == False
        )
        self.log_result(
            "Auto-Protection Activation",
            test2_passed,
            "Protection triggered, ML sizing disabled"
        )
        
        # Test reversibility
        print("\n→ Reversibility: disable protection after investigation")
        guard.disable_auto_protection("Issue investigated")
        restored_status = guard.get_status()
        print(f"  protection_active: {restored_status['protection_active']} (should be False)")
        print(f"  ml_sizing_enabled: {restored_status['ml_sizing_enabled']} (should be True)")
        
        test3_passed = (
            restored_status['protection_active'] == False and
            restored_status['ml_sizing_enabled'] == True
        )
        self.log_result(
            "Auto-Protection Reversibility",
            test3_passed,
            "Protection disabled, ML sizing restored"
        )
        
        # What "good" looks like
        print("\n  ✓ Good behavior: System autonomously disables ML sizing")
        print("  ✓ Good behavior: No trades modified mid-flight")
        print("  ✓ Good behavior: Easily reversible")
        
        # Red flags
        if not test2_passed:
            print("  🚨 RED FLAG: Protection doesn't actually disable ML sizing!")
        if not test3_passed:
            print("  🚨 RED FLAG: Protection irreversible!")
    
    # ==========================================================================
    # VALIDATION 5: BEHAVIORAL STRESS TEST
    # ==========================================================================
    
    def test_realistic_stress_scenario(self):
        """
        Test: The "bad week" scenario
        
        Reality check: Would your system actually protect you from:
        - Volatility spike
        - ML confidence inflation
        - Performance collapse
        - Drawdown creeping in
        """
        print("\n" + "=" * 70)
        print("TEST 5: REALISTIC STRESS SCENARIO")
        print("=" * 70)
        
        guard = SystemGuard(auto_protection_enabled=True)
        guard.initialize_feature_drift_monitor(["momentum", "volatility"])
        
        print("\n→ WEEK 1-2: Normal trading")
        # Normal signals and performance
        for day in range(10):
            for _ in range(20):
                conf = np.random.choice([1, 2, 3, 4, 5], p=[0.05, 0.30, 0.40, 0.20, 0.05])
                date = pd.Timestamp(self.current_date + timedelta(days=day))
                guard.add_signal(conf, date)
            
            for _ in range(15):
                conf = np.random.randint(1, 6)
                pnl = 100 if np.random.random() < 0.55 else -80
                guard.add_trade(conf, 100.0, 101.0 if pnl > 0 else 99.0, 1.0)
        
        print("  ✓ Signals: normal distribution")
        print("  ✓ Performance: 55% win rate")
        print("  ✓ Drawdown: minimal")
        
        print("\n→ WEEK 3: Early warning signs")
        # Volatility increases, signals get weird
        for day in range(5):
            # Confidence inflation
            for _ in range(20):
                conf = np.random.choice([1, 2, 3, 4, 5], p=[0.02, 0.10, 0.25, 0.30, 0.33])
                date = pd.Timestamp(self.current_date + timedelta(days=10 + day))
                guard.add_signal(conf, date)
            
            # Feature drift
            for _ in range(10):
                date = pd.Timestamp(self.current_date + timedelta(days=10 + day))
                guard.add_features({
                    "momentum": 1.0 + np.random.normal(0, 0.15),  # Shifted
                    "volatility": 0.04 + np.random.normal(0, 0.01),  # Elevated
                }, date)
            
            # Performance starts to slip (top tier)
            for _ in range(10):
                conf = np.random.choice([4, 5])
                pnl = 100 if np.random.random() < 0.45 else -100  # Declining
                guard.add_trade(conf, 100.0, 101.0 if pnl > 0 else 99.0, 1.0)
        
        print("  ⚠️  Signals: confidence 5 doubled")
        print("  ⚠️  Features: momentum & volatility shifted")
        print("  ⚠️  Performance: Top tier dropped to 45% win rate")
        
        print("\n→ WEEK 4: System should protect")
        guard.update_daily_snapshots()
        
        # Run full degradation check
        degradation = guard.check_degradation()
        
        print(f"\n  Degradation check result:")
        print(f"    has_degradation: {degradation['has_degradation']}")
        print(f"    consecutive_alerts: {degradation['consecutive_alerts']}")
        print(f"    should_trigger_protection: {degradation['should_trigger_protection']}")
        
        if degradation['should_trigger_protection']:
            guard.trigger_auto_protection("Stress scenario triggered")
            print(f"\n  ✅ PROTECTION TRIGGERED")
            print(f"     ML sizing disabled")
            print(f"     Falls back to rules-only + risk caps")
        
        status = guard.get_status()
        protection_worked = (
            degradation['has_degradation'] == True and
            status['protection_active'] == True and
            status['ml_sizing_enabled'] == False
        )
        
        self.log_result(
            "Stress Scenario Protection",
            protection_worked,
            "System autonomously disabled ML under stress"
        )
        
        # What "good" looks like
        print("\n  ✓ System detects early warning signs")
        print("  ✓ Accumulates evidence across multiple monitors")
        print("  ✓ Triggers protection before equity curve breaks")
        print("  ✓ Falls back safely to conservative mode")
        
        # Red flags
        if not protection_worked:
            print("\n  🚨 RED FLAG: System didn't protect itself under realistic stress!")
    
    # ==========================================================================
    # RUNNER
    # ==========================================================================
    
    def run_all_validations(self):
        """Run all behavioral validations."""
        print("\n")
        print("╔" + "=" * 68 + "╗")
        print("║" + " " * 68 + "║")
        print("║" + "PHASE H: BEHAVIORAL VALIDATION".center(68) + "║")
        print("║" + "Pre-Paper-Trading Sign-Off Review".center(68) + "║")
        print("║" + " " * 68 + "║")
        print("╚" + "=" * 68 + "╝")
        
        # Run all tests
        self.test_confidence_distribution_detection()
        self.test_performance_by_confidence_degradation()
        self.test_feature_drift_detection()
        self.test_system_guard_auto_protection()
        self.test_realistic_stress_scenario()
        
        # Summary
        self._print_summary()
    
    def _print_summary(self):
        """Print validation summary."""
        print("\n" + "=" * 70)
        print("VALIDATION SUMMARY")
        print("=" * 70)
        
        total = len(self.results)
        passed = sum(1 for r in self.results if r['passed'])
        failed = total - passed
        
        for result in self.results:
            print(f"{result['status']} {result['test']}")
        
        print(f"\n{passed}/{total} tests passed")
        
        if failed == 0:
            print("\n✅ PHASE H READY FOR PAPER TRADING")
            print("\nYour system is operationally mature:")
            print("  ✓ Detects signal quality degradation")
            print("  ✓ Tracks performance by confidence tier")
            print("  ✓ Detects market regime changes")
            print("  ✓ Autonomously protects under stress")
            print("  ✓ Would survive realistic failure scenarios")
            print("\n🚀 READY TO DEPLOY")
        else:
            print(f"\n❌ {failed} CRITICAL GAPS FOUND")
            for test, msg in self.failures:
                print(f"\n  FAILURE: {test}")
                print(f"  MESSAGE: {msg}")
            print("\n⚠️  DO NOT DEPLOY UNTIL FIXED")


if __name__ == "__main__":
    validator = BehavioralValidator()
    validator.run_all_validations()
