# LLVM Performance Analysis Wizard
Software Engineering Project  
Kevin Adkins, Jorge Munoz, Travis Shos, Eric Gerner

## Overview
An interactive GUI tool for analyzing and optimizing code performance using LLVM IR, flamegraphs, and control flow graphs. This wizard guides you through profiling your code and identifying performance bottlenecks.

## Features
- 🔥 **Interactive Flamegraph Visualization** - Visual representation of CPU time per function
- 📊 **LLVM IR Analysis** - View compiler intermediate representation
- 🔀 **Control Flow Graphs** - Visual diagrams of code execution paths
- 💻 **Source Code Mapping** - Trace performance back to original source
- ⚙️ **Multi-Language Support** - C++, Go, and Rust
- 🎨 **Modern PyQt5 Interface** - Clean, intuitive multi-page wizard

## Prerequisites

### System Requirements
- Linux (tested on Ubuntu/Debian)
- Python 3.8+
- Clang/LLVM toolchain
- perf (Linux performance profiling tool)

### Installation

1. **Install system dependencies:**
```bash
sudo apt update
sudo apt install -y clang llvm linux-tools-generic python3 python3-pip python3-venv git
```

2. **Clone the repository:**
```bash
git clone https://github.com/KevinAdkins/LLVM.git
cd LLVM
```

3. **Set up Python virtual environment:**
```bash
python3 -m venv venv
source venv/bin/activate
```

4. **Install Python dependencies:**
```bash
pip install PyQt5
```

5. **Set up FlameGraph scripts:**
```bash
cd scripts
git clone https://github.com/brendangregg/FlameGraph.git
cd ..
```

6. **Configure perf permissions (optional but recommended):**
```bash
# Allow perf to run without sudo
sudo sysctl -w kernel.perf_event_paranoid=-1
sudo sysctl -w kernel.kptr_restrict=0

# To make permanent, add to /etc/sysctl.conf:
echo "kernel.perf_event_paranoid=-1" | sudo tee -a /etc/sysctl.conf
echo "kernel.kptr_restrict=0" | sudo tee -a /etc/sysctl.conf
```

## Usage

### Starting the Application

```bash
# Activate virtual environment
source venv/bin/activate

# Launch the GUI
python3 UI_PyQt5.py
```

### Step-by-Step Workflow

#### **Page 1: Configuration & File Selection**
1. Select your programming language (C++, Go, or Rust)
2. Choose optimization level (-O0, -O1, -O2, -O3)
3. Click **"Upload Source File"** to select your code
4. Read the "What This Tool Does" section to understand the analysis
5. Click **"Continue →"** to start processing

#### **Page 2: Processing**
- Watch real-time compilation and profiling logs
- The tool will:
  - Compile your code with the selected optimization level
  - Generate LLVM IR
  - Run performance profiling with `perf`
  - Generate flamegraph HTML
  - Create control flow graphs
- Processing automatically advances when complete

#### **Page 3: Flamegraph Selection**
- Interactive flamegraph opens automatically in your browser
- **Flamegraph interpretation:**
  - Width of blocks = CPU time consumed
  - Y-axis = call stack depth
  - X-axis = alphabetical ordering (not time!)
  - Hover for details
- **Select a function to analyze:**
  - Click a block in the browser, OR
  - Select from the function list
  - Use search box to filter functions
- Selected block info appears on the right
- Click **"Continue →"** to view detailed analysis

#### **Page 4: Detailed Analysis**
Three tabbed views:

1. **📄 LLVM IR Tab**
   - Shows LLVM Intermediate Representation
   - See compiler optimizations and transformations
   - Identify inefficient IR patterns

2. **💻 Source Code Tab**
   - Original source code for the selected function
   - Maps performance back to your code

3. **🔀 CFG Tab**
   - Control Flow Graph visualization
   - Boxes = basic blocks of code
   - Arrows = execution flow paths
   - Zoom controls: 🔍+ 🔍- ⬜ 🔄

- Click **"← Back to Flamegraph"** to select another function
- Use the block index list on the left to browse all functions

## Example

```bash
# Example with test file
cd scripts
python3 UI_PyQt5.py
# Select test.cpp, use -O2, and analyze the results
```

## Project Structure

```
LLVM/
├── UI_PyQt5.py              # Main GUI application
├── UI.py                    # Legacy tkinter version
├── scripts/
│   ├── fg-IR.py            # IR analysis script
│   ├── process_flamegraph.py
│   ├── profile_flamegraph.sh
│   ├── test.cpp            # Example source file
│   └── FlameGraph/         # Flamegraph generation scripts
└── README.md
```

## Troubleshooting

### "perf requires sudo" error
- Run the perf permission configuration commands above
- Or the app will automatically prompt for sudo when needed

### "Program ran too fast for perf to collect samples"
- Add loops or more work to your program
- perf needs the program to run long enough to collect data

### Browser doesn't open automatically
- Manually open: `http://localhost:8765/test_O2.html`
- Check firewall settings

### No CFG displayed
- Ensure `opt` and `dot` commands are available
- Check that GraphViz is installed: `sudo apt install graphviz`

## Tips for Best Results

1. **Choose appropriate test cases** - Use realistic workloads
2. **Start with -O0** - Baseline unoptimized performance
3. **Compare optimization levels** - See impact of -O1, -O2, -O3
4. **Focus on wide blocks** - Biggest performance impact
5. **Look for optimization opportunities** - Loops, memory access patterns

## Contributing
This is an academic project. Feel free to fork and enhance!

## License
Educational use - Software Engineering Fall 2025

## Authors
- Kevin Adkins
- Jorge Munoz
- Travis Shos  
- Eric Gerner
