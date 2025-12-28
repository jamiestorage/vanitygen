import threading
import time
import queue
import os
import struct
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

class GPUGenerator:
    def __init__(self, prefix, addr_type='p2pkh'):
        self.prefix = prefix
        self.addr_type = addr_type
        self.result_queue = queue.Queue()
        self.running = False
        self.search_thread = None
        self.stats_counter = 0
        self.stats_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.gpu_available = False

        # OpenCL resources
        self.ctx = None
        self.queue = None
        self.program = None
        self.kernel = None

        # GPU configuration
        self.batch_size = 4096  # Number of keys to generate per batch
        self.rng_seed = int(time.time())

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

            # Use first platform and device
            self.device = platforms[0].get_devices()[0]
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

            print(f"GPU initialized: {self.device.name}")
            return True

        except Exception as e:
            print(f"OpenCL initialization failed: {e}")
            import traceback
            traceback.print_exc()
            return False

    def is_available(self):
        return self.gpu_available

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

    def _search_loop(self):
        """Main search loop using GPU for key generation"""
        while not self.stop_event.is_set():
            # Generate batch of keys on GPU
            gpu_keys = self._generate_keys_on_gpu(self.batch_size)

            if gpu_keys is None:
                # Fall back to CPU if GPU fails
                time.sleep(0.1)
                continue

            # Process keys on CPU (EC operations are complex to do on GPU)
            try:
                keys = self._keys_from_gpu_data(gpu_keys)

                for key in keys:
                    # Generate address
                    if self.addr_type == 'p2pkh':
                        address = key.get_p2pkh_address()
                    elif self.addr_type == 'p2wpkh':
                        address = key.get_p2wpkh_address()
                    elif self.addr_type == 'p2sh-p2wpkh':
                        address = key.get_p2sh_p2wpkh_address()
                    else:
                        address = key.get_p2pkh_address()

                    # Check for prefix match
                    if address.startswith(self.prefix):
                        self.result_queue.put((address, key.get_wif(), key.get_public_key().hex()))

                # Update stats
                with self.stats_lock:
                    self.stats_counter += self.batch_size

            except Exception as e:
                print(f"Error processing keys: {e}")

    def start(self):
        if self.running:
            return

        self.stop_event.clear()
        self.stats_counter = 0

        # Try to initialize OpenCL
        self.gpu_available = self.init_cl()

        if not self.gpu_available:
            raise RuntimeError("GPU acceleration not available. Please ensure:\n"
                           "- pyopencl is installed\n"
                           "- OpenCL drivers are installed\n"
                           "- A compatible GPU is available")

        print(f"Starting GPU-accelerated search with batch size {self.batch_size}")

        self.running = True
        self.search_thread = threading.Thread(target=self._search_loop, daemon=True)
        self.search_thread.start()

    def stop(self):
        if not self.running:
            return

        self.stop_event.set()
        self.running = False

        if self.search_thread and self.search_thread.is_alive():
            self.search_thread.join(timeout=2.0)

    def get_stats(self):
        with self.stats_lock:
            count = self.stats_counter
            self.stats_counter = 0
            return count
