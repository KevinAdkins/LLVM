#!/usr/bin/env python3
"""
Flamegraph Viewer
- Opens flamegraph in browser
- Receives block clicks via TCP
- Shows searchable block index
"""

import json
import sys
import webbrowser
import socket
import threading
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFileDialog, QListWidget, QLineEdit,
    QTextEdit, QSplitter, QMessageBox, QTabWidget, QSizePolicy,
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem
)
from PyQt5.QtCore import Qt, QObject, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QPixmap, QImage


# Global UI Configuration
WINDOW_WIDTH = 1800
WINDOW_HEIGHT = 1000
LEFT_PANEL_WIDTH = 400
RIGHT_PANEL_WIDTH = 1400
CODE_VIEW_HEIGHT = 800
BLOCK_INFO_HEIGHT = 140
TOOLBAR_HEIGHT = 40
MIN_TEXT_HEIGHT = 700


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
    blockClicked = pyqtSignal(str, str, float)  # function, detail, percent
    
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
                path = super().translate_path(path)
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


class FlamegraphViewer(QMainWindow):
    """Main application window"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Flamegraph Viewer")
        self.setGeometry(100, 100, WINDOW_WIDTH, WINDOW_HEIGHT)
        self.setMinimumSize(1400, 800)
        
        self.flamegraph_path = None
        self.all_blocks = []
        self.server = FlameGraphServer()
        self.server.blockClicked.connect(self.on_block_clicked)
        
        self.init_ui()
    
    def init_ui(self):
        """Initialize UI components"""
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(5)
        
        # Top toolbar - compact
        toolbar = QHBoxLayout()
        toolbar.setSpacing(5)
        
        self.load_btn = QPushButton("📂 Load")
        self.load_btn.clicked.connect(self.load_flamegraph)
        toolbar.addWidget(self.load_btn)
        
        self.open_browser_btn = QPushButton("🌐 Browser")
        self.open_browser_btn.clicked.connect(self.open_browser)
        self.open_browser_btn.setEnabled(False)
        toolbar.addWidget(self.open_browser_btn)
        
        self.status_label = QLabel("No flamegraph loaded")
        self.status_label.setStyleSheet("font-size: 11pt;")
        toolbar.addWidget(self.status_label, stretch=1)
        
        main_layout.addLayout(toolbar)
        
        # Main horizontal split: Left (block list) and Right (code views)
        main_splitter = QSplitter(Qt.Horizontal)
        
        # Left side: Block index and info
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(3)
        
        # Selected block info panel - compact header
        info_label = QLabel("Selected Block:")
        info_label.setStyleSheet("font-weight: bold; font-size: 10pt;")
        left_layout.addWidget(info_label)
        
        self.block_info = QTextEdit()
        self.block_info.setReadOnly(True)
        self.block_info.setPlaceholderText("Click a block in the browser or select from the list below...")
        self.block_info.setMinimumHeight(80)
        self.block_info.setMaximumHeight(120)
        self.block_info.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        left_layout.addWidget(self.block_info)
        
        # Block index panel - compact header
        index_label = QLabel("Block Index:")
        index_label.setStyleSheet("font-weight: bold; font-size: 10pt;")
        left_layout.addWidget(index_label)
        
        # Search box
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("🔍 Search blocks...")
        self.search_box.textChanged.connect(self.filter_blocks)
        left_layout.addWidget(self.search_box)
        
        # Block list
        self.block_list = QListWidget()
        self.block_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.block_list.itemClicked.connect(self.on_list_item_clicked)
        left_layout.addWidget(self.block_list, stretch=1)
        
        main_splitter.addWidget(left_widget)
        
        # Right side: Tabbed view for IR, C++ source, and CFG
        right_tabs = QTabWidget()
        right_tabs.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        # Tab 1: LLVM IR
        ir_widget = QWidget()
        ir_layout = QVBoxLayout(ir_widget)
        ir_layout.setContentsMargins(0, 0, 0, 0)
        
        self.ir_text = QTextEdit()
        self.ir_text.setReadOnly(True)
        self.ir_text.setPlaceholderText("Select a block to view its LLVM IR code...")
        self.ir_text.setStyleSheet("QTextEdit { font-family: 'Courier New', monospace; font-size: 10pt; }")
        self.ir_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        ir_layout.addWidget(self.ir_text, stretch=1)
        
        right_tabs.addTab(ir_widget, "📄 LLVM IR")
        
        # Tab 2: C++ Source
        cpp_widget = QWidget()
        cpp_layout = QVBoxLayout(cpp_widget)
        cpp_layout.setContentsMargins(0, 0, 0, 0)
        
        self.cpp_text = QTextEdit()
        self.cpp_text.setReadOnly(True)
        self.cpp_text.setPlaceholderText("C++ source code will appear here when available...")
        self.cpp_text.setStyleSheet("QTextEdit { font-family: 'Courier New', monospace; font-size: 10pt; }")
        self.cpp_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        cpp_layout.addWidget(self.cpp_text, stretch=1)
        
        right_tabs.addTab(cpp_widget, "💻 C++ Source")
        
        # Tab 3: CFG Visualization
        cfg_widget = QWidget()
        cfg_layout = QVBoxLayout(cfg_widget)
        cfg_layout.setContentsMargins(0, 0, 0, 0)
        
        # CFG toolbar with zoom controls
        cfg_toolbar = QHBoxLayout()
        cfg_toolbar.setSpacing(5)
        
        zoom_in_btn = QPushButton("🔍+ Zoom In")
        zoom_in_btn.clicked.connect(self.cfg_zoom_in)
        cfg_toolbar.addWidget(zoom_in_btn)
        
        zoom_out_btn = QPushButton("🔍- Zoom Out")
        zoom_out_btn.clicked.connect(self.cfg_zoom_out)
        cfg_toolbar.addWidget(zoom_out_btn)
        
        fit_btn = QPushButton("⬜ Fit View")
        fit_btn.clicked.connect(self.cfg_fit_view)
        cfg_toolbar.addWidget(fit_btn)
        
        reset_btn = QPushButton("🔄 Reset")
        reset_btn.clicked.connect(self.cfg_reset_zoom)
        cfg_toolbar.addWidget(reset_btn)
        
        cfg_toolbar.addStretch(1)
        
        cfg_layout.addLayout(cfg_toolbar)
        
        self.cfg_view = QGraphicsView()
        self.cfg_scene = QGraphicsScene()
        self.cfg_view.setScene(self.cfg_scene)
        self.cfg_view.setDragMode(QGraphicsView.ScrollHandDrag)
        self.cfg_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        cfg_layout.addWidget(self.cfg_view, stretch=1)
        
        right_tabs.addTab(cfg_widget, "🔀 CFG")
        
        main_splitter.addWidget(right_tabs)
        
        # Set initial sizes (left panel vs right panel)
        main_splitter.setSizes([LEFT_PANEL_WIDTH, RIGHT_PANEL_WIDTH])
        
        main_layout.addWidget(main_splitter, stretch=1)
    
    def load_flamegraph(self):
        """Load flamegraph HTML file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Flamegraph HTML",
            "",
            "HTML Files (*.html);;All Files (*)"
        )
        
        if not file_path:
            return
        
        self.flamegraph_path = Path(file_path)
        
        # Parse blocks from HTML
        self.parse_flamegraph_blocks()
        
        # Start server
        if self.server.start(self.flamegraph_path):
            self.status_label.setText(f"Loaded: {self.flamegraph_path.name}")
            self.open_browser_btn.setEnabled(True)
            QMessageBox.information(
                self,
                "Ready",
                "Flamegraph loaded! Click 'Open in Browser' to view it."
            )
        else:
            QMessageBox.critical(
                self,
                "Error",
                "Failed to start HTTP server"
            )
    
    def parse_flamegraph_blocks(self):
        """Extract all blocks from flamegraph HTML - each block separately, no grouping"""
        self.all_blocks = []
        
        try:
            with open(self.flamegraph_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Parse individual block divs from the HTML
            # Each block is a <div class="block" ...>
            import re
            
            # Find all block divs with their data attributes
            pattern = r'<div class="block"[^>]*data-name="([^"]*)"[^>]*data-samples="([^"]*)"[^>]*data-percent="([^"]*)"[^>]*data-depth="([^"]*)"'
            matches = re.findall(pattern, content)
            
            block_id = 1
            for name, samples, percent, depth in matches:
                # Unescape HTML entities
                name = name.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"')
                
                # Create unique entry for each block (no deduplication)
                full_text = f"{name} ({samples} samples, {percent}%)"
                
                self.all_blocks.append({
                    'id': block_id,
                    'function': name,
                    'samples': samples,
                    'percent': percent,
                    'depth': depth,
                    'detail': f"{samples} samples, {percent}%",
                    'full': full_text
                })
                block_id += 1
            
            print(f"Found {len(self.all_blocks)} individual blocks (no grouping)")
            
            # Populate list
            self.populate_block_list()
            
        except Exception as e:
            print(f"Error parsing flamegraph: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.warning(
                self,
                "Parse Warning",
                f"Could not parse all blocks: {e}\n\nYou can still use the browser to click blocks."
            )
    
    def populate_block_list(self, filter_text=""):
        """Populate the block list widget"""
        self.block_list.clear()
        
        filter_lower = filter_text.lower()
        
        for block in self.all_blocks:
            if not filter_text or filter_lower in block['full'].lower():
                self.block_list.addItem(block['full'])
    
    def filter_blocks(self, text):
        """Filter blocks based on search text"""
        self.populate_block_list(text)
    
    def open_browser(self):
        """Open flamegraph in browser"""
        if not self.flamegraph_path:
            return
        
        url = f"http://localhost:{self.server.port}/{self.flamegraph_path.name}"
        
        # Inject click handler script
        self.inject_click_handler()
        
        webbrowser.open(url)
        self.status_label.setText("Browser opened - click blocks to select them")
    
    def inject_click_handler(self):
        """Modify HTML to send clicks to our server"""
        try:
            with open(self.flamegraph_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Check if already injected
            if 'CLICK_HANDLER_INJECTED' in content:
                return
            
            # Inject script before </body>
            inject_script = """
<script>
// CLICK_HANDLER_INJECTED
document.addEventListener('DOMContentLoaded', function() {
    var svg = document.querySelector('svg');
    if (!svg) return;
    
    svg.addEventListener('click', function(e) {
        var target = e.target;
        while (target && target.tagName !== 'g') {
            target = target.parentElement;
        }
        
        if (target) {
            var titleEl = target.querySelector('title');
            if (titleEl) {
                var text = titleEl.textContent;
                var match = text.match(/^(.+?)\\s+\\(([^,]+),\\s*([^)]+)\\)/);
                
                if (match) {
                    var data = {
                        function: match[1],
                        detail: match[2] + ', ' + match[3],
                        percent: parseFloat(match[3])
                    };
                    
                    fetch('http://localhost:8765/', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify(data)
                    }).catch(err => console.log('Send failed:', err));
                }
            }
        }
    });
});
</script>
</body>"""
            
            content = content.replace('</body>', inject_script)
            
            # Write back
            with open(self.flamegraph_path, 'w', encoding='utf-8') as f:
                f.write(content)
                
        except Exception as e:
            print(f"Error injecting handler: {e}")
    
    @pyqtSlot(str, str, float)
    def on_block_clicked(self, function, detail, percent):
        """Handle block click from browser"""
        self.display_block_info(function, detail, percent)
    
    def on_list_item_clicked(self, item):
        """Handle block selection from list"""
        text = item.text()
        
        # Parse the text
        parts = text.split(' (')
        if len(parts) >= 2:
            function = parts[0]
            details = parts[1].rstrip(')')
            
            # Extract percent
            percent = 0.0
            if '%' in details:
                try:
                    percent_str = details.split(',')[-1].strip().rstrip('%')
                    percent = float(percent_str)
                except:
                    pass
            
            self.display_block_info(function, details, percent)
    
    def display_block_info(self, function, detail, percent):
        """Display selected block information and load corresponding code"""
        info = f"""Function: {function}
        
Details: {detail}

Percentage: {percent:.2f}%

Bottleneck Analysis:
- This function accounts for {percent:.2f}% of total execution time
- Review the IR and C++ code on the right to identify optimization opportunities
"""
        self.block_info.setPlainText(info)
        self.status_label.setText(f"Selected: {function} ({percent:.2f}%)")
        
        # Load IR and C++ source for this function
        self.load_function_code(function)
    
    def load_function_code(self, function_name):
        """Load IR and C++ source code for the given function using multiple trace sources"""
        # Look for files in the same directory as flamegraph
        if not self.flamegraph_path:
            self.ir_text.setPlainText("No flamegraph loaded")
            self.cpp_text.setPlainText("No flamegraph loaded")
            return
        
        flamegraph_dir = self.flamegraph_path.parent
        
        # Find related files
        ir_files = list(flamegraph_dir.glob("*.ll"))
        cpp_files = list(flamegraph_dir.glob("*.cpp")) + list(flamegraph_dir.glob("*.cc"))
        asm_files = list(flamegraph_dir.glob("*.s"))
        yaml_files = list(flamegraph_dir.glob("*.opt.yaml"))
        cfg_dirs = [d for d in flamegraph_dir.glob("*_cfg") if d.is_dir()]
        
        # Try to find source location from YAML optimization remarks
        source_info = self.find_function_in_yaml(function_name, yaml_files)
        
        # Load IR
        ir_content = self.find_function_in_ir(function_name, ir_files)
        if ir_content:
            # Add source location if found
            if source_info:
                ir_content = f"; Source location from optimization remarks:\n; {source_info}\n\n{ir_content}"
            self.ir_text.setPlainText(ir_content)
        else:
            # Try assembly file if IR not found
            asm_content = self.find_function_in_asm(function_name, asm_files)
            if asm_content:
                if source_info:
                    asm_content = f"; Source location: {source_info}\n\n{asm_content}"
                self.ir_text.setPlainText(asm_content)
            else:
                self.ir_text.setPlainText(f"IR/Assembly not found for: {function_name}\n\nSearched in: {flamegraph_dir}")
        
        # Load C++ source - use source info from YAML if available
        if source_info and 'file' in source_info and 'line' in source_info:
            cpp_content = self.load_cpp_from_location(source_info['file'], source_info['line'])
            if cpp_content:
                self.cpp_text.setPlainText(cpp_content)
            else:
                # Fallback to function name search
                cpp_content = self.find_function_in_cpp(function_name, cpp_files)
                if cpp_content:
                    self.cpp_text.setPlainText(cpp_content)
                else:
                    self.cpp_text.setPlainText(f"C++ source not found for: {function_name}\n\nSearched in: {flamegraph_dir}")
        else:
            # Fallback to function name search
            cpp_content = self.find_function_in_cpp(function_name, cpp_files)
            if cpp_content:
                self.cpp_text.setPlainText(cpp_content)
            else:
                self.cpp_text.setPlainText(f"C++ source not found for: {function_name}\n\nSearched in: {flamegraph_dir}")
        
        # Load CFG
        cfg_image_path = self.find_function_in_cfg(function_name, cfg_dirs)
        if cfg_image_path:
            # Load and display the image
            pixmap = QPixmap(cfg_image_path)
            if not pixmap.isNull():
                self.cfg_scene.clear()
                self.cfg_scene.addPixmap(pixmap)
                self.cfg_view.fitInView(self.cfg_scene.sceneRect(), Qt.KeepAspectRatio)
            else:
                self.cfg_scene.clear()
                text_item = self.cfg_scene.addText(f"Failed to load CFG image: {cfg_image_path}")
        else:
            self.cfg_scene.clear()
            text_item = self.cfg_scene.addText(f"CFG not found for: {function_name}\n\nSearched in: {flamegraph_dir}\n\nNote: Install graphviz if not available: sudo apt install graphviz")
    
    def find_function_in_yaml(self, function_name, yaml_files):
        """Extract source location from optimization remarks YAML"""
        import re
        try:
            import yaml
        except ImportError:
            return None
        
        for yaml_file in yaml_files:
            try:
                with open(yaml_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Look for function references in YAML
                # Parse YAML documents
                for doc in yaml.safe_load_all(content):
                    if not doc:
                        continue
                    
                    # Check if this remark is about our function
                    func = doc.get('Function', '')
                    if function_name in func or func in function_name:
                        debug_loc = doc.get('DebugLoc', {})
                        if debug_loc:
                            file_path = debug_loc.get('File', '')
                            line = debug_loc.get('Line', 0)
                            column = debug_loc.get('Column', 0)
                            
                            # Extract just the filename from full path
                            if '/' in file_path:
                                file_path = file_path.split('/')[-1]
                            
                            return {
                                'file': file_path,
                                'line': line,
                                'column': column,
                                'pass': doc.get('Pass', ''),
                                'name': doc.get('Name', '')
                            }
                    
                    # Also check Args for function references
                    args = doc.get('Args', [])
                    for arg in args:
                        if isinstance(arg, dict):
                            callee = arg.get('Callee', '')
                            caller = arg.get('Caller', '')
                            if function_name in callee or function_name in caller:
                                debug_loc = arg.get('DebugLoc', {})
                                if debug_loc:
                                    file_path = debug_loc.get('File', '')
                                    line = debug_loc.get('Line', 0)
                                    if '/' in file_path:
                                        file_path = file_path.split('/')[-1]
                                    return {'file': file_path, 'line': line, 'column': 0}
                
            except Exception as e:
                print(f"Error reading YAML {yaml_file}: {e}")
        
        return None
    
    def find_function_in_asm(self, function_name, asm_files):
        """Find and extract function from assembly files"""
        import re
        
        for asm_file in asm_files:
            try:
                with open(asm_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                
                # Look for function label
                for i, line in enumerate(lines):
                    if function_name in line and (':' in line or '@function' in line):
                        # Found the function, extract it
                        start = i
                        
                        # Find the end (next function or end marker)
                        end = len(lines)
                        for j in range(i + 1, len(lines)):
                            if '.size' in lines[j] and function_name in lines[j]:
                                end = j + 1
                                break
                            elif (lines[j].startswith('.') and 'function' in lines[j]) or \
                                 (lines[j].strip().endswith(':') and '@' in lines[j-1] if j > 0 else False):
                                end = j
                                break
                        
                        asm_code = ''.join(lines[start:end])
                        return f"; Found in: {asm_file.name}\n; Assembly code\n\n{asm_code}"
                
            except Exception as e:
                print(f"Error reading assembly file {asm_file}: {e}")
        
        return None
    
    def find_function_in_cfg(self, function_name, cfg_dirs):
        """Find function CFG and render it as an image"""
        import re
        import subprocess
        import tempfile
        
        for cfg_dir in cfg_dirs:
            # Look for .dot files with function name
            dot_files = list(cfg_dir.glob(f"*{function_name}*.dot"))
            if not dot_files:
                # Try to find any .dot files and search content
                dot_files = list(cfg_dir.glob("*.dot"))
            
            for dot_file in dot_files:
                try:
                    with open(dot_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    if function_name in content or dot_file.stem.endswith(function_name):
                        # Render DOT to PNG using graphviz
                        try:
                            output_png = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
                            result = subprocess.run(
                                ['dot', '-Tpng', str(dot_file), '-o', output_png.name],
                                capture_output=True,
                                text=True,
                                timeout=10
                            )
                            
                            if result.returncode == 0:
                                return output_png.name
                            else:
                                print(f"graphviz error: {result.stderr}")
                                # Fall back to returning dot content as text
                                return None
                        except FileNotFoundError:
                            print("graphviz 'dot' command not found. Install with: sudo apt install graphviz")
                            return None
                        except subprocess.TimeoutExpired:
                            print(f"Timeout rendering {dot_file}")
                            return None
                
                except Exception as e:
                    print(f"Error reading CFG {dot_file}: {e}")
        
        return None
    
    def load_cpp_from_location(self, filename, line_num):
        """Load C++ source code around a specific line number"""
        if not self.flamegraph_path:
            return None
        
        flamegraph_dir = self.flamegraph_path.parent
        
        # Find the source file
        cpp_files = list(flamegraph_dir.glob(filename))
        if not cpp_files:
            cpp_files = list(flamegraph_dir.glob(f"**/{filename}"))
        
        for cpp_file in cpp_files:
            try:
                with open(cpp_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                
                # Extract context around the line (±20 lines)
                start = max(0, line_num - 20)
                end = min(len(lines), line_num + 20)
                
                context_lines = []
                for i in range(start, end):
                    prefix = ">>> " if i == line_num - 1 else "    "
                    context_lines.append(f"{prefix}{i+1:4d}: {lines[i]}")
                
                return f"// Found in: {cpp_file.name}\n// Highlighted line {line_num}\n\n{''.join(context_lines)}"
            
            except Exception as e:
                print(f"Error reading C++ file {cpp_file}: {e}")
        
        return None
    
    def find_function_in_ir(self, function_name, ir_files):
        """Find and extract function from IR files"""
        import re
        
        # Clean up the function name for matching
        # Handle mangled names
        search_patterns = [
            function_name,
            f"@{function_name}",
            function_name.split('::')[-1] if '::' in function_name else function_name
        ]
        
        for ir_file in ir_files:
            try:
                with open(ir_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Look for function definition
                for pattern in search_patterns:
                    # Match function definition: define ... @function_name(...)
                    match = re.search(rf'define[^@]*@[^(]*{re.escape(pattern)}[^{{]*\{{', content, re.IGNORECASE)
                    if match:
                        # Extract the entire function
                        start = match.start()
                        
                        # Find the matching closing brace
                        brace_count = 0
                        in_function = False
                        end = start
                        
                        for i in range(start, len(content)):
                            if content[i] == '{':
                                brace_count += 1
                                in_function = True
                            elif content[i] == '}':
                                brace_count -= 1
                                if in_function and brace_count == 0:
                                    end = i + 1
                                    break
                        
                        function_code = content[start:end]
                        return f"; Found in: {ir_file.name}\n\n{function_code}"
                
            except Exception as e:
                print(f"Error reading IR file {ir_file}: {e}")
        
        return None
    
    def find_function_in_cpp(self, function_name, cpp_files):
        """Find and extract function from C++ source files"""
        import re
        
        # Clean up function name - remove C++ mangling, templates, etc.
        # Extract the base function name
        clean_name = function_name
        
        # Remove template parameters
        clean_name = re.sub(r'<[^>]+>', '', clean_name)
        
        # Get last part after ::
        if '::' in clean_name:
            parts = clean_name.split('::')
            clean_name = parts[-1]
        
        # Remove parameter list if present
        clean_name = clean_name.split('(')[0].strip()
        
        for cpp_file in cpp_files:
            try:
                with open(cpp_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                
                # Look for function definition
                for i, line in enumerate(lines):
                    # Match function definitions (simple heuristic)
                    if clean_name in line and ('(' in line) and ('{' in line or (i + 1 < len(lines) and '{' in lines[i + 1])):
                        # Found potential match, extract function body
                        start_line = i
                        
                        # Find opening brace
                        brace_line = i
                        while brace_line < len(lines) and '{' not in lines[brace_line]:
                            brace_line += 1
                        
                        if brace_line >= len(lines):
                            continue
                        
                        # Count braces to find end
                        brace_count = 0
                        end_line = brace_line
                        
                        for j in range(brace_line, len(lines)):
                            brace_count += lines[j].count('{')
                            brace_count -= lines[j].count('}')
                            if brace_count == 0:
                                end_line = j + 1
                                break
                        
                        function_code = ''.join(lines[start_line:end_line])
                        return f"// Found in: {cpp_file.name}\n\n{function_code}"
                
            except Exception as e:
                print(f"Error reading C++ file {cpp_file}: {e}")
        
        return None
    
    def cfg_zoom_in(self):
        """Zoom in on CFG view"""
        self.cfg_view.scale(1.2, 1.2)
    
    def cfg_zoom_out(self):
        """Zoom out on CFG view"""
        self.cfg_view.scale(1/1.2, 1/1.2)
    
    def cfg_fit_view(self):
        """Fit CFG to view"""
        self.cfg_view.fitInView(self.cfg_scene.sceneRect(), Qt.KeepAspectRatio)
    
    def cfg_reset_zoom(self):
        """Reset CFG zoom to 100%"""
        self.cfg_view.resetTransform()
    
    def closeEvent(self, event):
        """Clean up on exit"""
        self.server.stop()
        event.accept()


def main():
    app = QApplication(sys.argv)
    viewer = FlamegraphViewer()
    viewer.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
