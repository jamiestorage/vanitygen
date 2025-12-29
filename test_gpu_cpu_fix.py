#!/usr/bin/env python3
"""Test script to verify the GPU CPU usage fix."""

import sys
import multiprocessing

# Test that we can import the module
try:
    from vanitygen_py.gpu_generator import GPUGenerator
    print("✅ GPUGenerator imported successfully")
except ImportError as e:
    print(f"❌ Failed to import GPUGenerator: {e}")
    sys.exit(1)

# Test 1: Default cpu_cores parameter
def test_default_cpu_cores():
    """Test that GPUGenerator defaults to 2 CPU cores."""
    generator = GPUGenerator("test")
    assert generator.cpu_cores == 2, f"Expected 2 CPU cores, got {generator.cpu_cores}"
    print(f"✅ Default cpu_cores is 2 (not {multiprocessing.cpu_count()})")

# Test 2: Custom cpu_cores parameter
def test_custom_cpu_cores():
    """Test that we can set custom cpu_cores."""
    generator = GPUGenerator("test", cpu_cores=4)
    assert generator.cpu_cores == 4, f"Expected 4 CPU cores, got {generator.cpu_cores}"
    print("✅ Custom cpu_cores parameter works")

# Test 3: Zero cpu_cores (edge case)
def test_zero_cpu_cores():
    """Test edge case with 0 cpu_cores."""
    generator = GPUGenerator("test", cpu_cores=0)
    assert generator.cpu_cores == 0, f"Expected 0 CPU cores, got {generator.cpu_cores}"
    print("✅ Zero cpu_cores handled correctly")

# Test 4: None cpu_cores (should default to 2)
def test_none_cpu_cores():
    """Test that None cpu_cores defaults to 2."""
    generator = GPUGenerator("test", cpu_cores=None)
    assert generator.cpu_cores == 2, f"Expected 2 CPU cores, got {generator.cpu_cores}"
    print("✅ None cpu_cores defaults to 2")

# Test 5: Check that the parameter is used in the right place
def test_parameter_usage():
    """Test that cpu_cores is used instead of multiprocessing.cpu_count()."""
    # This is more of a code inspection test
    import inspect
    source = inspect.getsource(GPUGenerator._search_loop)
    
    # Check that the method uses self.cpu_cores instead of multiprocessing.cpu_count()
    assert "self.cpu_cores" in source, "Method should use self.cpu_cores"
    assert "multiprocessing.cpu_count()" not in source, "Method should not use multiprocessing.cpu_count()"
    print("✅ _search_loop uses self.cpu_cores correctly")

if __name__ == "__main__":
    try:
        print("Testing GPU CPU usage fix...")
        print(f"System has {multiprocessing.cpu_count()} CPU cores")
        
        test_default_cpu_cores()
        test_custom_cpu_cores()
        test_zero_cpu_cores()
        test_none_cpu_cores()
        test_parameter_usage()
        
        print("\n🎉 All tests passed!")
        print("✨ The fix should reduce CPU usage in GPU mode from 100% to ~2 cores")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)