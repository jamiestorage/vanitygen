#!/usr/bin/env python3
"""
Example script demonstrating Bitcoin Core LevelDB integration
for balance checking in vanity address generation.
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


def example_basic_usage():
    """Basic usage example: Load Bitcoin Core data and check addresses"""
    print("=" * 60)
    print("Example 1: Basic Bitcoin Core Integration")
    print("=" * 60)
    
    # Create balance checker
    checker = BalanceChecker()
    
    # Try to load from Bitcoin Core (auto-detects path)
    print("\nAttempting to load Bitcoin Core chainstate...")
    if checker.load_from_bitcoin_core():
        print(f"✓ Successfully loaded Bitcoin Core data")
        print(f"  - Addresses found: {len(checker.address_balances):,}")
        print(f"  - Source: {os.path.basename(checker.data_path)}")
        
        # Check a few example addresses
        example_addresses = [
            "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa",  # Genesis address
            "3J98t1WpEZ73CNmYviecrnyiWrnqRhWNLy",  # Example P2SH
            "bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4",  # Example Bech32
        ]
        
        print("\nChecking example addresses:")
        for addr in example_addresses:
            balance = checker.get_balance(addr)
            btc = balance / 100_000_000  # Convert to BTC
            status = "✓ FUNDED" if balance > 0 else "  empty"
            print(f"  {status} {addr}")
            print(f"         Balance: {balance:,} satoshis ({btc:.8f} BTC)")
        
        # Check some random addresses
        print("\nChecking randomly generated addresses:")
        for i in range(5):
            key = BitcoinKey()
            addr = key.get_p2pkh_address()
            balance = checker.get_balance(addr)
            status = "✓ FUNDED!" if balance > 0 else "  empty"
            print(f"  {status} {addr}")
    else:
        print("✗ Failed to load Bitcoin Core data")
        print("\nPossible reasons:")
        print("  - Bitcoin Core is not installed")
        print("  - Blockchain is not fully synchronized")
        print("  - Bitcoin Core is still running (stop it first)")
        print("  - Data directory is in a non-standard location")
    
    # Clean up
    checker.close()
    print()


def example_custom_path():
    """Example: Load from custom Bitcoin Core path"""
    print("=" * 60)
    print("Example 2: Loading from Custom Path")
    print("=" * 60)
    
    checker = BalanceChecker()
    
    # Example custom paths (uncomment the one you need)
    # custom_paths = [
    #     "/home/user/.bitcoin/chainstate",
    #     "/mnt/blockchain/bitcoin/chainstate",
    #     "C:\\Users\\YourName\\AppData\\Roaming\\Bitcoin\\chainstate",
    # ]
    
    # For demonstration, we'll use auto-detection
    print("\nAuto-detecting Bitcoin Core path...")
    path = checker.get_bitcoin_core_db_path()
    print(f"Detected path: {path}")
    
    if os.path.exists(path):
        print(f"✓ Path exists")
        
        if checker.load_from_bitcoin_core(path):
            print(f"✓ Successfully loaded from: {path}")
            print(f"  Addresses loaded: {len(checker.address_balances):,}")
        else:
            print(f"✗ Failed to load from: {path}")
    else:
        print(f"✗ Path does not exist: {path}")
    
    checker.close()
    print()


def example_address_types():
    """Example: Check balances for different address types"""
    print("=" * 60)
    print("Example 3: Checking Different Address Types")
    print("=" * 60)
    
    checker = BalanceChecker()
    
    if not checker.load_from_bitcoin_core():
        print("✗ Could not load Bitcoin Core data")
        print("  Skipping this example")
        checker.close()
        return
    
    # Generate addresses of different types
    key = BitcoinKey()
    
    addresses = {
        "P2PKH (Legacy)": key.get_p2pkh_address(compressed=True),
        "P2PKH (Uncompressed)": key.get_p2pkh_address(compressed=False),
        "P2WPKH (SegWit Native)": key.get_p2wpkh_address(),
        "P2SH-P2WPKH (SegWit Nested)": key.get_p2sh_p2wpkh_address(),
    }
    
    print("\nGenerated addresses (all from same key):")
    for addr_type, addr in addresses.items():
        balance = checker.get_balance(addr)
        status = "✓ FUNDED" if balance > 0 else "  empty"
        print(f"  {addr_type}:")
        print(f"    {status} {addr}")
        print(f"    Balance: {balance:,} satoshis")
    
    checker.close()
    print()


def example_performance_test():
    """Example: Performance test for balance lookups"""
    print("=" * 60)
    print("Example 4: Performance Test")
    print("=" * 60)
    
    import time
    
    checker = BalanceChecker()
    
    if not checker.load_from_bitcoin_core():
        print("✗ Could not load Bitcoin Core data")
        print("  Skipping this example")
        checker.close()
        return
    
    num_lookups = 10_000
    
    print(f"\nPerforming {num_lookups:,} random address lookups...")
    print("Generating random addresses and checking balances...")
    
    start_time = time.time()
    
    for i in range(num_lookups):
        key = BitcoinKey()
        addr = key.get_p2pkh_address()
        balance = checker.get_balance(addr)
        
        # Just to keep the example interesting, report any funded addresses found
        if balance > 0 and i < 10:  # Only report first 10 to avoid spam
            print(f"  ✓ Found funded address: {addr} ({balance:,} satoshis)")
    
    elapsed = time.time() - start_time
    rate = num_lookups / elapsed
    
    print(f"\nPerformance results:")
    print(f"  Total lookups: {num_lookups:,}")
    print(f"  Time elapsed: {elapsed:.3f} seconds")
    print(f"  Lookup rate: {rate:,.0f} addresses/second")
    
    checker.close()
    print()


def example_statistics():
    """Example: Show statistics about loaded Bitcoin Core data"""
    print("=" * 60)
    print("Example 5: Bitcoin Core Statistics")
    print("=" * 60)
    
    checker = BalanceChecker()
    
    if not checker.load_from_bitcoin_core():
        print("✗ Could not load Bitcoin Core data")
        print("  Skipping this example")
        checker.close()
        return
    
    # Analyze address types
    p2pkh_count = 0
    p2sh_count = 0
    p2wpkh_count = 0
    p2wsh_count = 0
    p2tr_count = 0
    total_balance = 0
    
    for addr, balance in checker.address_balances.items():
        total_balance += balance
        
        if addr.startswith('1'):
            p2pkh_count += 1
        elif addr.startswith('3'):
            p2sh_count += 1
        elif addr.startswith('bc1q'):
            # Distinguish between P2WPKH and P2WSH by length
            if len(addr) == 42:  # P2WPKH
                p2wpkh_count += 1
            else:  # P2WSH
                p2wsh_count += 1
        elif addr.startswith('bc1p'):
            p2tr_count += 1
    
    print("\nAddress Type Distribution:")
    print(f"  P2PKH (1...):      {p2pkh_count:>10,} ({p2pkh_count/len(checker.address_balances)*100:.1f}%)")
    print(f"  P2SH (3...):       {p2sh_count:>10,} ({p2sh_count/len(checker.address_balances)*100:.1f}%)")
    print(f"  P2WPKH (bc1q...):  {p2wpkh_count:>10,} ({p2wpkh_count/len(checker.address_balances)*100:.1f}%)")
    print(f"  P2WSH (bc1q...):   {p2wsh_count:>10,} ({p2wsh_count/len(checker.address_balances)*100:.1f}%)")
    print(f"  P2TR (bc1p...):    {p2tr_count:>10,} ({p2tr_count/len(checker.address_balances)*100:.1f}%)")
    print(f"  Total addresses:   {len(checker.address_balances):>10,}")
    
    print(f"\nTotal Balance in UTXO Set:")
    print(f"  {total_balance:,} satoshis")
    print(f"  {total_balance/100_000_000:.8f} BTC")
    
    checker.close()
    print()


def main():
    """Run all examples"""
    print("\n" + "=" * 60)
    print("Bitcoin Core LevelDB Integration Examples")
    print("=" * 60)
    print()
    
    # Run examples
    example_basic_usage()
    example_custom_path()
    example_address_types()
    
    # Performance and statistics examples (optional, can be slow)
    response = input("\nRun performance test? (y/N): ")
    if response.lower() == 'y':
        example_performance_test()
    
    response = input("\nRun statistics analysis? (y/N): ")
    if response.lower() == 'y':
        example_statistics()
    
    print("=" * 60)
    print("Examples completed!")
    print("=" * 60)
    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
