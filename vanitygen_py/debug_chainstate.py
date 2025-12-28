#!/usr/bin/env python3
"""
Debug script to diagnose Bitcoin Core chainstate parsing issues.
"""

import sys
import os
import struct

# Handle both module and direct execution
try:
    from .balance_checker import BalanceChecker
except ImportError:
    from balance_checker import BalanceChecker

def debug_chainstate_parsing():
    """Debug the Bitcoin Core chainstate parsing"""
    print("=" * 70)
    print("Bitcoin Core Chainstate Parsing Debug Tool")
    print("=" * 70)
    
    try:
        import plyvel
    except ImportError:
        print("\nERROR: plyvel is not installed")
        print("Install it with: pip install plyvel")
        return False
    
    checker = BalanceChecker()
    path = checker.get_bitcoin_core_db_path()
    
    print(f"\nDetected Bitcoin Core path: {path}")
    print(f"Path exists: {os.path.exists(path)}")
    
    if not os.path.exists(path):
        print("\nERROR: Bitcoin Core chainstate directory not found")
        return False
    
    try:
        db = plyvel.DB(path, create_if_missing=False, compression=None)
    except Exception as e:
        print(f"\nERROR: Failed to open LevelDB: {e}")
        if 'lock' in str(e).lower() or 'already held' in str(e).lower():
            print("\nHINT: Bitcoin Core may be running. Stop it first with: bitcoin-cli stop")
        return False
    
    print("\nOpened LevelDB successfully")
    
    # Count total entries
    total_entries = 0
    utxo_entries = 0
    other_entries = 0
    
    for key, value in db:
        total_entries += 1
        if len(key) >= 1 and key[0] == ord('C'):
            utxo_entries += 1
        else:
            other_entries += 1
    
    print(f"\nDatabase statistics:")
    print(f"  Total entries: {total_entries:,}")
    print(f"  UTXO entries (start with 'C'): {utxo_entries:,}")
    print(f"  Other entries: {other_entries:,}")
    
    # Sample some UTXO entries
    print(f"\nSampling first 5 UTXO entries:")
    print("-" * 70)
    
    sample_count = 0
    for key, value in db:
        if len(key) >= 1 and key[0] == ord('C'):
            sample_count += 1
            if sample_count > 5:
                break
            
            print(f"\nEntry #{sample_count}:")
            print(f"  Key length: {len(key)} bytes")
            print(f"  Key hex: {key.hex()[:100]}{'...' if len(key) > 50 else ''}")
            print(f"  Value length: {len(value)} bytes")
            print(f"  Value hex: {value.hex()[:100]}{'...' if len(value) > 50 else ''}")
            
            # Try to parse
            offset = 0
            print(f"\n  Parsing attempt:")
            
            # Parse compact size (code)
            try:
                code, new_offset = checker._parse_compact_size(value, offset)
                print(f"    Code: {code} (offset: {offset} -> {new_offset})")
                offset = new_offset
            except Exception as e:
                print(f"    ERROR parsing code: {e}")
                continue
            
            # Parse amount
            try:
                amount, new_offset = checker._decode_varint_amount(value, offset)
                print(f"    Amount: {amount} satoshis (offset: {offset} -> {new_offset})")
                offset = new_offset
            except Exception as e:
                print(f"    ERROR parsing amount: {e}")
                continue
            
            # Parse script size
            try:
                script_size, new_offset = checker._parse_compact_size(value, offset)
                print(f"    Script size: {script_size} bytes (offset: {offset} -> {new_offset})")
                offset = new_offset
            except Exception as e:
                print(f"    ERROR parsing script size: {e}")
                continue
            
            # Check if script fits
            if offset + script_size > len(value):
                print(f"    ERROR: Script ({script_size} bytes) exceeds value length ({len(value)} bytes)")
                continue
            
            # Extract script
            script_pubkey = value[offset:offset+script_size]
            print(f"    ScriptPubKey: {script_pubkey.hex()[:100]}{'...' if len(script_pubkey) > 50 else ''}")
            
            # Extract address
            try:
                address = checker._extract_address_from_script(script_pubkey)
                if address:
                    print(f"    Address: {address}")
                else:
                    print(f"    WARNING: Could not extract address from script")
            except Exception as e:
                print(f"    ERROR extracting address: {e}")
    
    db.close()
    
    # Now try the actual loading
    print("\n" + "=" * 70)
    print("Attempting actual load_from_bitcoin_core...")
    print("=" * 70)
    
    checker2 = BalanceChecker()
    result = checker2.load_from_bitcoin_core()
    
    if result:
        print(f"\nSUCCESS: Loaded {len(checker2.address_balances)} addresses")
    else:
        print("\nFAILED: load_from_bitcoin_core returned False")
    
    checker2.close()
    
    return result


if __name__ == "__main__":
    try:
        debug_chainstate_parsing()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
