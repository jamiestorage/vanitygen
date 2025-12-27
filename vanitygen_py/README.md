# Python Bitcoin Vanity Address Generator

A Python-based Bitcoin vanity address generator that supports both CPU and GPU acceleration.

## Features
- CPU-based generation: Works on any system with Python installed
- GPU acceleration: OpenCL support (via pyopencl)
- Multiple address types: P2PKH, P2WPKH (SegWit), P2SH-P2WPKH
- Vanity pattern matching
- Progress tracking: Real-time speed statistics
- GUI Interface: PySide6-based graphical interface
- Balance Checking: Check against local UTXO set

## Requirements
```
pip install -r requirements.txt
```

## Usage
### GUI
```
python -m vanitygen_py.main --gui
```

### CLI
```
python -m vanitygen_py.main --prefix 1ABC
```

## Balance Checking

The vanity address generator now supports **real-time balance checking** against your local Bitcoin Core blockchain data using plyvel to read the LevelDB chainstate directly.

### Method 1: Bitcoin Core LevelDB (Recommended)

**Requirements:**
- Bitcoin Core installed and fully synchronized
- Bitcoin Core must be stopped before reading chainstate
- plyvel package (included in requirements.txt)

**Usage:**
1. Launch the GUI: `python -m vanitygen_py.main --gui`
2. Click "Load from Bitcoin Core Data" in the Settings tab
3. The application will:
   - Auto-detect your Bitcoin Core data directory
   - Read the chainstate LevelDB
   - Parse all UTXOs and extract addresses
   - Cache address balances for fast lookups

**Supported Address Types:**
- P2PKH (addresses starting with '1')
- P2SH (addresses starting with '3')
- P2WPKH (addresses starting with 'bc1q')
- P2WSH (addresses starting with 'bc1q')
- P2TR (addresses starting with 'bc1p')

**Bitcoin Core Data Locations:**
- Linux: `~/.bitcoin/chainstate/`
- Linux (Snap): `~/snap/bitcoin-core/common/.bitcoin/chainstate/`
- macOS: `~/Library/Application Support/Bitcoin/chainstate/`
- Windows: `%APPDATA%\Bitcoin\chainstate\`

For detailed documentation, see [BITCOIN_CORE_INTEGRATION.md](BITCOIN_CORE_INTEGRATION.md)

### Method 2: Address File

You can also load addresses from a text file (one address per line). This is useful if you prefer not to use Bitcoin Core directly or if you want to use a pre-processed address list.

Generate this file from your local Bitcoin Core blockchain using third-party tools that dump the UTXO set. Load this file in the Settings tab.
