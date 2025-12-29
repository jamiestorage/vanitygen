#!/usr/bin/env python3
"""
Test script for GPU-only mode with direct address list loading.

This script tests the new feature where funded addresses are loaded directly
into GPU memory for exact matching without bloom filter false positives.
"""

import sys
import os
import time

# Add the vanitygen_py directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'vanitygen_py'))

from vanitygen_py.balance_checker import BalanceChecker
from vanitygen_py.gpu_generator import GPUGenerator
from vanitygen_py.bitcoin_keys import BitcoinKey

def create_test_address_file(filename, num_addresses=1000):
    """Create a test file with known Bitcoin addresses"""
    print(f"Creating test file with {num_addresses} addresses...")
    
    addresses = []
    for i in range(num_addresses):
        # Generate a random key
        import secrets
        key_bytes = secrets.token_bytes(32)
        key = BitcoinKey(key_bytes)
        address = key.get_p2pkh_address()
        addresses.append(address)
    
    # Write to file
    with open(filename, 'w') as f:
        for addr in addresses:
            f.write(f"{addr}\n")
    
    print(f"Created {filename} with {len(addresses)} addresses")
    return addresses

def test_gpu_address_list_creation():
    """Test creating GPU address list"""
    print("\n=== Test 1: GPU Address List Creation ===")
    
    # Create test addresses
    test_file = "/tmp/test_addresses.txt"
    addresses = create_test_address_file(test_file, 100)
    
    # Load into balance checker
    checker = BalanceChecker()
    checker.load_addresses(test_file)
    
    # Create GPU address list
    address_list_info = checker.create_gpu_address_list(format='sorted_array')
    
    if address_list_info:
        print(f"✓ GPU address list created successfully")
        print(f"  Format: {address_list_info['format']}")
        print(f"  Count: {address_list_info['count']}")
        print(f"  Size: {address_list_info['size_bytes'] / 1024:.2f} KB")
        return True
    else:
        print("✗ Failed to create GPU address list")
        return False

def test_gpu_only_mode_with_address_list():
    """Test GPU-only mode with direct address list loading"""
    print("\n=== Test 2: GPU-Only Mode with Address List ===")
    
    try:
        # Create a small test address file
        test_file = "/tmp/test_addresses_small.txt"
        addresses = create_test_address_file(test_file, 10)
        
        # Pick one address to search for (use its private key)
        target_address = addresses[5]
        print(f"Target address to find: {target_address}")
        
        # Load balance checker
        checker = BalanceChecker()
        checker.load_addresses(test_file)
        
        print(f"Loaded {len(checker.funded_addresses)} addresses")
        
        # Create GPU generator in GPU-only mode
        print("Initializing GPU generator in GPU-only mode...")
        gen = GPUGenerator(
            prefix="",  # No prefix, just search for funded addresses
            addr_type='p2pkh',
            batch_size=4096,
            power_percent=100,
            balance_checker=checker,
            gpu_only=True  # Enable GPU-only mode
        )
        
        # Start the generator
        gen.start()
        print("Generator started. Checking if GPU address list is loaded...")
        
        # Check if GPU address list was loaded
        if gen.gpu_address_list_buffer is not None:
            print(f"✓ GPU address list loaded: {gen.gpu_address_list_count} addresses")
        else:
            print("✗ GPU address list NOT loaded (using bloom filter instead)")
        
        # Run for a few seconds
        print("Running for 5 seconds...")
        start_time = time.time()
        total_checked = 0
        
        while time.time() - start_time < 5:
            time.sleep(0.5)
            checked = gen.get_stats()
            total_checked += checked
            print(f"  Checked: {total_checked} addresses, Speed: {total_checked / (time.time() - start_time):.0f} addr/s")
            
            # Check for results
            while not gen.result_queue.empty():
                result = gen.result_queue.get()
                print(f"\n*** MATCH FOUND! ***")
                print(f"  Address: {result[0]}")
                print(f"  WIF: {result[1]}")
        
        gen.stop()
        print("✓ Test completed successfully")
        return True
        
    except Exception as e:
        print(f"✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_gpu_memory_check():
    """Test GPU memory availability check"""
    print("\n=== Test 3: GPU Memory Check ===")
    
    try:
        import pyopencl as cl
        
        platforms = cl.get_platforms()
        if not platforms:
            print("✗ No OpenCL platforms found")
            return False
        
        # Get first GPU device
        device = None
        for platform in platforms:
            try:
                gpus = platform.get_devices(device_type=cl.device_type.GPU)
                if gpus:
                    device = gpus[0]
                    break
            except:
                pass
        
        if device is None:
            print("✗ No GPU device found")
            return False
        
        print(f"GPU Device: {device.name}")
        print(f"Global Memory: {device.global_mem_size / (1024**3):.2f} GB")
        print(f"Max Alloc Size: {device.max_mem_alloc_size / (1024**3):.2f} GB")
        
        # Calculate how many addresses can fit
        bytes_per_address = 20  # hash160 size
        max_addresses = device.max_mem_alloc_size // bytes_per_address
        print(f"Max addresses that can fit: {max_addresses:,} ({max_addresses / 1e6:.1f} million)")
        
        return True
        
    except ImportError:
        print("✗ PyOpenCL not installed")
        return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

def main():
    print("=" * 60)
    print("GPU Address List Testing")
    print("=" * 60)
    
    # Run tests
    results = []
    
    results.append(("GPU Address List Creation", test_gpu_address_list_creation()))
    results.append(("GPU Memory Check", test_gpu_memory_check()))
    results.append(("GPU-Only Mode with Address List", test_gpu_only_mode_with_address_list()))
    
    # Print summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    
    for test_name, result in results:
        status = "✓ PASSED" if result else "✗ FAILED"
        print(f"{test_name:40s} {status}")
    
    all_passed = all(result for _, result in results)
    
    if all_passed:
        print("\n✓ All tests passed!")
        return 0
    else:
        print("\n✗ Some tests failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())
