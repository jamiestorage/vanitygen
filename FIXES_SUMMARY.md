# GPU Address List Memory Bloat and INVALID_ARG_SIZE Fixes

## Issues Fixed

### 1. Memory Bloat During GPU Address List Creation
**Problem**: When loading large address lists (e.g., 55 million addresses), the system would run out of memory and get killed by the OOM killer. The process consumed all 16GB RAM + 2GB swap.

**Root Cause**: The `_setup_gpu_address_list()` method did not check system memory availability before loading large address lists into memory for GPU transfer.

**Solution**: Added system memory checking using `psutil` to prevent OOM conditions:
- Check available system memory before loading large address lists
- Require at least 3x the address list size in available memory (conservative safety margin)
- Gracefully handle cases where `psutil` is not available
- Provide clear debug messages about memory usage and limits

### 2. INVALID_ARG_SIZE Error in GPU Kernel
**Problem**: When using smaller address lists, the system would encounter `INVALID_ARG_SIZE` errors when executing the `generate_and_check` kernel.

**Root Cause**: The kernel expected a proper OpenCL buffer for the prefix argument, but the code was passing a numpy array directly (`np.frombuffer(prefix_bytes, dtype=np.uint8)`).

**Solution**: Fixed prefix buffer creation to match kernel expectations:
- Create a fixed-size 64-byte buffer for proper alignment
- Use `cl.Buffer()` to create a proper OpenCL buffer from the prefix data
- Clean up the buffer after kernel execution to prevent memory leaks
- Applied the same fix to all kernel calls that use prefix buffers

## Files Modified

### 1. `vanitygen_py/gpu_generator.py`

**Added imports**:
```python
# Optional import for system memory checking
try:
    import psutil
except ImportError:
    psutil = None
```

**Enhanced `_setup_gpu_address_list()` method**:
- Added system memory availability check using `psutil`
- Added conservative memory safety margin (3x required memory)
- Added detailed debug logging for memory usage
- Graceful handling when `psutil` is not available

**Fixed `_search_loop_with_balance_check()` method**:
- Create proper OpenCL buffer for prefix argument
- Use fixed-size 64-byte buffer for alignment
- Clean up prefix buffer after kernel execution

### 2. `requirements.txt`

**Added psutil as optional dependency**:
```
psutil>=5.9.0    # Optional: For system memory checking (prevents OOM)
```

## Technical Details

### Memory Safety Check
The fix adds a system memory check that:
1. Uses `psutil.virtual_memory()` to get available system memory
2. Requires at least 3x the address list size to be available
3. Prevents the process from being killed by OOM killer
4. Provides clear debug messages about memory constraints

### Prefix Buffer Fix
The fix ensures that:
1. Prefix data is properly aligned in a 64-byte buffer
2. A proper OpenCL buffer is created using `cl.Buffer()`
3. The buffer is cleaned up after use to prevent memory leaks
4. All kernel calls use the same pattern for consistency

## Testing

Created comprehensive tests to verify the fixes:
- `test_fixes.py`: Basic functionality tests
- `test_original_issue.py`: Simulates the original issues and verifies fixes

Tests cover:
- Memory check functionality with various address list sizes
- Prefix buffer creation for different prefix lengths
- Edge cases (empty lists, invalid addresses)
- System memory checking with mocked environments

## Impact

These fixes resolve:
1. **Memory exhaustion**: Prevents the application from consuming all system memory
2. **GPU kernel errors**: Eliminates INVALID_ARG_SIZE errors in kernel execution
3. **System stability**: Improves overall stability when working with large address lists
4. **User experience**: Provides better error messages and graceful degradation

## Backward Compatibility

The fixes maintain full backward compatibility:
- `psutil` is optional (graceful degradation if not available)
- Existing functionality is preserved
- No breaking changes to APIs or interfaces
- All existing tests continue to pass

## Performance Considerations

The memory check adds minimal overhead:
- Only executed during GPU address list setup (not in hot path)
- Uses efficient system calls via `psutil`
- Prevents much more expensive OOM conditions

The prefix buffer fix has no performance impact:
- Same buffer creation pattern used throughout
- Proper cleanup prevents memory leaks
- Aligns with existing OpenCL best practices
