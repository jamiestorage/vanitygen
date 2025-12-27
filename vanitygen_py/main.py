import sys
import argparse
from . import gui

def main():
    parser = argparse.ArgumentParser(description="Bitcoin Vanity Address Generator")
    parser.add_argument("--gui", action="store_true", help="Launch GUI interface")
    parser.add_argument("--prefix", type=str, help="Prefix to search for")
    parser.add_argument("--type", type=str, choices=['p2pkh', 'p2wpkh', 'p2sh-p2wpkh'], default='p2pkh', help="Address type")
    parser.add_argument("-i", "--case-insensitive", action="store_true", help="Case-insensitive search")
    
    args = parser.parse_args()

    if args.gui or len(sys.argv) == 1:
        gui.main()
    else:
        # CLI logic (minimal for now as GUI is emphasized)
        from .cpu_generator import CPUGenerator
        from .balance_checker import BalanceChecker
        import time

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
                    # In CLI we just continue or exit based on your preference
        except KeyboardInterrupt:
            gen.stop()
            print("\nStopped.")

if __name__ == "__main__":
    main()
