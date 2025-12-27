# Bitcoin Core LevelDB Integration

This document describes how to use the Bitcoin Core LevelDB integration for real-time balance checking in the vanity address generator.

## Overview

The BalanceChecker class can now directly read Bitcoin Core's LevelDB chainstate database to extract all UTXOs and their associated addresses. This enables:

- **Real-time balance checking** against your local blockchain data
- **No external dependencies** on block explorers or APIs
- **Support for multiple address types**: P2PKH (1...), P2SH (3...), P2WPKH (bc1q...), P2WSH (bc1q...), and P2TR (bc1p...)
- **Fast lookups** by caching address balances in memory

## Prerequisites

1. **Bitcoin Core** must be installed and fully synchronized
2. **plyvel** Python package must be installed (already in requirements.txt)
3. Bitcoin Core must be stopped before accessing the chainstate database

## Setting Up Bitcoin Core

### Linux

```bash
# Install Bitcoin Core
sudo apt-get install bitcoin-core

# Or download from bitcoin.org
# Run Bitcoin Core and wait for full sync
bitcoind -daemon

# Stop Bitcoin Core before reading chainstate
bitcoin-cli stop
```

Data directory locations:
- Standard: `~/.bitcoin/chainstate/`
- Snap install: `~/snap/bitcoin-core/common/.bitcoin/chainstate/`

### macOS

```bash
# Install via Homebrew
brew install bitcoin

# Run Bitcoin Core and wait for full sync
bitcoind -daemon

# Stop Bitcoin Core before reading chainstate
bitcoin-cli stop
```

Data directory: `~/Library/Application Support/Bitcoin/chainstate/`

### Windows

```bash
# Download from bitcoin.org
# Run Bitcoin Core and wait for full sync
# Stop Bitcoin Core before reading chainstate
```

Data directory: `%APPDATA%\Bitcoin\chainstate\`

## Usage

### Via GUI

1. Launch the vanity address generator:
   ```bash
   python -m vanitygen_py.main --gui
   ```

2. In the Settings tab, click "Load from Bitcoin Core Data"

3. The application will:
   - Automatically detect Bitcoin Core data directory
   - Read the chainstate LevelDB
   - Parse all UTXOs and extract addresses
   - Cache address balances in memory

4. Start generating vanity addresses with real-time balance checking enabled

### Via Python API

```python
from vanitygen_py.balance_checker import BalanceChecker

# Create balance checker
checker = BalanceChecker()

# Load from Bitcoin Core (auto-detects path)
if checker.load_from_bitcoin_core():
    print(f"Loaded {len(checker.address_balances)} addresses")
    
    # Check an address balance
    balance = checker.get_balance("1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa")
    print(f"Balance: {balance} satoshis")
else:
    print("Failed to load Bitcoin Core data")

# Load from specific path
if checker.load_from_bitcoin_core("/path/to/.bitcoin/chainstate"):
    print("Successfully loaded from custom path")

# Clean up
checker.close()
```

### Specifying Custom Path

If your Bitcoin Core data is in a non-standard location:

```python
checker = BalanceChecker()
success = checker.load_from_bitcoin_core("/custom/path/to/chainstate")
```

## How It Works

### Bitcoin Core chainstate Structure

Bitcoin Core stores UTXO data in a LevelDB database with the following structure:

- **Keys**: `C` + transaction hash (32 bytes) + output index (4 bytes)
- **Values**: Serialized UTXO data including:
  - Compact size code
  - Amount (in satoshis)
  - scriptPubKey size
  - scriptPubKey (output script)

### Address Extraction

The balance checker parses scriptPubKey to extract addresses for different output types:

1. **P2PKH** (addresses starting with '1'):
   - Script pattern: `OP_DUP OP_HASH160 <20-byte hash> OP_EQUALVERIFY OP_CHECKSIG`
   - Extracts 20-byte hash and encodes as Base58Check

2. **P2SH** (addresses starting with '3'):
   - Script pattern: `OP_HASH160 <20-byte hash> OP_EQUAL`
   - Extracts 20-byte hash and encodes as Base58Check

3. **P2WPKH** (addresses starting with 'bc1q'):
   - Script pattern: `OP_0 <20-byte witness program>`
   - Encodes as Bech32

4. **P2WSH** (addresses starting with 'bc1q'):
   - Script pattern: `OP_0 <32-byte witness program>`
   - Encodes as Bech32

5. **P2TR** (addresses starting with 'bc1p'):
   - Script pattern: `OP_1 <32-byte witness program>`
   - Encodes as Bech32m

### Performance Considerations

- **Initial load time**: 5-30 seconds depending on UTXO set size (typically 60-80 million UTXOs)
- **Memory usage**: ~500MB-2GB depending on blockchain size
- **Lookup time**: O(1) after loading (dictionary lookup)
- **Recommended for**: Local development, testing, and personal use

## Security Notes

1. **Stop Bitcoin Core**: Always stop Bitcoin Core before reading chainstate to avoid corruption
2. **Read-only access**: The balance checker only reads from LevelDB, never writes
3. **No data export**: Address balances are kept in memory only
4. **Privacy**: All data stays on your local machine

## Troubleshooting

### "Bitcoin Core chainstate not found"

- Ensure Bitcoin Core is fully installed
- Check that blockchain is fully synchronized
- Verify the data directory path
- Try specifying the path manually

### "Failed to load Bitcoin Core DB"

- Ensure Bitcoin Core is stopped
- Check file permissions on the chainstate directory
- Verify plyvel is installed: `pip install plyvel`
- Check for disk space issues

### "No addresses found"

- Ensure Bitcoin Core has synchronized the blockchain
- Verify the chainstate directory contains valid data
- Check that the Bitcoin Core version is recent (0.15+)

### Performance Issues

- Close other applications to free memory
- Consider using a machine with more RAM
- For large blockchain sizes, initial loading may take time

## Alternative: Using Address Files

If you prefer not to use Bitcoin Core directly, you can load addresses from a text file:

```python
checker = BalanceChecker()
if checker.load_addresses("funded_addresses.txt"):
    print("Loaded addresses from file")
```

File format (one address per line):
```
1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa
3J98t1WpEZ73CNmYviecrnyiWrnqRhWNLy
bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4
```

## API Reference

### BalanceChecker Methods

#### `__init__(data_path=None)`
Initialize the balance checker.

#### `load_addresses(filepath)`
Load funded addresses from a text file.

**Parameters:**
- `filepath`: Path to text file with one address per line

**Returns:** `bool` - Success status

#### `load_from_bitcoin_core(path=None)`
Load UTXO data from Bitcoin Core chainstate LevelDB.

**Parameters:**
- `path`: Optional custom path to chainstate directory

**Returns:** `bool` - Success status

#### `check_balance(address)`
Check if an address has a non-zero balance.

**Parameters:**
- `address`: Bitcoin address to check

**Returns:** `int` - Balance in satoshis (0 if no balance)

#### `get_balance(address)`
Get the exact balance for an address.

**Parameters:**
- `address`: Bitcoin address to check

**Returns:** `int` - Balance in satoshis

#### `get_status()`
Get a human-readable status message.

**Returns:** `str` - Status description

#### `close()`
Clean up resources (close database connection if open).

## Future Enhancements

Potential improvements for future versions:

- Support for reading live Bitcoin Core data (without stopping)
- Incremental updates when new blocks are added
- Support for pruning mode Bitcoin Core installations
- Export/import functionality for cached balances
- Multi-threaded loading for faster initialization
