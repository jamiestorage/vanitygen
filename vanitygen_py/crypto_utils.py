import hashlib
import base58
import bech32

def sha256(data):
    return hashlib.sha256(data).digest()

def ripemd160(data):
    h = hashlib.new('ripemd160')
    h.update(data)
    return h.digest()

def hash160(data):
    return ripemd160(sha256(data))

def base58check_encode(version, payload):
    data = bytes([version]) + payload
    checksum = sha256(sha256(data))[:4]
    return base58.b58encode(data + checksum).decode('ascii')

def convertbits(data, frombits, tobits, pad=True):
    acc = 0
    bits = 0
    ret = []
    maxv = (1 << tobits) - 1
    for value in data:
        acc = (acc << frombits) | value
        bits += frombits
        while bits >= tobits:
            bits -= tobits
            ret.append((acc >> bits) & maxv)
    if pad:
        if bits:
            ret.append((acc << (tobits - bits)) & maxv)
    return ret

def bech32_encode(hrp, witver, witprog):
    data = [witver] + convertbits(witprog, 8, 5)
    return bech32.bech32_encode(hrp, data)

def base58_decode(s):
    """
    Decode a base58check-encoded string to raw bytes.
    
    This is the inverse of base58check_encode. It decodes the base58 string
    and verifies the checksum.
    
    Args:
        s: Base58check-encoded string (e.g., Bitcoin address)
    
    Returns:
        bytes: Raw decoded data including version byte, payload (hash160), and checksum.
              Returns None if decoding fails or checksum doesn't match.
    
    Example:
        >>> addr = "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"
        >>> decoded = base58_decode(addr)
        >>> version = decoded[0]
        >>> hash160 = decoded[1:21]
        >>> checksum = decoded[21:25]
    """
    try:
        import hashlib
        
        # Use the base58 library which handles all edge cases correctly
        # including leading zeros, big numbers, etc.
        decoded = base58.b58decode(s)
        
        if len(decoded) < 25:
            return None
        
        # Verify checksum: SHA256(SHA256(version + hash160))[:4]
        payload = decoded[:21]
        provided_checksum = decoded[21:25]
        computed_checksum = hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
        
        if provided_checksum != computed_checksum:
            return None
        
        return decoded
        
    except Exception:
        return None
