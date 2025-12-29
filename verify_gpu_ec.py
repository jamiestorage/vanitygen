
import numpy as np
import pyopencl as cl
import os
import struct
import time
from vanitygen_py.bitcoin_keys import BitcoinKey

def test_gpu_ec():
    # Initialize OpenCL
    platforms = cl.get_platforms()
    if not platforms:
        print("No OpenCL platforms found")
        return
    
    # Prefer GPU
    device = None
    for platform in platforms:
        gpus = platform.get_devices(device_type=cl.device_type.GPU)
        if gpus:
            device = gpus[0]
            break
    if not device:
        device = platforms[0].get_devices()[0]
    
    print(f"Using device: {device.name}")
    
    ctx = cl.Context([device])
    queue = cl.CommandQueue(ctx)
    
    # Load kernel
    kernel_path = os.path.join('vanitygen_py', 'gpu_kernel.cl')
    with open(kernel_path, 'r') as f:
        kernel_source = f.read()
    
    try:
        program = cl.Program(ctx, kernel_source).build()
    except Exception as e:
        print(f"Build failed: {e}")
        return

    # Use generate_addresses_full kernel
    kernel = program.generate_addresses_full
    
    batch_size = 10
    seed = int(time.time())
    
    # Output buffer: 128 bytes per result (32 key + 64 addr + 32 spare)
    results_buffer = np.zeros(batch_size * 128, dtype=np.uint8)
    found_count = np.zeros(1, dtype=np.int32)
    
    mf = cl.mem_flags
    results_buf = cl.Buffer(ctx, mf.WRITE_ONLY, results_buffer.nbytes)
    found_count_buf = cl.Buffer(ctx, mf.READ_WRITE | mf.COPY_HOST_PTR, hostbuf=found_count)
    
    # Prefix buffer (empty)
    prefix_buffer = np.zeros(64, dtype=np.uint8)
    gpu_prefix_buffer = cl.Buffer(ctx, mf.READ_ONLY | mf.COPY_HOST_PTR, hostbuf=prefix_buffer)
    
    # Bloom filter (dummy)
    dummy_bloom = np.zeros(1, dtype=np.uint8)
    gpu_bloom = cl.Buffer(ctx, mf.READ_ONLY | mf.COPY_HOST_PTR, hostbuf=dummy_bloom)
    
    print(f"Running GPU kernel with seed {seed}...")
    
    # Execute kernel (treating all as matches to get results)
    # We'll modify the kernel temporarily if needed or just use a very short prefix
    # Actually, let's just use a prefix of "" (empty string)
    
    kernel(
        queue, (batch_size,), None,
        results_buf,
        found_count_buf,
        np.uint64(seed),
        np.uint32(batch_size),
        gpu_prefix_buffer,
        np.int32(0), # prefix_len = 0
        np.uint32(batch_size),
        gpu_bloom,
        np.uint32(0),
        np.uint32(0) # check_balance = 0
    )
    
    cl.enqueue_copy(queue, results_buffer, results_buf)
    cl.enqueue_copy(queue, found_count, found_count_buf)
    
    print(f"GPU found {found_count[0]} results")
    
    # Verify each result
    for i in range(found_count[0]):
        offset = i * 128
        key_words = struct.unpack('<8I', results_buffer[offset:offset+32])
        key_bytes = b''.join(struct.pack('<I', word) for word in key_words)
        
        gpu_addr = ""
        for k in range(offset + 32, offset + 96):
            if results_buffer[k] == 0: break
            gpu_addr += chr(results_buffer[k])
            
        # Compute real address on CPU
        key = BitcoinKey(key_bytes)
        cpu_addr = key.get_p2pkh_address()
        
        print(f"Result {i}:")
        print(f"  Private Key (hex): {key_bytes.hex()}")
        print(f"  GPU Address: {gpu_addr}")
        print(f"  CPU Address: {cpu_addr}")
        
        if gpu_addr == cpu_addr:
            print("  ✅ MATCH!")
        else:
            print("  ❌ MISMATCH!")

if __name__ == "__main__":
    test_gpu_ec()
