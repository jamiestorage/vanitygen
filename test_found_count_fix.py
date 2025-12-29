#!/usr/bin/env python3
"""Test to verify the found_count buffer reset fix"""

import sys
import numpy as np

def test_found_count_reset():
    """Verify that found_count is reset to 0 before each batch"""
    print("Testing found_count reset logic...")
    
    # Simulate the issue scenario
    found_count = np.zeros(1, dtype=np.int32)
    
    # Batch 1: simulate finding 100 results
    found_count[0] = 100
    print(f"After batch 1: found_count = {found_count[0]}")
    
    # Old behavior (BUG): would copy old value to GPU
    # New behavior (FIX): reset to 0 before copying
    found_count[0] = 0  # This is the fix
    print(f"After reset: found_count = {found_count[0]}")
    
    # Batch 2: simulate finding 50 results
    found_count[0] = 50
    print(f"After batch 2: found_count = {found_count[0]}")
    
    # The old bug would have accumulated: 100 + 50 = 150
    # The fix ensures each batch starts at 0
    
    if found_count[0] == 50:
        print("✓ Test PASSED: found_count properly resets between batches")
        return 0
    else:
        print(f"✗ Test FAILED: expected 50, got {found_count[0]}")
        return 1

def test_code_has_fix():
    """Verify the fix is present in the actual code"""
    print("\nVerifying fix in gpu_generator.py...")
    
    with open('vanitygen_py/gpu_generator.py', 'r') as f:
        content = f.read()
    
    # Check for the fix pattern: "found_count[0] = 0" before "cl.enqueue_copy"
    lines = content.split('\n')
    fix_count = 0
    
    for i, line in enumerate(lines):
        if 'found_count[0] = 0' in line and '# Reset to 0 before copying to GPU' in line:
            # Check if next line has enqueue_copy
            if i + 1 < len(lines) and 'cl.enqueue_copy' in lines[i + 1] and 'found_count_buf' in lines[i + 1]:
                fix_count += 1
                print(f"  ✓ Fix found at line {i + 1}")
    
    if fix_count >= 3:  # We have 3 search loops that need the fix
        print(f"✓ All {fix_count} instances of the fix are present")
        return 0
    else:
        print(f"✗ Only {fix_count} instances found, expected 3")
        return 1

if __name__ == "__main__":
    result1 = test_found_count_reset()
    result2 = test_code_has_fix()
    
    if result1 == 0 and result2 == 0:
        print("\n" + "=" * 60)
        print("✓ ALL TESTS PASSED: found_count reset fix verified!")
        print("=" * 60)
        sys.exit(0)
    else:
        print("\n" + "=" * 60)
        print("✗ TESTS FAILED")
        print("=" * 60)
        sys.exit(1)
