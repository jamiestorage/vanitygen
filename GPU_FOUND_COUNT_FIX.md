# GPU Found Count Buffer Reset Fix

## Issue Summary

**Problem:** GPU-based address generation was failing with "Invalid value for secexp" error when using balance checking mode.

**Root Cause:** The `found_count` buffer was not being reset between GPU batches, causing it to accumulate indefinitely.

## Technical Details

### The Bug

In the GPU search loops (`_search_loop_with_balance_check`, `_search_loop_gpu_only`, and `_search_loop_gpu_only_exact`), the found count buffer was managed as follows:

1. **Initialization:** `found_count = np.zeros(1, dtype=np.int32)` - starts at 0
2. **Batch execution:** GPU kernel increments counter with `atomic_inc(count)` 
3. **After batch:** Results copied back with `cl.enqueue_copy(self.queue, found_count, found_count_buf)`
4. **Next batch:** Old value copied back to GPU with `cl.enqueue_copy(self.queue, found_count_buf, found_count)` ❌

**The problem:** Step 4 was copying the accumulated count from the previous batch back to the GPU, instead of resetting it to 0.

### Observable Symptoms

```
[DEBUG] Batch 1: Found 4096 potential matches
[DEBUG] Batch 2: Found 8192 potential matches  ← Should be ~0-100, not 2x batch 1
[DEBUG] Batch 3: Found 12288 potential matches ← Continues accumulating
[DEBUG] ERROR: Invalid value for secexp, expected integer between 1 and ...
```

The error occurred because:
1. The counter accumulated (4096, 8192, 12288, ...)
2. Python tried to read results beyond the allocated buffer size (max_results)
3. Uninitialized memory was interpreted as invalid private keys
4. ECDSA library rejected the malformed keys

### The Fix

Added `found_count[0] = 0` before copying to GPU in all three search loops:

```python
# Before (BUG):
cl.enqueue_copy(self.queue, found_count_buf, found_count)

# After (FIX):
found_count[0] = 0  # Reset to 0 before copying to GPU
cl.enqueue_copy(self.queue, found_count_buf, found_count)
```

## Files Modified

- `vanitygen_py/gpu_generator.py`:
  - Line 516: `_search_loop_with_balance_check()` - Balance checking mode
  - Line 758: `_search_loop_gpu_only()` - GPU-only mode with bloom filter
  - Line 954: `_search_loop_gpu_only_exact()` - GPU-only mode with exact matching

## Testing

Created `test_found_count_fix.py` to verify:
1. ✓ Logic test: Confirms found_count properly resets between batches
2. ✓ Code verification: Confirms all 3 instances have the fix

## Impact

This fix resolves:
- ❌ "Invalid value for secexp" errors during GPU address generation
- ❌ Accumulating found count across batches
- ❌ Reading uninitialized memory from result buffers
- ❌ False positive matches exceeding max_results limit

After the fix:
- ✓ Each batch starts with found_count = 0
- ✓ Only actual matches in current batch are reported
- ✓ No memory corruption from buffer overruns
- ✓ Valid private keys are generated and processed correctly

## Related Code

The GPU kernels (`gpu_kernel.cl`) use `atomic_inc(count)` to track matches:

```c
if(prefix_match || might_be_funded) { 
    int idx = atomic_inc(count);  // Atomically increment counter
    if(idx < (int)max_addr) { 
        // Store result at index idx
    }
}
```

The counter must start at 0 for each batch to correctly index into the result buffer.
