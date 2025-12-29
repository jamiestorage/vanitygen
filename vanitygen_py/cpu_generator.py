import multiprocessing
import time
from .bitcoin_keys import BitcoinKey

def worker(prefix, addr_type, result_queue, stop_event, pause_event, stats_counter, case_insensitive=False):
    while not stop_event.is_set():
        # Check if paused
        if pause_event.is_set():
            time.sleep(0.1)
            continue

        key = BitcoinKey()
        if addr_type == 'p2pkh':
            address = key.get_p2pkh_address()
        elif addr_type == 'p2wpkh':
            address = key.get_p2wpkh_address()
        elif addr_type == 'p2sh-p2wpkh':
            address = key.get_p2sh_p2wpkh_address()
        else:
            address = key.get_p2pkh_address()

        match = False
        if case_insensitive:
            if address.lower().startswith(prefix.lower()):
                match = True
        else:
            if address.startswith(prefix):
                match = True

        if match:
            result_queue.put((address, key.get_wif(), key.get_public_key().hex()))
            # Don't stop yet, let the main process decide

        stats_counter.value += 1

class CPUGenerator:
    def __init__(self, prefix, addr_type='p2pkh', cores=None, case_insensitive=False):
        self.prefix = prefix
        self.addr_type = addr_type
        self.cores = cores or multiprocessing.cpu_count()
        self.case_insensitive = case_insensitive
        self.result_queue = multiprocessing.Queue()
        self.stop_event = multiprocessing.Event()
        self.pause_event = multiprocessing.Event()  # For pause/resume
        self.stats_counter = multiprocessing.Value('i', 0)
        self.processes = []
        self.paused = False

    def start(self):
        for _ in range(self.cores):
            p = multiprocessing.Process(target=worker, args=(
                self.prefix, self.addr_type, self.result_queue, self.stop_event,
                self.pause_event, self.stats_counter, self.case_insensitive
            ))
            p.start()
            self.processes.append(p)

    def stop(self):
        self.stop_event.set()
        for p in self.processes:
            p.join()

    def pause(self):
        """Pause the generator"""
        self.paused = True
        self.pause_event.set()

    def resume(self):
        """Resume the generator"""
        self.paused = False
        self.pause_event.clear()

    def is_paused(self):
        """Check if generator is paused"""
        return self.paused

    def get_stats(self):
        count = self.stats_counter.value
        self.stats_counter.value = 0
        return count
