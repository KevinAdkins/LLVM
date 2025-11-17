#!/bin/bash

# Flamegraph profiling script for C++ files using Clang/LLVM
# This script compiles a C++ file with selectable optimization levels
# and generates a flamegraph from the execution profile
# Linux only

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check dependencies
check_dependencies() {
    local missing_deps=()
    
    if ! command -v clang++ &> /dev/null; then
        missing_deps+=("clang++ (install with: sudo apt install clang)")
    fi
    
    if ! command -v perf &> /dev/null; then
        missing_deps+=("perf (install with: sudo apt install linux-tools-generic)")
    fi
    
    if ! command -v flamegraph.pl &> /dev/null; then
        if [ ! -f "./FlameGraph/flamegraph.pl" ]; then
            missing_deps+=("flamegraph (clone from https://github.com/brendangregg/FlameGraph)")
        fi
    fi
    
    if [ ${#missing_deps[@]} -ne 0 ]; then
        echo -e "${RED}Error: Missing dependencies:${NC}"
        for dep in "${missing_deps[@]}"; do
            echo "  - $dep"
        done
        exit 1
    fi
}

# Prompt for C++ file path
get_cpp_file() {
    while true; do
        echo -e "${GREEN}Enter the path to your C++ file:${NC}"
        read -r cpp_file
        
        # Expand tilde and resolve path
        cpp_file="${cpp_file/#\~/$HOME}"
        
        if [ -f "$cpp_file" ]; then
            echo -e "${GREEN}✓ Found file: $cpp_file${NC}"
            break
        else
            echo -e "${RED}Error: File not found. Please try again.${NC}"
        fi
    done
}

# Prompt for optimization level
get_optimization_level() {
    echo -e "\n${GREEN}Select optimization level:${NC}"
    echo "  0) -O0 (No optimization - fastest compilation)"
    echo "  1) -O1 (Basic optimizations)"
    echo "  2) -O2 (Moderate optimizations - recommended)"
    echo "  3) -O3 (Aggressive optimizations)"
    echo "  4) -Os (Optimize for size)"
    echo "  5) -Ofast (Aggressive optimizations, may break standards compliance)"
    echo "  6) -Oz (Optimize for smallest size)"
    
    while true; do
        echo -e "${GREEN}Enter your choice (0-6):${NC}"
        read -r opt_choice
        
        case $opt_choice in
            0) opt_flag="-O0"; break;;
            1) opt_flag="-O1"; break;;
            2) opt_flag="-O2"; break;;
            3) opt_flag="-O3"; break;;
            4) opt_flag="-Os"; break;;
            5) opt_flag="-Ofast"; break;;
            6) opt_flag="-Oz"; break;;
            *) echo -e "${RED}Invalid choice. Please enter a number between 0 and 6.${NC}";;
        esac
    done
    
    echo -e "${GREEN}✓ Selected optimization level: $opt_flag${NC}"
}

# Compile the C++ file
compile_cpp() {
    local cpp_file="$1"
    local opt_flag="$2"
    local output_file="$3"
    local ir_file="${output_file}.ll"
    
    echo -e "\n${YELLOW}Compiling with Clang...${NC}"
    echo "Command: clang++ $opt_flag -g -fno-omit-frame-pointer \"$cpp_file\" -o \"$output_file\""
    
    if clang++ $opt_flag -g -fno-omit-frame-pointer "$cpp_file" -o "$output_file"; then
        echo -e "${GREEN}✓ Compilation successful!${NC}"
    else
        echo -e "${RED}✗ Compilation failed!${NC}"
        return 1
    fi
    
    # Generate LLVM IR
    echo -e "\n${YELLOW}Generating LLVM IR...${NC}"
    echo "Command: clang++ $opt_flag -S -emit-llvm \"$cpp_file\" -o \"$ir_file\""
    
    if clang++ $opt_flag -S -emit-llvm "$cpp_file" -o "$ir_file"; then
        echo -e "${GREEN}✓ LLVM IR generated: $ir_file${NC}"
        return 0
    else
        echo -e "${YELLOW}⚠ Warning: Failed to generate LLVM IR (executable still created)${NC}"
        return 0
    fi
}

# Profile the executable and generate flamegraph
profile_and_generate_flamegraph() {
    local executable="$1"
    local flamegraph_file="flamegraph.svg"
    
    echo -e "\n${YELLOW}Checking if perf supports flamegraph command...${NC}"
    
    # Check if perf has built-in flamegraph support (Linux 5.8+)
    if perf script report flamegraph &> /dev/null; then
        echo -e "${GREEN}Using perf's built-in flamegraph generator${NC}"
        
        echo -e "\n${YELLOW}Running executable with perf profiling...${NC}"
        if sudo perf record -F 99 -g -- "$executable"; then
            echo -e "${GREEN}✓ Profiling complete!${NC}"
        else
            echo -e "${RED}✗ Profiling failed!${NC}"
            return 1
        fi
        
        # Generate flamegraph using perf's built-in command
        echo -e "${YELLOW}Generating flamegraph with perf...${NC}"
        sudo perf script report flamegraph
        
        if [ -f "flamegraph.html" ]; then
            mv flamegraph.html "$flamegraph_file"
            echo -e "${GREEN}✓ Flamegraph generated: $flamegraph_file${NC}"
        fi
    else
        echo -e "${YELLOW}Using FlameGraph scripts${NC}"
        profile_with_perf_flamegraph "$executable"
    fi
}

# Profile using perf + FlameGraph scripts
profile_with_perf_flamegraph() {
    local executable="$1"
    local perf_data="perf.data"
    local perf_script="perf.script"
    local folded_file="perf.folded"
    local flamegraph_file="flamegraph.svg"
    
    echo -e "\n${YELLOW}Running executable with perf profiling...${NC}"
    echo "Command: perf record -F 99 -g -- \"$executable\""
    
    # Run perf record
    if sudo perf record -F 99 -g -- "$executable"; then
        echo -e "${GREEN}✓ Profiling complete!${NC}"
    else
        echo -e "${RED}✗ Profiling failed!${NC}"
        return 1
    fi
    
    # Check if perf.data exists
    if [ ! -f "$perf_data" ]; then
        echo -e "${RED}Error: perf.data not found${NC}"
        return 1
    fi
    
    echo -e "\n${YELLOW}Processing perf data...${NC}"
    sudo perf script > "$perf_script"
    
    # Determine flamegraph script location
    if command -v flamegraph.pl &> /dev/null; then
        FLAMEGRAPH_PL="flamegraph.pl"
        STACKCOLLAPSE_PL="stackcollapse-perf.pl"
    elif [ -f "./FlameGraph/flamegraph.pl" ]; then
        FLAMEGRAPH_PL="./FlameGraph/flamegraph.pl"
        STACKCOLLAPSE_PL="./FlameGraph/stackcollapse-perf.pl"
    else
        echo -e "${RED}Error: Could not find flamegraph.pl${NC}"
        return 1
    fi
    
    echo -e "${YELLOW}Generating flamegraph...${NC}"
    $STACKCOLLAPSE_PL "$perf_script" > "$folded_file"
    $FLAMEGRAPH_PL "$folded_file" > "$flamegraph_file"
    
    if [ -f "$flamegraph_file" ]; then
        echo -e "${GREEN}✓ Flamegraph generated successfully!${NC}"
        echo -e "${GREEN}Flamegraph saved as: $flamegraph_file${NC}"
        
        # Try to open the flamegraph in a browser
        if command -v xdg-open &> /dev/null; then
            xdg-open "$flamegraph_file" &> /dev/null &
        elif command -v open &> /dev/null; then
            open "$flamegraph_file" &> /dev/null &
        fi
        
        return 0
    else
        echo -e "${RED}✗ Failed to generate flamegraph${NC}"
        return 1
    fi
}

# Cleanup function
cleanup() {
    echo -e "\n${YELLOW}Cleaning up temporary files...${NC}"
    rm -f perf.data perf.script perf.folded
    echo -e "${GREEN}✓ Cleanup complete${NC}"
}

# Main script
main() {
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}  C++ Flamegraph Profiling Tool${NC}"
    echo -e "${GREEN}========================================${NC}\n"
    
    # Check dependencies
    echo -e "${YELLOW}Checking dependencies...${NC}"
    check_dependencies
    echo -e "${GREEN}✓ All dependencies found${NC}\n"
    
    # Get C++ file path
    get_cpp_file
    
    # Get optimization level
    get_optimization_level
    
    # Set output executable name
    cpp_basename=$(basename "$cpp_file" .cpp)
    output_executable="${cpp_basename}_${opt_flag#-}"
    
    # Compile
    if ! compile_cpp "$cpp_file" "$opt_flag" "$output_executable"; then
        exit 1
    fi
    
    # Profile and generate flamegraph
    if ! profile_and_generate_flamegraph "./$output_executable"; then
        cleanup
        exit 1
    fi
    
    # Cleanup
    cleanup
    
    echo -e "\n${GREEN}========================================${NC}"
    echo -e "${GREEN}  Profiling Complete!${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo -e "Executable: ${YELLOW}$output_executable${NC}"
    echo -e "LLVM IR: ${YELLOW}${output_executable}.ll${NC}"
    echo -e "Flamegraph: ${YELLOW}flamegraph.svg${NC}"
}

# Run main function
main
