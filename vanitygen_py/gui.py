import sys
import time
import multiprocessing
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QTabWidget,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QComboBox,
    QCheckBox,
    QTextEdit,
    QFileDialog,
    QMessageBox,
    QSpinBox,
    QSlider,
    QProgressBar,
)
from PySide6.QtCore import QThread, Signal, Qt
from .cpu_generator import CPUGenerator
from .gpu_generator import GPUGenerator
from .balance_checker import BalanceChecker

class LoadBitcoinCoreThread(QThread):
    """Background thread for loading Bitcoin Core chainstate data."""
    success = Signal(bool)
    error = Signal(str)
    debug_info = Signal(str)
    
    def __init__(self, balance_checker, path=None):
        super().__init__()
        self.balance_checker = balance_checker
        self.path = path
    
    def run(self):
        try:
            result = self.balance_checker.load_from_bitcoin_core(self.path)
            if self.balance_checker.debug_mode:
                debug_msgs = self.balance_checker.get_debug_messages()
                for msg in debug_msgs:
                    self.debug_info.emit(msg)
            self.success.emit(result)
        except Exception as e:
            self.error.emit(str(e))

class GeneratorThread(QThread):
    stats_updated = Signal(int, float)
    address_found = Signal(str, str, str, float, bool)

    def __init__(
        self,
        prefix,
        addr_type,
        balance_checker,
        auto_resume=False,
        mode='cpu',
        case_insensitive=False,
        batch_size=4096,
        cpu_cores=None,
        gpu_power_percent=100,
        gpu_device_selector=None,
        gpu_only=False,
    ):
        super().__init__()
        self.prefix = prefix
        self.addr_type = addr_type
        self.balance_checker = balance_checker
        self.auto_resume = auto_resume
        self.mode = mode
        self.case_insensitive = case_insensitive

        self.batch_size = batch_size
        self.cpu_cores = cpu_cores
        self.gpu_power_percent = gpu_power_percent
        self.gpu_device_selector = gpu_device_selector
        self.gpu_only = gpu_only

        self.generator = None
        self.running = True

    def run(self):
        if self.mode == 'gpu':
            self.generator = GPUGenerator(
                self.prefix,
                self.addr_type,
                batch_size=self.batch_size,
                power_percent=self.gpu_power_percent,
                device_selector=self.gpu_device_selector,
                cpu_cores=self.cpu_cores,
                balance_checker=self.balance_checker,
                gpu_only=self.gpu_only,
            )
        else:
            self.generator = CPUGenerator(
                self.prefix,
                self.addr_type,
                cores=self.cpu_cores,
                case_insensitive=self.case_insensitive,
            )
        
        try:
            self.generator.start()
        except RuntimeError as e:
            # GPU not available or other startup error
            print(f"Error starting generator: {e}")
            return
            
        start_time = time.time()
        total_keys = 0
        
        while self.running:
            time.sleep(1)
            new_keys = self.generator.get_stats()
            total_keys += new_keys
            elapsed = time.time() - start_time
            speed = total_keys / elapsed if elapsed > 0 else 0
            self.stats_updated.emit(total_keys, speed)

            # Check results
            try:
                while not self.generator.result_queue.empty():
                    result = self.generator.result_queue.get_nowait()
                    # Handle both 3-tuple and 4-tuple results for backward compatibility
                    if len(result) == 3:
                        addr, wif, pubkey = result
                    elif len(result) == 4:
                        addr, wif, pubkey, _ = result  # Ignore balance if already computed
                    else:
                        print(f"Unexpected result format: {result}")
                        continue

                    # Check balance
                    balance, is_in_funded_list = self.balance_checker.check_balance_and_membership(addr)
                    self.address_found.emit(addr, wif, pubkey, balance, is_in_funded_list)
                    if balance > 0 and not self.auto_resume:
                        # Pause if funded address found (as per requirements)
                        self.running = False
                        self.generator.stop()
                        break
            except Exception as e:
                print(f"Error processing results: {e}")
                import traceback
                traceback.print_exc()

    def stop(self):
        self.running = False
        if self.generator:
            self.generator.stop()

class VanityGenGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Bitcoin Vanity Address Generator")
        self.setMinimumSize(600, 400)
        
        self.balance_checker = BalanceChecker()
        self.gen_thread = None
        self.load_core_thread = None
        
        self.init_ui()

    def init_ui(self):
        tabs = QTabWidget()
        self.setCentralWidget(tabs)
        
        # Settings Tab
        settings_tab = QWidget()
        settings_layout = QVBoxLayout()
        
        # Search all address types checkbox
        self.search_all_types_check = QCheckBox("Search All Bitcoin Address Types")
        self.search_all_types_check.clicked.connect(self.on_search_all_types_changed)
        settings_layout.addWidget(self.search_all_types_check)
        
        prefix_layout = QHBoxLayout()
        prefix_layout.addWidget(QLabel("Prefix:"))
        self.prefix_edit = QLineEdit("1")
        prefix_layout.addWidget(self.prefix_edit)
        self.case_insensitive_check = QCheckBox("Case Insensitive")
        prefix_layout.addWidget(self.case_insensitive_check)
        settings_layout.addLayout(prefix_layout)
        
        type_layout = QHBoxLayout()
        type_layout.addWidget(QLabel("Address Type:"))
        self.type_combo = QComboBox()
        self.type_combo.addItems(["P2PKH (Legacy)", "P2WPKH (SegWit)", "P2SH-P2WPKH (Nested SegWit)"])
        type_layout.addWidget(self.type_combo)
        settings_layout.addLayout(type_layout)
        
        # Auto-save checkbox for funded addresses
        self.auto_save_check = QCheckBox("Auto-Save Private Keys for Funded Addresses")
        settings_layout.addWidget(self.auto_save_check)
        
        gen_mode_layout = QHBoxLayout()
        gen_mode_layout.addWidget(QLabel("Generation Mode:"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["CPU", "GPU (OpenCL)"])
        self.mode_combo.currentIndexChanged.connect(self.on_mode_changed)
        gen_mode_layout.addWidget(self.mode_combo)
        settings_layout.addLayout(gen_mode_layout)

        # CPU Settings (visible in CPU mode)
        self.cpu_settings_widget = QWidget()
        cpu_settings_layout = QHBoxLayout()
        cpu_settings_layout.addWidget(QLabel("CPU Cores:"))
        self.cpu_cores_spin = QSpinBox()
        max_cores = multiprocessing.cpu_count()
        self.cpu_cores_spin.setRange(1, max_cores)
        self.cpu_cores_spin.setValue(max_cores)
        cpu_settings_layout.addWidget(self.cpu_cores_spin)
        cpu_settings_layout.addWidget(QLabel(f"(1-{max_cores})"))
        self.cpu_settings_widget.setLayout(cpu_settings_layout)
        settings_layout.addWidget(self.cpu_settings_widget)

        # GPU Settings (initially hidden)
        self.gpu_settings_widget = QWidget()
        gpu_settings_layout = QVBoxLayout()
        
        # Batch size setting
        batch_layout = QHBoxLayout()
        batch_layout.addWidget(QLabel("GPU Batch Size:"))
        self.batch_size_combo = QComboBox()
        self.batch_size_combo.addItems(["1024", "2048", "4096", "8192", "16384", "32768", "65536"])
        self.batch_size_combo.setCurrentIndex(2)  # Default to 4096
        batch_layout.addWidget(self.batch_size_combo)
        batch_layout.addWidget(QLabel("(Higher = faster but more memory)"))
        gpu_settings_layout.addLayout(batch_layout)

        # Power limit
        power_layout = QHBoxLayout()
        power_layout.addWidget(QLabel("GPU Power:"))
        self.gpu_power_slider = QSlider(Qt.Horizontal)
        self.gpu_power_slider.setRange(10, 100)
        self.gpu_power_slider.setSingleStep(10)
        self.gpu_power_slider.setPageStep(10)
        self.gpu_power_slider.setValue(100)
        self.gpu_power_value_label = QLabel("100%")
        self.gpu_power_slider.valueChanged.connect(lambda v: self.gpu_power_value_label.setText(f"{v}%"))
        power_layout.addWidget(self.gpu_power_slider)
        power_layout.addWidget(self.gpu_power_value_label)
        power_layout.addWidget(QLabel("(Lower = less GPU usage)"))
        gpu_settings_layout.addLayout(power_layout)

        # Device selector
        device_layout = QHBoxLayout()
        device_layout.addWidget(QLabel("GPU Device:"))
        self.gpu_device_combo = QComboBox()
        device_layout.addWidget(self.gpu_device_combo)
        gpu_settings_layout.addLayout(device_layout)

        # GPU Only mode checkbox
        self.gpu_only_check = QCheckBox("GPU Only Mode (ALL operations on GPU)")
        self.gpu_only_check.setToolTip("When enabled, ALL operations (key generation, address generation, matching) happen on GPU.\nThis eliminates CPU load entirely but may be slightly slower than GPU+CPU combined.")
        gpu_settings_layout.addWidget(self.gpu_only_check)

        self.gpu_settings_widget.setLayout(gpu_settings_layout)
        self.gpu_settings_widget.setVisible(False)  # Hidden by default
        settings_layout.addWidget(self.gpu_settings_widget)

        self.gpu_device_options = []
        self.populate_gpu_devices()
        
        self.balance_check = QCheckBox("Enable Balance Checking")
        settings_layout.addWidget(self.balance_check)
        
        self.auto_resume = QCheckBox("Auto-Resume after finding funded address")
        settings_layout.addWidget(self.auto_resume)
        
        self.show_only_funded_check = QCheckBox("Filter: Only show matches with positive balance")
        self.show_only_funded_check.setToolTip("Speeds up GUI by not displaying every prefix match, only those with funds.")
        settings_layout.addWidget(self.show_only_funded_check)

        self.load_balance_btn = QPushButton("Load Funded Addresses File")
        self.load_balance_btn.clicked.connect(self.load_balance_file)
        settings_layout.addWidget(self.load_balance_btn)
        
        self.load_core_btn = QPushButton("Load from Bitcoin Core Data")
        self.load_core_btn.clicked.connect(self.load_bitcoin_core)
        settings_layout.addWidget(self.load_core_btn)

        settings_layout.addWidget(QLabel("Bitcoin Core Path:"))
        self.core_path_edit = QLineEdit()
        self.core_path_edit.setPlaceholderText("Leave empty to auto-detect")
        settings_layout.addWidget(self.core_path_edit)

        self.debug_check = QCheckBox("Enable Debug Logging")
        self.debug_check.clicked.connect(self.toggle_debug)
        settings_layout.addWidget(self.debug_check)

        self.balance_status_label = QLabel("Balance checking not active")
        # Address type tally labels (will be updated during generation)
        self.tally_widget = QWidget()
        tally_layout = QHBoxLayout()
        
        self.p2pkh_count_label = QLabel("P2PKH: 0")
        tally_layout.addWidget(self.p2pkh_count_label)
        
        self.p2wpkh_count_label = QLabel("P2WPKH: 0")
        tally_layout.addWidget(self.p2wpkh_count_label)
        
        self.p2sh_count_label = QLabel("P2SH: 0")
        tally_layout.addWidget(self.p2sh_count_label)
        
        self.tally_widget.setLayout(tally_layout)
        settings_layout.addWidget(self.tally_widget)
        
        self.balance_status_label = QLabel("Balance checking not active")
        settings_layout.addWidget(self.balance_status_label)

        # Control buttons layout
        control_layout = QHBoxLayout()

        self.start_btn = QPushButton("Start Generation")
        self.start_btn.clicked.connect(self.toggle_generation)
        control_layout.addWidget(self.start_btn)

        self.pause_btn = QPushButton("Pause")
        self.pause_btn.clicked.connect(self.pause_generation)
        self.pause_btn.setEnabled(False)
        control_layout.addWidget(self.pause_btn)

        self.resume_btn = QPushButton("Resume")
        self.resume_btn.clicked.connect(self.resume_generation)
        self.resume_btn.setEnabled(False)
        control_layout.addWidget(self.resume_btn)

        settings_layout.addLayout(control_layout)
        
        settings_tab.setLayout(settings_layout)
        tabs.addTab(settings_tab, "Settings")
        
        # Initialize counters
        self.address_counters = {'p2pkh': 0, 'p2wpkh': 0, 'p2sh-p2wpkh': 0}
        self.update_address_counters()
        
        # Progress Tab
        progress_tab = QWidget()
        progress_layout = QVBoxLayout()
        
        # Status indicators container
        status_container = QWidget()
        status_layout = QHBoxLayout()
        
        # CPU Status
        cpu_status_layout = QVBoxLayout()
        cpu_status_layout.addWidget(QLabel("CPU Status:"))
        self.cpu_status_label = QLabel("Idle")
        self.cpu_status_label.setStyleSheet("color: gray; font-weight: bold;")
        cpu_status_layout.addWidget(self.cpu_status_label)
        self.cpu_activity_bar = QProgressBar()
        self.cpu_activity_bar.setRange(0, 100)
        self.cpu_activity_bar.setValue(0)
        self.cpu_activity_bar.setFormat("%p%")
        cpu_status_layout.addWidget(self.cpu_activity_bar)
        status_layout.addLayout(cpu_status_layout)
        
        # GPU Status  
        gpu_status_layout = QVBoxLayout()
        gpu_status_layout.addWidget(QLabel("GPU Status:"))
        self.gpu_status_label = QLabel("Idle")
        self.gpu_status_label.setStyleSheet("color: gray; font-weight: bold;")
        gpu_status_layout.addWidget(self.gpu_status_label)
        self.gpu_activity_bar = QProgressBar()
        self.gpu_activity_bar.setRange(0, 100)
        self.gpu_activity_bar.setValue(0)
        self.gpu_activity_bar.setFormat("%p%")
        gpu_status_layout.addWidget(self.gpu_activity_bar)
        status_layout.addLayout(gpu_status_layout)
        
        status_container.setLayout(status_layout)
        progress_layout.addWidget(status_container)
        
        self.stats_label = QLabel("Keys Searched: 0 | Speed: 0 keys/s")
        progress_layout.addWidget(self.stats_label)
        
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        progress_layout.addWidget(self.log_output)
        
        progress_tab.setLayout(progress_layout)
        tabs.addTab(progress_tab, "Progress")
        
        # Results Tab
        results_tab = QWidget()
        results_layout = QVBoxLayout()
        
        self.results_list = QTextEdit()
        self.results_list.setReadOnly(True)
        results_layout.addWidget(self.results_list)
        
        btn_layout = QHBoxLayout()
        self.copy_btn = QPushButton("Copy Results")
        self.copy_btn.clicked.connect(self.copy_results)
        btn_layout.addWidget(self.copy_btn)
        
        self.clear_btn = QPushButton("Clear Results")
        self.clear_btn.clicked.connect(self.results_list.clear)
        btn_layout.addWidget(self.clear_btn)
        
        results_layout.addLayout(btn_layout)
        
        results_tab.setLayout(results_layout)
        tabs.addTab(results_tab, "Results")

    def copy_results(self):
        clipboard = QApplication.clipboard()
        clipboard.setText(self.results_list.toPlainText())

    def on_search_all_types_changed(self):
        """Enable/disable prefix box when searching all address types."""
        search_all = self.search_all_types_check.isChecked()
        self.prefix_edit.setEnabled(not search_all)
        if search_all:
            self.prefix_edit.setPlaceholderText("Searching all types (prefix not used)")
            if not self.show_only_funded_check.isChecked():
                self.show_only_funded_check.setChecked(True)
                self.log_output.append("Tip: Filter enabled automatically for 'Search All Types' mode.")
        else:
            self.prefix_edit.setPlaceholderText("")

    def update_address_counters(self):
        """Update the address type counters in the GUI."""
        self.p2pkh_count_label.setText(f"P2PKH: {self.address_counters['p2pkh']}")
        self.p2wpkh_count_label.setText(f"P2WPKH: {self.address_counters['p2wpkh']}")
        self.p2sh_count_label.setText(f"P2SH: {self.address_counters['p2sh-p2wpkh']}")

    def save_funded_address(self, addr, wif, pubkey, balance, addr_type=None):
        """Save private key info for funded addresses."""
        try:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"funded_address_{addr[:8]}_{timestamp}.txt"
            
            with open(filename, 'w') as f:
                f.write(f"Congratulations! Funded Address Found!\n")
                f.write(f"{'='*50}\n\n")
                f.write(f"Address Type: {addr_type or 'P2PKH'}\n")
                f.write(f"Address: {addr}\n")
                f.write(f"Balance: {balance:,} satoshis\n")
                f.write(f"Balance (BTC): {balance / 100_000_000:.8f} BTC\n\n")
                f.write(f"Private Key (WIF): {wif}\n")
                f.write(f"Public Key: {pubkey}\n")
                f.write(f"{'='*50}\n\n")
                f.write(f"Generated at: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"WARNING: Keep this file secure! Whoever has the private key controls the funds.\n")
            
            return filename
        except Exception as e:
            print(f"Error saving funded address: {e}")
            return None

    def show_congratulations(self, addr, wif, pubkey, balance, is_in_funded_list):
        """Show congratulations dialog when funded address found."""
        title = "🏆 Congratulations! Funded Address Found! 🏆"
        message = f"""
<b><font color='green' size='+2'>CONGRATULATIONS!</font></b><br><br>

You found a funded Bitcoin address with balance!<br><br>

<b>Address:</b> {addr}<br>
<b>Balance:</b> {balance:,} satoshis ({balance / 100_000_000:.8f} BTC)<br>
<b>In Funded List:</b> {'<b><font color="green">YES</font></b>' if is_in_funded_list else 'NO'}<br><br>

<b>Private Key:</b><br>
<font color='red' size='-1'>{wif}</font><br><br>

<b>Public Key:</b><br>
<font size='-2'>{pubkey}</font><br><br>

<font color='red'><b>⚠ SECURITY WARNING:</b></font><br>
The private key is displayed above. <b>Secure it immediately!</b><br>
Whoever has this key controls these funds.<br><br>

<b>Next Steps:</b>
1. Import the private key into a Bitcoin wallet
2. Transfer the funds to a new secure address
3. Never share your private key with anyone
"""
        QMessageBox.information(self, title, message)

    def load_balance_file(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Open Funded Addresses File", "", "Text Files (*.txt);;All Files (*)")
        if filename:
            if self.balance_checker.load_addresses(filename):
                self.balance_status_label.setText(self.balance_checker.get_status())
                self.balance_check.setChecked(True)
            else:
                QMessageBox.critical(self, "Error", "Failed to load addresses file")

    def toggle_debug(self):
        """Toggle debug mode for the balance checker."""
        self.balance_checker.debug_mode = self.debug_check.isChecked()
        if self.balance_checker.debug_mode:
            self.log_output.append("Debug logging enabled")
        else:
            self.log_output.append("Debug logging disabled")

    def populate_gpu_devices(self):
        self.gpu_device_combo.clear()
        self.gpu_device_options = [None]
        self.gpu_device_combo.addItem("Auto-detect")

        devices = GPUGenerator.list_available_devices()
        devices = sorted(devices, key=lambda d: 0 if d.get("device_type") == "GPU" else 1)
        for dev in devices:
            label = f"{dev['device_name']} ({dev['device_type']})"
            platform_name = dev.get("platform_name")
            if platform_name:
                label += f" - {platform_name}"

            self.gpu_device_combo.addItem(label)
            self.gpu_device_options.append((dev["platform_index"], dev["device_index"]))

    def on_mode_changed(self, index):
        """Show/hide CPU/GPU settings when mode changes."""
        gpu_mode = index == 1
        self.gpu_settings_widget.setVisible(gpu_mode)
        self.cpu_settings_widget.setVisible(not gpu_mode)

        if gpu_mode:
            self.populate_gpu_devices()
            self.log_output.append("GPU mode selected - adjust batch size and power for optimal performance")
            self.log_output.append("Tip: Larger batch sizes are faster but use more GPU memory")

    def load_bitcoin_core(self):
        # Disable button and show loading state
        self.load_core_btn.setEnabled(False)
        self.load_core_btn.setText("Loading...")
        self.balance_status_label.setText("Loading Bitcoin Core data (this may take a while)...")
        
        # Get custom path if provided
        custom_path = self.core_path_edit.text().strip()
        chosen_path = custom_path if custom_path else None
        
        # Start background thread to load data
        self.load_core_thread = LoadBitcoinCoreThread(self.balance_checker, chosen_path)
        self.load_core_thread.success.connect(self.on_load_core_success)
        self.load_core_thread.error.connect(self.on_load_core_error)
        self.load_core_thread.debug_info.connect(self.on_load_core_debug)
        self.load_core_thread.finished.connect(self.on_load_core_finished)
        self.load_core_thread.start()
    
    def on_load_core_success(self, result):
        if result:
            self.balance_status_label.setText(self.balance_checker.get_status())
            self.balance_check.setChecked(True)
            QMessageBox.information(self, "Success", "Successfully connected to Bitcoin Core data")
        else:
            path = self.balance_checker.get_bitcoin_core_db_path()
            QMessageBox.warning(self, "Failed", 
                f"Could not find or load Bitcoin Core data at {path}.\n\n"
                "Common issues:\n"
                "- Bitcoin Core is running (chainstate is locked)\n"
                "- Path doesn't exist or is incorrect\n"
                "- plyvel library not installed\n\n"
                "Try closing Bitcoin Core and loading again, or use a file-based address list instead.")
    
    def on_load_core_error(self, error_message):
        QMessageBox.critical(self, "Error", f"Failed to load Bitcoin Core data: {error_message}")
        self.log_output.append(f"Error loading Bitcoin Core data: {error_message}")
        
    def on_load_core_debug(self, message):
        if self.debug_check.isChecked():
            self.log_output.append(f"[DEBUG] {message}")
    
    def on_load_core_finished(self):
        self.load_core_btn.setEnabled(True)
        self.load_core_btn.setText("Load from Bitcoin Core Data")

    def toggle_generation(self):
        if self.gen_thread and self.gen_thread.isRunning():
            self.stop_generation()
        else:
            self.start_generation()

    def start_generation(self):
        # Reset address counters when starting new generation
        self.address_counters = {'p2pkh': 0, 'p2wpkh': 0, 'p2sh-p2wpkh': 0}
        self.update_address_counters()
        
        prefix = self.prefix_edit.text() if not self.search_all_types_check.isChecked() else ""
        addr_type_idx = self.type_combo.currentIndex()
        addr_types = ['p2pkh', 'p2wpkh', 'p2sh-p2wpkh']
        addr_type = addr_types[addr_type_idx]
        
        mode = 'gpu' if self.mode_combo.currentIndex() == 1 else 'cpu'
        case_insensitive = self.case_insensitive_check.isChecked()

        cpu_cores = None
        gpu_power_percent = 100
        gpu_device_selector = None
        batch_size = 4096
        gpu_only = False

        if mode == 'gpu':
            batch_size = int(self.batch_size_combo.currentText())
            gpu_power_percent = int(self.gpu_power_slider.value())
            gpu_only = self.gpu_only_check.isChecked()
            if self.gpu_device_options and self.gpu_device_combo.currentIndex() < len(self.gpu_device_options):
                gpu_device_selector = self.gpu_device_options[self.gpu_device_combo.currentIndex()]

            mode_str = "GPU Only" if gpu_only else "GPU"
            self.log_output.append(
                f"Using {mode_str}: batch size={batch_size}, power={gpu_power_percent}%, device={self.gpu_device_combo.currentText()}"
            )
            if gpu_only:
                self.log_output.append("WARNING: GPU Only mode performs ALL operations on GPU (no CPU address generation)")
        else:
            cpu_cores = int(self.cpu_cores_spin.value())
            self.log_output.append(f"Using CPU cores: {cpu_cores}")

        self.gen_thread = GeneratorThread(
            prefix,
            addr_type,
            self.balance_checker,
            auto_resume=self.auto_resume.isChecked(),
            mode=mode,
            case_insensitive=case_insensitive,
            batch_size=batch_size,
            cpu_cores=cpu_cores,
            gpu_power_percent=gpu_power_percent,
            gpu_device_selector=gpu_device_selector,
            gpu_only=gpu_only,
        )
        self.gen_thread.stats_updated.connect(self.update_stats)
        self.gen_thread.address_found.connect(self.on_address_found)
        self.gen_thread.finished.connect(self.on_gen_finished)
        
        self.gen_thread.start()
        self.start_btn.setText("Stop Generation")
        self.pause_btn.setEnabled(True)
        self.resume_btn.setEnabled(False)

        if self.search_all_types_check.isChecked():
            self.log_output.append("Started searching for ALL Bitcoin address types...")
        else:
            self.log_output.append(f"Started searching for prefix '{prefix}' ({addr_type})...")

    def stop_generation(self):
        if self.gen_thread:
            self.gen_thread.stop()
            self.start_btn.setText("Start Generation")
            self.pause_btn.setEnabled(False)
            self.resume_btn.setEnabled(False)

    def pause_generation(self):
        """Pause the current generation"""
        if self.gen_thread and self.gen_thread.isRunning():
            self.gen_thread.generator.pause()
            self.pause_btn.setEnabled(False)
            self.resume_btn.setEnabled(True)
            self.log_output.append("Generation paused")
            self.update_status_labels()

    def resume_generation(self):
        """Resume the current generation"""
        if self.gen_thread and self.gen_thread.isRunning():
            self.gen_thread.generator.resume()
            self.pause_btn.setEnabled(True)
            self.resume_btn.setEnabled(False)
            self.log_output.append("Generation resumed")
            self.update_status_labels()

    def update_status_labels(self):
        """Update status labels based on current state"""
        if not self.gen_thread or not self.gen_thread.isRunning():
            self.cpu_status_label.setText("Idle")
            self.cpu_status_label.setStyleSheet("color: gray; font-weight: bold;")
            self.gpu_status_label.setText("Idle")
            self.gpu_status_label.setStyleSheet("color: gray; font-weight: bold;")
            return

        if self.gen_thread.generator.is_paused():
            if self.gen_thread.mode == 'cpu':
                self.cpu_status_label.setText("Paused")
                self.cpu_status_label.setStyleSheet("color: orange; font-weight: bold;")
            else:
                self.gpu_status_label.setText("Paused")
                self.gpu_status_label.setStyleSheet("color: orange; font-weight: bold;")
        else:
            if self.gen_thread.mode == 'cpu':
                self.cpu_status_label.setText("Active")
                self.cpu_status_label.setStyleSheet("color: green; font-weight: bold;")
            else:
                self.gpu_status_label.setText("Active")
                self.gpu_status_label.setStyleSheet("color: green; font-weight: bold;")

    def update_stats(self, total_keys, speed):
        self.stats_label.setText(f"Keys Searched: {total_keys} | Speed: {speed:.2f} keys/s")
        
        # Update CPU/GPU activity bars based on current mode
        if self.gen_thread and self.gen_thread.isRunning():
            if self.gen_thread.mode == 'cpu':
                # Simulate CPU activity based on speed
                cpu_activity = min(95, int(speed / 1000000 * 100))  # Scale to millions of keys/s
                self.cpu_activity_bar.setValue(cpu_activity)
                self.cpu_status_label.setText(f"Active ({self.gen_thread.cpu_cores or multiprocessing.cpu_count()} cores)")
                self.cpu_status_label.setStyleSheet("color: green; font-weight: bold;")
                
                # GPU idle
                self.gpu_activity_bar.setValue(0)
                self.gpu_status_label.setText("Idle")
                self.gpu_status_label.setStyleSheet("color: gray; font-weight: bold;")
            else:
                # GPU active
                gpu_activity = min(95, int(self.gen_thread.gpu_power_percent * 0.9))  # Use power setting as activity
                self.gpu_activity_bar.setValue(gpu_activity)
                self.gpu_status_label.setText(f"Active ({self.gen_thread.gpu_power_percent}%)")
                self.gpu_status_label.setStyleSheet("color: green; font-weight: bold;")
                
                # CPU idle (minimal activity for thread management)
                self.cpu_activity_bar.setValue(5)
                self.cpu_status_label.setText("Idle (Management)")
                self.cpu_status_label.setStyleSheet("color: gray; font-weight: bold;")
        else:
            # Generation stopped - both idle
            self.cpu_activity_bar.setValue(0)
            self.cpu_status_label.setText("Idle")
            self.cpu_status_label.setStyleSheet("color: gray; font-weight: bold;")
            
            self.gpu_activity_bar.setValue(0)
            self.gpu_status_label.setText("Idle")
            self.gpu_status_label.setStyleSheet("color: gray; font-weight: bold;")

    def on_address_found(self, addr, wif, pubkey, balance, is_in_funded_list):
        addr_type = None
        if self.gen_thread and self.gen_thread.addr_type:
            addr_type = self.gen_thread.addr_type
            # Update address type counter
            self.address_counters[addr_type] = self.address_counters.get(addr_type, 0) + 1
            self.update_address_counters()
        
        # Filter results if requested
        if self.show_only_funded_check.isChecked() and balance <= 0:
            return

        membership_status = "✓ YES" if is_in_funded_list else "✗ NO"
        type_display = addr_type if addr_type else 'N/A'
        result_str = f"Address: {addr}\nPrivate Key: {wif}\nPublic Key: {pubkey}\nBalance: {balance}\nIn Funded List: {membership_status}\nAddress Type: {type_display}\n" + "-"*40 + "\n"
        self.results_list.append(result_str)
        self.log_output.append(f"Match found: {addr} (Type: {type_display})")
        
        if balance > 0:
            self.log_output.append("🏆 !!! FUNDED ADDRESS FOUND !!! 🏆")
            
            # Auto-save private key if enabled
            saved_file = None
            if self.auto_save_check.isChecked():
                saved_file = self.save_funded_address(addr, wif, pubkey, balance, addr_type)
                if saved_file:
                    self.log_output.append(f"Private key saved to: {saved_file}")
            
            if not self.auto_resume.isChecked():
                # Show congratulations dialog
                self.show_congratulations(addr, wif, pubkey, balance, is_in_funded_list)
                if saved_file:
                    QMessageBox.information(self, "File Saved", f"Private key information saved to:\n{saved_file}\n\nKeep this file secure!")
            else:
                self.log_output.append("Funded address found, auto-resume is ON - continuing generation...")
                print("Funded address found, auto-resume is ON")

    def on_gen_finished(self):
        self.start_btn.setText("Start Generation")
        self.pause_btn.setEnabled(False)
        self.resume_btn.setEnabled(False)
        self.cpu_activity_bar.setValue(0)
        self.gpu_activity_bar.setValue(0)
        self.cpu_status_label.setText("Idle")
        self.cpu_status_label.setStyleSheet("color: gray; font-weight: bold;")
        self.gpu_status_label.setText("Idle")
        self.gpu_status_label.setStyleSheet("color: gray; font-weight: bold;")
        self.log_output.append("Generation stopped.")

def main():
    app = QApplication(sys.argv)
    window = VanityGenGUI()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
