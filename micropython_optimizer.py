#!/usr/bin/env python3
"""
MicroPython Code Optimizer

This script optimizes MicroPython code files for deployment on constrained devices by:
1. Removing comments (single line, multi-line, and docstrings)
2. Removing print statements
3. Removing empty lines and trailing whitespace
4. Optionally removing unused imports (experimental)

Usage:
    python micropython_optimizer.py [options] <input_file_or_dir> [output_dir]
    python micropython_optimizer.py --manifest=manifest.json [options] [output_dir]

Options:
    --manifest=FILE.json  Use manifest.json to identify files to optimize
    --no-backup          Don't create backup files
    --keep-docstrings    Keep docstrings (class and function documentation)
    --keep-prints        Keep print statements
    --keep-comments      Keep regular comments (not docstrings)
    --preserve-header    Keep the first comment block at the start of the file
    --remove-imports     Attempt to remove unused imports (experimental)
    --stats-only         Show statistics without modifying files
    --verbose            Show detailed information during processing
    --exclude=FILE1,FILE2 Comma-separated list of files to exclude

Examples:
    # Process a single file
    python micropython_optimizer.py main.py
    
    # Process a directory with custom options
    python micropython_optimizer.py --keep-docstrings --verbose src/ optimized/
    
    # Process only files listed in manifest.json
    python micropython_optimizer.py --manifest=manifest.json --verbose optimized/
"""

import os
import re
import sys
import shutil
import argparse
from typing import Dict, List, Tuple, Any, Set
import ast

import json

# Color codes for terminal output
class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def colorize(text: str, color: str) -> str:
    """Add color to terminal output"""
    return f"{color}{text}{Colors.ENDC}"

class MicropythonOptimizer:
    """Optimizer for MicroPython code files"""
    
    def __init__(self, options: argparse.Namespace):
        """Initialize with the specified options"""
        self.options = options
        self.total_original_size = 0
        self.total_optimized_size = 0
        self.files_processed = 0
        
    def optimize_file(self, input_path: str, output_path: str = None) -> Dict[str, Any]:
        """Optimize a single Python file
        
        Args:
            input_path: Path to input file
            output_path: Path for output file (uses input_path if None)
            
        Returns:
            Dict with statistics about the optimization
        """
        # Default to overwriting input file if no output path specified
        if output_path is None:
            output_path = input_path
            
        # Create backup if needed
        if not self.options.no_backup and output_path == input_path:
            backup_path = f"{input_path}.bak"
            if self.options.verbose:
                print(f"Creating backup: {backup_path}")
            shutil.copy2(input_path, backup_path)
            
        # Read input file
        try:
            with open(input_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            print(colorize(f"Error reading {input_path}: {e}", Colors.RED))
            return {"success": False, "error": str(e)}
            
        original_size = len(content)
        original_lines = content.count('\n') + 1
        
        # Apply optimizations
        if self.options.verbose:
            print(f"Optimizing: {input_path}")
            
        # Process the file
        optimized = self._optimize_content(content, input_path)
        
        # Calculate statistics
        optimized_size = len(optimized)
        optimized_lines = optimized.count('\n') + 1
        bytes_saved = original_size - optimized_size
        size_reduction_pct = (bytes_saved / original_size) * 100 if original_size > 0 else 0
        
        stats = {
            "success": True,
            "original_size": original_size,
            "optimized_size": optimized_size,
            "bytes_saved": bytes_saved,
            "size_reduction_pct": size_reduction_pct,
            "original_lines": original_lines,
            "optimized_lines": optimized_lines,
            "lines_removed": original_lines - optimized_lines
        }
        
        # Only write the file if not in stats-only mode
        if not self.options.stats_only:
            try:
                # Ensure output directory exists
                os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
                
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(optimized)
            except Exception as e:
                print(colorize(f"Error writing to {output_path}: {e}", Colors.RED))
                stats["success"] = False
                stats["error"] = str(e)
                
        return stats

    def _optimize_content(self, content: str, filename: str) -> str:
        """Apply all optimizations to content"""
        # Parse the file to check syntax first
        try:
            ast.parse(content)
        except SyntaxError as e:
            print(colorize(f"Syntax error in {filename}: {e}", Colors.RED))
            print("File will not be optimized to avoid breaking it.")
            return content

        # Step 1: Preserve header if option is set
        header = ""
        if self.options.preserve_header:
            # Try to find the first comment block
            match = re.match(r'(#.*?(?:\n#.*?)*\n)', content)
            if match:
                header = match.group(1)
                content = content[len(header):]
        
        # Step 2: Remove docstrings (triple-quoted strings)
        if not self.options.keep_docstrings:
            # Handle triple-quoted strings (both styles)
            content = self._remove_docstrings(content)
        
        # Step 3: Remove regular comments if option is set
        if not self.options.keep_comments:
            # Remove single-line comments that aren't inside strings
            content = self._remove_line_comments(content)
        
        # Step 4: Remove print statements if option is set
        if not self.options.keep_prints:
            content = self._remove_print_statements(content)
        
        # Step 5: Remove empty lines
        content = self._remove_empty_lines(content)
        
        # Step 6: Experimental - attempt to remove unused imports
        if self.options.remove_imports:
            try:
                content = self._remove_unused_imports(content)
            except Exception as e:
                if self.options.verbose:
                    print(colorize(f"Error removing imports in {filename}: {e}", Colors.YELLOW))
        
        # Reattach the header if we preserved it
        if header:
            content = header + content
            
        return content

    def _remove_docstrings(self, content: str) -> str:
        """Remove docstrings from the content
        
        This is more complex than a simple regex since we need to handle
        nested triple quotes and avoid removing actual string literals.
        """
        # Use a regex pattern that looks for triple quotes outside of strings
        # This is a simplified approach and may not handle all edge cases
        patterns = [
            r'""".*?"""',  # Triple double quotes
            r"'''.*?'''"    # Triple single quotes
        ]
        
        # Apply each pattern with the DOTALL flag to match across lines
        for pattern in patterns:
            content = re.sub(pattern, '', content, flags=re.DOTALL)
            
        return content

    def _remove_line_comments(self, content: str) -> str:
        """Remove single-line comments while preserving strings"""
        lines = content.split('\n')
        result = []
        
        for line in lines:
            # Skip lines that are just comments
            if line.strip().startswith('#'):
                continue
                
            # For lines with code and comments, strip the comment part
            in_string = False
            string_char = None
            i = 0
            
            while i < len(line):
                char = line[i]
                
                # Handle string boundaries
                if char in "\"'" and (i == 0 or line[i-1] != '\\'):
                    if not in_string:
                        in_string = True
                        string_char = char
                    elif string_char == char:
                        in_string = False
                        
                # Handle comments outside strings
                if char == '#' and not in_string:
                    line = line[:i].rstrip()
                    break
                    
                i += 1
                
            # Add the processed line
            result.append(line)
            
        return '\n'.join(result)

    def _remove_print_statements(self, content: str) -> str:
        """Remove print statements from the content"""
        # This matches both simple print("text") and more complex print(f"{var}")
        lines = content.split('\n')
        result = []
        
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            
            # Skip simple print lines
            if re.match(r'^\s*print\s*\(', stripped) and stripped.count('(') == stripped.count(')'):
                i += 1
                continue
                
            # Handle multi-line print statements
            if re.match(r'^\s*print\s*\(', stripped) and stripped.count('(') > stripped.count(')'):
                paren_count = stripped.count('(') - stripped.count(')')
                j = i + 1
                
                # Find the end of the print statement
                while j < len(lines) and paren_count > 0:
                    paren_count += lines[j].count('(') - lines[j].count(')')
                    j += 1
                    
                # Skip all these lines
                i = j
                continue
                
            # Keep non-print lines
            result.append(line)
            i += 1
            
        return '\n'.join(result)

    def _remove_empty_lines(self, content: str) -> str:
        """Remove empty lines and trailing whitespace"""
        lines = content.split('\n')
        
        # Remove empty lines and trailing whitespace
        non_empty_lines = [line.rstrip() for line in lines if line.strip()]
        
        # Combine adjacent non-empty lines with appropriate spacing
        result = []
        for line in non_empty_lines:
            result.append(line)
            
        return '\n'.join(result)

    def _remove_unused_imports(self, content: str) -> str:
        """Attempt to identify and remove unused imports"""
        try:
            # Parse the code
            tree = ast.parse(content)
            
            # Find all imports
            imports = {}
            
            # Track imports from 'import x' statements
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for name in node.names:
                        imports[name.name] = {
                            'asname': name.asname or name.name,
                            'node': node,
                            'used': False
                        }
                elif isinstance(node, ast.ImportFrom):
                    module = node.module
                    for name in node.names:
                        full_name = f"{module}.{name.name}" if module else name.name
                        imports[full_name] = {
                            'asname': name.asname or name.name,
                            'node': node,
                            'used': False,
                            'from_import': True,
                            'module': module,
                            'name': name.name
                        }
            
            # Mark imports as used if they appear in the code
            for node in ast.walk(tree):
                if isinstance(node, ast.Name):
                    name = node.id
                    # Check if this name is an import alias
                    for import_info in imports.values():
                        if import_info['asname'] == name:
                            import_info['used'] = True
                            
            # Check for attribute access (e.g., module.function)
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute):
                    if isinstance(node.value, ast.Name):
                        name = node.value.id
                        # Check if this is a module name
                        for import_info in imports.values():
                            if import_info['asname'] == name:
                                import_info['used'] = True
            
            # Find unused imports
            unused_imports = [
                info for name, info in imports.items() 
                if not info['used'] and not name.startswith('_')
            ]
            
            # Simple implementation: just comment out unused import lines
            lines = content.split('\n')
            for info in unused_imports:
                node = info['node']
                start_line = node.lineno - 1  # AST is 1-indexed, list is 0-indexed
                
                # Comment out the line
                if start_line < len(lines):
                    lines[start_line] = f"# UNUSED: {lines[start_line]}"
            
            return '\n'.join(lines)
        except Exception as e:
            # If any error occurs, return the original content
            if self.options.verbose:
                print(colorize(f"Error analyzing imports: {e}", Colors.YELLOW))
            return content

    def process_directory(self, input_dir: str, output_dir: str = None) -> Dict[str, Any]:
        """Process all Python files in a directory
        
        Args:
            input_dir: Input directory path
            output_dir: Output directory path (uses input_dir if None)
            
        Returns:
            Dict with statistics about the optimization
        """
        if not os.path.isdir(input_dir):
            print(colorize(f"Error: {input_dir} is not a directory", Colors.RED))
            return {"success": False, "error": "Not a directory"}
            
        if output_dir is None:
            output_dir = input_dir
            
        # Get list of excluded files
        excluded_files = []
        if self.options.exclude:
            excluded_files = [f.strip() for f in self.options.exclude.split(',')]
        
        stats = {
            "files_processed": 0,
            "total_original_size": 0,
            "total_optimized_size": 0,
            "total_bytes_saved": 0,
            "average_reduction_pct": 0,
            "file_stats": {}
        }
        
        # Process all Python files recursively
        for root, _, files in os.walk(input_dir):
            for filename in files:
                # Skip non-Python files
                if not filename.endswith('.py'):
                    continue
                    
                # Skip excluded files
                if filename in excluded_files:
                    if self.options.verbose:
                        print(f"Skipping excluded file: {filename}")
                    continue
                
                # Construct full paths
                rel_path = os.path.relpath(os.path.join(root, filename), input_dir)
                input_path = os.path.join(root, filename)
                output_path = os.path.join(output_dir, rel_path)
                
                # Optimize the file
                file_stats = self.optimize_file(input_path, output_path)
                
                if file_stats["success"]:
                    stats["files_processed"] += 1
                    stats["total_original_size"] += file_stats["original_size"]
                    stats["total_optimized_size"] += file_stats["optimized_size"]
                    stats["total_bytes_saved"] += file_stats["bytes_saved"]
                    stats["file_stats"][rel_path] = file_stats
        
        # Calculate average reduction percentage
        if stats["total_original_size"] > 0:
            stats["average_reduction_pct"] = (stats["total_bytes_saved"] / stats["total_original_size"]) * 100
            
        return stats

    def print_stats(self, stats: Dict[str, Any], title: str = None) -> None:
        """Print optimization statistics
        
        Args:
            stats: Statistics dictionary
            title: Optional title to display
        """
        if title:
            print(colorize(f"\n{title}", Colors.BOLD))
            
        if "error" in stats and not stats.get("success", True):
            print(colorize(f"Error: {stats['error']}", Colors.RED))
            return
            
        if "files_processed" in stats:
            # Directory stats
            print(colorize(f"Files processed: {stats['files_processed']}", Colors.BOLD))
            print(f"Total original size: {_format_size(stats['total_original_size'])}")
            print(f"Total optimized size: {_format_size(stats['total_optimized_size'])}")
            print(f"Total bytes saved: {_format_size(stats['total_bytes_saved'])}")
            print(colorize(f"Average reduction: {stats['average_reduction_pct']:.2f}%", Colors.GREEN))
            
            # Print detailed stats for each file if verbose
            if self.options.verbose and stats["file_stats"]:
                print("\nFile Details:")
                print("-" * 80)
                print(f"{'Filename':<40} {'Original':<10} {'Optimized':<10} {'Saved':<10} {'Reduction':<10}")
                print("-" * 80)
                
                # Sort files by bytes saved (descending)
                sorted_files = sorted(
                    stats["file_stats"].items(),
                    key=lambda x: x[1]["bytes_saved"],
                    reverse=True
                )
                
                for filename, file_stats in sorted_files:
                    print(f"{filename:<40} {_format_size(file_stats['original_size']):<10} "
                          f"{_format_size(file_stats['optimized_size']):<10} "
                          f"{_format_size(file_stats['bytes_saved']):<10} "
                          f"{file_stats['size_reduction_pct']:.2f}%")
        else:
            # Single file stats
            print(f"Original size: {_format_size(stats['original_size'])}")
            print(f"Optimized size: {_format_size(stats['optimized_size'])}")
            print(f"Bytes saved: {_format_size(stats['bytes_saved'])}")
            print(colorize(f"Size reduction: {stats['size_reduction_pct']:.2f}%", Colors.GREEN))
            print(f"Lines removed: {stats['lines_removed']}")


def _format_size(size_bytes: int) -> str:
    """Format byte size with appropriate units"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.2f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.2f} MB"


def parse_args() -> argparse.Namespace:
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="Optimize MicroPython code files for constrained devices",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split('\n\n')[1:]  # Use the module docstring for examples
    )
    
    parser.add_argument('input', nargs='?', help="Input file or directory (not needed with --manifest)")
    parser.add_argument('output', nargs='?', help="Output file or directory (defaults to input)")
    
    parser.add_argument('--manifest', help="Path to manifest.json file to identify files to optimize")
    parser.add_argument('--no-backup', action='store_true', help="Don't create backup files")
    parser.add_argument('--keep-docstrings', action='store_true', help="Keep docstrings")
    parser.add_argument('--keep-prints', action='store_true', help="Keep print statements")
    parser.add_argument('--keep-comments', action='store_true', help="Keep regular comments")
    parser.add_argument('--preserve-header', action='store_true', help="Preserve file header comments")
    parser.add_argument('--remove-imports', action='store_true', help="Remove unused imports (experimental)")
    parser.add_argument('--stats-only', action='store_true', help="Show statistics without modifying files")
    parser.add_argument('--verbose', action='store_true', help="Show detailed information")
    parser.add_argument('--exclude', help="Comma-separated list of files to exclude")
    
    return parser.parse_args()


def load_manifest(manifest_path):
    """Load and parse manifest.json file
    
    Args:
        manifest_path: Path to manifest.json file
        
    Returns:
        dict: Parsed manifest data or None if failed
    """
    try:
        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest = json.load(f)
            
        # Validate manifest structure
        if not isinstance(manifest, dict) or 'files' not in manifest:
            print(colorize("Error: Invalid manifest format - missing 'files' key", Colors.RED))
            return None
            
        if not isinstance(manifest['files'], dict):
            print(colorize("Error: Invalid manifest format - 'files' is not a dictionary", Colors.RED))
            return None
            
        return manifest
    except json.JSONDecodeError:
        print(colorize(f"Error: {manifest_path} is not a valid JSON file", Colors.RED))
        return None
    except Exception as e:
        print(colorize(f"Error loading manifest: {e}", Colors.RED))
        return None

def process_manifest_files(optimizer, manifest, output_dir, base_dir=None):
    """Process files listed in manifest
    
    Args:
        optimizer: MicropythonOptimizer instance
        manifest: Parsed manifest data
        output_dir: Output directory for optimized files
        base_dir: Base directory for relative paths (defaults to current directory)
        
    Returns:
        dict: Statistics about the optimization
    """
    if base_dir is None:
        base_dir = os.getcwd()
        
    stats = {
        "files_processed": 0,
        "total_original_size": 0,
        "total_optimized_size": 0,
        "total_bytes_saved": 0,
        "average_reduction_pct": 0,
        "file_stats": {}
    }
    
    # Get list of excluded files
    excluded_files = []
    if optimizer.options.exclude:
        excluded_files = [f.strip() for f in optimizer.options.exclude.split(',')]
    
    if optimizer.options.verbose:
        print(f"Processing {len(manifest['files'])} files from manifest")
    
    # Process each file listed in manifest
    for rel_path, file_info in manifest['files'].items():
        # Skip excluded files
        filename = os.path.basename(rel_path)
        if filename in excluded_files:
            if optimizer.options.verbose:
                print(f"Skipping excluded file: {filename}")
            continue
        
        # Use path from manifest if available
        if 'path' in file_info and file_info['path']:
            # Remove leading slash if present
            file_path = file_info['path']
            if file_path.startswith('/'):
                file_path = file_path[1:]
        else:
            file_path = rel_path
            
        # Construct full paths
        input_path = os.path.normpath(os.path.join(base_dir, file_path))
        
        # Skip non-Python files
        if not input_path.endswith('.py'):
            if optimizer.options.verbose:
                print(f"Skipping non-Python file: {input_path}")
            continue
            
        # Skip files that don't exist
        if not os.path.isfile(input_path):
            print(colorize(f"Warning: File in manifest not found: {input_path}", Colors.YELLOW))
            continue
        
        # Construct output path
        output_path = os.path.normpath(os.path.join(output_dir, file_path))
        
        # Optimize the file
        if optimizer.options.verbose:
            print(f"Processing file: {input_path} -> {output_path}")
            
        file_stats = optimizer.optimize_file(input_path, output_path)
        
        if file_stats["success"]:
            stats["files_processed"] += 1
            stats["total_original_size"] += file_stats["original_size"]
            stats["total_optimized_size"] += file_stats["optimized_size"]
            stats["total_bytes_saved"] += file_stats["bytes_saved"]
            stats["file_stats"][rel_path] = file_stats
    
    # Calculate average reduction percentage
    if stats["total_original_size"] > 0:
        stats["average_reduction_pct"] = (stats["total_bytes_saved"] / stats["total_original_size"]) * 100
        
    return stats

def main() -> None:
    """Main function"""
    args = parse_args()
    
    # Create optimizer with options
    optimizer = MicropythonOptimizer(args)
    
    # Check if using manifest mode
    if args.manifest:
        # Load manifest
        manifest = load_manifest(args.manifest)
        if not manifest:
            sys.exit(1)
            
        # Determine output directory
        manifest_dir = os.path.dirname(os.path.abspath(args.manifest))
        output_path = os.path.abspath(args.output) if args.output else manifest_dir
        
        # Process files from manifest
        stats = process_manifest_files(optimizer, manifest, output_path, manifest_dir)
        optimizer.print_stats(stats, "Manifest File Optimization Results")
    else:
        # Traditional mode requires input path
        if not args.input:
            print(colorize("Error: input file or directory required when not using --manifest", Colors.RED))
            sys.exit(1)
            
        # Process input
        input_path = os.path.abspath(args.input)
        output_path = os.path.abspath(args.output) if args.output else input_path
        
        if os.path.isfile(input_path):
            # Process single file
            stats = optimizer.optimize_file(input_path, output_path)
            optimizer.print_stats(stats, "File Optimization Results")
        else:
            # Process directory
            stats = optimizer.process_directory(input_path, output_path)
            optimizer.print_stats(stats, "Directory Optimization Results")
    
    # Print mode summary
    if args.stats_only:
        print(colorize("\nStats-only mode: No files were modified", Colors.YELLOW))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(colorize("\nOperation cancelled by user", Colors.YELLOW))
        sys.exit(1)
    except Exception as e:
        print(colorize(f"\nUnexpected error: {e}", Colors.RED))
        if "--verbose" in sys.argv:
            import traceback
            traceback.print_exc()
        sys.exit(1)