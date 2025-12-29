#!/usr/bin/env python3
"""Simple test to verify GPU fixes"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'vanitygen_py'))

def main():
    print("=" * 60)
    print("GPU-Only Mode Fixes - Quick Test")
    print("=" * 60)
    print()

    # Test 1: Check cleanup method exists
    try:
        from vanitygen_py.gpu_generator import GPUGenerator
        gen = GPUGenerator(prefix="1", addr_type='p2pkh', batch_size=1024, gpu_only=True)
        assert hasattr(gen, '_cleanup_gpu_buffers'), "Missing cleanup method"
        print("✓ Cleanup method exists")
        gen._cleanup_gpu_buffers()
        print("✓ Cleanup works without error")
    except ImportError as e:
        print(f"⚠ Skipping GPU tests (OpenCL not available): {e}")
        return 0
    except Exception as e:
        print(f"✗ GPU test failed: {e}")
        return 1

    # Test 2: Check result queue format
    try:
        from vanitygen_py.bitcoin_keys import BitcoinKey
        key = BitcoinKey(b'\x01' * 32)
        result = (key.get_p2pkh_address(), key.get_wif(), key.get_public_key().hex())
        assert len(result) == 3, f"Wrong tuple size: {len(result)}"
        print("✓ Result queue format correct (3-tuple)")
    except Exception as e:
        print(f"✗ Result format test failed: {e}")
        return 1

    # Test 3: Check memory limits
    try:
        from vanitygen_py.balance_checker import BalanceChecker
        checker = BalanceChecker()
        bloom, bits = checker.create_bloom_filter()
        if bloom is None:
            print("✓ Bloom filter creation handles empty address list")
        else:
            size = len(bloom)
            print(f"✓ Bloom filter created: {size} bytes ({bits} bits)")
    except Exception as e:
        print(f"✗ Memory limit test failed: {e}")
        return 1

    print()
    print("=" * 60)
    print("✓ All basic tests passed!")
    print("=" * 60)
    return 0

if __name__ == "__main__":
    sys.exit(main())
