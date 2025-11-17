# C++ Flamegraph Profiling Tool

A comprehensive bash script for profiling C++ applications and generating flamegraphs to visualize performance bottlenecks.

## Features

- **Multiple Optimization Levels**: Choose from O0, O1, O2, O3, Os, Ofast, and Oz
- **Automatic Dependency Checking**: Verifies all required tools are installed
- **Easy-to-Use Interface**: Interactive prompts guide you through the process
- **Automatic Compilation**: Compiles your C++ code with Clang/LLVM
- **Flamegraph Generation**: Creates visual flamegraphs for performance analysis

## Prerequisites

```bash
# Install Clang compiler
sudo apt install clang

# Install perf tool
sudo apt install linux-tools-generic

# Clone FlameGraph repository (if not already present)
git clone https://github.com/brendangregg/FlameGraph
```

## Installation

1. Clone or download the script:
```bash
cd ~/scripts
# Ensure profile_flamegraph.sh is in this directory
```

2. Make the script executable:
```bash
chmod +x profile_flamegraph.sh
```

3. Ensure FlameGraph tools are available:
```bash
# If FlameGraph directory is not in the same folder:
cd ~/scripts
git clone https://github.com/brendangregg/FlameGraph
```

## Usage

### Basic Usage

Run the script:
```bash
./profile_flamegraph.sh
```

The script will guide you through:

1. **File Selection**: Enter the path to your C++ file
   - Example: `./test.cpp` or `/path/to/your/file.cpp`
   - Supports absolute and relative paths
   - Supports tilde expansion (`~/my_code.cpp`)

2. **Optimization Level**: Choose from:
   - `0` - **-O0**: No optimization (fastest compilation, useful for debugging)
   - `1` - **-O1**: Basic optimizations
   - `2` - **-O2**: Moderate optimizations (recommended for most cases)
   - `3` - **-O3**: Aggressive optimizations
   - `4` - **-Os**: Optimize for size
   - `5` - **-Ofast**: Aggressive optimizations (may break standards compliance)
   - `6` - **-Oz**: Optimize for smallest size

3. **Automatic Processing**: The script will:
   - Compile your code with selected optimization level
   - Profile the executable
   - Generate a flamegraph

### Example Session

```bash
$ ./profile_flamegraph.sh

========================================
  C++ Flamegraph Profiling Tool
========================================

Checking dependencies...
✓ All dependencies found

Enter the path to your C++ file:
./test.cpp
✓ Found file: ./test.cpp

Select optimization level:
  0) -O0 (No optimization - fastest compilation)
  1) -O1 (Basic optimizations)
  2) -O2 (Moderate optimizations - recommended)
  3) -O3 (Aggressive optimizations)
  4) -Os (Optimize for size)
  5) -Ofast (Aggressive optimizations, may break standards compliance)
  6) -Oz (Optimize for smallest size)
Enter your choice (0-6):
2
✓ Selected optimization level: -O2

Compiling with Clang...
✓ Compilation successful!

Running executable with perf profiling...
✓ Profiling complete!

Generating flamegraph...
✓ Flamegraph generated successfully!
Flamegraph saved as: flamegraph.svg

========================================
  Profiling Complete!
========================================
```

## Output Files

- **Executable**: `<filename>_<optimization_level>` (e.g., `test_O2`) - Compiled binary
- **LLVM IR**: `<filename>_<optimization_level>.ll` (e.g., `test_O2.ll`) - LLVM Intermediate Representation
  - Human-readable text format showing optimized code
  - Useful for understanding compiler optimizations
  - Can be analyzed to see how code was transformed
- **Flamegraph**: `flamegraph.svg` - Interactive SVG visualization
  - Open in any web browser
  - Click on stack frames to zoom in
  - Use browser back button to zoom out

## Interpreting Flamegraphs

Flamegraphs are visual representations of stack traces:

- **Width**: Represents the total time spent in a function (including children)
- **Height**: Represents call stack depth
- **Colors**: Randomly assigned for differentiation (no semantic meaning)
- **Hover**: Shows function name and percentage of total time
- **Click**: Zoom into specific function calls

### Key Insights
- **Wide boxes**: Functions consuming significant CPU time
- **Tall stacks**: Deep call chains (potential recursion or layering)
- **Plateau patterns**: Hot code paths worth optimizing

## Troubleshooting

### Permission Denied for perf

If you get permission errors:
```bash
# Temporarily allow perf for non-root users
sudo sysctl -w kernel.perf_event_paranoid=-1

# Or run script with sudo
sudo ./profile_flamegraph.sh
```

### Missing Dependencies

The script will automatically detect missing dependencies and provide installation instructions.

### Compilation Errors

- Ensure your C++ code is valid
- Check that all required headers and libraries are available
- Try compiling manually first: `clang++ -O2 -g your_file.cpp -o test`

### No Flamegraph Generated

- Ensure your program runs long enough to collect meaningful samples (at least a few seconds)
- Check that perf can access performance counters
- Verify FlameGraph scripts are in the correct location

## Test Example

A sample `test.cpp` file is provided that performs integer addition operations:

```bash
# Profile the test file
./profile_flamegraph.sh
# Enter: ./test.cpp
# Select optimization level (e.g., 2 for -O2)
```

The test program will run for several seconds, generating enough profile data for a meaningful flamegraph.

## Advanced Usage

### Custom Compilation Flags

To add custom compilation flags, modify the `compile_cpp` function in the script:

```bash
clang++ $opt_flag -g -fno-omit-frame-pointer -std=c++17 "$cpp_file" -o "$output_file"
```

### Profiling Frequency

To change the sampling frequency (default: 99 Hz), modify the perf command:

```bash
sudo perf record -F 999 -g -- "$executable"  # 999 Hz sampling
```

Higher frequencies provide more detail but increase overhead.

## Resources

- [FlameGraph by Brendan Gregg](https://github.com/brendangregg/FlameGraph)
- [Linux perf Documentation](https://perf.wiki.kernel.org/)
- [Windows Performance Toolkit](https://docs.microsoft.com/en-us/windows-hardware/test/wpt/)
- [Understanding Flamegraphs](http://www.brendangregg.com/flamegraphs.html)

## License

This script is provided as-is for educational and development purposes.

## Support

For issues or questions:
1. Check that all dependencies are installed correctly
2. Verify your C++ code compiles independently
3. Review the troubleshooting section above
