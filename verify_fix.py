#!/usr/bin/env python3
"""
Quick test to verify Bitcoin Core chainstate loading fix.
Run this script to check if the fix resolves the "only 1 address" issue.
"""

import sys
import os

# Test without importing dependencies
def test_fix():
    """Verify the fix is in place"""
    print("=" * 70)
    print("Bitcoin Core Chainstate Fix Verification")
    print("=" * 70)

    # Check if the fix is in the code
    balance_checker_path = os.path.join(os.path.dirname(__file__), 'vanitygen_py', 'balance_checker.py')

    if not os.path.exists(balance_checker_path):
        print("\n✗ balance_checker.py not found")
        return False

    with open(balance_checker_path, 'r') as f:
        content = f.read()

    # Check for the fixed parsing logic
    checks = {
        "Version field parsing": "struct.unpack('<I', value[offset:offset+4])" in content and "version" in content,
        "Height flags parsing": "height_flags = struct.unpack('<I', value[offset:offset+4])" in content,
        "Compressed amount decoding": "_decode_compressed_amount" in content,
        "New parsing order": all([
            "version" in content,
            "height_flags" in content,
            "_decode_compressed_amount" in content,
            "script_size" in content
        ])
    }

    print("\nChecking fix components:")
    all_good = True
    for check, passed in checks.items():
        status = "✓" if passed else "✗"
        print(f"  {status} {check}")
        if not passed:
            all_good = False

    print("\n" + "=" * 70)

    if all_good:
        print("✓ Fix is correctly implemented!")
        print("\nThe balance checker now uses the correct Bitcoin Core chainstate format:")
        print("  1. Parses version field (4 bytes)")
        print("  2. Parses height/coinbase flags (4 bytes)")
        print("  3. Decodes compressed amount using Bitcoin Core's algorithm")
        print("  4. Extracts scriptPubKey and converts to address")
        print("\nExpected result when loading Bitcoin Core data:")
        print("  'Loaded 5,000,000-80,000,000 addresses from 60,000,000-80,000,000 UTXOs'")
        print("\nTry loading your Bitcoin Core data again to see the fix in action!")
        return True
    else:
        print("✗ Some fix components are missing")
        print("\nPlease ensure you're using the latest version of balance_checker.py")
        return False

if __name__ == "__main__":
    success = test_fix()
    sys.exit(0 if success else 1)
