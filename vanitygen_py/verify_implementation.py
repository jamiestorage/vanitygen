#!/usr/bin/env python3
"""
Quick verification script to test the Bitcoin Core LevelDB integration.
"""

import sys
import os

# Handle both module and direct execution
try:
    from .balance_checker import BalanceChecker
    from .bitcoin_keys import BitcoinKey
except ImportError:
    from balance_checker import BalanceChecker
    from bitcoin_keys import BitcoinKey

def test_basic_functionality():
    """Test basic functionality of the balance checker"""
    print("=" * 60)
    print("Bitcoin Core LevelDB Integration Verification")
    print("=" * 60)
    
    # Test 1: Initialize BalanceChecker
    print("\n[1/6] Testing BalanceChecker initialization...")
    checker = BalanceChecker()
    print("✓ BalanceChecker initialized successfully")
    print(f"  - is_loaded: {checker.is_loaded}")
    print(f"  - address_balances: {len(checker.address_balances)}")
    
    # Test 2: Test BitcoinKey integration
    print("\n[2/6] Testing BitcoinKey integration...")
    key = BitcoinKey()
    p2pkh_addr = key.get_p2pkh_address()
    p2wpkh_addr = key.get_p2wpkh_address()
    p2sh_addr = key.get_p2sh_p2wpkh_address()
    print("✓ Generated addresses:")
    print(f"  - P2PKH: {p2pkh_addr}")
    print(f"  - P2WPKH: {p2wpkh_addr}")
    print(f"  - P2SH-P2WPKH: {p2sh_addr}")
    
    # Test 3: Test address file loading
    print("\n[3/6] Testing address file loading...")
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
        test_addresses = [p2pkh_addr, "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"]
        for addr in test_addresses:
            f.write(addr + '\n')
        temp_file = f.name
    
    try:
        result = checker.load_addresses(temp_file)
        if result:
            print("✓ Address file loaded successfully")
            print(f"  - Loaded {len(checker.funded_addresses)} addresses")
        else:
            print("✗ Failed to load address file")
            return False
    finally:
        os.unlink(temp_file)
    
    # Test 4: Test balance checking with loaded file
    print("\n[4/6] Testing balance checking...")
    balance = checker.check_balance(p2pkh_addr)
    print(f"✓ Balance check for {p2pkh_addr}")
    print(f"  - Balance: {balance} (file mode returns 1 for present addresses)")
    
    balance2 = checker.check_balance("1BvBMSEYstWetqTFn5Au4m4GFg7xJaNVN2")
    print(f"✓ Balance check for non-loaded address")
    print(f"  - Balance: {balance2}")
    
    # Test 5: Test Bitcoin Core path detection
    print("\n[5/6] Testing Bitcoin Core path detection...")
    path = checker.get_bitcoin_core_db_path()
    print(f"✓ Auto-detected path:")
    print(f"  - {path}")
    if os.path.exists(path):
        print(f"  - Path exists!")
    else:
        print(f"  - Path does not exist (expected if Bitcoin Core not installed)")
    
    # Test 6: Test script parsing
    print("\n[6/6] Testing scriptPubKey parsing...")
    
    # P2PKH script
    pubkey_hash = b'\x00' * 20
    p2pkh_script = b'\x76\xa9\x14' + pubkey_hash + b'\x88\xac'
    addr = checker._extract_address_from_script(p2pkh_script)
    if addr and addr.startswith('1'):
        print("✓ P2PKH script parsed successfully")
        print(f"  - Address: {addr}")
    else:
        print("✗ P2PKH script parsing failed")
        return False
    
    # P2SH script
    script_hash = b'\x00' * 20
    p2sh_script = b'\xa9\x14' + script_hash + b'\x87'
    addr = checker._extract_address_from_script(p2sh_script)
    if addr and addr.startswith('3'):
        print("✓ P2SH script parsed successfully")
        print(f"  - Address: {addr}")
    else:
        print("✗ P2SH script parsing failed")
        return False
    
    # P2WPKH script
    witness_program = b'\x00' * 20
    p2wpkh_script = b'\x00\x14' + witness_program
    addr = checker._extract_address_from_script(p2wpkh_script)
    if addr and addr.startswith('bc1q'):
        print("✓ P2WPKH script parsed successfully")
        print(f"  - Address: {addr}")
    else:
        print("✗ P2WPKH script parsing failed")
        return False
    
    # P2TR script
    witness_program = b'\x00' * 32
    p2tr_script = b'\x51\x20' + witness_program
    addr = checker._extract_address_from_script(p2tr_script)
    if addr and addr.startswith('bc1p'):
        print("✓ P2TR script parsed successfully")
        print(f"  - Address: {addr}")
    else:
        print("✗ P2TR script parsing failed")
        return False
    
    # Cleanup
    checker.close()
    
    print("\n" + "=" * 60)
    print("All verification tests passed! ✓")
    print("=" * 60)
    print("\nThe Bitcoin Core LevelDB integration is ready to use.")
    print("See QUICKSTART.md for detailed setup instructions.")
    print()
    
    return True


def test_bitcoin_core_availability():
    """Test if Bitcoin Core data is available"""
    print("\n" + "=" * 60)
    print("Checking Bitcoin Core Availability")
    print("=" * 60)
    
    checker = BalanceChecker()
    path = checker.get_bitcoin_core_db_path()
    
    print(f"\nDetected path: {path}")
    
    if os.path.exists(path):
        print("✓ Bitcoin Core chainstate directory found!")
        
        # Try to load it
        print("\nAttempting to load Bitcoin Core data...")
        if checker.load_from_bitcoin_core():
            print("✓ Successfully loaded Bitcoin Core data!")
            print(f"  - Addresses loaded: {len(checker.address_balances):,}")
            print(f"  - Status: {checker.get_status()}")
            checker.close()
            return True
        else:
            print("✗ Failed to load Bitcoin Core data")
            print("  Possible reasons:")
            print("    - Bitcoin Core is still running (stop it first)")
            print("    - Blockchain is not fully synchronized")
            print("    - File permissions issue")
            checker.close()
            return False
    else:
        print("✗ Bitcoin Core chainstate not found")
        print("\nTo use Bitcoin Core integration:")
        print("1. Install Bitcoin Core")
        print("2. Synchronize the blockchain")
        print("3. Stop Bitcoin Core before reading chainstate")
        print("4. Run this verification script again")
        checker.close()
        return False


if __name__ == "__main__":
    try:
        # Test basic functionality first
        if test_basic_functionality():
            # Then test Bitcoin Core availability
            test_bitcoin_core_availability()
            sys.exit(0)
        else:
            print("\n✗ Verification failed!")
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
