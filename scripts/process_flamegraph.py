#!/usr/bin/env python3
"""
Flamegraph Processor
Generates flamegraph using flamegraph.pl and converts to interactive HTML.
Takes folded stack data, generates SVG via flamegraph.pl, then creates clickable HTML.
"""

import sys
import xml.etree.ElementTree as ET
from pathlib import Path
import re
import subprocess


def parse_svg_flamegraph(svg_file):
    """Parse SVG flamegraph and extract all blocks"""
    try:
        tree = ET.parse(svg_file)
        root = tree.getroot()
    except Exception as e:
        print(f"Error parsing SVG: {e}")
        return None, 0
    
    blocks = []
    total_samples = 0
    
    # Find all <g> elements that have both <title> and <rect> children
    # This works regardless of namespace
    for g_elem in root.iter():
        if not g_elem.tag.endswith('g'):
            continue
        
        # Skip the frames container itself
        if g_elem.get('id') == 'frames':
            continue
        
        # Find title and rect children
        title_elem = None
        rect_elem = None
        
        for child in g_elem:
            if child.tag.endswith('title'):
                title_elem = child
            elif child.tag.endswith('rect'):
                rect_elem = child
        
        if title_elem is None or rect_elem is None:
            continue
        
        if not title_elem.text:
            continue
        
        title_text = title_elem.text.strip()
        
        # Parse title: "function_name (samples, percent%)"
        # Example: "main (70,311,285,775 samples, 100.00%)"
        match = re.match(r'^(.+?)\s+\(([0-9,]+)\s+samples?,\s*([0-9.]+)%?\)$', title_text)
        if not match:
            # Try alternate format: "function_name (samples)"
            match = re.match(r'^(.+?)\s+\((.+?)\)$', title_text)
            if match:
                func_name = match.group(1)
                samples_str = match.group(2).replace(',', '')
                try:
                    samples = int(float(samples_str))
                except:
                    continue
                percent = 0.0
            else:
                continue
        else:
            func_name = match.group(1)
            samples_str = match.group(2).replace(',', '')
            percent_str = match.group(3).replace('%', '').strip()
            try:
                samples = int(float(samples_str))
                percent = float(percent_str)
            except:
                continue
        
        try:
            x = float(rect_elem.get('x', 0))
            y = float(rect_elem.get('y', 0))
            width = float(rect_elem.get('width', 0))
            height = float(rect_elem.get('height', 16))
        except:
            continue
        
        # Calculate depth from y position (assuming 16px height per level)
        depth = int(y / height) if height > 0 else 0
        
        blocks.append({
            'name': func_name,
            'samples': samples,
            'percent': percent,
            'x': x,
            'y': y,
            'width': width,
            'height': height,
            'depth': depth
        })
        
        total_samples = max(total_samples, samples)
    
    # If we couldn't determine total from individual blocks, calculate it
    if total_samples == 0:
        total_samples = sum(b['samples'] for b in blocks)
    
    # Recalculate percentages if needed
    if total_samples > 0:
        for block in blocks:
            if block['percent'] == 0.0:
                block['percent'] = (block['samples'] / total_samples) * 100
    
    return blocks, total_samples


def create_html_flamegraph(blocks, total_samples, output_file):
    """Generate standalone HTML flamegraph from parsed SVG blocks"""
    
    if not blocks:
        print("No blocks to generate")
        return
    
    # Find dimensions
    max_x = max(b['x'] + b['width'] for b in blocks)
    max_y = max(b['y'] + b['height'] for b in blocks)
    max_depth = max(b['depth'] for b in blocks)
    
    width = max(1200, int(max_x) + 20)
    height = max(600, int(max_y) + 40)
    
    # Generate HTML
    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Flamegraph</title>
    <style>
        body {{
            margin: 0;
            padding: 20px;
            font-family: Arial, sans-serif;
            background: #f5f5f5;
        }}
        #container {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            max-width: {width + 40}px;
            margin: 0 auto;
        }}
        #info {{
            margin-bottom: 15px;
            padding: 10px;
            background: #e8f4f8;
            border-left: 4px solid #2196F3;
            border-radius: 4px;
        }}
        #flamegraph {{
            position: relative;
            width: {width}px;
            height: {height}px;
            border: 1px solid #ddd;
            background: white;
            overflow: auto;
        }}
        .block {{
            position: absolute;
            border: 1px solid #fff;
            cursor: pointer;
            transition: all 0.2s;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            font-size: 12px;
            padding: 2px 4px;
            box-sizing: border-box;
        }}
        .block:hover {{
            filter: brightness(0.9);
            transform: translateY(-1px);
            box-shadow: 0 2px 4px rgba(0,0,0,0.2);
            z-index: 100;
        }}
        .block.selected {{
            border: 2px solid #000;
            z-index: 99;
        }}
        #tooltip {{ 
            position: fixed;
            display: none;
            background: rgba(0,0,0,0.9);
            color: white;
            padding: 8px 12px;
            border-radius: 4px;
            font-size: 12px;
            pointer-events: none;
            z-index: 1000;
            max-width: 400px;
            word-wrap: break-word;
        }}
        #selected-info {{
            margin-top: 15px;
            padding: 10px;
            background: #fff3cd;
            border-left: 4px solid #ffc107;
            border-radius: 4px;
            min-height: 60px;
        }}
    </style>
</head>
<body>
    <div id="container">
        <h1>🔥 Flamegraph Viewer</h1>
        <div id="info">
            <strong>Total Samples:</strong> {total_samples:,} | 
            <strong>Blocks:</strong> {len(blocks):,} | 
            <strong>Max Depth:</strong> {max_depth + 1}
            <br>
            <em>Click any block to view details. Each block represents time spent in that function.</em>
        </div>
        
        <div id="flamegraph">
"""
    
    # Add blocks
    for i, block in enumerate(blocks):
        # Color based on depth
        hue = (block['depth'] * 35) % 360
        saturation = 65 + (block['depth'] % 3) * 10
        lightness = 55 + (block['depth'] % 2) * 5
        color = f"hsl({hue}, {saturation}%, {lightness}%)"
        
        # Escape HTML in function name
        name_escaped = block['name'].replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')
        
        # Calculate line height based on block height
        line_height = max(12, int(block['height']) - 4)
        
        html += f"""            <div class="block" 
                 style="left: {block['x']:.1f}px; top: {block['y']:.1f}px; width: {block['width']:.1f}px; height: {block['height']:.1f}px; background: {color}; line-height: {line_height}px;"
                 data-name="{name_escaped}"
                 data-samples="{block['samples']}"
                 data-percent="{block['percent']:.2f}"
                 data-depth="{block['depth']}"
                 onclick="selectBlock(this)">
                {name_escaped}
            </div>
"""
    
    html += """        </div>
        
        <div id="selected-info">
            <strong>Selected Block:</strong> None - Click a block to see details
        </div>
    </div>
    
    <div id="tooltip"></div>
    
    <script>
        // Tooltip handling
        const tooltip = document.getElementById('tooltip');
        const blocks = document.querySelectorAll('.block');
        
        blocks.forEach(block => {
            block.addEventListener('mouseenter', (e) => {
                const name = block.dataset.name;
                const samples = block.dataset.samples;
                const percent = block.dataset.percent;
                const depth = block.dataset.depth;
                
                tooltip.innerHTML = `
                    <strong>${name}</strong><br>
                    Samples: ${samples} (${percent}%)<br>
                    Depth: ${depth}
                `;
                tooltip.style.display = 'block';
            });
            
            block.addEventListener('mousemove', (e) => {
                tooltip.style.left = (e.clientX + 15) + 'px';
                tooltip.style.top = (e.clientY + 15) + 'px';
            });
            
            block.addEventListener('mouseleave', () => {
                tooltip.style.display = 'none';
            });
        });
        
        // Block selection
        function selectBlock(block) {
            const name = block.dataset.name;
            const samples = block.dataset.samples;
            const percent = block.dataset.percent;
            const depth = block.dataset.depth;
            
            // Update UI
            document.getElementById('selected-info').innerHTML = `
                <strong>Selected Block:</strong> ${name}<br>
                <strong>Samples:</strong> ${samples} (${percent}%)<br>
                <strong>Depth:</strong> ${depth}
            `;
            
            // Send to PyQt app via HTTP POST
            const data = {
                function: name,
                detail: samples + ' samples, ' + percent + '%',
                percent: parseFloat(percent),
                depth: parseInt(depth)
            };
            
            fetch('http://localhost:8765/', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(data)
            }).catch(err => console.log('PyQt app not running:', err));
            
            // Visual feedback
            blocks.forEach(b => b.classList.remove('selected'));
            block.classList.add('selected');
        }
    </script>
</body>
</html>
"""
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html)
    
    print(f"Generated flamegraph: {output_file}")
    print(f"Total samples: {total_samples:,}")
    print(f"Total blocks: {len(blocks):,}")


def generate_svg_with_flamegraph_pl(folded_file, svg_output):
    """Use flamegraph.pl to generate SVG from folded stacks"""
    flamegraph_dir = Path(__file__).parent / 'FlameGraph'
    flamegraph_pl = flamegraph_dir / 'flamegraph.pl'
    
    if not flamegraph_pl.exists():
        print(f"Error: flamegraph.pl not found at {flamegraph_pl}")
        print("Clone FlameGraph: git clone https://github.com/brendangregg/FlameGraph.git")
        return False
    
    try:
        with open(folded_file, 'r') as f:
            result = subprocess.run(
                ['perl', str(flamegraph_pl), '--title', 'Performance Flamegraph'],
                stdin=f,
                capture_output=True,
                text=True
            )
        
        if result.returncode != 0:
            print(f"Error running flamegraph.pl: {result.stderr}")
            return False
        
        with open(svg_output, 'w') as f:
            f.write(result.stdout)
        
        print(f"Generated SVG: {svg_output}")
        return True
        
    except Exception as e:
        print(f"Error generating SVG: {e}")
        return False


def main():
    if len(sys.argv) < 2:
        print("Usage: python process_flamegraph.py <input> [output.html]")
        print("\nInput can be:")
        print("  - Folded stack file (.folded, .txt) - will generate SVG via flamegraph.pl")
        print("  - SVG flamegraph (.svg) - will convert directly")
        print("\nExample workflow:")
        print("  perf script | stackcollapse-perf.pl > stacks.folded")
        print("  python process_flamegraph.py stacks.folded output.html")
        sys.exit(1)
    
    input_file = Path(sys.argv[1])
    output_file = Path(sys.argv[2]) if len(sys.argv) > 2 else input_file.with_suffix('.html')
    
    if not input_file.exists():
        print(f"Error: File not found: {input_file}")
        sys.exit(1)
    
    print(f"Processing: {input_file}")
    
    svg_file = input_file
    
    # If input is not SVG, generate it using flamegraph.pl
    if input_file.suffix.lower() not in ['.svg']:
        print(f"Detected {input_file.suffix} file, generating SVG with flamegraph.pl...")
        temp_svg = input_file.with_suffix('.svg')
        
        if not generate_svg_with_flamegraph_pl(input_file, temp_svg):
            print("Failed to generate SVG")
            sys.exit(1)
        
        svg_file = temp_svg
        print(f"SVG generated: {svg_file}")
    
    # Parse SVG flamegraph
    blocks, total_samples = parse_svg_flamegraph(str(svg_file))
    
    if not blocks:
        print("Error: No blocks found in SVG file")
        print("Make sure the SVG is a flamegraph generated by flamegraph.pl")
        sys.exit(1)
    
    create_html_flamegraph(blocks, total_samples, str(output_file))
    print(f"\n✓ Success! Open {output_file} in the viewer app")
    print(f"  Or run: python fg-IR.py")


if __name__ == '__main__':
    main()
