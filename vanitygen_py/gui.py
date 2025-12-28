import sys
import time
from PySide6.QtWidgets import (QApplication, QMainWindow, QTabWidget, QWidget, 
                             QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
                             QPushButton, QComboBox, QCheckBox, QTextEdit, 
                             QProgressBar, QFileDialog, QMessageBox)
from PySide6.QtCore import QThread, Signal, Qt
from .cpu_generator import CPUGenerator
from .gpu_generator import GPUGenerator
from .balance_checker import BalanceChecker

class GeneratorThread(QThread):
    stats_updated = Signal(int, float)
    address_found = Signal(str, str, str, float)
    
    def __init__(self, prefix, addr_type, balance_checker, auto_resume=False, mode='cpu', case_insensitive=False):
        super().__init__()
        self.prefix = prefix
        self.addr_type = addr_type
        self.balance_checker = balance_checker
        self.auto_resume = auto_resume
        self.mode = mode
        self.case_insensitive = case_insensitive
        self.generator = None
        self.running = True

    def run(self):
        if self.mode == 'gpu':
            self.generator = GPUGenerator(self.prefix, self.addr_type)
        else:
            self.generator = CPUGenerator(self.prefix, self.addr_type, case_insensitive=self.case_insensitive)
        
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
            while not self.generator.result_queue.empty():
                addr, wif, pubkey = self.generator.result_queue.get()
                balance = self.balance_checker.check_balance(addr)
                self.address_found.emit(addr, wif, pubkey, balance)
                if balance > 0 and not self.auto_resume:
                    # Pause if funded address found (as per requirements)
                    self.running = False
                    self.generator.stop()
                    break

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
        
        self.init_ui()

    def init_ui(self):
        tabs = QTabWidget()
        self.setCentralWidget(tabs)
        
        # Settings Tab
        settings_tab = QWidget()
        settings_layout = QVBoxLayout()
        
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
        
        gen_mode_layout = QHBoxLayout()
        gen_mode_layout.addWidget(QLabel("Generation Mode:"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["CPU (All Cores)", "GPU (OpenCL)"])
        gen_mode_layout.addWidget(self.mode_combo)
        settings_layout.addLayout(gen_mode_layout)
        
        self.balance_check = QCheckBox("Enable Balance Checking")
        settings_layout.addWidget(self.balance_check)
        
        self.auto_resume = QCheckBox("Auto-Resume after finding funded address")
        settings_layout.addWidget(self.auto_resume)
        
        self.load_balance_btn = QPushButton("Load Funded Addresses File")
        self.load_balance_btn.clicked.connect(self.load_balance_file)
        settings_layout.addWidget(self.load_balance_btn)
        
        self.load_core_btn = QPushButton("Load from Bitcoin Core Data")
        self.load_core_btn.clicked.connect(self.load_bitcoin_core)
        settings_layout.addWidget(self.load_core_btn)

        self.balance_status_label = QLabel("Balance checking not active")
        settings_layout.addWidget(self.balance_status_label)
        
        self.start_btn = QPushButton("Start Generation")
        self.start_btn.clicked.connect(self.toggle_generation)
        settings_layout.addWidget(self.start_btn)
        
        settings_tab.setLayout(settings_layout)
        tabs.addTab(settings_tab, "Settings")
        
        # Progress Tab
        progress_tab = QWidget()
        progress_layout = QVBoxLayout()
        
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

    def load_balance_file(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Open Funded Addresses File", "", "Text Files (*.txt);;All Files (*)")
        if filename:
            if self.balance_checker.load_addresses(filename):
                self.balance_status_label.setText(self.balance_checker.get_status())
                self.balance_check.setChecked(True)
            else:
                QMessageBox.critical(self, "Error", "Failed to load addresses file")

    def load_bitcoin_core(self):
        if self.balance_checker.load_from_bitcoin_core():
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

    def toggle_generation(self):
        if self.gen_thread and self.gen_thread.isRunning():
            self.stop_generation()
        else:
            self.start_generation()

    def start_generation(self):
        prefix = self.prefix_edit.text()
        addr_type_idx = self.type_combo.currentIndex()
        addr_types = ['p2pkh', 'p2wpkh', 'p2sh-p2wpkh']
        addr_type = addr_types[addr_type_idx]
        
        mode = 'gpu' if self.mode_combo.currentIndex() == 1 else 'cpu'
        case_insensitive = self.case_insensitive_check.isChecked()
        
        self.gen_thread = GeneratorThread(prefix, addr_type, self.balance_checker, 
                                        self.auto_resume.isChecked(), mode, case_insensitive)
        self.gen_thread.stats_updated.connect(self.update_stats)
        self.gen_thread.address_found.connect(self.on_address_found)
        self.gen_thread.finished.connect(self.on_gen_finished)
        
        self.gen_thread.start()
        self.start_btn.setText("Stop Generation")
        self.log_output.append(f"Started searching for prefix '{prefix}' ({addr_type})...")

    def stop_generation(self):
        if self.gen_thread:
            self.gen_thread.stop()
            self.start_btn.setText("Start Generation")

    def update_stats(self, total_keys, speed):
        self.stats_label.setText(f"Keys Searched: {total_keys} | Speed: {speed:.2f} keys/s")

    def on_address_found(self, addr, wif, pubkey, balance):
        result_str = f"Address: {addr}\nPrivate Key: {wif}\nPublic Key: {pubkey}\nBalance: {balance}\n" + "-"*40 + "\n"
        self.results_list.append(result_str)
        self.log_output.append(f"Match found: {addr}")
        
        if balance > 0:
            self.log_output.append("!!! FUNDED ADDRESS FOUND !!!")
            if not self.auto_resume.isChecked():
                # The thread already stopped itself if balance > 0
                QMessageBox.information(self, "Funded Address Found!", f"Found a funded address: {addr}\nBalance: {balance}")
            else:
                # If auto-resume is checked, we should restart if it stopped, 
                # but wait, how about we just don't stop it in the first place?
                print("Funded address found, auto-resume is ON")

    def on_gen_finished(self):
        self.start_btn.setText("Start Generation")
        self.log_output.append("Generation stopped.")

def main():
    app = QApplication(sys.argv)
    window = VanityGenGUI()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
