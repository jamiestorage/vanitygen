import os
import struct

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

    def get_bitcoin_core_db_path(self) -> str:
        """Get the Bitcoin Core LevelDB database path"""
        home = os.path.expanduser("~")
        
        # Try multiple possible Bitcoin Core data locations
        possible_paths = [
            # Linux snap install
            os.path.join(home, "snap", "bitcoin-core", "common", ".bitcoin", "chainstate"),
            # Linux standard
            os.path.join(home, ".bitcoin", "chainstate"),
            # macOS
            os.path.join(home, "Library", "Application Support", "Bitcoin", "chainstate"),
            # Windows
            os.path.join(os.environ.get('APPDATA', ''), "Bitcoin", "chainstate"),
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                return path
        
        # Return default path (likely to fail but consistent with old behavior)
        return possible_paths[0]

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
        except ImportError:
            print("plyvel is not installed. Install it with: pip install plyvel")
            return False
        
        if path is None:
            path = self.get_bitcoin_core_db_path()
        
        if not os.path.exists(path):
            print(f"Bitcoin Core chainstate not found at: {path}")
            return False
        
        try:
            # Open the chainstate LevelDB
            try:
                db = plyvel.DB(path, create_if_missing=False, compression=None)
            except Exception as db_error:
                error_msg = str(db_error)
                if 'lock' in error_msg.lower() or 'already held' in error_msg.lower():
                    print(f"Failed to load Bitcoin Core DB: {db_error}")
                    print("The chainstate database is locked by another process (likely Bitcoin Core).")
                    print("Please close Bitcoin Core and try again, or use a file-based address list instead.")
                else:
                    print(f"Failed to open Bitcoin Core DB: {db_error}")
                return False
            
            # Iterate through all entries in the database
            address_balances = {}
            total_utxos = 0
            
            for key, value in db:
                # Skip non-UTXO entries (keys starting with 'C' for coins)
                if len(key) < 1 or key[0] != ord('C'):
                    continue
                
                # Parse the UTXO entry
                # Value format: [varint code] [amount] [scriptPubKey_size] [scriptPubKey]
                # Note: Modern Bitcoin Core uses a different format
                offset = 0
                
                # Decode the compact size (usually 0 for coin entries)
                try:
                    code, offset = self._parse_compact_size(value, offset)
                except:
                    continue
                
                # Decode amount (in satoshis)
                try:
                    amount, offset = self._decode_varint_amount(value, offset)
                except:
                    continue
                
                # Decode scriptPubKey size
                try:
                    script_size, offset = self._parse_compact_size(value, offset)
                except:
                    continue
                
                # Extract scriptPubKey
                if offset + script_size > len(value):
                    continue
                
                script_pubkey = value[offset:offset+script_size]
                
                # Extract address from script
                address = self._extract_address_from_script(script_pubkey)
                
                if address:
                    if address in address_balances:
                        address_balances[address] += amount
                    else:
                        address_balances[address] = amount
                    total_utxos += 1
            
            db.close()
            
            if not address_balances:
                print("No addresses found in Bitcoin Core data")
                return False
            
            self.address_balances = address_balances
            self.data_path = path
            self.is_loaded = True
            
            print(f"Loaded {len(address_balances)} addresses from {total_utxos} UTXOs")
            return True
            
        except Exception as e:
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
