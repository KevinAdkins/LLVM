#!/usr/bin/env python3
"""
LLVM IR Optimization Visualization Tool - PyQt5 Version
Integrates profiling, flamegraph generation, and IR visualization
"""

import os
import sys
import subprocess
import webbrowser
import json
import re
import threading
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFileDialog, QComboBox, QRadioButton,
    QButtonGroup, QTextEdit, QMessageBox, QProgressDialog,
    QTabWidget, QListWidget, QLineEdit, QSplitter,
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QGroupBox,
    QInputDialog
)
from PyQt5.QtCore import Qt, QObject, pyqtSignal, QThread, pyqtSlot, QProcess
from PyQt5.QtGui import QFont, QPixmap, QImage


class ClickHandler(SimpleHTTPRequestHandler):
    """HTTP handler that captures click events from flamegraph"""
    click_callback = None
    
    def do_GET(self):
        """Serve files"""
        return super().do_GET()
    
    def do_POST(self):
        """Handle block click events"""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length).decode('utf-8')
            click_info = json.loads(post_data)
            
            if ClickHandler.click_callback:
                ClickHandler.click_callback(click_info)
            
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(b'OK')
        except Exception as e:
            print(f"Error handling POST: {e}")
            self.send_response(500)
            self.end_headers()
    
    def do_OPTIONS(self):
        """Handle CORS preflight"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
    
    def log_message(self, format, *args):
        """Suppress HTTP server logs"""
        pass


class FlameGraphServer(QObject):
    """HTTP server for flamegraph"""
    blockClicked = pyqtSignal(str, str, float)
    
    def __init__(self, port=8765):
        super().__init__()
        self.port = port
        self.httpd = None
        self.server_thread = None
        
    def start(self, flamegraph_path):
        """Start HTTP server"""
        if self.httpd:
            return True
            
        flamegraph_dir = Path(flamegraph_path).parent
        
        class CustomHandler(ClickHandler):
            def translate_path(self, path):
                path = path.split('?', 1)[0].split('#', 1)[0]
                if path == '/' or path == '':
                    return str(flamegraph_dir / Path(flamegraph_path).name)
                return str(flamegraph_dir / Path(path).name)
        
        ClickHandler.click_callback = self._handle_click
        
        try:
            self.httpd = HTTPServer(('localhost', self.port), CustomHandler)
            self.server_thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
            self.server_thread.start()
            return True
        except Exception as e:
            print(f"Failed to start server: {e}")
            return False
    
    def stop(self):
        """Stop HTTP server"""
        if self.httpd:
            self.httpd.shutdown()
            self.httpd = None
    
    def _handle_click(self, click_info):
        """Emit signal when block is clicked"""
        function = click_info.get('function', '')
        detail = click_info.get('detail', '')
        percent = click_info.get('percent', 0.0)
        self.blockClicked.emit(function, detail, percent)


class CompilationWorker(QThread):
    """Worker thread for compilation and profiling"""
    progress = pyqtSignal(str)
    finished = pyqtSignal(bool, str, str)
    error = pyqtSignal(str, str)
    request_password = pyqtSignal()
    
    def __init__(self, cpp_file, language, opt_level, scripts_dir):
        super().__init__()
        self.cpp_file = cpp_file
        self.language = language
        self.opt_level = opt_level
        self.scripts_dir = scripts_dir
        self.output_dir = Path(cpp_file).parent
        self.sudo_password = None
    
    def run_with_sudo(self, cmd, cwd=None):
        """Run a command with sudo, prompting for password if needed"""
        try:
            result = subprocess.run(cmd, capture_output=True, cwd=cwd)
            if result.returncode == 0:
                return result
            
            stderr = result.stderr.decode('utf-8', errors='replace')
            if 'Permission denied' not in stderr and 'perf_event_paranoid' not in stderr:
                return result
            
            if subprocess.run(['which', 'pkexec'], capture_output=True).returncode == 0:
                self.progress.emit("Requesting administrator privileges (graphical prompt)...")
                sudo_cmd = ['pkexec'] + cmd
                result = subprocess.run(sudo_cmd, capture_output=True, cwd=cwd)
                return result
            
            self.progress.emit("Running with sudo (you may need to enter your password in terminal)...")
            sudo_cmd = ['sudo', '-S'] + cmd
            
            result = subprocess.run(sudo_cmd, capture_output=True, cwd=cwd, 
                                  input=b'', timeout=60)
            return result
            
        except subprocess.TimeoutExpired:
            self.progress.emit("✗ Sudo command timed out")
            result = subprocess.CompletedProcess(cmd, 1, b'', b'Timeout')
            return result
        except Exception as e:
            self.progress.emit(f"✗ Error running sudo command: {e}")
            result = subprocess.CompletedProcess(cmd, 1, b'', str(e).encode())
            return result
        
    def run(self):
        """Execute compilation and profiling"""
        try:
            self.progress.emit("Compiling source code...")
            cpp_basename = Path(self.cpp_file).stem
            output_executable = self.output_dir / f"{cpp_basename}_{self.opt_level}"
            ir_file = self.output_dir / f"{cpp_basename}_{self.opt_level}.ll"
            
            if self.language == 'cpp':
                compile_cmd = [
                    'clang++', 
                    f'-{self.opt_level}',
                    '-g',
                    '-fno-omit-frame-pointer',
                    str(self.cpp_file),
                    '-o', str(output_executable)
                ]
            elif self.language == 'go':
                compile_cmd = [
                    'go', 
                    'build',
                    '-o', str(output_executable),
                    str(self.cpp_file)
                ]
            elif self.language == 'rust':
                compile_cmd = [
                    'rustc',
                    '-C', f'opt-level={self.opt_level[-1]}',
                    '-g',
                    str(self.cpp_file),
                    '-o', str(output_executable)
                ]
            else:
                self.finished.emit(False, "", "")
                self.progress.emit(f"Unsupported language: {self.language}")
                return
            
            result = subprocess.run(compile_cmd, capture_output=True, text=True)
            if result.returncode != 0:
                self.finished.emit(False, "", "")
                self.progress.emit(f"Compilation failed: {result.stderr}")
                return
            
            self.progress.emit("✓ Compilation successful")
            
            if self.language == 'cpp':
                self.progress.emit("Generating LLVM IR...")
                ir_cmd = [
                    'clang++',
                    f'-{self.opt_level}',
                    '-S',
                    '-emit-llvm',
                    str(self.cpp_file),
                    '-o', str(ir_file)
                ]
                subprocess.run(ir_cmd, capture_output=True, text=True)
                self.progress.emit("✓ LLVM IR generated")
            elif self.language == 'rust':
                self.progress.emit("Generating LLVM IR...")
                ir_cmd = [
                    'rustc',
                    '--emit=llvm-ir',
                    '-C', f'opt-level={self.opt_level[-1]}',
                    str(self.cpp_file),
                    '-o', str(ir_file)
                ]
                subprocess.run(ir_cmd, capture_output=True, text=True)
                self.progress.emit("✓ LLVM IR generated")
            else:
                self.progress.emit("⚠ LLVM IR generation not supported for Go")
            
            self.progress.emit("Running performance profiling (this may take a moment)...")
            perf_data = self.output_dir / "perf.data"
            perf_script = self.output_dir / "perf.script"
            folded_file = self.output_dir / "perf.folded"
            
            perf_record_cmd = [
                'perf', 'record',
                '-F', '99',
                '-g',
                '--', str(output_executable)
            ]
            
            result = self.run_with_sudo(perf_record_cmd, cwd=str(self.output_dir))
            
            if result.returncode != 0:
                stderr = result.stderr.decode('utf-8', errors='replace') if result.stderr else ''
                self.progress.emit(f"⚠ Profiling failed: {stderr}")
                self.finished.emit(False, "", "")
                return
            
            self.progress.emit("✓ Profiling complete")
            
            self.progress.emit("Processing profiling data...")
            
            perf_script_cmd = ['perf', 'script']
            result = self.run_with_sudo(perf_script_cmd, cwd=str(self.output_dir))
            
            if result.returncode == 0:
                with open(perf_script, 'wb') as f:
                    f.write(result.stdout)
                self.progress.emit("✓ Profiling data processed")
            else:
                self.progress.emit("⚠ Failed to process profiling data")
                self.finished.emit(False, "", "")
                return
            
            self.progress.emit("Generating flamegraph...")
            
            flamegraph_dir = self.scripts_dir / 'FlameGraph'
            stackcollapse_pl = flamegraph_dir / 'stackcollapse-perf.pl'
            flamegraph_pl = flamegraph_dir / 'flamegraph.pl'
            
            if not stackcollapse_pl.exists() or not flamegraph_pl.exists():
                self.progress.emit("⚠ FlameGraph scripts not found")
                self.progress.emit("Clone from: git clone https://github.com/brendangregg/FlameGraph.git")
                self.finished.emit(False, "", "")
                return
            
            with open(perf_script, 'r') as f:
                stackcollapse_result = subprocess.run(
                    ['perl', str(stackcollapse_pl)],
                    stdin=f,
                    capture_output=True,
                    text=True
                )
            
            if stackcollapse_result.returncode != 0:
                self.progress.emit(f"⚠ Failed to collapse stacks: {stackcollapse_result.stderr}")
                self.finished.emit(False, "", "")
                return
            
            with open(folded_file, 'w') as f:
                f.write(stackcollapse_result.stdout)
            
            process_script = self.scripts_dir / 'process_flamegraph.py'
            html_output = self.output_dir / 'flamegraph.html'
            
            if process_script.exists():
                result = subprocess.run(
                    [sys.executable, str(process_script), str(folded_file), str(html_output)],
                    capture_output=True,
                    text=True,
                    cwd=str(self.scripts_dir)
                )
                
                if result.returncode == 0 and html_output.exists():
                    self.progress.emit("✓ Flamegraph generated successfully!")
                    self.finished.emit(True, str(output_executable), str(html_output))
                else:
                    self.progress.emit(f"⚠ Failed to generate HTML flamegraph: {result.stderr}")
                    self.finished.emit(False, "", "")
            else:
                self.progress.emit("⚠ process_flamegraph.py not found")
                self.finished.emit(False, "", "")
            
        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            self.progress.emit(f"Error: {str(e)}")
            self.error.emit(str(e), error_detail)
            self.finished.emit(False, "", "")


class LLVMOptimizerUI(QMainWindow):
    """Main UI window"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LLVM IR Optimization Visualizer")
        self.setGeometry(100, 100, 1400, 900)
        
        self.selected_file = None
        self.flamegraph_path = None
        self.ir_file = None
        self.selected_function = None
        self.selected_detail = None
        self.selected_percent = 0.0
        self.scripts_dir = Path(__file__).parent
        
        self.server = FlameGraphServer()
        self.server.blockClicked.connect(self.on_block_clicked)
        
        self.setup_ui()
    
    def setup_ui(self):
        """Setup the UI"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        self.pages = QTabWidget()
        self.pages.setTabsClosable(False)
        layout.addWidget(self.pages)
        
        self.create_page1()
        self.create_page2()
        self.create_page3()
        self.create_page4()
        
        self.pages.setCurrentIndex(0)
    
    def create_page1(self):
        """Create configuration page"""
        page = QWidget()
        layout = QVBoxLayout(page)
        
        title = QLabel("Configuration")
        title.setFont(QFont("Arial", 24, QFont.Bold))
        layout.addWidget(title)
        
        config_group = QGroupBox("Settings")
        config_layout = QVBoxLayout()
        
        lang_layout = QHBoxLayout()
        lang_layout.addWidget(QLabel("Language:"))
        
        self.cpp_radio = QRadioButton("C++")
        self.go_radio = QRadioButton("Go")
        self.rust_radio = QRadioButton("Rust")
        self.cpp_radio.setChecked(True)
        
        lang_group = QButtonGroup(self)
        lang_group.addButton(self.cpp_radio)
        lang_group.addButton(self.go_radio)
        lang_group.addButton(self.rust_radio)
        
        lang_layout.addWidget(self.cpp_radio)
        lang_layout.addWidget(self.go_radio)
        lang_layout.addWidget(self.rust_radio)
        lang_layout.addStretch()
        config_layout.addLayout(lang_layout)
        
        opt_layout = QHBoxLayout()
        opt_layout.addWidget(QLabel("Optimization Level:"))
        self.opt_combo = QComboBox()
        self.opt_combo.addItems(['O0', 'O1', 'O2', 'O3', 'Os', 'Ofast', 'Oz'])
        self.opt_combo.setCurrentText('O0')
        opt_layout.addWidget(self.opt_combo)
        opt_layout.addStretch()
        config_layout.addLayout(opt_layout)
        
        config_group.setLayout(config_layout)
        layout.addWidget(config_group)
        
        file_group = QGroupBox("Source File")
        file_layout = QVBoxLayout()
        
        self.file_label = QLabel("No file selected")
        file_layout.addWidget(self.file_label)
        
        file_btn_layout = QHBoxLayout()
        self.select_file_btn = QPushButton("Select File")
        self.select_file_btn.clicked.connect(self.select_source_file)
        file_btn_layout.addWidget(self.select_file_btn)
        file_btn_layout.addStretch()
        file_layout.addLayout(file_btn_layout)
        
        file_group.setLayout(file_layout)
        layout.addWidget(file_group)
        
        layout.addStretch()
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.continue_btn_page1 = QPushButton("Continue →")
        self.continue_btn_page1.setEnabled(False)
        self.continue_btn_page1.clicked.connect(self.go_to_page2)
        btn_layout.addWidget(self.continue_btn_page1)
        layout.addLayout(btn_layout)
        
        self.pages.addTab(page, "1. Configuration")
    
    def get_selected_language(self):
        """Get currently selected programming language"""
        if self.cpp_radio.isChecked():
            return 'cpp'
        elif self.go_radio.isChecked():
            return 'go'
        elif self.rust_radio.isChecked():
            return 'rust'
        return 'cpp'
    
    def create_page2(self):
        """Create compilation page"""
        page = QWidget()
        layout = QVBoxLayout(page)
        
        title = QLabel("Processing Your Code")
        title.setFont(QFont("Arial", 24, QFont.Bold))
        layout.addWidget(title)
        
        subtitle = QLabel("Please wait while we compile, profile, and generate the flamegraph...")
        layout.addWidget(subtitle)
        
        self.progress_label = QLabel("Ready to start")
        layout.addWidget(self.progress_label)
        
        log_group = QGroupBox("Process Log")
        log_layout = QVBoxLayout()
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Courier", 9))
        log_layout.addWidget(self.log_text)
        log_group.setLayout(log_layout)
        layout.addWidget(log_group)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.continue_btn_page2 = QPushButton("Continue →")
        self.continue_btn_page2.setEnabled(False)
        self.continue_btn_page2.clicked.connect(self.go_to_page3)
        btn_layout.addWidget(self.continue_btn_page2)
        layout.addLayout(btn_layout)
        
        self.pages.addTab(page, "2. Processing")
    
    def create_page3(self):
        """Create flamegraph selection page"""
        page = QWidget()
        layout = QVBoxLayout(page)
        
        title = QLabel("Select Function to Analyze")
        title.setFont(QFont("Arial", 24, QFont.Bold))
        layout.addWidget(title)
        
        subtitle = QLabel("Click on a block in the flamegraph or select from the list to analyze")
        layout.addWidget(subtitle)
        
        content_layout = QHBoxLayout()
        
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("Search:"))
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Filter functions...")
        self.search_box.textChanged.connect(self.filter_blocks)
        search_layout.addWidget(self.search_box)
        left_layout.addLayout(search_layout)
        
        self.block_list = QListWidget()
        self.block_list.itemClicked.connect(self.on_list_item_clicked)
        left_layout.addWidget(self.block_list)
        
        content_layout.addWidget(left_panel, 1)
        
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        
        flamegraph_label = QLabel("Flamegraph Viewer")
        flamegraph_label.setFont(QFont("Arial", 14, QFont.Bold))
        right_layout.addWidget(flamegraph_label)
        
        self.selected_block_label = QLabel("No block selected - Click a block or select from list")
        self.selected_block_label.setWordWrap(True)
        self.selected_block_label.setStyleSheet("padding: 10px; background: #fff3cd; border-left: 4px solid #ffc107;")
        right_layout.addWidget(self.selected_block_label)
        
        self.open_flamegraph_btn = QPushButton("Open Flamegraph in Browser")
        self.open_flamegraph_btn.clicked.connect(self.open_flamegraph_browser)
        right_layout.addWidget(self.open_flamegraph_btn)
        
        content_layout.addWidget(right_panel, 2)
        
        layout.addLayout(content_layout)
        
        btn_layout = QHBoxLayout()
        back_btn = QPushButton("← Back")
        back_btn.clicked.connect(lambda: self.pages.setCurrentIndex(1))
        btn_layout.addWidget(back_btn)
        btn_layout.addStretch()
        self.continue_btn_page3 = QPushButton("Analyze Selected Function →")
        self.continue_btn_page3.setEnabled(False)
        self.continue_btn_page3.clicked.connect(self.go_to_page4)
        btn_layout.addWidget(self.continue_btn_page3)
        layout.addLayout(btn_layout)
        
        self.pages.addTab(page, "3. Select Function")
    
    def create_page4(self):
        """Create analysis page"""
        page = QWidget()
        layout = QVBoxLayout(page)
        
        title = QLabel("Function Analysis")
        title.setFont(QFont("Arial", 24, QFont.Bold))
        layout.addWidget(title)
        
        splitter = QSplitter(Qt.Horizontal)
        
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        
        self.function_info = QTextEdit()
        self.function_info.setReadOnly(True)
        self.function_info.setMaximumHeight(150)
        left_layout.addWidget(QLabel("Function Information:"))
        left_layout.addWidget(self.function_info)
        
        tabs = QTabWidget()
        
        self.ir_text = QTextEdit()
        self.ir_text.setReadOnly(True)
        self.ir_text.setFont(QFont("Courier", 9))
        tabs.addTab(self.ir_text, "LLVM IR")
        
        self.cpp_text = QTextEdit()
        self.cpp_text.setReadOnly(True)
        self.cpp_text.setFont(QFont("Courier", 9))
        tabs.addTab(self.cpp_text, "Source Code")
        
        cfg_widget = QWidget()
        cfg_layout = QVBoxLayout(cfg_widget)
        
        cfg_toolbar = QHBoxLayout()
        zoom_in_btn = QPushButton("Zoom In")
        zoom_in_btn.clicked.connect(self.cfg_zoom_in)
        zoom_out_btn = QPushButton("Zoom Out")
        zoom_out_btn.clicked.connect(self.cfg_zoom_out)
        fit_btn = QPushButton("Fit to View")
        fit_btn.clicked.connect(self.cfg_fit_view)
        reset_btn = QPushButton("Reset")
        reset_btn.clicked.connect(self.cfg_reset_zoom)
        cfg_toolbar.addWidget(zoom_in_btn)
        cfg_toolbar.addWidget(zoom_out_btn)
        cfg_toolbar.addWidget(fit_btn)
        cfg_toolbar.addWidget(reset_btn)
        cfg_toolbar.addStretch()
        cfg_layout.addLayout(cfg_toolbar)
        
        self.cfg_scene = QGraphicsScene()
        self.cfg_view = QGraphicsView(self.cfg_scene)
        self.cfg_view.setRenderHint(self.cfg_view.Antialiasing)
        cfg_layout.addWidget(self.cfg_view)
        
        tabs.addTab(cfg_widget, "Control Flow Graph")
        
        left_layout.addWidget(tabs)
        splitter.addWidget(left_panel)
        
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        
        right_layout.addWidget(QLabel("Flamegraph:"))
        
        self.flamegraph_list_page4 = QListWidget()
        self.flamegraph_list_page4.itemClicked.connect(self.on_list_item_clicked)
        right_layout.addWidget(self.flamegraph_list_page4)
        
        self.open_flamegraph_btn_page4 = QPushButton("Open in Browser")
        self.open_flamegraph_btn_page4.clicked.connect(self.open_flamegraph_browser)
        right_layout.addWidget(self.open_flamegraph_btn_page4)
        
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        
        layout.addWidget(splitter)
        
        btn_layout = QHBoxLayout()
        back_btn = QPushButton("← Back to Selection")
        back_btn.clicked.connect(lambda: self.pages.setCurrentIndex(2))
        btn_layout.addWidget(back_btn)
        btn_layout.addStretch()
        new_analysis_btn = QPushButton("Start New Analysis")
        new_analysis_btn.clicked.connect(self.reset_to_start)
        btn_layout.addWidget(new_analysis_btn)
        layout.addLayout(btn_layout)
        
        self.pages.addTab(page, "4. Analysis")
    
    def select_source_file(self):
        """Select source file"""
        file_filter = "Source Files (*.cpp *.cc *.cxx *.c *.go *.rs);;All Files (*)"
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Select Source File",
            "",
            file_filter
        )
        
        if filename:
            self.selected_file = filename
            self.file_label.setText(f"Selected: {Path(filename).name}")
            self.continue_btn_page1.setEnabled(True)
    
    def go_to_page2(self):
        """Go to processing page and start compilation"""
        self.pages.setCurrentIndex(1)
        self.start_compilation()
    
    def start_compilation(self):
        """Start compilation process"""
        if not self.selected_file:
            QMessageBox.warning(self, "No File", "Please select a source file first")
            return
        
        language = self.get_selected_language()
        opt_level = self.opt_combo.currentText()
        
        self.log_text.clear()
        self.log_text.append("Starting compilation and profiling...\n")
        
        self.worker = CompilationWorker(
            self.selected_file,
            language,
            opt_level,
            self.scripts_dir
        )
        
        self.worker.progress.connect(self.update_progress)
        self.worker.finished.connect(self.compilation_finished)
        self.worker.error.connect(self.compilation_error)
        
        self.worker.start()
    
    def update_progress(self, message):
        """Update progress log"""
        self.log_text.append(message)
        self.log_text.verticalScrollBar().setValue(
            self.log_text.verticalScrollBar().maximum()
        )
    
    def compilation_finished(self, success, output_file, html_file):
        """Handle compilation completion"""
        if success and html_file:
            self.log_text.append("\n✓ All steps completed successfully!")
            self.flamegraph_path = html_file
            self.continue_btn_page2.setEnabled(True)
            
            if self.server.start(html_file):
                self.log_text.append(f"\n✓ Flamegraph server started on port {self.server.port}")
            
            self.populate_block_list()
        else:
            self.log_text.append("\n⚠ Processing completed but flamegraph was not generated")
    
    def compilation_error(self, error_type, error_detail):
        """Handle compilation error"""
        self.log_text.append(f"\nError: {error_type}")
        self.log_text.append(f"Details:\n{error_detail}")
    
    def go_to_page3(self):
        """Go to flamegraph selection page"""
        self.pages.setCurrentIndex(2)
    
    def go_to_page4(self):
        """Go to analysis page"""
        self.pages.setCurrentIndex(3)
        
        if self.selected_function:
            self.display_block_info(
                self.selected_function,
                self.selected_detail,
                self.selected_percent
            )
            
            self.flamegraph_list_page4.clear()
            for i in range(self.block_list.count()):
                item = self.block_list.item(i)
                self.flamegraph_list_page4.addItem(item.text())
    
    def reset_to_start(self):
        """Reset to start"""
        self.pages.setCurrentIndex(0)
        self.selected_file = None
        self.flamegraph_path = None
        self.selected_function = None
        self.file_label.setText("No file selected")
        self.continue_btn_page1.setEnabled(False)
        self.continue_btn_page2.setEnabled(False)
        self.continue_btn_page3.setEnabled(False)
        self.log_text.clear()
        self.server.stop()
    
    def populate_block_list(self, filter_text=""):
        """Populate block list from flamegraph"""
        self.block_list.clear()
        
        if not self.flamegraph_path:
            return
        
        try:
            with open(self.flamegraph_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            blocks = []
            
            pattern = r'data-name="([^"]+)"\s+data-samples="([^"]+)"\s+data-percent="([^"]+)"'
            matches = re.findall(pattern, content)
            
            for name, samples, percent in matches:
                if filter_text.lower() in name.lower():
                    blocks.append({
                        'name': name,
                        'samples': samples,
                        'percent': float(percent)
                    })
            
            blocks.sort(key=lambda x: x['percent'], reverse=True)
            
            for block in blocks:
                item_text = f"{block['name']} ({block['samples']} samples, {block['percent']:.2f}%)"
                self.block_list.addItem(item_text)
                
        except Exception as e:
            print(f"Error populating block list: {e}")
    
    def filter_blocks(self, text):
        """Filter blocks"""
        self.populate_block_list(text)
    
    def open_flamegraph_browser(self):
        """Open flamegraph in browser"""
        if not self.flamegraph_path:
            return
        
        url = f"http://localhost:{self.server.port}/{Path(self.flamegraph_path).name}"
        webbrowser.open(url)
    
    @pyqtSlot(str, str, float)
    def on_block_clicked(self, function, detail, percent):
        """Handle block click from browser - route based on current page"""
        current_page = self.pages.currentIndex()
        
        if current_page == 2:
            self.selected_function = function
            self.selected_detail = detail
            self.selected_percent = percent
            self.selected_block_label.setText(f"✓ Selected: {function}\n{detail}")
            self.continue_btn_page3.setEnabled(True)
        elif current_page == 3:
            self.display_block_info(function, detail, percent)
    
    def on_list_item_clicked(self, item):
        """Handle block selection from list"""
        text = item.text()
        parts = text.split(' (')
        if len(parts) >= 2:
            function = parts[0]
            details = parts[1].rstrip(')')
            
            percent = 0.0
            if '%' in details:
                try:
                    percent = float(details.split(',')[-1].strip().rstrip('%'))
                except:
                    pass
            
            self.display_block_info(function, details, percent)
    
    def display_block_info(self, function, detail, percent):
        """Display selected block information on page 4"""
        info = f"""Selected Function: {function}

Details: {detail}
Percentage: {percent:.2f}%

Bottleneck Analysis:
- This function accounts for {percent:.2f}% of total execution time
- Review the LLVM IR and source code tabs to identify optimization opportunities
"""
        self.function_info.setPlainText(info)
        
        self.load_function_code(function)
    
    def load_function_code(self, function_name):
        """Load IR and source code for function"""
        if not self.flamegraph_path:
            return
        
        flamegraph_dir = Path(self.flamegraph_path).parent
        
        ir_files = list(flamegraph_dir.glob("*.ll"))
        cpp_files = list(flamegraph_dir.glob("*.cpp")) + list(flamegraph_dir.glob("*.cc"))
        cfg_dirs = [d for d in flamegraph_dir.glob("*_cfg") if d.is_dir()]
        
        ir_content = self.find_function_in_ir(function_name, ir_files)
        if ir_content:
            self.ir_text.setPlainText(ir_content)
        else:
            self.ir_text.setPlainText(f"Could not find IR for function: {function_name}")
        
        cpp_content = self.find_function_in_cpp(function_name, cpp_files)
        if cpp_content:
            self.cpp_text.setPlainText(cpp_content)
        else:
            self.cpp_text.setPlainText(f"Could not find source for function: {function_name}")
        
        cfg_image_path = self.find_function_in_cfg(function_name, cfg_dirs)
        if cfg_image_path:
            self.load_cfg_image(cfg_image_path)
        else:
            self.cfg_scene.clear()
    
    def find_function_in_ir(self, function_name, ir_files):
        """Find function in IR files"""
        search_patterns = [
            function_name,
            f"@{function_name}",
            function_name.split('::')[-1] if '::' in function_name else function_name
        ]
        
        for ir_file in ir_files:
            try:
                with open(ir_file, 'r') as f:
                    lines = f.readlines()
                
                for i, line in enumerate(lines):
                    if any(f'define ' in line and pattern in line for pattern in search_patterns):
                        func_lines = [line]
                        brace_count = 0
                        
                        for j in range(i+1, len(lines)):
                            func_lines.append(lines[j])
                            brace_count += lines[j].count('{') - lines[j].count('}')
                            if '}' in lines[j] and brace_count <= 0:
                                break
                        
                        return ''.join(func_lines)
            except:
                continue
        
        return None
    
    def find_function_in_cpp(self, function_name, cpp_files):
        """Find function in C++ files"""
        clean_name = function_name
        clean_name = re.sub(r'<[^>]+>', '', clean_name)
        if '::' in clean_name:
            clean_name = clean_name.split('::')[-1]
        clean_name = clean_name.split('(')[0].strip()
        
        for cpp_file in cpp_files:
            try:
                with open(cpp_file, 'r') as f:
                    lines = f.readlines()
                
                for i, line in enumerate(lines):
                    if clean_name in line and ('(' in line or 'class' in line or 'struct' in line):
                        start = max(0, i - 5)
                        end = min(len(lines), i + 30)
                        return ''.join(lines[start:end])
            except:
                continue
        
        return None
    
    def find_function_in_cfg(self, function_name, cfg_dirs):
        """Find CFG for function"""
        for cfg_dir in cfg_dirs:
            try:
                dot_files = list(cfg_dir.glob("*.dot"))
                
                for dot_file in dot_files:
                    if function_name in dot_file.stem:
                        png_file = dot_file.with_suffix('.png')
                        
                        if not png_file.exists():
                            subprocess.run(
                                ['dot', '-Tpng', str(dot_file), '-o', str(png_file)],
                                capture_output=True
                            )
                        
                        if png_file.exists():
                            return str(png_file)
            except:
                continue
        
        return None
    
    def load_cfg_image(self, image_path):
        """Load CFG image"""
        self.cfg_scene.clear()
        pixmap = QPixmap(image_path)
        
        if not pixmap.isNull():
            item = QGraphicsPixmapItem(pixmap)
            self.cfg_scene.addItem(item)
            self.cfg_scene.setSceneRect(item.boundingRect())
            self.cfg_view.fitInView(self.cfg_scene.sceneRect(), Qt.KeepAspectRatio)
    
    def cfg_zoom_in(self):
        """Zoom in CFG"""
        self.cfg_view.scale(1.2, 1.2)
    
    def cfg_zoom_out(self):
        """Zoom out CFG"""
        self.cfg_view.scale(1/1.2, 1/1.2)
    
    def cfg_fit_view(self):
        """Fit CFG to view"""
        self.cfg_view.fitInView(self.cfg_scene.sceneRect(), Qt.KeepAspectRatio)
    
    def cfg_reset_zoom(self):
        """Reset CFG zoom"""
        self.cfg_view.resetTransform()
    
    def closeEvent(self, event):
        """Clean up on exit"""
        self.server.stop()
        event.accept()


def main():
    app = QApplication(sys.argv)
    window = LLVMOptimizerUI()
    window.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()