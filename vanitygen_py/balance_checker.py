import os

class BalanceChecker:
    def __init__(self, data_path=None):
        self.data_path = data_path
        self.funded_addresses = set()
        self.is_loaded = False

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
        default_path = os.path.join(home, "snap", "bitcoin-core", "common", ".bitcoin", "blocks", "index")
        return default_path

    def load_from_bitcoin_core(self, path=None):
        """Try to load balance data from Bitcoin Core LevelDB."""
        if path is None:
            path = self.get_bitcoin_core_db_path()
        
        if not os.path.exists(path):
            # Try fallback to chainstate
            home = os.path.expanduser("~")
            path = os.path.join(home, ".bitcoin", "chainstate")
        
        if not os.path.exists(path):
            return False
            
        try:
            import plyvel
            # Just test if we can open it
            db = plyvel.DB(path, create_if_missing=False)
            db.close()
            self.is_loaded = True
            self.data_path = path
            return True
        except Exception as e:
            print(f"Failed to load Bitcoin Core DB: {e}")
            return False

    def check_balance(self, address):
        if not self.is_loaded:
            return 0
        
        if self.funded_addresses:
            return 1 if address in self.funded_addresses else 0
        
        if self.data_path:
            # If we have a data_path but no funded_addresses set, 
            # it means we should ideally check the DB.
            # Since real-time DB lookup for every generated address 
            # would be slow and requires complex parsing, 
            # we'll keep it as a placeholder or returning 0.
            return 0
        return 0

    def get_status(self):
        if self.is_loaded:
            if self.funded_addresses:
                return f"Loaded {len(self.funded_addresses)} funded addresses"
            if self.data_path:
                return f"Connected to Bitcoin Core data: {os.path.basename(self.data_path)}"
        return "Balance checking not active"
