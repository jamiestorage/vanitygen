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
To use balance checking, you need a list of addresses with balance. You can generate this from your local Bitcoin Core blockchain using third-party tools that dump the UTXO set to a text file. Load this file in the Settings tab.
