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
    def __init__(self, prefix, addr_type='p2pkh', batch_size=4096, power_percent=100, device_selector=None):
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
        self.device = None

        # GPU configuration
        self.batch_size = int(batch_size) if batch_size else 4096
        self.power_percent = 100 if power_percent is None else int(power_percent)
        self.device_selector = device_selector  # (platform_index, device_index) or None for auto
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

    def _search_loop(self):
        """Main search loop using GPU for key generation"""
        while not self.stop_event.is_set():
            loop_start = time.time()

            # Generate batch of keys on GPU
            gpu_keys = self._generate_keys_on_gpu(self.batch_size)

            if gpu_keys is None:
                # GPU failed for this iteration; back off a bit
                self.stop_event.wait(timeout=0.1)
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

        self.stop_event.clear()
        self.stats_counter = 0

        # Try to initialize OpenCL
        self.gpu_available = self.init_cl()

        if not self.gpu_available:
            raise RuntimeError("GPU acceleration not available. Please ensure:\n"
                           "- pyopencl is installed\n"
                           "- OpenCL drivers are installed\n"
                           "- A compatible GPU is available")

        print(
            f"Starting GPU-accelerated search on {self.device.name if self.device else 'device'} "
            f"(batch size={self.batch_size}, power={self.power_percent}%)"
        )

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
