import os
import ecdsa
import hashlib
from .crypto_utils import hash160, base58check_encode, bech32_encode

class BitcoinKey:
    def __init__(self, privkey_bytes=None):
        if privkey_bytes is None:
            self.privkey_bytes = os.urandom(32)
        else:
            self.privkey_bytes = privkey_bytes
        
        self.sk = ecdsa.SigningKey.from_string(self.privkey_bytes, curve=ecdsa.SECP256k1)
        self.vk = self.sk.get_verifying_key()
    
    def get_public_key(self, compressed=True):
        point = self.vk.pubkey.point
        if compressed:
            prefix = b'\x02' if point.y() % 2 == 0 else b'\x03'
            return prefix + point.x().to_bytes(32, 'big')
        else:
            return b'\x04' + point.x().to_bytes(32, 'big') + point.y().to_bytes(32, 'big')

    def get_p2pkh_address(self, compressed=True):
        pubkey = self.get_public_key(compressed)
        h160 = hash160(pubkey)
        return base58check_encode(0, h160)

    def get_p2wpkh_address(self):
        # Native SegWit (Bech32)
        pubkey = self.get_public_key(compressed=True) # Always compressed for SegWit
        h160 = hash160(pubkey)
        return bech32_encode('bc', 0, list(h160))

    def get_p2sh_p2wpkh_address(self):
        # Nested SegWit
        pubkey = self.get_public_key(compressed=True)
        h160 = hash160(pubkey)
        redeem_script = b'\x00\x14' + h160
        script_hash = hash160(redeem_script)
        return base58check_encode(5, script_hash)

    def get_wif(self, compressed=True):
        payload = self.privkey_bytes
        if compressed:
            payload += b'\x01'
        return base58check_encode(128, payload)
