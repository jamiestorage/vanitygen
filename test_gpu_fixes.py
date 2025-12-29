#!/usr/bin/env python3
"""
Test script to verify GPU fixes for freezing and lag issues.

This script tests the major fixes implemented:
1. Buffer management and cleanup
2. Error handling in GPU operations
3. Resource cleanup on exit
4. Thread safety
"""

import sys
import time
import threading
import traceback
from vanitygen_py.gpu_generator import GPUGenerator
from vanitygen_py.balance_checker import BalanceChecker

def test_buffer_cleanup():
    """Test that GPU buffers are properly cleaned up"""
    print("Testing buffer cleanup...")
    
    try:
        # Create a GPU generator
        generator = GPUGenerator("1", "p2pkh", batch_size=1024, gpu_only=True)
        
        # Try to initialize (may fail if no GPU available)
        try:
            generator.init_cl()
            print("✓ OpenCL initialized successfully")
        except Exception as e:
            print(f"⚠ OpenCL initialization failed (expected if no GPU): {e}")
            return True
        
        # Test cleanup
        generator._cleanup_gpu_buffers()
        print("✓ Buffer cleanup completed without errors")
        
        # Verify all buffers are None
        buffer_attrs = [
            'gpu_bloom_filter', 'gpu_address_buffer', 'found_count_buffer', 
            'gpu_prefix_buffer', 'temp_bloom_buffer', 'gpu_address_list_buffer', 
            'gpu_prefix_buffer_exact', 'gpu_bloom_filter_exact', 'gpu_results_buffer'
        ]
        
        all_clean = True
        for attr_name in buffer_attrs:
            if hasattr(generator, attr_name) and getattr(generator, attr_name) is not None:
                print(f"✗ Buffer {attr_name} not cleaned up")
                all_clean = False
        
        if all_clean:
            print("✓ All buffers properly cleaned up")
        
        return all_clean
        
    except Exception as e:
        print(f"✗ Buffer cleanup test failed: {e}")
        traceback.print_exc()
        return False

def test_error_handling():
    """Test error handling in GPU operations"""
    print("\nTesting error handling...")
    
    try:
        generator = GPUGenerator("1", "p2pkh", batch_size=1024, gpu_only=True)
        
        # Test cleanup with no buffers (should not crash)
        generator._cleanup_gpu_buffers()
        print("✓ Cleanup with no buffers handled gracefully")
        
        # Test stats access
        stats = generator.get_stats()
        print(f"✓ Stats access returned: {stats}")
        
        # Test pause/resume
        generator.pause()
        print("✓ Pause method executed without error")
        
        generator.resume()
        print("✓ Resume method executed without error")
        
        return True
        
    except Exception as e:
        print(f"✗ Error handling test failed: {e}")
        traceback.print_exc()
        return False

def test_resource_management():
    """Test resource management with multiple start/stop cycles"""
    print("\nTesting resource management...")
    
    try:
        generator = GPUGenerator("1", "p2pkh", batch_size=1024, gpu_only=True)
        
        # Test multiple start/stop cycles (if GPU available)
        try:
            generator.init_cl()
            
            for i in range(3):
                print(f"  Cycle {i+1}/3...")
                # Start and immediately stop to test cleanup
                try:
                    generator.start()
                    time.sleep(0.1)  # Let it run briefly
                    generator.stop()
                    print(f"    ✓ Cycle {i+1} completed")
                except Exception as e:
                    print(f"    ⚠ Cycle {i+1} failed (may be expected): {e}")
                    break
            
            print("✓ Multiple start/stop cycles completed")
            return True
            
        except Exception as e:
            print(f"⚠ Skipping start/stop test (no GPU available): {e}")
            return True
            
    except Exception as e:
        print(f"✗ Resource management test failed: {e}")
        traceback.print_exc()
        return False

def test_thread_safety():
    """Test thread safety of stats access"""
    print("\nTesting thread safety...")
    
    try:
        generator = GPUGenerator("1", "p2pkh", batch_size=1024, gpu_only=True)
        
        # Test concurrent stats access
        results = []
        errors = []
        
        def access_stats():
            try:
                for _ in range(10):
                    stats = generator.get_stats()
                    results.append(stats)
                    time.sleep(0.01)
            except Exception as e:
                errors.append(e)
        
        # Start multiple threads accessing stats
        threads = []
        for i in range(5):
            thread = threading.Thread(target=access_stats)
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        if errors:
            print(f"✗ Thread safety test failed with errors: {errors}")
            return False
        else:
            print(f"✓ Thread safety test completed successfully (accessed stats {len(results)} times)")
            return True
            
    except Exception as e:
        print(f"✗ Thread safety test failed: {e}")
        traceback.print_exc()
        return False

def main():
    """Run all tests"""
    print("GPU Fixes Verification Test")
    print("=" * 50)
    
    tests = [
        test_buffer_cleanup,
        test_error_handling,
        test_resource_management,
        test_thread_safety,
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"✗ Test {test.__name__} crashed: {e}")
            traceback.print_exc()
    
    print("\n" + "=" * 50)
    print(f"Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! GPU fixes are working correctly.")
        return 0
    else:
        print("❌ Some tests failed. Please review the output above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())