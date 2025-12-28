import os
import struct
from typing import List

# Handle both module and direct execution
try:
    from .crypto_utils import hash160, base58check_encode, bech32_encode
except ImportError:
    from crypto_utils import hash160, base58check_encode, bech32_encode

class BalanceChecker:
    def __init__(self, data_path=None):
        self.data_path = data_path
        self.funded_addresses = set()
        self.address_balances = {}
        self.is_loaded = False
        self.db = None
        self.debug_mode = False
        self.debug_messages = []

    def _debug(self, message):
        """Add debug message if debug mode is enabled."""
        if self.debug_mode:
            self.debug_messages.append(message)
            print(f"[DEBUG] {message}")

    def get_debug_messages(self):
        """Retrieve all debug messages."""
        messages = self.debug_messages.copy()
        self.debug_messages.clear()
        return messages

    def load_addresses(self, filepath):
        """Load funded addresses from a text file or binary dump."""
        if not os.path.exists(filepath):
            return False
        
        try:
            with open(filepath, 'r') as f:
                for line in f:
                    addr = line.strip()
                    if addr:
                        self.funded_addresses.add(addr)
            self.is_loaded = True
            return True
        except Exception:
            return False

    def get_bitcoin_core_db_paths(self) -> List[str]:
        """Get all plausible Bitcoin Core chainstate LevelDB paths on this machine."""
        home = os.path.expanduser("~")
        appdata = os.environ.get('APPDATA')

        base_dirs = [
            # Linux snap install (per-user)
            os.path.join(home, "snap", "bitcoin-core", "common", ".bitcoin"),
            # Linux snap install (system-wide daemon)
            os.path.join(os.sep, "var", "snap", "bitcoin-core", "common", ".bitcoin"),
            # Linux standard
            os.path.join(home, ".bitcoin"),
            # macOS
            os.path.join(home, "Library", "Application Support", "Bitcoin"),
        ]
        if appdata:
            # Windows
            base_dirs.append(os.path.join(appdata, "Bitcoin"))

        network_subdirs = ["", "testnet3", "signet", "regtest"]

        candidates: List[str] = []
        for base in base_dirs:
            for net in network_subdirs:
                chainstate_dir = os.path.join(base, net, "chainstate") if net else os.path.join(base, "chainstate")
                if os.path.exists(chainstate_dir):
                    candidates.append(chainstate_dir)

        return candidates

    def get_bitcoin_core_db_path(self) -> str:
        """Get the default Bitcoin Core chainstate LevelDB path."""
        candidates = self.get_bitcoin_core_db_paths()
        if candidates:
            return candidates[0]

        # Fallback path (likely to fail, but consistent with previous behavior)
        home = os.path.expanduser("~")
        return os.path.join(home, "snap", "bitcoin-core", "common", ".bitcoin", "chainstate")

    def _parse_compact_size(self, data, offset):
        """Parse Bitcoin's compact size (varint) format"""
        if offset >= len(data):
            return 0, offset
        
        first_byte = data[offset]
        if first_byte < 0xfd:
            return first_byte, offset + 1
        elif first_byte == 0xfd:
            if offset + 3 > len(data):
                return 0, offset
            return struct.unpack('<H', data[offset+1:offset+3])[0], offset + 3
        elif first_byte == 0xfe:
            if offset + 5 > len(data):
                return 0, offset
            return struct.unpack('<I', data[offset+1:offset+5])[0], offset + 5
        else:
            if offset + 9 > len(data):
                return 0, offset
            return struct.unpack('<Q', data[offset+1:offset+9])[0], offset + 9

    def _decode_varint_amount(self, data, offset):
        """Decode Bitcoin's variable-length amount encoding"""
        if offset >= len(data):
            return 0, offset
        
        n = data[offset]
        offset += 1
        
        if n < 0xfd:
            return n, offset
        elif n == 0xfd:
            if offset + 2 > len(data):
                return 0, offset
            return struct.unpack('<H', data[offset:offset+2])[0], offset + 2
        elif n == 0xfe:
            if offset + 4 > len(data):
                return 0, offset
            return struct.unpack('<I', data[offset:offset+4])[0], offset + 4
        else:
            if offset + 8 > len(data):
                return 0, offset
            return struct.unpack('<Q', data[offset:offset+8])[0], offset + 8

    def _decode_compressed_amount(self, data, offset):
        """
        Decode Bitcoin Core's compressed amount format (CTxOutCompressor).

        Based on Bitcoin Core's compressor.h implementation:
        - CompressAmount removes trailing zeros and encodes the mantissa
        - DecompressAmount reverses this process

        The algorithm stores amounts in a compressed format that optimizes
        for common satoshi values (ending in zeros).
        """
        if offset >= len(data):
            return 0, offset

        # Read the varint that encodes the compressed amount
        n = data[offset]
        offset += 1

        if n < 0xfd:
            xn = n
        elif n == 0xfd:
            if offset + 2 > len(data):
                return 0, offset
            xn = struct.unpack('<H', data[offset:offset+2])[0]
            offset += 2
        elif n == 0xfe:
            if offset + 4 > len(data):
                return 0, offset
            xn = struct.unpack('<I', data[offset:offset+4])[0]
            offset += 4
        else:
            if offset + 8 > len(data):
                return 0, offset
            xn = struct.unpack('<Q', data[offset:offset+8])[0]
            offset += 8

        # Decompress using Bitcoin Core's algorithm
        # From compressor.h: uint64_t DecompressAmount(uint64_t x)
        if xn == 0:
            return 0, offset

        xn -= 1  # Subtract 1 (encoding adds 1)
        e = xn % 10  # Extract the exponent (number of trailing zeros)
        xn //= 10

        n = 0
        if e < 9:
            # Decode mantissa: (x % 9) gives digit (1-9)
            d = (xn % 9) + 1
            xn //= 9
            n = xn * 10 + d
        else:
            # e == 9 means large amounts
            n = xn + 1

        # Add back trailing zeros
        while e > 0:
            n *= 10
            e -= 1

        return n, offset

    def _extract_address_from_script(self, script):
        """Extract Bitcoin address from scriptPubKey"""
        if len(script) < 1:
            return None
        
        # P2PKH (Pay to Public Key Hash)
        # script: OP_DUP OP_HASH160 <hash> OP_EQUALVERIFY OP_CHECKSIG
        # bytes: 76 a9 14 <20 bytes> 88 ac
        if (len(script) == 25 and script[0] == 0x76 and script[1] == 0xa9 and 
            script[2] == 0x14 and script[23] == 0x88 and script[24] == 0xac):
            pubkey_hash = script[3:23]
            return base58check_encode(0, pubkey_hash)
        
        # P2SH (Pay to Script Hash)
        # script: OP_HASH160 <hash> OP_EQUAL
        # bytes: a9 14 <20 bytes> 87
        if (len(script) == 23 and script[0] == 0xa9 and script[1] == 0x14 and 
            script[22] == 0x87):
            script_hash = script[2:22]
            return base58check_encode(5, script_hash)
        
        # P2WPKH (Pay to Witness Public Key Hash)
        # script: OP_0 <20-byte hash>
        # bytes: 00 14 <20 bytes>
        if (len(script) == 22 and script[0] == 0x00 and script[1] == 0x14):
            witness_program = script[2:22]
            return bech32_encode('bc', 0, list(witness_program))
        
        # P2WSH (Pay to Witness Script Hash)
        # script: OP_0 <32-byte hash>
        # bytes: 00 20 <32 bytes>
        if (len(script) == 34 and script[0] == 0x00 and script[1] == 0x20):
            witness_program = script[2:34]
            return bech32_encode('bc', 0, list(witness_program))
        
        # P2TR (Taproot)
        # script: OP_1 <32-byte program>
        if (len(script) == 34 and script[0] == 0x51 and script[1] == 0x20):
            witness_program = script[2:34]
            return bech32_encode('bc', 1, list(witness_program))
        
        return None

    def load_from_bitcoin_core(self, path=None):
        """Load balance data from Bitcoin Core chainstate LevelDB."""
        try:
            import plyvel
            self._debug("plyvel library imported successfully")
        except ImportError:
            self._debug("ERROR: plyvel is not installed")
            print("plyvel is not installed. Install it with: pip install plyvel")
            return False
        
        auto_detected = path is None

        if auto_detected:
            candidate_paths = self.get_bitcoin_core_db_paths()
            if not candidate_paths:
                candidate_paths = [self.get_bitcoin_core_db_path()]
            self._debug(f"No path specified, found {len(candidate_paths)} candidate chainstate path(s)")
            for i, candidate in enumerate(candidate_paths[:10], start=1):
                self._debug(f"  Candidate {i}: {candidate}")
        else:
            candidate_paths = [path]
            self._debug(f"Using specified path: {path}")

        if not auto_detected and (path is None or not os.path.exists(path)):
            self._debug(f"ERROR: Bitcoin Core chainstate not found at: {path}")
            self._debug(f"Directory exists: {os.path.exists(os.path.dirname(path))}")
            self._debug(
                f"Contents of parent directory: {os.listdir(os.path.dirname(path)) if os.path.exists(os.path.dirname(path)) else 'N/A'}"
            )
            print(f"Bitcoin Core chainstate not found at: {path}")
            return False

        try:
            # Open the chainstate LevelDB
            db = None
            selected_path = None
            fallback_db = None
            fallback_path = None

            for candidate_path in candidate_paths:
                if not os.path.exists(candidate_path):
                    continue

                try:
                    self._debug(f"Attempting to open LevelDB at: {candidate_path}")
                    candidate_db = plyvel.DB(candidate_path, create_if_missing=False, compression=None)
                except Exception as db_error:
                    error_msg = str(db_error)
                    self._debug(f"ERROR: Failed to open DB at {candidate_path}: {error_msg}")
                    if 'lock' in error_msg.lower() or 'already held' in error_msg.lower():
                        print(f"Failed to load Bitcoin Core DB: {db_error}")
                        print("The chainstate database is locked by another process (likely Bitcoin Core).")
                        print("Please close Bitcoin Core and try again, or use a file-based address list instead.")
                        return False
                    if not auto_detected:
                        print(f"Failed to open Bitcoin Core DB: {db_error}")
                        return False
                    continue

                if not auto_detected:
                    db = candidate_db
                    selected_path = candidate_path
                    break

                # When auto-detecting, prefer a chainstate that actually contains UTXO entries ('C' keys).
                has_utxos = False
                it = None
                try:
                    it = candidate_db.iterator(prefix=b'C')
                    for _k, _v in it:
                        has_utxos = True
                        break
                finally:
                    if it is not None:
                        it.close()

                if has_utxos:
                    if fallback_db is not None:
                        fallback_db.close()
                    db = candidate_db
                    selected_path = candidate_path
                    self._debug(f"Selected chainstate path (UTXO entries present): {candidate_path}")
                    break

                if fallback_db is None:
                    fallback_db = candidate_db
                    fallback_path = candidate_path
                else:
                    candidate_db.close()

            if db is None and fallback_db is not None:
                db = fallback_db
                selected_path = fallback_path
                self._debug(f"Selected chainstate path (no UTXO entries detected in other candidates): {selected_path}")

            if db is None or selected_path is None:
                print("Bitcoin Core chainstate not found at any known location")
                return False

            path = selected_path
            self._debug(f"Chainstate directory found at: {path}")
            self._debug(f"Directory contents: {os.listdir(path) if os.path.isdir(path) else 'Not a directory'}")
            self._debug("Successfully opened LevelDB connection")
            
            # Iterate through all entries in the database
            address_balances = {}
            total_utxos = 0
            utxo_entries_seen = 0
            processed_entries = 0
            skipped_entries = 0
            
            self._debug("Starting to iterate through LevelDB entries...")
            
            for key, value in db:
                processed_entries += 1
                key_prefix = key[0] if len(key) > 0 else None
                key_prefix_hex = f"0x{key_prefix:02x}" if key_prefix is not None else "empty"
                key_prefix_chr = (
                    chr(key_prefix)
                    if key_prefix is not None and 32 <= key_prefix <= 126
                    else None
                )
                key_prefix_display = (
                    key_prefix_hex
                    if key_prefix_chr is None
                    else f"{key_prefix_hex} ('{key_prefix_chr}')"
                )

                if key_prefix is None or key_prefix != ord('C'):
                    skipped_entries += 1
                    if processed_entries <= 100:  # Log first 100 entries for debugging
                        self._debug(
                            f"Skipping entry {processed_entries}: key_prefix={key_prefix_display}, key_len={len(key)}, value_len={len(value)}"
                        )
                    continue

                utxo_entries_seen += 1
                self._debug(f"Processing UTXO entry {processed_entries}: key_len={len(key)}, value_len={len(value)}")

                # Parse the UTXO entry using modern Bitcoin Core CCoins format
                # Format: [version (4 bytes)] [height/coinbase flags (4 bytes)] [amount] [scriptPubKey]
                offset = 0

                # Read version (uint32)
                if offset + 4 > len(value):
                    self._debug(f"Skipping: value too short for version field (len={len(value)})")
                    continue
                version = struct.unpack('<I', value[offset:offset+4])[0]
                self._debug(f"  Version: {version}")
                offset += 4

                # Read height and coinbase flags (uint32, but bit-packed)
                if offset + 4 > len(value):
                    self._debug(f"Skipping: value too short for height_flags field (offset={offset}, len={len(value)})")
                    continue
                height_flags = struct.unpack('<I', value[offset:offset+4])[0]
                height = height_flags >> 1  # High bits are block height
                is_coinbase = height_flags & 1  # Low bit is coinbase flag
                self._debug(f"  Height: {height}, Coinbase: {is_coinbase}")
                offset += 4

                # Decode amount using Bitcoin Core's compressed format
                try:
                    amount, offset = self._decode_compressed_amount(value, offset)
                    self._debug(f"  Amount: {amount} satoshis")
                except Exception as e:
                    self._debug(f"Skipping: Failed to decode amount: {e}")
                    continue

                # Decode scriptPubKey size
                try:
                    script_size, offset = self._parse_compact_size(value, offset)
                    self._debug(f"  Script size: {script_size}")
                except Exception as e:
                    self._debug(f"Skipping: Failed to parse script size: {e}")
                    continue

                # Extract scriptPubKey
                if offset + script_size > len(value):
                    self._debug(f"Skipping: script extends beyond value bounds (offset={offset}, script_size={script_size}, value_len={len(value)})")
                    continue

                script_pubkey = value[offset:offset+script_size]
                self._debug(f"  Script: {script_pubkey.hex()}")

                # Extract address from script
                address = self._extract_address_from_script(script_pubkey)
                self._debug(f"  Extracted address: {address}")

                if address:
                    if address in address_balances:
                        address_balances[address] += amount
                    else:
                        address_balances[address] = amount
                    total_utxos += 1
                    self._debug(f"  Added/updated address in balances: {address}")
            
            db.close()
            
            self._debug(f"Total entries processed: {processed_entries}")
            self._debug(f"Skipped entries (non-UTXO): {skipped_entries}")
            self._debug(f"UTXO entries encountered: {utxo_entries_seen}")
            self._debug(f"UTXO entries with addresses: {total_utxos}")
            self._debug(f"Unique addresses extracted: {len(address_balances)}")

            if not address_balances:
                print("No addresses found in Bitcoin Core data")
                self._debug("No addresses could be extracted from the chainstate data")

                if utxo_entries_seen == 0:
                    self._debug("No UTXO entries ('C' keys) were found in this chainstate database")
                    self._debug("This usually means:")
                    self._debug("  - Bitcoin Core is still in 'headers-first' sync - it has downloaded")
                    self._debug("    block headers but hasn't validated and committed UTXO entries yet")
                    self._debug("  - The blockchain sync is at ~10% as you mentioned - Bitcoin Core")
                    self._debug("    needs to fully validate blocks before adding to chainstate")
                    self._debug("  - You're using testnet/signet/regtest but reading the mainnet chainstate")
                    self._debug("  - Snap: the synced data may be under /var/snap/bitcoin-core/common/.bitcoin")
                    self._debug("")
                    self._debug("The chainstate only contains UTXOs from FULLY VALIDATED blocks.")
                    self._debug("You need to wait for Bitcoin Core to sync more blocks, OR:")
                    self._debug("  1. Use a pre-synced Bitcoin Core node on another machine")
                    self._debug("  2. Export funded addresses from Bitcoin Core using RPC:")
                    self._debug("     bitcoin-cli listunspent > addresses.txt")
                    self._debug("  3. Use the 'Load Funded Addresses File' option instead")
                else:
                    self._debug("This could mean:")
                    self._debug("  - The blockchain is not fully synced")
                    self._debug("  - The UTXO entries don't contain recognizable address formats")
                    self._debug("  - The chainstate file format is incompatible")

                return False
            
            self.address_balances = address_balances
            self.data_path = path
            self.is_loaded = True
            
            print(f"Loaded {len(address_balances)} addresses from {total_utxos} UTXOs")
            return True
            
        except Exception as e:
            self._debug(f"ERROR: Exception during load: {e}")
            print(f"Failed to load Bitcoin Core DB: {e}")
            import traceback
            traceback.print_exc()
            return False

    def check_balance(self, address):
        """Check if an address has a non-zero balance"""
        if not self.is_loaded:
            return 0
        
        # Check against loaded address file
        if self.funded_addresses:
            return 1 if address in self.funded_addresses else 0
        
        # Check against Bitcoin Core chainstate
        if self.address_balances:
            balance = self.address_balances.get(address, 0)
            return balance
        
        return 0

    def get_balance(self, address):
        """Get the exact balance for an address (in satoshis)"""
        if not self.is_loaded:
            return 0
        
        if self.funded_addresses:
            return 1 if address in self.funded_addresses else 0
        
        if self.address_balances:
            return self.address_balances.get(address, 0)
        
        return 0

    def get_status(self):
        """Get status message"""
        if self.is_loaded:
            if self.funded_addresses:
                return f"Loaded {len(self.funded_addresses)} funded addresses from file"
            if self.address_balances:
                return f"Loaded {len(self.address_balances)} addresses from Bitcoin Core chainstate"
            if self.data_path:
                return f"Connected to Bitcoin Core data: {os.path.basename(self.data_path)}"
        return "Balance checking not active"

    def close(self):
        """Clean up resources"""
        if self.db:
            self.db.close()
            self.db = None
