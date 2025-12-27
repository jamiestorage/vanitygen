# Quick Start Guide: Bitcoin Core LevelDB Integration

This guide will help you get started with using Bitcoin Core's LevelDB data for real-time balance checking in the vanity address generator.

## Prerequisites Checklist

- [ ] Bitcoin Core installed and fully synchronized
- [ ] Bitcoin Core stopped (before reading chainstate)
- [ ] Python 3.8 or higher
- [ ] All required packages installed (`pip install -r requirements.txt`)

## Step-by-Step Setup

### 1. Install Bitcoin Core

**Linux (Ubuntu/Debian):**
```bash
sudo apt-get install bitcoin-core
```

**macOS:**
```bash
brew install bitcoin
```

**Windows:**
Download from https://bitcoincore.org/en/download/

### 2. Synchronize the Blockchain

Run Bitcoin Core and wait for full synchronization. This can take several hours or days depending on your internet speed and hardware.

```bash
# Start Bitcoin Core
bitcoind -daemon

# Check sync progress
bitcoin-cli getblockchaininfo | grep "blocks"
```

Wait until `blocks` equals `headers`.

### 3. Stop Bitcoin Core

**Important:** Stop Bitcoin Core before reading the chainstate database.

```bash
bitcoin-cli stop
```

Wait a few seconds to ensure the process has fully stopped.

### 4. Install Python Dependencies

```bash
# From the project root directory
cd /home/engine/project
pip install -r requirements.txt
```

Or if you're using a virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 5. Launch the Vanity Address Generator

```bash
python -m vanitygen_py.main --gui
```

### 6. Load Bitcoin Core Data

1. In the GUI, go to the **Settings** tab
2. Click **"Load from Bitcoin Core Data"** button
3. The application will:
   - Auto-detect your Bitcoin Core data directory
   - Read the chainstate LevelDB
   - Parse all UTXOs
   - Extract addresses and cache balances

4. Verify the status message shows success, e.g.:
   ```
   Loaded 12345678 addresses from Bitcoin Core chainstate
   ```

### 7. Generate Vanity Addresses with Balance Checking

1. Enter your desired prefix (e.g., "1Love")
2. Select address type (P2PKH, P2WPKH, or P2SH-P2WPKH)
3. Ensure **"Enable Balance Checking"** is checked
4. Click **"Start Generation"**

The generator will now:
- Generate addresses matching your pattern
- Check each address against your local Bitcoin Core data
- Alert you immediately if a funded address is found
- Optionally pause when a funded address is found

## Testing the Integration

Run the example script to verify everything works:

```bash
cd vanitygen_py
python example_bitcoin_core_integration.py
```

This will:
- Load Bitcoin Core data
- Show statistics about loaded addresses
- Perform balance lookups on example addresses
- Run performance benchmarks

Run the test suite:

```bash
cd vanitygen_py
python test_balance_checker.py
```

All tests should pass.

## Troubleshooting

### "Bitcoin Core chainstate not found"

**Solution:** Check Bitcoin Core data directory location:

**Linux:**
```bash
ls -la ~/.bitcoin/chainstate/
# Or for snap installations:
ls -la ~/snap/bitcoin-core/common/.bitcoin/chainstate/
```

**macOS:**
```bash
ls -la ~/Library/Application\ Support/Bitcoin/chainstate/
```

**Windows:**
```cmd
dir "%APPDATA%\Bitcoin\chainstate"
```

### "Failed to load Bitcoin Core DB"

**Possible causes:**
1. Bitcoin Core is still running
   ```bash
   bitcoin-cli stop
   ```
2. File permissions issue
   ```bash
   chmod -R u+r ~/.bitcoin/chainstate
   ```
3. plyvel not installed
   ```bash
   pip install plyvel
   ```

### "No addresses found"

**Possible causes:**
1. Blockchain not fully synchronized
2. Running in pruning mode (check `bitcoin-cli getblockchaininfo`)
3. Corrupted chainstate (try re-indexing: `bitcoind -reindex-chainstate`)

### Application is slow after loading

This is normal! Loading the entire UTXO set (60-80 million addresses) requires significant memory (500MB-2GB). After loading, lookups are very fast (O(1)).

## Common Use Cases

### 1. Find Funded Vanity Addresses

Generate vanity addresses and automatically check if they have any balance:

```
Prefix: 1Love
Check: Generate until a funded address is found
```

This is useful for finding "lost" vanity addresses that were generated in the past but never used.

### 2. Verify Address Ownership

Generate addresses from a known private key and verify they have the expected balance.

### 3. Bulk Address Generation

Generate thousands of addresses and quickly filter for those with balances.

## Performance Tips

- **Initial load time:** 5-30 seconds (depends on UTXO set size)
- **Memory usage:** 500MB-2GB (depends on blockchain size)
- **Lookup speed:** 100,000+ addresses per second after loading
- **Recommendation:** Use a machine with at least 4GB RAM for optimal performance

## Security Best Practices

1. **Never share your Bitcoin Core data directory** with others
2. **Always stop Bitcoin Core** before reading chainstate
3. **Keep your wallet.dat encrypted** if it contains funds
4. **Run on a secure machine** with no malware
5. **Backup regularly** - both Bitcoin Core data and any generated keys

## Next Steps

- Read [BITCOIN_CORE_INTEGRATION.md](BITCOIN_CORE_INTEGRATION.md) for detailed technical documentation
- Run the example scripts to explore features
- Check the main README.md for general vanity address generator usage
- Consider contributing improvements or reporting issues

## Getting Help

If you encounter issues:

1. Check the troubleshooting section above
2. Run the test suite: `python test_balance_checker.py`
3. Run the example script: `python example_bitcoin_core_integration.py`
4. Enable verbose output to see detailed error messages
5. Check Bitcoin Core logs: `~/.bitcoin/debug.log`

## Advanced Usage

### Custom Path

If your Bitcoin Core data is in a non-standard location:

```python
from vanitygen_py.balance_checker import BalanceChecker

checker = BalanceChecker()
checker.load_from_bitcoin_core("/custom/path/to/chainstate")
```

### Programmatic Usage

```python
from vanitygen_py.balance_checker import BalanceChecker
from vanitygen_py.bitcoin_keys import BitcoinKey

# Load Bitcoin Core data
checker = BalanceChecker()
checker.load_from_bitcoin_core()

# Generate and check addresses
for _ in range(1000):
    key = BitcoinKey()
    address = key.get_p2pkh_address()
    balance = checker.get_balance(address)
    
    if balance > 0:
        print(f"Found funded address: {address}")
        print(f"Balance: {balance} satoshis")

checker.close()
```

---

Congratulations! You're now ready to use Bitcoin Core LevelDB integration for real-time balance checking in your vanity address generation.
