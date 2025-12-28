#!/usr/bin/env python3
"""Test that modified modules can be imported without errors."""

import sys

try:
    from vanitygen_py.balance_checker import BalanceChecker
    print("✓ BalanceChecker imported successfully")
    
    # Test the new method
    checker = BalanceChecker()
    balance, is_member = checker.check_balance_and_membership("test")
    print(f"✓ check_balance_and_membership({balance}, {is_member})")
    
    sys.exit(0)
except Exception as e:
    print(f"❌ Import failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)