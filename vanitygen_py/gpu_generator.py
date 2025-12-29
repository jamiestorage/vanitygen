import threading
import time
import queue
import os
import struct
import multiprocessing

# Handle both module and direct execution
try:
    from .bitcoin_keys import BitcoinKey
except ImportError:
    from bitcoin_keys import BitcoinKey

try:
    import pyopencl as cl
    import numpy as np
except ImportError:
    cl = None
    np = None


def _process_keys_batch(args):
    """Worker function to process a batch of keys on CPU"""
    key_bytes_list, addr_type, prefix = args
    results = []
    for key_bytes in key_bytes_list:
        key = BitcoinKey(key_bytes)
        # Generate address
        if addr_type == 'p2pkh':
            address = key.get_p2pkh_address()
        elif addr_type == 'p2wpkh':
            address = key.get_p2wpkh_address()
        elif addr_type == 'p2sh-p2wpkh':
            address = key.get_p2sh_p2wpkh_address()
        else:
            address = key.get_p2pkh_address()

        # Check for prefix match
        if address.startswith(prefix):
            results.append((address, key.get_wif(), key.get_public_key().hex()))
    return results


class GPUGenerator:
    def __init__(self, prefix, addr_type='p2pkh', batch_size=4096, power_percent=100, device_selector=None, cpu_cores=None, balance_checker=None, gpu_only=False):
        """
        GPU-accelerated vanity address generator.

        Args:
            prefix: The desired address prefix to search for
            addr_type: Address type ('p2pkh', 'p2wpkh', 'p2sh-p2wpkh')
            batch_size: Number of keys to generate per GPU batch
            power_percent: GPU power usage percentage (1-100)
            device_selector: Tuple of (platform_index, device_index) for specific GPU selection
            cpu_cores: Number of CPU cores to use for post-processing (default: 2)
            balance_checker: Optional BalanceChecker instance for GPU-accelerated balance checking
            gpu_only: If True, perform ALL operations on GPU (no CPU needed for address generation)
        """
        self.prefix = prefix
        self.addr_type = addr_type
        self.result_queue = queue.Queue()
        self.running = False
        self.search_thread = None
        self.stats_counter = 0
        self.stats_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.pause_event = threading.Event()  # For pause/resume
        self.gpu_available = False
        self.pool = None
        self.paused = False

        # OpenCL resources
        self.ctx = None
        self.queue = None
        self.program = None
        self.kernel = None
        self.kernel_check = None
        self.kernel_full = None  # Full GPU address generation
        self.device = None

        # GPU configuration
        self.batch_size = int(batch_size) if batch_size else 4096
        self.power_percent = 100 if power_percent is None else int(power_percent)
        self.device_selector = device_selector
        self.rng_seed = int(time.time())

        # CPU configuration for post-processing
        self.cpu_cores = cpu_cores if cpu_cores is not None else 2

        # Balance checking configuration
        self.balance_checker = balance_checker
        self.bloom_filter = None
        self.bloom_filter_size = 0
        self.address_buffer = None
        self.gpu_bloom_filter = None
        self.gpu_address_buffer = None
        self.found_count_buffer = None

        # GPU-only mode: do everything on GPU
        self.gpu_only = gpu_only

    def set_balance_checker(self, balance_checker):
        """
        Set a BalanceChecker for GPU-accelerated balance checking.

        This enables GPU-side filtering of addresses against a bloom filter
        of funded addresses, reducing CPU load significantly when checking
        millions of addresses.

        Args:
            balance_checker: A BalanceChecker instance with addresses loaded
        """
        self.balance_checker = balance_checker
        if balance_checker and balance_checker.is_loaded:
            print("Balance checker configured for GPU-accelerated checking")
            self._setup_gpu_balance_check()
        else:
            print("Warning: Balance checker not ready (no addresses loaded)")

    def _setup_gpu_balance_check(self):
        """Set up GPU buffers for balance checking"""
        if not self.balance_checker or not self.ctx:
            return

        try:
            # Create bloom filter
            self.bloom_filter, self.bloom_filter_size = self.balance_checker.create_bloom_filter()
            if self.bloom_filter is None:
                print("Failed to create bloom filter")
                return

            # Create address buffer for verification
            self.address_buffer = self.balance_checker.create_gpu_address_buffer()
            if self.address_buffer is None:
                print("Failed to create address buffer")
                return

            # Allocate GPU buffers
            mf = cl.mem_flags

            # Bloom filter buffer
            self.gpu_bloom_filter = cl.Buffer(self.ctx, mf.READ_ONLY | mf.COPY_HOST_PTR,
                                              hostbuf=np.frombuffer(self.bloom_filter, dtype=np.uint8))

            # Address buffer for verification (contains hash160 + address pairs)
            self.gpu_address_buffer = cl.Buffer(self.ctx, mf.READ_ONLY | mf.COPY_HOST_PTR,
                                                hostbuf=np.frombuffer(self.address_buffer, dtype=np.uint8))

            # Found count buffer (for tracking potential matches)
            self.found_count_buffer = cl.Buffer(self.ctx, mf.READ_WRITE, 4)

            print(f"GPU balance checking enabled: {len(self.bloom_filter)} byte bloom filter, "
                  f"{len(self.address_buffer)} byte address buffer")

        except Exception as e:
            print(f"Failed to setup GPU balance checking: {e}")
            import traceback
            traceback.print_exc()

    def init_cl(self):
        """Initialize OpenCL context and compile kernel"""
        try:
            if cl is None:
                print("pyopencl not installed")
                return False

            platforms = cl.get_platforms()
            if not platforms:
                print("No OpenCL platforms found")
                return False

            # Select device
            if self.device_selector is not None:
                try:
                    p_idx, d_idx = self.device_selector
                    platform = platforms[p_idx]
                    devices = platform.get_devices()
                    self.device = devices[d_idx]
                except Exception as e:
                    print(f"Invalid OpenCL device selection {self.device_selector}: {e}")
                    return False
            else:
                # Auto-detect: prefer a GPU device, otherwise fall back to the first available device
                selected = None
                for platform in platforms:
                    try:
                        gpus = platform.get_devices(device_type=cl.device_type.GPU)
                    except Exception:
                        gpus = []
                    if gpus:
                        selected = gpus[0]
                        break
                if selected is None:
                    selected = platforms[0].get_devices()[0]
                self.device = selected

            self.ctx = cl.Context([self.device])
            self.queue = cl.CommandQueue(self.ctx)

            # Load and compile kernel
            kernel_path = os.path.join(os.path.dirname(__file__), 'gpu_kernel.cl')
            if not os.path.exists(kernel_path):
                print(f"OpenCL kernel not found at {kernel_path}")
                return False

            with open(kernel_path, 'r') as f:
                kernel_source = f.read()

            self.program = cl.Program(self.ctx, kernel_source).build()
            self.kernel = self.program.generate_private_keys

            # Compile the generate_and_check kernel for balance checking
            try:
                self.kernel_check = self.program.generate_and_check
                print("GPU kernel for balance checking compiled")
            except Exception:
                print("Warning: GPU kernel for balance checking not available")
                self.kernel_check = None

            # Compile the full GPU kernel for GPU-only mode (no CPU needed)
            try:
                self.kernel_full = self.program.generate_addresses_full
                print("Full GPU address generation kernel compiled (GPU-only mode)")
            except Exception:
                print("Note: Full GPU kernel not available, will use CPU for address generation")
                self.kernel_full = None

            print(f"GPU initialized: {self.device.name}")
            return True

        except Exception as e:
            print(f"OpenCL initialization failed: {e}")
            import traceback
            traceback.print_exc()
            return False

    def is_available(self):
        return self.gpu_available

    @staticmethod
    def list_available_devices():
        if cl is None:
            return []

        devices = []
        try:
            for p_idx, platform in enumerate(cl.get_platforms()):
                for d_idx, device in enumerate(platform.get_devices()):
                    dev_type = "GPU" if (device.type & cl.device_type.GPU) else "CPU" if (device.type & cl.device_type.CPU) else "OTHER"
                    devices.append({
                        "platform_index": p_idx,
                        "device_index": d_idx,
                        "platform_name": getattr(platform, "name", str(platform)),
                        "device_name": device.name,
                        "device_type": dev_type,
                    })
        except Exception:
            return []

        return devices

    def _generate_keys_on_gpu(self, count):
        """Generate private keys using OpenCL GPU"""
        if not self.gpu_available or self.kernel is None:
            return None

        try:
            # Prepare output buffer (8 uint32 per key = 256 bits)
            output_buffer = np.zeros(count * 8, dtype=np.uint32)

            # Create OpenCL buffer
            mf = cl.mem_flags
            output_buf = cl.Buffer(self.ctx, mf.WRITE_ONLY, output_buffer.nbytes)

            # Execute kernel
            self.kernel(self.queue, (count,), None, output_buf, np.uint64(self.rng_seed), np.uint32(count))

            # Read results back
            cl.enqueue_copy(self.queue, output_buffer, output_buf)
            self.queue.finish()

            # Update seed for next batch
            self.rng_seed += count

            return output_buffer.reshape(-1, 8)

        except Exception as e:
            print(f"GPU key generation failed: {e}")
            return None

    def _keys_from_gpu_data(self, gpu_keys):
        """Convert GPU-generated data to BitcoinKey objects"""
        keys = []
        for key_data in gpu_keys:
            # Convert 8 uint32s to 32 bytes
            key_bytes = b''.join(struct.pack('<I', word) for word in key_data)
            keys.append(BitcoinKey(key_bytes))
        return keys

    def _search_loop_with_balance_check(self):
        """
        GPU-accelerated search loop with GPU-side balance checking using bloom filter.

        This method uses the GPU to:
        1. Generate private keys
        2. Compute hash160 (SHA256 + RIPEMD160)
        3. Generate P2PKH addresses
        4. Check against bloom filter for potential balance matches
        5. Check prefix for vanity matching

        Only addresses that pass both checks are returned to CPU for verification.
        This significantly reduces CPU load when checking millions of addresses.
        """
        if self.kernel_check is None:
            print("Balance checking kernel not available, falling back to CPU processing")
            self._search_loop()
            return

        # Allocate result buffer (64 bytes per potential match)
        max_results = 256
        results_buffer = np.zeros(max_results * 64, dtype=np.uint8)
        found_count = np.zeros(1, dtype=np.int32)

        # Prepare prefix for GPU
        prefix_bytes = np.frombuffer(self.prefix.encode('ascii'), dtype=np.uint8)
        prefix_len = len(self.prefix)

        while not self.stop_event.is_set():
            # Check if paused
            if self.pause_event.is_set():
                time.sleep(0.1)
                continue

            loop_start = time.time()

            try:
                mf = cl.mem_flags

                # Create output buffers
                output_keys = np.zeros(self.batch_size * 8, dtype=np.uint32)

                # Create GPU buffer for output keys
                output_keys_buf = cl.Buffer(self.ctx, mf.WRITE_ONLY, output_keys.nbytes)

                # Ensure buffers are on GPU
                results_buf = cl.Buffer(self.ctx, mf.WRITE_ONLY, results_buffer.nbytes)
                found_count_buf = cl.Buffer(self.ctx, mf.READ_WRITE | mf.COPY_HOST_PTR, hostbuf=found_count)

                # Reset found count on GPU
                cl.enqueue_copy(self.queue, found_count_buf, found_count)
                self.queue.finish()

                # Execute the combined kernel
                self.kernel_check(
                    self.queue, (self.batch_size,), None,
                    output_keys_buf,  # output_keys
                    results_buf,  # found_addresses (not used directly)
                    found_count_buf,  # found_count
                    np.uint64(self.rng_seed),  # seed
                    np.uint32(self.batch_size),  # batch_size
                    self.gpu_bloom_filter,  # bloom_filter
                    np.uint32(self.bloom_filter_size),  # filter_size
                    np.frombuffer(prefix_bytes, dtype=np.uint8),  # prefix
                    np.int32(prefix_len),  # prefix_len
                    self.gpu_address_buffer,  # addresses_buffer
                    np.uint32(max_results)  # max_addresses
                )

                self.queue.finish()

                # Read back results
                cl.enqueue_copy(self.queue, results_buffer, results_buf)
                cl.enqueue_copy(self.queue, found_count, found_count_buf)
                self.queue.finish()

                # Update seed
                self.rng_seed += self.batch_size

                # Clean up GPU buffers to prevent memory leak
                output_keys_buf.release()
                results_buf.release()
                found_count_buf.release()

                # Process found results
                num_found = found_count[0]
                for i in range(min(num_found, max_results)):
                    offset = i * 64
                    # Extract key words (first 32 bytes = 8 uint32)
                    key_words = []
                    for j in range(8):
                        word = int.from_bytes(results_buffer[offset + j*4:offset + j*4 + 4], 'little')
                        key_words.append(word)
                    key_bytes = b''.join(struct.pack('<I', word) for word in key_words)

                    # Extract address string
                    addr_end = offset + 54
                    addr = ''
                    for k in range(offset + 32, addr_end):
                        if results_buffer[k] == 0:
                            break
                        addr += chr(results_buffer[k])

                    # Verify on CPU and check balance
                    key = BitcoinKey(key_bytes)
                    address = key.get_p2pkh_address()

                    # Verify balance on CPU
                    if self.balance_checker:
                        balance = self.balance_checker.check_balance(address)
                        if balance > 0:
                            # Funded address found!
                            self.result_queue.put((
                                address,
                                key.get_wif(),
                                key.get_public_key().hex()
                            ))
                            print(f"*** FUNDED ADDRESS FOUND! ***")
                            print(f"Address: {address}")
                            print(f"Balance: {balance} satoshis")
                            print(f"WIF: {key.get_wif()}")

                    # Also check prefix match (vanity)
                    if self.prefix and address.startswith(self.prefix):
                        self.result_queue.put((
                            address,
                            key.get_wif(),
                            key.get_public_key().hex()
                        ))

                # Update stats
                with self.stats_lock:
                    self.stats_counter += self.batch_size

            except Exception as e:
                print(f"Error in GPU balance checking: {e}")
                import traceback
                traceback.print_exc()

            # Power throttling
            power = self.power_percent
            if power is not None and power < 100:
                duty = max(0.05, min(1.0, power / 100.0))
                work_time = time.time() - loop_start
                sleep_time = work_time * (1.0 / duty - 1.0)
                if sleep_time > 0:
                    self.stop_event.wait(timeout=sleep_time)

    def _search_loop_gpu_only(self):
        """
        GPU-only search loop - ALL operations happen on GPU.

        This method performs:
        1. Private key generation on GPU
        2. Address generation (hash160 + base58) on GPU
        3. Prefix matching on GPU
        4. Balance checking (bloom filter) on GPU

        Only matching results are returned to CPU for display.
        Zero CPU usage for address generation - GPU handles everything!
        """
        if self.kernel_full is None:
            print("Full GPU kernel not available, falling back to CPU-assisted mode")
            if self.balance_checker and self.gpu_bloom_filter is not None:
                self._search_loop_with_balance_check()
            else:
                self._search_loop()
            return

        # Allocate result buffer (128 bytes per potential match: 32 key + 64 addr + 32 spare)
        max_results = 512
        results_buffer = np.zeros(max_results * 128, dtype=np.uint8)
        found_count = np.zeros(1, dtype=np.int32)

        # Prepare prefix for GPU - create fixed-size buffer
        prefix_bytes = self.prefix.encode('ascii')
        prefix_len = len(prefix_bytes)
        # Pad to 64 bytes for alignment
        prefix_buffer = np.zeros(64, dtype=np.uint8)
        prefix_buffer[:prefix_len] = np.frombuffer(prefix_bytes, dtype=np.uint8)

        print(f"Starting GPU-only mode (batch size={self.batch_size})")
        print("All operations (key gen + address generation + matching) on GPU")

        # Allocate GPU buffer for prefix
        mf = cl.mem_flags
        gpu_prefix_buffer = cl.Buffer(self.ctx, mf.READ_ONLY | mf.COPY_HOST_PTR, hostbuf=prefix_buffer)

        # Store prefix buffer for cleanup
        self.gpu_prefix_buffer = gpu_prefix_buffer

        # Set up bloom filter for balance checking
        check_balance = 0
        gpu_bloom_filter = None
        bloom_filter_size = 0
        bloom_buffer = None
        if self.balance_checker and self.balance_checker.is_loaded:
            print("Setting up GPU bloom filter for balance checking...")
            bloom_data, bloom_size = self.balance_checker.create_bloom_filter()
            if bloom_data is not None:
                check_balance = 1
                bloom_filter_size = len(bloom_data)
                # Use np.array instead of np.frombuffer to create a copy and avoid keeping reference
                bloom_buffer = np.array(bloom_data, dtype=np.uint8)
                gpu_bloom_filter = cl.Buffer(self.ctx, mf.READ_ONLY | mf.COPY_HOST_PTR, hostbuf=bloom_buffer)
                # Store for cleanup
                self.temp_bloom_buffer = gpu_bloom_filter
                print(f"Bloom filter: {bloom_filter_size} bytes ({bloom_size} bits)")
                # Clear the buffer reference to free memory
                del bloom_buffer
            else:
                print("Bloom filter creation failed, proceeding without balance checking")
        else:
            print("No balance checker loaded, proceeding without balance checking")

        # Ensure we have a valid buffer for kernel (even if empty)
        if gpu_bloom_filter is None:
            dummy_buffer = np.zeros(1, dtype=np.uint8)
            gpu_bloom_filter = cl.Buffer(self.ctx, mf.READ_ONLY | mf.COPY_HOST_PTR, hostbuf=dummy_buffer)
            # Store for cleanup
            self.temp_bloom_buffer = gpu_bloom_filter
            del dummy_buffer

        while not self.stop_event.is_set():
            # Check if paused
            if self.pause_event.is_set():
                time.sleep(0.1)
                continue

            loop_start = time.time()

            try:
                mf = cl.mem_flags

                # Create output buffer for results
                results_buf = cl.Buffer(self.ctx, mf.WRITE_ONLY, results_buffer.nbytes)
                found_count_buf = cl.Buffer(self.ctx, mf.READ_WRITE | mf.COPY_HOST_PTR, hostbuf=found_count)

                # Reset found count on GPU
                cl.enqueue_copy(self.queue, found_count_buf, found_count)
                self.queue.finish()

                # Execute the full GPU kernel with bloom filter support
                self.kernel_full(
                    self.queue, (self.batch_size,), None,
                    results_buf,           # found_addresses
                    found_count_buf,       # found_count
                    np.uint64(self.rng_seed),  # seed
                    np.uint32(self.batch_size),  # batch_size
                    gpu_prefix_buffer,     # prefix (must be a cl.Buffer)
                    np.int32(prefix_len),  # prefix_len
                    np.uint32(max_results), # max_addresses
                    gpu_bloom_filter if gpu_bloom_filter else np.uint32(0),  # bloom_filter
                    np.uint32(bloom_filter_size),  # filter_size
                    np.uint32(check_balance)  # check_balance
                )

                self.queue.finish()

                # Read back results
                cl.enqueue_copy(self.queue, results_buffer, results_buf)
                cl.enqueue_copy(self.queue, found_count, found_count_buf)
                self.queue.finish()

                # Update seed
                self.rng_seed += self.batch_size

                # Clean up GPU buffers to prevent memory leak
                results_buf.release()
                found_count_buf.release()

                # Update stats BEFORE processing results to ensure counter increments even on errors
                with self.stats_lock:
                    self.stats_counter += self.batch_size

                # Process found results
                # First pass: check bloom filter matches (high priority)
                num_found = found_count[0]

                # Collect all results first
                results = []
                try:
                    for i in range(min(num_found, max_results)):
                        offset = i * 128

                        # Extract key words (first 32 bytes = 8 uint32)
                        key_words = []
                        for j in range(8):
                            word = int.from_bytes(results_buffer[offset + j*4:offset + j*4 + 4], 'little')
                            key_words.append(word)
                        key_bytes = b''.join(struct.pack('<I', word) for word in key_words)

                        # Extract address string (after key, null-terminated)
                        addr_start = offset + 32
                        addr_end = offset + 96  # Allow up to 64 chars for address
                        addr = ''
                        for k in range(addr_start, addr_end):
                            if results_buffer[k] == 0:
                                break
                            addr += chr(results_buffer[k])

                        # Check if bloom filter matched (byte 96)
                        bloom_match = results_buffer[offset + 96] == 1

                        results.append((addr, key_bytes, bloom_match))

                    # Sort results: bloom filter matches first
                    results.sort(key=lambda x: not x[2])

                    # Process results
                    for addr, key_bytes, bloom_match in results:
                        if addr:
                            # Generate WIF and public key from key_bytes
                            key = BitcoinKey(key_bytes)
                            wif = key.get_wif()
                            pubkey = key.get_public_key().hex()
                            # Report result with full key information
                            self.result_queue.put((addr, wif, pubkey))
                except Exception as e:
                    print(f"Error processing GPU results: {e}")
                    import traceback
                    traceback.print_exc()

            except Exception as e:
                print(f"Error in GPU-only mode: {e}")
                import traceback
                traceback.print_exc()

            # Power throttling
            power = self.power_percent
            if power is not None and power < 100:
                duty = max(0.05, min(1.0, power / 100.0))
                work_time = time.time() - loop_start
                sleep_time = work_time * (1.0 / duty - 1.0)
                if sleep_time > 0:
                    self.stop_event.wait(timeout=sleep_time)

        # Clean up temporary bloom filter buffer when loop exits
        if hasattr(self, 'temp_bloom_buffer') and self.temp_bloom_buffer is not None:
            try:
                self.temp_bloom_buffer.release()
            except Exception:
                pass
            self.temp_bloom_buffer = None

        # Clean up prefix buffer
        if hasattr(self, 'gpu_prefix_buffer') and self.gpu_prefix_buffer is not None:
            try:
                self.gpu_prefix_buffer.release()
            except Exception:
                pass
            self.gpu_prefix_buffer = None

    def _search_loop(self):
        """Main search loop using GPU for key generation and multiprocessing for CPU processing"""
        num_workers = self.cpu_cores
        if self.pool is None:
            self.pool = multiprocessing.Pool(processes=num_workers)

        while not self.stop_event.is_set():
            # Check if paused
            if self.pause_event.is_set():
                time.sleep(0.1)
                continue

            loop_start = time.time()

            # Generate batch of keys on GPU
            gpu_keys_data = self._generate_keys_on_gpu(self.batch_size)

            if gpu_keys_data is None:
                # GPU failed for this iteration; back off a bit
                self.stop_event.wait(timeout=0.1)
                continue

            # Split data into chunks for workers
            # Convert 8 uint32s to 32 bytes
            all_key_bytes = [b''.join(struct.pack('<I', word) for word in key_data) for key_data in gpu_keys_data]
            
            chunk_size = max(1, len(all_key_bytes) // num_workers)
            chunks = [all_key_bytes[i:i + chunk_size] for i in range(0, len(all_key_bytes), chunk_size)]
            
            worker_args = [(chunk, self.addr_type, self.prefix) for chunk in chunks]
            
            # Process chunks in parallel
            try:
                batch_results = self.pool.map(_process_keys_batch, worker_args)

                for results in batch_results:
                    for res in results:
                        self.result_queue.put(res)

                # Update stats
                with self.stats_lock:
                    self.stats_counter += self.batch_size

            except Exception as e:
                print(f"Error processing keys in parallel: {e}")

            # Check stop event before power throttling
            if self.stop_event.is_set():
                break

            power = self.power_percent
            if power is not None and power < 100:
                duty = max(0.05, min(1.0, power / 100.0))
                work_time = time.time() - loop_start
                sleep_time = work_time * (1.0 / duty - 1.0)
                if sleep_time > 0:
                    self.stop_event.wait(timeout=sleep_time)

    def start(self):
        if self.running:
            return

        # Clean up any previous resources
        self.stop()
        self.stop_event.clear()
        self.pause_event.clear()
        self.paused = False
        self.stats_counter = 0
        self.rng_seed = int(time.time())

        # Clear result queue
        try:
            while not self.result_queue.empty():
                self.result_queue.get_nowait()
        except Exception:
            pass

        # Try to initialize OpenCL
        self.gpu_available = self.init_cl()

        if not self.gpu_available:
            raise RuntimeError("GPU acceleration not available. Please ensure:\n"
                           "- pyopencl is installed\n"
                           "- OpenCL drivers are installed\n"
                           "- A compatible GPU is available")

        # Set up GPU balance checking if configured
        if self.balance_checker and self.balance_checker.is_loaded:
            self._setup_gpu_balance_check()

        self.running = True

        # Choose search loop based on mode priority:
        # 1. GPU-only mode: all operations on GPU (if enabled)
        # 2. GPU + balance checking: GPU handles address generation + bloom filter
        # 3. GPU-assisted: GPU generates keys, CPU generates addresses
        if self.gpu_only and self.kernel_full is not None:
            print(
                f"Starting GPU-ONLY mode on {self.device.name if self.device else 'device'} "
                f"(batch size={self.batch_size}, power={self.power_percent}%)"
            )
            print("ALL operations (key gen + address generation + matching) on GPU - ZERO CPU load!")
            self.search_thread = threading.Thread(target=self._search_loop_gpu_only, daemon=True)
        elif self.balance_checker and self.gpu_bloom_filter is not None:
            print(
                f"Starting GPU-accelerated search with balance checking on {self.device.name if self.device else 'device'} "
                f"(batch size={self.batch_size}, power={self.power_percent}%)"
            )
            print(
                "GPU will perform address generation and bloom filter matching."
                " Only addresses passing both checks are verified on CPU."
            )
            self.search_thread = threading.Thread(target=self._search_loop_with_balance_check, daemon=True)
        else:
            print(
                f"Starting GPU-accelerated search on {self.device.name if self.device else 'device'} "
                f"(batch size={self.batch_size}, power={self.power_percent}%, cpu_cores={self.cpu_cores})"
            )
            print(
                "Note: GPU mode uses the GPU for key generation but CPU for address processing."
                f" Using {self.cpu_cores} CPU cores for post-processing."
            )
            self.search_thread = threading.Thread(target=self._search_loop, daemon=True)

        self.search_thread.start()

    def stop(self):
        if not self.running:
            return

        self.stop_event.set()
        self.running = False

        # Terminate the pool if running
        if self.pool:
            try:
                self.pool.terminate()
                self.pool.join()
            except Exception:
                pass
            self.pool = None

        # Wait for search thread to finish
        if self.search_thread and self.search_thread.is_alive():
            try:
                self.search_thread.join(timeout=3.0)
            except Exception:
                pass
            self.search_thread = None

        # Reset pause state
        self.paused = False
        self.pause_event.clear()

        # Clean up GPU resources
        self._cleanup_gpu_buffers()

        # Clear result queue
        try:
            while not self.result_queue.empty():
                self.result_queue.get_nowait()
        except Exception:
            pass

    def _cleanup_gpu_buffers(self):
        """Clean up all GPU buffers"""
        for attr_name in ['gpu_bloom_filter', 'gpu_address_buffer', 'found_count_buffer', 'gpu_prefix_buffer', 'temp_bloom_buffer']:
            if hasattr(self, attr_name) and getattr(self, attr_name) is not None:
                try:
                    getattr(self, attr_name).release()
                except Exception as e:
                    print(f"Error releasing {attr_name}: {e}")
                setattr(self, attr_name, None)

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
        with self.stats_lock:
            count = self.stats_counter
            self.stats_counter = 0
        return count
