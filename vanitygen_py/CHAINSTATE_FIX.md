# Fix for "Loaded 1 Address" Issue

## Problem

Users reported that loading Bitcoin Core chainstate data would only find 1 address instead of the expected millions of funded addresses.

## Root Cause

The original implementation parsed the Bitcoin Core chainstate LevelDB format incorrectly:

### Incorrect Parsing (Before Fix)
```python
# Assumed format: [varint code] [amount] [scriptPubKey_size] [scriptPubKey]
code, offset = self._parse_compact_size(value, offset)
amount, offset = self._decode_varint_amount(value, offset)
```

This format was outdated and didn't match modern Bitcoin Core versions (0.15+).

### Correct Parsing (After Fix)
```python
# Actual format: [version (4 bytes)] [height/coinbase flags (4 bytes)] [compressed amount] [scriptPubKey_size] [scriptPubKey]
version = struct.unpack('<I', value[offset:offset+4])[0]
offset += 4

height_flags = struct.unpack('<I', value[offset:offset+4])[0]
offset += 4

amount, offset = self._decode_compressed_amount(value, offset)
```

## What Changed

### 1. Added Version Field Parsing
Modern Bitcoin Core stores a version field (4 bytes) at the beginning of each CCoins entry.

### 2. Added Height/Coinbase Flags
A 4-byte field containing:
- Block height for coinbase UTXOs
- Coinbase flag (is this a coinbase transaction?)

### 3. Implemented Correct Amount Decompression
Bitcoin Core uses a special compression algorithm for amounts (`CTxOutCompressor`) that:
- Removes trailing zeros from amounts
- Encodes using base-10 compression
- Optimizes for common satoshi values (ending in zeros)

The compression algorithm (from Bitcoin Core's `compressor.h`):
```cpp
uint64_t CompressAmount(uint64_t n) {
  if (n == 0) return 0;
  int e = 0;
  while (((n % 10) == 0) && e < 9) {
    n /= 10;
    e++;
  }
  if (e < 9) {
    int d = (n % 10);
    assert(d >= 1 && d <= 9);
    n /= 10;
    return 1 + (n * 9 + d - 1) * 10 + e;
  } else {
    return 1 + (n - 1) * 10 + 9;
  }
}
```

## Testing

The fix has been validated with:
1. Unit tests for compression/decompression algorithm
2. Verified correct parsing of Bitcoin Core chainstate format
3. Tested with various amount values (from 1 satoshi to 50+ BTC)

## Expected Results

After the fix, loading Bitcoin Core chainstate should report:
```
Loaded ~5,000,000-80,000,000 addresses from ~60,000,000-80,000,000 UTXOs
```

(The exact numbers depend on the current blockchain state)

## Compatibility

This fix is compatible with:
- Bitcoin Core 0.15+ (when the modern chainstate format was introduced)
- All supported address types (P2PKH, P2SH, P2WPKH, P2WSH, P2TR)
- All operating systems (Linux, macOS, Windows)

## Files Modified

- `vanitygen_py/balance_checker.py`:
  - Updated `load_from_bitcoin_core()` to parse correct format
  - Added `_decode_compressed_amount()` method
  - Maintains backward compatibility with file-based balance checking
