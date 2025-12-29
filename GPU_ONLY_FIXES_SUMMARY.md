# GPU-Only Mode Memory Leak and Counter Fixes

## Summary
Fixed critical memory leaks and counter update issues in GPU-only mode that were causing system lockups and incorrect progress reporting.

## Issues Fixed

### 1. GPU Memory Leaks in Search Loops
**Problem**: GPU buffers created in each loop iteration were never released, causing GPU memory to fill up and eventually lock up the system.

**Locations**:
- `gpu_generator.py` - `_search_loop_gpu_only()` (lines 526-567)
- `gpu_generator.py` - `_search_loop_with_balance_check()` (lines 336-382)

**Fix**: Added `.release()` calls for all GPU buffers after each iteration:
```python
# Clean up GPU buffers to prevent memory leak
results_buf.release()
found_count_buf.release()
output_keys_buf.release()  # In balance checking mode
```

### 2. Result Queue Data Corruption
**Problem**: GPU-only mode was putting empty strings for WIF and public key in the result queue, causing unpacking errors and preventing address display.

**Location**: `gpu_generator.py` - `_search_loop_gpu_only()` (line 580)

**Fix**: Generate proper WIF and public key from GPU-returned key bytes:
```python
# Generate WIF and public key from key_bytes
key = BitcoinKey(key_bytes)
wif = key.get_wif()
pubkey = key.get_public_key().hex()
# Report result with full key information
self.result_queue.put((addr, wif, pubkey))
```

### 3. Memory Exhaustion with Large Address Sets
**Problem**: When loading large address lists for balance checking, bloom filters and address buffers could consume all system memory, causing lockup.

**Locations**:
- `balance_checker.py` - `create_bloom_filter()` (lines 958-974)
- `balance_checker.py` - `create_gpu_address_buffer()` (lines 1028-1048)

**Fix**: Added size limits to prevent memory exhaustion:
```python
# Bloom filter: Cap at 1GB
max_byte_size = 1024 * 1024 * 1024  # 1GB max
if byte_size > max_byte_size:
    print(f"WARNING: Bloom filter would be too large ({byte_size / (1024**3):.2f} GB)")
    # Reduce bits_per_item to fit within limit

# Address buffer: Cap at 512MB
max_buffer_size = 512 * 1024 * 1024  # 512MB max
if buffer_size > max_buffer_size:
    print(f"WARNING: Address buffer would be too large ({buffer_size / (1024**2):.2f} MB)")
    # Limit to first N addresses
```

### 4. Counter Update Issues
**Problem**: Stats counter was only updated after processing results, so if no addresses matched the prefix, the counter wouldn't increment even though keys were being processed.

**Location**: `gpu_generator.py` - `_search_loop_gpu_only()` (lines 569-571)

**Fix**: Move stats update before result processing:
```python
# Update stats BEFORE processing results to ensure counter increments even on errors
with self.stats_lock:
    self.stats_counter += self.batch_size
```

### 5. Improved Error Handling
**Problem**: Unhandled exceptions during result processing could cause the generator to stop updating.

**Locations**:
- `gpu_generator.py` - `_search_loop_gpu_only()` (lines 606-619)
- `gui.py` - `GeneratorThread.run()` (lines 124-147)

**Fix**: Added try-except blocks with proper error logging:
```python
try:
    # Process results
    ...
except Exception as e:
    print(f"Error processing GPU results: {e}")
    import traceback
    traceback.print_exc()
```

### 6. Buffer Memory Management
**Problem**: Using `np.frombuffer()` kept references to bloom filter data in memory, preventing cleanup.

**Location**: `gpu_generator.py` - `_search_loop_gpu_only()` (lines 502-509)

**Fix**: Use `np.array()` to create a copy and explicitly delete the buffer:
```python
# Use np.array instead of np.frombuffer to create a copy and avoid keeping reference
bloom_buffer = np.array(bloom_data, dtype=np.uint8)
gpu_bloom_filter = cl.Buffer(self.ctx, mf.READ_ONLY | mf.COPY_HOST_PTR, hostbuf=bloom_buffer)
# Store for cleanup
self.temp_bloom_buffer = gpu_bloom_filter
# Clear buffer reference to free memory
del bloom_buffer
```

### 7. Proper Buffer Cleanup
**Problem**: Temporary buffers created for bloom filters and prefix were not cleaned up when the loop exited.

**Locations**:
- `gpu_generator.py` - `_search_loop_gpu_only()` (lines 631-645)
- `gpu_generator.py` - `_cleanup_gpu_buffers()` (lines 791-799)

**Fix**: Added cleanup code at loop exit and added new buffer to cleanup list:
```python
# Clean up temporary bloom filter buffer when loop exits
if hasattr(self, 'temp_bloom_buffer') and self.temp_bloom_buffer is not None:
    try:
        self.temp_bloom_buffer.release()
    except Exception:
        pass
    self.temp_bloom_buffer = None

# Clean up prefix buffer
if hasattr(self, 'gpu_prefix_buffer') and self.gpu_prefix_buffer is not None:
    try:
        self.gpu_prefix_buffer.release()
    except Exception:
        pass
    self.gpu_prefix_buffer = None
```

## Result Queue Format Handling
**Problem**: The generator was sending different tuple formats (3-tuple vs 4-tuple) which could cause unpacking errors.

**Location**: `gui.py` - `GeneratorThread.run()` (lines 124-147)

**Fix**: Handle both formats for backward compatibility:
```python
result = self.generator.result_queue.get_nowait()
# Handle both 3-tuple and 4-tuple results for backward compatibility
if len(result) == 3:
    addr, wif, pubkey = result
elif len(result) == 4:
    addr, wif, pubkey, _ = result  # Ignore balance if already computed
else:
    print(f"Unexpected result format: {result}")
    continue
```

## Testing Recommendations

1. **Test without balance checking**:
   - Start GPU-only mode with no balance checker loaded
   - Verify counter increments correctly in general tab
   - Monitor system memory - should remain stable

2. **Test with small balance file** (100-1000 addresses):
   - Load a funded address file
   - Start GPU-only mode
   - Verify addresses are being checked
   - Monitor GPU memory usage

3. **Test with large balance file** (>100,000 addresses):
   - Should see warning about buffer size limits
   - Should not cause system lockup
   - Should continue processing within memory limits

4. **Test counter updates**:
   - Watch general tab counter during generation
   - Verify it updates even when no prefix matches found
   - Verify progress tab shows same data

## Files Modified

1. `vanitygen_py/gpu_generator.py` - Memory leak fixes, buffer cleanup, counter updates
2. `vanitygen_py/balance_checker.py` - Memory limits for large address sets
3. `vanitygen_py/gui.py` - Error handling, result queue format handling

## Performance Impact

- **Memory Usage**: Significantly reduced due to proper buffer cleanup
- **CPU Usage**: Slightly reduced due to efficient buffer management
- **GPU Memory**: Properly released each iteration, preventing exhaustion
- **Throughput**: No negative impact, may actually improve due to less memory pressure
