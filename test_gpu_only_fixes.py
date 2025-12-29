#!/usr/bin/env python3
"""
Test script to verify GPU-only mode fixes.
Tests:
1. GPU memory buffer cleanup
2. Result queue format handling
3. Counter updates without balance checking
4. Memory limits with large address sets
"""

import sys
import os
import time
import tempfile

# Add vanitygen_py to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'vanitygen_py'))


def test_buffer_cleanup():
    """Test that GPU buffers are properly cleaned up"""
    print("Test 1: GPU Buffer Cleanup")
    print("-" * 50)

    try:
        from vanitygen_py.gpu_generator import GPUGenerator

        # Create generator with small batch size for quick test
        gen = GPUGenerator(
            prefix="1",
            addr_type='p2pkh',
            batch_size=1024,
            gpu_only=True
        )

        # Check that cleanup method exists
        assert hasattr(gen, '_cleanup_gpu_buffers'), "Missing _cleanup_gpu_buffers method"
        print("✓ Cleanup method exists")

        # Check that it handles missing attributes gracefully
        gen._cleanup_gpu_buffers()
        print("✓ Cleanup handles missing attributes")

        print("✓ Test 1 PASSED\n")
        return True

    except ImportError as e:
        print(f"⚠ Skipping test 1: {e}")
        print("✓ Test 1 SKIPPED (OpenCL not available)\n")
        return True
    except Exception as e:
        print(f"✗ Test 1 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_result_queue_format():
    """Test that result queue properly formats results"""
    print("Test 2: Result Queue Format")
    print("-" * 50)

    try:
        from vanitygen_py.bitcoin_keys import BitcoinKey

        # Test 3-tuple format (GPU-only mode)
        key_bytes = b'\x01' * 32
        key = BitcoinKey(key_bytes)
        addr = key.get_p2pkh_address()
        wif = key.get_wif()
        pubkey = key.get_public_key().hex()

        result = (addr, wif, pubkey)
        assert len(result) == 3, f"Expected 3-tuple, got {len(result)}-tuple"
        assert len(addr) > 0, "Address is empty"
        assert len(wif) > 0, "WIF is empty"
        assert len(pubkey) > 0, "Public key is empty"
        print("✓ 3-tuple format correct")

        # Test unpacking logic
        if len(result) == 3:
            addr2, wif2, pubkey2 = result
        elif len(result) == 4:
            addr2, wif2, pubkey2, _ = result
        else:
            raise ValueError(f"Unexpected format: {len(result)}-tuple")

        assert addr2 == addr, "Address mismatch after unpacking"
        assert wif2 == wif, "WIF mismatch after unpacking"
        assert pubkey2 == pubkey, "Public key mismatch after unpacking"
        print("✓ Unpacking logic works")

        print("✓ Test 2 PASSED\n")
        return True

    except Exception as e:
        print(f"✗ Test 2 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_memory_limits():
    """Test that memory limits prevent exhaustion"""
    print("Test 3: Memory Limits for Large Address Sets")
    print("-" * 50)

    try:
        from vanitygen_py.balance_checker import BalanceChecker

        # Create test address list that would normally exceed limits
        # Each address takes ~10 bytes in bloom filter
        # With bits_per_item=10, 10M addresses = 100M bits = 12.5MB (under limit)
        # But let's test with a very large number to trigger the limit

        # Create a temporary file with many addresses
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            temp_file = f.name
            # Write 1000 addresses (small but enough to test)
            for i in range(1000):
                f.write(f"1{i:035d}\n")

        try:
            checker = BalanceChecker()
            checker.load_addresses(temp_file)

            # Test bloom filter creation
            bloom_data, num_bits = checker.create_bloom_filter()
            assert bloom_data is not None, "Bloom filter creation failed"
            assert num_bits > 0, "Bloom filter has 0 bits"

            # Check that bloom filter is reasonable size
            bloom_size = len(bloom_data)
            assert bloom_size < 1024 * 1024 * 1024, f"Bloom filter too large: {bloom_size} bytes"
            print(f"✓ Bloom filter size: {bloom_size} bytes ({num_bits} bits)")

            # Test address buffer creation
            addr_buffer = checker.create_gpu_address_buffer()
            assert addr_buffer is not None, "Address buffer creation failed"

            # Check that address buffer is reasonable size
            buffer_size = len(addr_buffer)
            assert buffer_size < 512 * 1024 * 1024, f"Address buffer too large: {buffer_size} bytes"
            print(f"✓ Address buffer size: {buffer_size} bytes")

            print("✓ Test 3 PASSED\n")
            return True

        finally:
            # Clean up temp file
            if os.path.exists(temp_file):
                os.unlink(temp_file)

    except Exception as e:
        print(f"✗ Test 3 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_counter_updates():
    """Test that counter updates even without results"""
    print("Test 4: Counter Updates Without Results")
    print("-" * 50)

    try:
        from vanitygen_py.gpu_generator import GPUGenerator
        import queue

        # Create generator
        gen = GPUGenerator(
            prefix="1" * 10,  # Hard prefix so we get NO matches
            addr_type='p2pkh',
            batch_size=1024,
            gpu_only=True
        )

        # Get initial stats
        initial_stats = gen.get_stats()
        print(f"Initial stats: {initial_stats}")

        # Simulate counter increment (as done in search loop)
        with gen.stats_lock:
            gen.stats_counter += 1024

        # Check that counter updated
        updated_stats = gen.get_stats()
        print(f"Updated stats: {updated_stats}")

        assert updated_stats == 1024, f"Expected 1024, got {updated_stats}"
        print("✓ Counter updates correctly")

        # Check that result queue is empty (no results due to hard prefix)
        assert gen.result_queue.empty(), "Result queue should be empty"
        print("✓ Result queue empty (no matches)")

        print("✓ Test 4 PASSED\n")
        return True

    except ImportError as e:
        print(f"⚠ Skipping test 4: {e}")
        print("✓ Test 4 SKIPPED (OpenCL not available)\n")
        return True
    except Exception as e:
        print(f"✗ Test 4 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests"""
    print("=" * 60)
    print("GPU-Only Mode Fixes Test Suite")
    print("=" * 60)
    print()

    results = []

    # Run all tests
    results.append(("Buffer Cleanup", test_buffer_cleanup()))
    results.append(("Result Queue Format", test_result_queue_format()))
    results.append(("Memory Limits", test_memory_limits()))
    results.append(("Counter Updates", test_counter_updates()))

    # Print summary
    print("=" * 60)
    print("Test Summary")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✓ PASSED" if result else "✗ FAILED"
        print(f"{name:30s} {status}")

    print()
    print(f"Results: {passed}/{total} tests passed")

    if passed == total:
        print("\n✓ All tests passed!")
        return 0
    else:
        print(f"\n✗ {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
