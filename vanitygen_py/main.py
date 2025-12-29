import sys
import argparse
from . import gui

def main():
    parser = argparse.ArgumentParser(description="Bitcoin Vanity Address Generator")
    parser.add_argument("--gui", action="store_true", help="Launch GUI interface")
    parser.add_argument("--prefix", type=str, help="Prefix to search for")
    parser.add_argument("--type", type=str, choices=['p2pkh', 'p2wpkh', 'p2sh-p2wpkh'], default='p2pkh', help="Address type")
    parser.add_argument("-i", "--case-insensitive", action="store_true", help="Case-insensitive search")
    parser.add_argument("--gpu", action="store_true", help="Use GPU acceleration for address generation")
    parser.add_argument("--balance-check", type=str, help="Path to funded addresses file or chainstate for GPU balance checking")
    parser.add_argument("--batch-size", type=int, default=4096, help="GPU batch size (default: 4096)")
    parser.add_argument("--power", type=int, default=100, help="GPU power usage percentage 1-100 (default: 100)")

    args = parser.parse_args()

    if args.gui or len(sys.argv) == 1:
        gui.main()
    else:
        # CLI logic
        import time

        if args.gpu:
            # GPU-accelerated generation
            try:
                from .gpu_generator import GPUGenerator
                from .balance_checker import BalanceChecker

                # Set up balance checker if provided
                balance_checker = None
                if args.balance_check:
                    balance_checker = BalanceChecker(args.balance_check)
                    if balance_checker.funded_addresses or balance_checker.address_balances:
                        print(f"Loaded {len(balance_checker.funded_addresses or balance_checker.address_balances)} addresses for balance checking")
                    else:
                        print("Warning: Could not load balance checking data")
                        balance_checker = None

                gen = GPUGenerator(
                    args.prefix,
                    args.type,
                    batch_size=args.batch_size,
                    power_percent=args.power,
                    balance_checker=balance_checker
                )

                print(f"Starting GPU-accelerated search for prefix '{args.prefix}'...")
                if balance_checker:
                    print("GPU balance checking ENABLED - will search for funded addresses")
                gen.start()

                try:
                    total_keys = 0
                    start_time = time.time()
                    while True:
                        time.sleep(1)
                        new_keys = gen.get_stats()
                        total_keys += new_keys
                        elapsed = time.time() - start_time
                        speed = total_keys / elapsed if elapsed > 0 else 0
                        print(f"\rSpeed: {speed:.2f} keys/s | Total: {total_keys}", end="", flush=True)

                        while not gen.result_queue.empty():
                            result = gen.result_queue.get()
                            if len(result) >= 4:
                                # Funded address result with balance
                                addr, wif, pubkey, balance = result
                                print(f"\n*** FUNDED ADDRESS FOUND! ***")
                                print(f"Address: {addr}")
                                print(f"Balance: {balance} satoshis")
                                print(f"Private Key: {wif}")
                            else:
                                # Vanity match result
                                addr, wif, pubkey = result
                                print(f"\nMatch found!")
                                print(f"Address: {addr}")
                                print(f"Private Key: {wif}")
                                print(f"Public Key: {pubkey}")

                except KeyboardInterrupt:
                    gen.stop()
                    print("\nStopped.")

            except ImportError as e:
                print(f"GPU libraries not available: {e}")
                print("Install pyopencl for GPU support")
                return

        else:
            # CPU generation (original behavior)
            from .cpu_generator import CPUGenerator
            from .balance_checker import BalanceChecker

            bc = BalanceChecker()
            gen = CPUGenerator(args.prefix, args.type, case_insensitive=args.case_insensitive)
            gen.start()
            print(f"Searching for prefix '{args.prefix}'...")
            try:
                total_keys = 0
                start_time = time.time()
                while True:
                    time.sleep(1)
                    new_keys = gen.get_stats()
                    total_keys += new_keys
                    elapsed = time.time() - start_time
                    speed = total_keys / elapsed if elapsed > 0 else 0
                    print(f"\rSpeed: {speed:.2f} keys/s | Total: {total_keys}", end="")

                    while not gen.result_queue.empty():
                        addr, wif, pubkey = gen.result_queue.get()
                        print(f"\nMatch found!")
                        print(f"Address: {addr}")
                        print(f"Private Key: {wif}")
                        print(f"Public Key: {pubkey}")
            except KeyboardInterrupt:
                gen.stop()
                print("\nStopped.")

if __name__ == "__main__":
    main()
