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
from PyQt5.QtGui import QFont, QPixmap, QImage, QPainter


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
    finished = pyqtSignal(bool, str, str)  # success, output_file, html_file
    error = pyqtSignal(str, str)  # error_type, error_message
    request_password = pyqtSignal()  # Signal to request password from UI
    
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
            # First try without sudo (system might be configured)
            result = subprocess.run(cmd, capture_output=True, cwd=cwd)
            if result.returncode == 0:
                return result
            
            # Check if it's a permission error
            stderr = result.stderr.decode('utf-8', errors='replace')
            if 'Permission denied' not in stderr and 'perf_event_paranoid' not in stderr:
                return result
            
            # Need sudo - try with pkexec (graphical prompt)
            if subprocess.run(['which', 'pkexec'], capture_output=True).returncode == 0:
                self.progress.emit("Requesting administrator privileges (graphical prompt)...")
                sudo_cmd = ['pkexec'] + cmd
                result = subprocess.run(sudo_cmd, capture_output=True, cwd=cwd)
                return result
            
            # Try with sudo (will use system's sudo password cache)
            self.progress.emit("Running with sudo (you may need to enter your password in terminal)...")
            sudo_cmd = ['sudo', '-S'] + cmd
            
            # If we don't have a cached password, the system sudo will handle it
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
            # Step 1: Compile with optimization
            self.progress.emit("Compiling source code...")
            cpp_basename = Path(self.cpp_file).stem
            output_executable = self.output_dir / f"{cpp_basename}_{self.opt_level}"
            ir_file = self.output_dir / f"{cpp_basename}_{self.opt_level}.ll"
            
            # Compile command
            if self.language == 'go':
                compile_cmd = [
                    'go', 
                    'build',
                    '-o', str(output_executable),
                    str(self.cpp_file)
                ]
            else:
                compile_cmd = [
                    'clang++', 
                    f'-{self.opt_level}',
                    '-g',
                    '-fno-omit-frame-pointer',
                    str(self.cpp_file),
                    '-o', str(output_executable)
                ]
            
            result = subprocess.run(compile_cmd, capture_output=True, text=True)
            if result.returncode != 0:
                self.finished.emit(False, "", "")
                self.progress.emit(f"Compilation failed: {result.stderr}")
                return
            
            self.progress.emit("✓ Compilation successful")
            
            # Generate LLVM IR (only for C++)
            if self.language != 'go':
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
            else:
                self.progress.emit("⚠ LLVM IR generation not supported for Go")
            
            # Step 2: Run perf profiling
            self.progress.emit("Running performance profiling (this may take a moment)...")
            perf_data = self.output_dir / "perf.data"
            perf_script = self.output_dir / "perf.script"
            folded_file = self.output_dir / "perf.folded"
            
            # Clean up old perf data
            try:
                perf_data.unlink(missing_ok=True)
                perf_script.unlink(missing_ok=True)
                folded_file.unlink(missing_ok=True)
            except:
                pass
            
            # Try to run perf (with sudo if needed)
            # Use higher frequency and longer duration for better sampling
            perf_cmd = ['perf', 'record', '-F', '997', '-g', '--call-graph', 'dwarf', 
                       '-o', str(perf_data), '--', str(output_executable)]
            
            self.progress.emit(f"Running: {' '.join(perf_cmd)}")
            result = self.run_with_sudo(perf_cmd, cwd=str(self.output_dir))
            
            # Show perf output
            if result.stdout:
                try:
                    stdout_text = result.stdout.decode('utf-8', errors='replace')
                    if stdout_text.strip():
                        self.progress.emit(f"Perf stdout: {stdout_text}")
                except:
                    pass
            
            if result.returncode != 0:
                # Decode stderr carefully
                try:
                    stderr_text = result.stderr.decode('utf-8', errors='replace')
                except:
                    stderr_text = str(result.stderr)
                
                self.progress.emit(f"Perf failed with return code {result.returncode}")
                self.progress.emit(f"Perf stderr: {stderr_text}")
                
                # Check if it's still a permission issue
                if 'Permission denied' in stderr_text or 'perf_event_paranoid' in stderr_text:
                    self.progress.emit("⚠ Perf requires system configuration")
                    self.error.emit("perf_permission", stderr_text)
                    self.finished.emit(True, str(output_executable), "")
                    return
                else:
                    self.progress.emit(f"⚠ Warning: Profiling failed")
                    self.finished.emit(True, str(output_executable), "")
                    return
            
            # Check if perf.data was created and has content
            self.progress.emit(f"Checking for perf.data at: {perf_data}")
            
            if not perf_data.exists():
                # Maybe it was created in current directory instead?
                alt_perf_data = Path.cwd() / "perf.data"
                if alt_perf_data.exists():
                    self.progress.emit(f"Found perf.data in current directory, moving it...")
                    alt_perf_data.rename(perf_data)
                else:
                    self.progress.emit(f"⚠ Warning: perf.data was not created")
                    self.progress.emit(f"Checked: {perf_data}")
                    self.progress.emit(f"Also checked: {alt_perf_data}")
                    self.progress.emit(f"Working directory was: {self.output_dir}")
                    self.finished.emit(True, str(output_executable), "")
                    return
            
            perf_data_size = perf_data.stat().st_size
            self.progress.emit(f"✓ Profiling complete (perf.data: {perf_data_size} bytes)")
            
            if perf_data_size < 1000:
                self.progress.emit("⚠ Warning: perf.data is very small - program may have run too quickly")
                self.progress.emit("Consider making your program run longer for better profiling results")
            
            # Step 3: Process perf data
            self.progress.emit("Processing profiling data...")
            perf_script_cmd = ['perf', 'script']
            result = self.run_with_sudo(perf_script_cmd, cwd=str(self.output_dir))
            
            # Write the output as bytes, then let stackcollapse handle it
            with open(perf_script, 'wb') as f:
                f.write(result.stdout)
            
            perf_script_size = perf_script.stat().st_size
            self.progress.emit(f"perf script output: {perf_script_size} bytes")
            
            if perf_script_size == 0:
                self.progress.emit("⚠ Warning: No perf samples collected")
                self.progress.emit("This usually means the program ran too fast or perf couldn't collect samples")
                self.progress.emit("")
                self.progress.emit("💡 Tips to fix this:")
                self.progress.emit("   1. Make your program run longer (add loops, more work)")
                self.progress.emit("   2. Add a sleep or computation loop in main()")
                self.progress.emit("   3. For testing, you can use 'perf record -F 997 -g -- ./your_program'")
                self.progress.emit("")
                self.progress.emit("Compilation and IR generation were successful though!")
                
                # Show a user-friendly dialog
                QMessageBox.information(
                    None,
                    "Profiling Note",
                    "The program compiled successfully, but ran too quickly for perf to collect samples.\n\n"
                    "To generate a flamegraph, your program needs to run long enough for perf to capture data.\n\n"
                    "Suggestions:\n"
                    "• Add more computation or loops to your program\n"
                    "• Add a sleep() call to make it run longer\n"
                    "• Process larger datasets\n\n"
                    "The LLVM IR and executable were generated successfully!"
                )
                
                self.finished.emit(True, str(output_executable), "")
                return
            
            # Step 4: Fold stacks
            flamegraph_dir = self.scripts_dir / 'FlameGraph'
            stackcollapse_pl = flamegraph_dir / 'stackcollapse-perf.pl'
            
            if not stackcollapse_pl.exists():
                self.progress.emit("⚠ FlameGraph scripts not found. Checking parent directory...")
                # Try parent directory scripts folder
                alt_flamegraph_dir = Path(self.cpp_file).parent.parent / 'scripts' / 'FlameGraph'
                stackcollapse_pl = alt_flamegraph_dir / 'stackcollapse-perf.pl'
                
                if not stackcollapse_pl.exists():
                    # Try current directory
                    alt_flamegraph_dir = Path.cwd() / 'scripts' / 'FlameGraph'
                    stackcollapse_pl = alt_flamegraph_dir / 'stackcollapse-perf.pl'
                    
                    if not stackcollapse_pl.exists():
                        self.progress.emit(f"✗ FlameGraph scripts not found in:")
                        self.progress.emit(f"  - {flamegraph_dir}")
                        self.progress.emit(f"  - {alt_flamegraph_dir}")
                        self.progress.emit("Please clone FlameGraph: cd scripts && git clone https://github.com/brendangregg/FlameGraph.git")
                        self.finished.emit(True, str(output_executable), "")
                        return
                    flamegraph_dir = alt_flamegraph_dir
                else:
                    flamegraph_dir = alt_flamegraph_dir
                
                self.progress.emit(f"✓ Found FlameGraph scripts at {flamegraph_dir}")
            
            with open(perf_script, 'rb') as infile:
                with open(folded_file, 'w') as outfile:
                    result = subprocess.run(['perl', str(stackcollapse_pl)], stdin=infile, stdout=outfile, stderr=subprocess.PIPE)
                    if result.returncode != 0:
                        self.progress.emit(f"⚠ stackcollapse-perf.pl warning: {result.stderr.decode('utf-8', errors='replace')}")
            
            self.progress.emit("✓ Stack data folded")
            
            # Check if folded file has content
            if folded_file.exists():
                size = folded_file.stat().st_size
                self.progress.emit(f"Folded file size: {size} bytes")
                if size == 0:
                    self.progress.emit("⚠ Warning: Folded file is empty - no samples collected")
            
            # Step 5: Generate flamegraph using process_flamegraph.py
            self.progress.emit("Generating interactive flamegraph...")
            html_file = self.output_dir / f"{cpp_basename}_{self.opt_level}.html"
            
            process_script = self.scripts_dir / 'process_flamegraph.py'
            if process_script.exists():
                self.progress.emit(f"Running: {process_script} {folded_file} {html_file}")
                result = subprocess.run([
                    sys.executable,
                    str(process_script),
                    str(folded_file),
                    str(html_file)
                ], capture_output=True, text=True)
                
                if result.returncode != 0:
                    self.progress.emit(f"⚠ process_flamegraph.py failed with code {result.returncode}")
                    self.progress.emit(f"STDOUT: {result.stdout}")
                    self.progress.emit(f"STDERR: {result.stderr}")
                else:
                    self.progress.emit(f"process_flamegraph.py output: {result.stdout}")
            else:
                self.progress.emit(f"⚠ process_flamegraph.py not found at {process_script}")
            
            # Verify the HTML file was created
            if not html_file.exists():
                self.progress.emit(f"⚠ Flamegraph HTML file was not created at: {html_file}")
                self.progress.emit(f"Files in directory: {list(self.output_dir.glob('*'))}")
                self.finished.emit(True, str(output_executable), "")
                return
            
            # Cleanup
            try:
                perf_data.unlink(missing_ok=True)
                perf_script.unlink(missing_ok=True)
                folded_file.unlink(missing_ok=True)
            except:
                pass
            
            self.progress.emit("✓ Flamegraph generated successfully!")
            self.finished.emit(True, str(output_executable), str(html_file))
            
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            self.progress.emit(f"Error: {str(e)}")
            self.progress.emit(f"Details:\n{error_details}")
            self.finished.emit(False, "", "")


class LLVMOptimizerUI(QMainWindow):
    """Main application window - Multi-page wizard"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LLVM IR Optimization Wizard")
        self.setGeometry(100, 50, 1200, 800)
        
        # State variables
        self.cpp_file = None
        self.language = "C++"
        self.opt_level = "O0"
        self.flamegraph_path = None
        self.output_executable = None
        self.all_blocks = []
        self.scripts_dir = Path(__file__).parent / 'scripts'
        self.selected_function = None
        self.current_page = 0
        
        # Server
        self.server = FlameGraphServer()
        self.server.blockClicked.connect(self.on_block_clicked)
        
        self.init_ui()
        # Don't check permissions on startup - do it when processing
        # self.check_perf_permissions()
        
    def check_perf_permissions(self):
        """Check if perf can run without sudo and warn user if not"""
        try:
            # Check perf_event_paranoid value
            with open('/proc/sys/kernel/perf_event_paranoid', 'r') as f:
                paranoid_value = int(f.read().strip())
            
            if paranoid_value > 1:
                # Perf will likely require sudo
                msg = QMessageBox(self)
                msg.setIcon(QMessageBox.Information)
                msg.setWindowTitle("Perf Configuration Notice")
                msg.setText("Your system may require configuration for perf profiling.")
                
                detailed_text = f"""Current perf_event_paranoid value: {paranoid_value}

For perf to work without sudo, this value should be -1, 0, or 1.

To fix this (choose one):

Temporary (until reboot):
    sudo sysctl -w kernel.perf_event_paranoid=-1

Permanent:
    echo 'kernel.perf_event_paranoid=-1' | sudo tee /etc/sysctl.d/99-perf.conf
    sudo sysctl --system

You can still use the application, but perf profiling will fail unless you apply the fix.
The compilation and LLVM IR generation will still work.
"""
                
                msg.setDetailedText(detailed_text)
                msg.setStandardButtons(QMessageBox.Ok | QMessageBox.Ignore)
                msg.setDefaultButton(QMessageBox.Ok)
                
                copy_button = msg.addButton("Copy Fix Command", QMessageBox.ActionRole)
                
                result = msg.exec_()
                
                if msg.clickedButton() == copy_button:
                    clipboard = QApplication.clipboard()
                    clipboard.setText("sudo sysctl -w kernel.perf_event_paranoid=-1")
                    QMessageBox.information(self, "Copied", "Command copied to clipboard!")
                    
        except Exception as e:
            # If we can't read the file, just continue
            pass
        
    def init_ui(self):
        """Initialize multi-page wizard UI"""
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Stacked widget for pages
        from PyQt5.QtWidgets import QStackedWidget
        self.pages = QStackedWidget()
        
        # Create all pages
        self.page1 = self.create_page1_selection()
        self.page2 = self.create_page2_loading()
        self.page3 = self.create_page3_flamegraph()
        self.page4 = self.create_page4_analysis()
        
        self.pages.addWidget(self.page1)
        self.pages.addWidget(self.page2)
        self.pages.addWidget(self.page3)
        self.pages.addWidget(self.page4)
        
        main_layout.addWidget(self.pages)
        
        # Start on page 1
        self.pages.setCurrentIndex(0)
    
    def create_page1_selection(self):
        """Page 1: Source file selection"""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(50, 30, 50, 30)
        layout.setSpacing(20)
        
        # Title
        title = QLabel("🔧 LLVM IR Optimization Wizard")
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # Subtitle
        subtitle = QLabel("Step 1: Configure and Select Source Code")
        subtitle.setStyleSheet("font-size: 13pt; color: #555; margin-bottom: 15px;")
        subtitle.setAlignment(Qt.AlignCenter)
        layout.addWidget(subtitle)
        
        layout.addSpacing(20)
        
        # Configuration panel
        config_group = QGroupBox("Configuration")
        config_group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 12pt; padding: 15px; }")
        config_layout = QVBoxLayout()
        config_layout.setSpacing(15)
        
        # Language selection
        lang_layout = QHBoxLayout()
        lang_label = QLabel("Language:")
        lang_label.setMinimumWidth(180)
        lang_label.setStyleSheet("font-size: 11pt;")
        lang_layout.addWidget(lang_label)
        
        self.lang_group = QButtonGroup()
        self.cpp_radio = QRadioButton("C++")
        self.go_radio = QRadioButton("Go")
        self.rust_radio = QRadioButton("Rust")
        self.cpp_radio.setChecked(True)
        
        for rb in [self.cpp_radio, self.go_radio, self.rust_radio]:
            rb.setStyleSheet("font-size: 11pt;")
        
        self.lang_group.addButton(self.cpp_radio)
        self.lang_group.addButton(self.go_radio)
        self.lang_group.addButton(self.rust_radio)
        
        lang_layout.addWidget(self.cpp_radio)
        lang_layout.addWidget(self.go_radio)
        lang_layout.addWidget(self.rust_radio)
        lang_layout.addStretch()
        
        self.cpp_radio.toggled.connect(lambda: setattr(self, 'language', 'C++'))
        self.go_radio.toggled.connect(lambda: setattr(self, 'language', 'Go'))
        self.rust_radio.toggled.connect(lambda: setattr(self, 'language', 'Rust'))
        
        config_layout.addLayout(lang_layout)
        
        # Optimization level
        opt_layout = QHBoxLayout()
        opt_label = QLabel("Optimization Level:")
        opt_label.setMinimumWidth(180)
        opt_label.setStyleSheet("font-size: 11pt;")
        opt_layout.addWidget(opt_label)
        
        self.opt_combo = QComboBox()
        self.opt_combo.addItems(['O0', 'O1', 'O2', 'O3', 'Os', 'Ofast', 'Oz'])
        self.opt_combo.setStyleSheet("font-size: 11pt; padding: 5px;")
        self.opt_combo.setToolTip(
            "O0: No optimization\nO1: Basic optimizations\nO2: Moderate optimizations (recommended)\n"
            "O3: Aggressive optimizations\nOs: Optimize for size\nOfast: Maximum speed\nOz: Smallest size"
        )
        self.opt_combo.currentTextChanged.connect(lambda x: setattr(self, 'opt_level', x))
        opt_layout.addWidget(self.opt_combo)
        opt_layout.addStretch()
        
        config_layout.addLayout(opt_layout)
        
        config_group.setLayout(config_layout)
        layout.addWidget(config_group)
        
        # File upload section
        file_group = QGroupBox("Source File")
        file_group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 12pt; padding: 15px; }")
        file_layout = QVBoxLayout()
        
        self.file_path_label = QLabel("No file selected")
        self.file_path_label.setStyleSheet("font-size: 11pt; color: #888; font-style: italic; padding: 10px;")
        self.file_path_label.setWordWrap(True)
        file_layout.addWidget(self.file_path_label)
        
        upload_btn = QPushButton("📂 Browse and Select Source File")
        upload_btn.setMinimumHeight(50)
        upload_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                font-size: 12pt;
                font-weight: bold;
                border-radius: 5px;
                padding: 10px;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
        """)
        upload_btn.clicked.connect(self.upload_file)
        file_layout.addWidget(upload_btn)
        
        file_group.setLayout(file_layout)
        layout.addWidget(file_group)
        
        # Add description/info section
        info_group = QGroupBox("What This Tool Does")
        info_group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 12pt; padding: 15px; }")
        info_layout = QVBoxLayout()
        
        info_text = QLabel("""
<b>Performance Analysis Wizard</b><br><br>

This tool helps you identify and optimize performance bottlenecks in your code:<br><br>

<b>1. Flamegraph Visualization</b><br>
   • Interactive flame graph showing which functions consume the most CPU time<br>
   • Wider blocks = more time spent in that function<br>
   • Click blocks to select them for detailed analysis<br><br>

<b>2. LLVM IR Analysis</b><br>
   • View the LLVM Intermediate Representation of your code<br>
   • See exactly how the compiler translates and optimizes your source<br>
   • Identify optimization opportunities at the IR level<br><br>

<b>3. Control Flow Graph (CFG)</b><br>
   • Visual representation of your function's execution paths<br>
   • Boxes represent basic blocks of code<br>
   • Arrows show how control flows between blocks<br>
   • Helps understand branching, loops, and code structure<br><br>

<b>4. Source Code Mapping</b><br>
   • Side-by-side view of source code with IR and CFG<br>
   • Trace performance issues back to original code
        """)
        info_text.setWordWrap(True)
        info_text.setStyleSheet("""
            font-size: 10pt;
            padding: 10px;
            line-height: 1.5;
            background-color: #f5f5f5;
            border-radius: 5px;
        """)
        info_layout.addWidget(info_text)
        info_group.setLayout(info_layout)
        layout.addWidget(info_group)
        
        layout.addStretch()
        
        # Navigation - Continue button
        nav_layout = QHBoxLayout()
        nav_layout.addStretch()
        
        self.continue_btn_page1 = QPushButton("Continue →")
        self.continue_btn_page1.setEnabled(False)
        self.continue_btn_page1.setMinimumSize(150, 50)
        self.continue_btn_page1.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-size: 13pt;
                font-weight: bold;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
        """)
        self.continue_btn_page1.clicked.connect(self.start_processing)
        nav_layout.addWidget(self.continue_btn_page1)
        
        layout.addLayout(nav_layout)
        
        return page
    
    def create_page2_loading(self):
        """Page 2: Loading/Processing screen"""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(50, 30, 50, 30)
        layout.setSpacing(20)
        
        # Title
        title = QLabel("⚙️ Processing Your Code")
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        subtitle = QLabel("Please wait while we compile, profile, and generate the flamegraph...")
        subtitle.setStyleSheet("font-size: 12pt; color: #555;")
        subtitle.setAlignment(Qt.AlignCenter)
        layout.addWidget(subtitle)
        
        layout.addSpacing(30)
        
        # Progress indicator
        from PyQt5.QtWidgets import QProgressBar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # Indeterminate
        self.progress_bar.setMinimumHeight(30)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 2px solid grey;
                border-radius: 5px;
                text-align: center;
                font-size: 11pt;
            }
            QProgressBar::chunk {
                background-color: #4CAF50;
            }
        """)
        layout.addWidget(self.progress_bar)
        
        layout.addSpacing(20)
        
        # Log output
        log_group = QGroupBox("Process Log")
        log_layout = QVBoxLayout()
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("font-family: 'Courier New', monospace; font-size: 10pt;")
        log_layout.addWidget(self.log_text)
        
        log_group.setLayout(log_layout)
        layout.addWidget(log_group)
        
        return page
    
    def create_page3_flamegraph(self):
        """Page 3: Flamegraph display"""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Header
        header_layout = QHBoxLayout()
        
        title = QLabel("🔥 Interactive Flamegraph")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title.setFont(title_font)
        header_layout.addWidget(title)
        
        header_layout.addStretch()
        
        open_browser_btn = QPushButton("🌐 Open in Browser")
        open_browser_btn.clicked.connect(self.open_flamegraph_browser)
        header_layout.addWidget(open_browser_btn)
        
        layout.addLayout(header_layout)
        
        # Instructions
        instructions = QLabel("The flamegraph has been opened in your browser. Click any block to select it, then click Continue below to view detailed IR analysis.")
        instructions.setStyleSheet("font-size: 10pt; color: #555; padding: 10px; background: #e3f2fd; border-radius: 5px;")
        instructions.setWordWrap(True)
        layout.addWidget(instructions)
        
        # Block index for selection
        blocks_group = QGroupBox("Available Blocks (Click to Select)")
        blocks_layout = QVBoxLayout()
        
        self.search_box_page3 = QLineEdit()
        self.search_box_page3.setPlaceholderText("🔍 Search blocks...")
        self.search_box_page3.textChanged.connect(self.filter_blocks_page3)
        blocks_layout.addWidget(self.search_box_page3)
        
        self.block_list_page3 = QListWidget()
        self.block_list_page3.itemClicked.connect(self.on_block_selected_page3)
        blocks_layout.addWidget(self.block_list_page3)
        
        blocks_group.setLayout(blocks_layout)
        layout.addWidget(blocks_group)
        
        # Selected block info
        self.selected_block_label = QLabel("No block selected - click a block in the browser or select from the list above")
        self.selected_block_label.setStyleSheet("""
            font-size: 11pt;
            padding: 15px;
            background: #fff3cd;
            border-left: 4px solid #ffc107;
            border-radius: 5px;
        """)
        self.selected_block_label.setWordWrap(True)
        layout.addWidget(self.selected_block_label)
        
        # Navigation buttons
        nav_layout = QHBoxLayout()
        
        back_btn = QPushButton("← Back")
        back_btn.setMinimumSize(120, 45)
        back_btn.setStyleSheet("""
            QPushButton {
                background-color: #757575;
                color: white;
                font-size: 12pt;
                font-weight: bold;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #616161;
            }
        """)
        back_btn.clicked.connect(lambda: self.pages.setCurrentIndex(0))
        nav_layout.addWidget(back_btn)
        
        nav_layout.addStretch()
        
        self.continue_btn_page3 = QPushButton("Continue →")
        self.continue_btn_page3.setEnabled(False)
        self.continue_btn_page3.setMinimumSize(150, 45)
        self.continue_btn_page3.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-size: 13pt;
                font-weight: bold;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
        """)
        self.continue_btn_page3.clicked.connect(self.go_to_analysis)
        nav_layout.addWidget(self.continue_btn_page3)
        
        layout.addLayout(nav_layout)
        
        return page
    
    def create_page4_analysis(self):
        """Page 4: Detailed IR analysis"""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(5)
        
        # Header
        header_layout = QHBoxLayout()
        
        title = QLabel("📊 LLVM IR Analysis")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title.setFont(title_font)
        header_layout.addWidget(title)
        
        header_layout.addStretch()
        
        layout.addLayout(header_layout)
        
        # Selected function info - smaller fixed height
        self.function_info = QTextEdit()
        self.function_info.setReadOnly(True)
        self.function_info.setFixedHeight(80)
        self.function_info.setStyleSheet("""
            font-size: 9pt;
            padding: 8px;
            background: #e8f5e9;
            border-left: 4px solid #4CAF50;
        """)
        layout.addWidget(self.function_info)
        
        # Main splitter - give it stretch priority
        main_splitter = QSplitter(Qt.Horizontal)
        
        # Left: Block index
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        index_label = QLabel("Block Index:")
        index_label.setStyleSheet("font-weight: bold; font-size: 11pt;")
        left_layout.addWidget(index_label)
        
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("🔍 Search blocks...")
        self.search_box.textChanged.connect(self.filter_blocks)
        left_layout.addWidget(self.search_box)
        
        self.block_list = QListWidget()
        self.block_list.itemClicked.connect(self.on_list_item_clicked)
        left_layout.addWidget(self.block_list)
        
        main_splitter.addWidget(left_widget)
        
        # Right: Code tabs
        from PyQt5.QtWidgets import QTabWidget
        code_tabs = QTabWidget()
        
        # LLVM IR tab
        self.ir_text = QTextEdit()
        self.ir_text.setReadOnly(True)
        self.ir_text.setStyleSheet("font-family: 'Courier New', monospace; font-size: 10pt;")
        self.ir_text.setPlaceholderText("Select a block to view LLVM IR...")
        code_tabs.addTab(self.ir_text, "📄 LLVM IR")
        
        # Source code tab
        self.cpp_text = QTextEdit()
        self.cpp_text.setReadOnly(True)
        self.cpp_text.setStyleSheet("font-family: 'Courier New', monospace; font-size: 10pt;")
        self.cpp_text.setPlaceholderText("Select a block to view source code...")
        code_tabs.addTab(self.cpp_text, "💻 Source Code")
        
        # CFG tab
        cfg_widget = QWidget()
        cfg_layout = QVBoxLayout(cfg_widget)
        cfg_layout.setContentsMargins(0, 0, 0, 0)
        
        cfg_toolbar = QHBoxLayout()
        zoom_in = QPushButton("🔍+")
        zoom_in.clicked.connect(self.cfg_zoom_in)
        zoom_out = QPushButton("🔍-")
        zoom_out.clicked.connect(self.cfg_zoom_out)
        fit_view = QPushButton("⬜ Fit")
        fit_view.clicked.connect(self.cfg_fit_view)
        reset_zoom = QPushButton("🔄 Reset")
        reset_zoom.clicked.connect(self.cfg_reset_zoom)
        
        cfg_toolbar.addWidget(zoom_in)
        cfg_toolbar.addWidget(zoom_out)
        cfg_toolbar.addWidget(fit_view)
        cfg_toolbar.addWidget(reset_zoom)
        cfg_toolbar.addStretch()
        cfg_layout.addLayout(cfg_toolbar)
        
        self.cfg_view = QGraphicsView()
        self.cfg_scene = QGraphicsScene()
        self.cfg_view.setScene(self.cfg_scene)
        self.cfg_view.setDragMode(QGraphicsView.ScrollHandDrag)
        cfg_layout.addWidget(self.cfg_view)
        
        code_tabs.addTab(cfg_widget, "🔀 CFG")
        
        main_splitter.addWidget(code_tabs)
        main_splitter.setSizes([300, 1000])
        
        # Give splitter maximum space - stretch factor
        layout.addWidget(main_splitter, stretch=1)
        
        # Navigation - compact
        nav_layout = QHBoxLayout()
        
        back_btn = QPushButton("← Back to Flamegraph")
        back_btn.setMinimumSize(150, 40)
        back_btn.setStyleSheet("""
            QPushButton {
                background-color: #757575;
                color: white;
                font-size: 11pt;
                font-weight: bold;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #616161;
            }
        """)
        back_btn.clicked.connect(lambda: self.pages.setCurrentIndex(2))
        nav_layout.addWidget(back_btn)
        
        nav_layout.addStretch()
        
        layout.addLayout(nav_layout, stretch=0)
        
        return page
    
    # Remove all the old UI code that was here
    def set_language(self, language):
        """Set the programming language"""
        self.language = language
        
    def set_opt_level(self, level):
        """Set the optimization level"""
        self.opt_level = level
        
    def upload_file(self):
        """Upload source file"""
        file_filter = "Source Files (*.cpp *.cc *.cxx *.go *.rs);;All Files (*)"
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Source Code File",
            "",
            file_filter
        )
        
        if file_path:
            self.cpp_file = file_path
            self.file_path_label.setText(f"✓ Selected: {file_path}")
            self.file_path_label.setStyleSheet("font-size: 11pt; color: #4CAF50; font-weight: bold; padding: 10px;")
            self.continue_btn_page1.setEnabled(True)
    
    def start_processing(self):
        """Start compilation and profiling - called from page 1 continue button"""
        # Go to loading page
        self.pages.setCurrentIndex(1)
        self.log_text.clear()
        self.log_text.append("Starting compilation and profiling...\n")
        
        # Start worker thread
        self.worker = CompilationWorker(
            self.cpp_file,
            self.language,
            self.opt_level,
            self.scripts_dir
        )
        
        self.worker.progress.connect(self.update_log)
        self.worker.finished.connect(self.on_processing_finished)
        self.worker.error.connect(self.on_processing_error)
        
        self.worker.start()
    
    def on_processing_finished(self, success, output_file, html_file):
        """Handle processing completion"""
        if success and html_file and Path(html_file).exists():
            self.flamegraph_path = html_file
            self.output_executable = output_file
            self.log_text.append("\n" + "="*50)
            self.log_text.append("✓ SUCCESS!")
            self.log_text.append(f"Executable: {output_file}")
            self.log_text.append(f"Flamegraph: {html_file}")
            self.log_text.append("="*50)
            
            # Parse blocks
            self.parse_flamegraph_blocks()
            
            # Start server
            self.server.start(self.flamegraph_path)
            
            # Auto-advance to flamegraph page after 2 seconds
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(2000, self.go_to_flamegraph_page)
        else:
            self.log_text.append("\n⚠ Processing completed but flamegraph was not generated")
            QMessageBox.warning(self, "Warning", "Compilation succeeded but flamegraph generation failed.\n\nCheck the log for details.")
    
    def go_to_flamegraph_page(self):
        """Go to flamegraph page and open browser"""
        self.pages.setCurrentIndex(2)
        # Populate the block list on page 3
        self.populate_block_list_page3()
        # Auto-open flamegraph in browser
        self.open_flamegraph_browser()
    
    def populate_block_list_page3(self, filter_text=""):
        """Populate block list on page 3"""
        self.block_list_page3.clear()
        filter_lower = filter_text.lower()
        
        for block in self.all_blocks:
            if not filter_text or filter_lower in block['full'].lower():
                self.block_list_page3.addItem(block['full'])
    
    def filter_blocks_page3(self, text):
        """Filter blocks on page 3"""
        self.populate_block_list_page3(text)
    
    def on_block_selected_page3(self, item):
        """Handle block selection on page 3"""
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
            
            # Store complete info for page 4
            self.selected_function = function
            self.selected_detail = details
            self.selected_percent = percent
            
            self.selected_block_label.setText(f"✓ Selected: {function}\n{details}")
            self.continue_btn_page3.setEnabled(True)
    
    def go_to_analysis(self):
        """Go to analysis page"""
        if self.selected_function:
            self.pages.setCurrentIndex(3)
            # Use stored info from page 3 selection
            detail = getattr(self, 'selected_detail', '')
            percent = getattr(self, 'selected_percent', 0.0)
            self.display_block_info(self.selected_function, detail, percent)
    
    # Page navigation and processing methods
    def update_log(self, message):
        """Update the log text"""
        self.log_text.append(message)
        self.log_text.verticalScrollBar().setValue(
            self.log_text.verticalScrollBar().maximum()
        )
    
    def on_processing_finished(self, success, output_file, html_file):
        """Handle processing completion - page-based version"""
        if success and html_file and Path(html_file).exists():
            self.flamegraph_path = html_file
            self.output_executable = output_file
            self.log_text.append("\n" + "="*50)
            self.log_text.append("✓ SUCCESS!")
            self.log_text.append(f"Executable: {output_file}")
            self.log_text.append(f"Flamegraph: {html_file}")
            self.log_text.append("="*50)
            
            # Parse blocks
            self.parse_flamegraph_blocks()
            
            # Start server
            self.server.start(self.flamegraph_path)
            
            # Auto-advance to flamegraph page after 2 seconds
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(2000, self.go_to_flamegraph_page)
        else:
            self.log_text.append("\n⚠ Processing completed but flamegraph was not generated")
            QMessageBox.warning(self, "Warning", "Compilation succeeded but flamegraph generation failed.\n\nCheck the log for details.")
    
    def on_processing_error(self, error_type, error_message):
        """Handle processing errors"""
        if error_type == "perf_permission":
            # Show dialog with instructions to fix perf permissions
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Warning)
            msg.setWindowTitle("Perf Permission Required")
            msg.setText("Perf profiling requires system configuration to run without sudo.")
            
            detailed_text = f"""Error details:
{error_message}

To fix this, run ONE of the following commands in a terminal:

Option 1 (Temporary - until reboot):
    sudo sysctl -w kernel.perf_event_paranoid=-1

Option 2 (Permanent):
    echo 'kernel.perf_event_paranoid=-1' | sudo tee -a /etc/sysctl.conf
    sudo sysctl -p

Option 3 (Alternative permanent):
    echo 'kernel.perf_event_paranoid=-1' | sudo tee /etc/sysctl.d/99-perf.conf
    sudo sysctl --system

After running one of these commands, try processing again.

Note: Setting perf_event_paranoid to -1 allows all users to use perf.
For more restrictive settings, use 0 (allow kernel profiling) or 1 (allow CPU event access).
"""
            
            msg.setDetailedText(detailed_text)
            msg.setStandardButtons(QMessageBox.Ok)
            
            # Add a button to copy the command
            copy_button = msg.addButton("Copy Fix Command", QMessageBox.ActionRole)
            
            msg.exec_()
            
            if msg.clickedButton() == copy_button:
                clipboard = QApplication.clipboard()
                clipboard.setText("sudo sysctl -w kernel.perf_event_paranoid=-1")
                QMessageBox.information(self, "Copied", "Command copied to clipboard!\n\nPaste it in a terminal and run it.")
    
    def parse_flamegraph_blocks(self):
        """Parse blocks from the HTML flamegraph"""
        if not self.flamegraph_path:
            return
        
        self.all_blocks = []
        
        try:
            with open(self.flamegraph_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Parse block divs
            pattern = r'<div class="block"[^>]*data-name="([^"]*)"[^>]*data-samples="([^"]*)"[^>]*data-percent="([^"]*)"[^>]*data-depth="([^"]*)"'
            matches = re.findall(pattern, content)
            
            for name, samples, percent, depth in matches:
                self.all_blocks.append({
                    'name': name,
                    'samples': samples,
                    'percent': percent,
                    'depth': depth,
                    'full': f"{name} ({samples} samples, {percent}%)"
                })
            
            self.populate_block_list()
            # Don't try to update flamegraph_info - it doesn't exist in page-based UI
            
        except Exception as e:
            print(f"Error parsing flamegraph: {e}")
    
    def populate_block_list(self, filter_text=""):
        """Populate block list"""
        self.block_list.clear()
        filter_lower = filter_text.lower()
        
        for block in self.all_blocks:
            if not filter_text or filter_lower in block['full'].lower():
                self.block_list.addItem(block['full'])
    
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
        
        if current_page == 2:  # Page 3 (flamegraph selection page)
            # Update selection on page 3
            self.selected_function = function
            self.selected_detail = detail
            self.selected_percent = percent
            self.selected_block_label.setText(f"✓ Selected: {function}\n{detail}")
            self.continue_btn_page3.setEnabled(True)
        elif current_page == 3:  # Page 4 (analysis page)
            # Display full analysis
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
        
        # Load function code
        self.load_function_code(function)
    
    def load_function_code(self, function_name):
        """Load IR and source code for function"""
        if not self.flamegraph_path:
            return
        
        flamegraph_dir = Path(self.flamegraph_path).parent
        
        # Find IR files
        ir_files = list(flamegraph_dir.glob("*.ll"))
        cpp_files = list(flamegraph_dir.glob("*.cpp")) + list(flamegraph_dir.glob("*.cc"))
        cfg_dirs = [d for d in flamegraph_dir.glob("*_cfg") if d.is_dir()]
        
        # Load IR
        ir_content = self.find_function_in_ir(function_name, ir_files)
        if ir_content:
            self.ir_text.setPlainText(ir_content)
        else:
            self.ir_text.setPlainText(f"Could not find IR for function: {function_name}")
        
        # Load C++ source
        cpp_content = self.find_function_in_cpp(function_name, cpp_files)
        if cpp_content:
            self.cpp_text.setPlainText(cpp_content)
        else:
            self.cpp_text.setPlainText(f"Could not find source for function: {function_name}")
        
        # Load CFG
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
                        # Extract function
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
                        # Extract surrounding context
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
                        # Generate PNG from dot
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
