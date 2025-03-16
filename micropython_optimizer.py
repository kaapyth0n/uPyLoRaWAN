#!/usr/bin/env python3
"""
MicroPython Code Optimizer

This script optimizes MicroPython code files for deployment on constrained devices by:
1. Removing comments (single line, multi-line, and docstrings)
2. Removing print statements (safely replacing with 'pass' where needed)
3. Removing empty lines and trailing whitespace
4. Optionally removing unused imports (experimental)

Usage:
    python micropython_optimizer.py [options] <input_file_or_dir> [output_dir]
    python micropython_optimizer.py --manifest=manifest.json [options] [output_dir]

Options:
    --manifest=FILE.json  Use manifest.json to identify files to optimize
    --safe-mode           Replace print statements with 'pass' instead of removing them
    --no-backup          Don't create backup files
    --keep-docstrings    Keep docstrings (class and function documentation)
    --keep-prints        Keep print statements
    --keep-comments      Keep regular comments (not docstrings)
    --preserve-header    Keep the first comment block at the start of the file
    --remove-imports     Attempt to remove unused imports (experimental)
    --stats-only         Show statistics without modifying files
    --verbose            Show detailed information during processing
    --exclude=FILE1,FILE2 Comma-separated list of files to exclude
    --remove-redundant-if-else  Experimental: Remove if-else blocks where both branches are empty or pass

Examples:
    # Process a single file
    python micropython_optimizer.py main.py
    
    # Process a directory with custom options
    python micropython_optimizer.py --keep-docstrings --verbose src/ optimized/
    
    # Process only files listed in manifest.json
    python micropython_optimizer.py --manifest=manifest.json --verbose optimized/
    
    # Process files safely replacing prints with pass instead of removing them
    python micropython_optimizer.py --safe-mode src/ optimized/
"""

import os
import re
import sys
import json
import shutil
import argparse
from typing import Dict, List, Tuple, Any, Set
import ast

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

    def _remove_redundant_if_else(self, content: str) -> str:
        """Experimental: Remove if-else blocks where both branches are empty or pass."""
        try:
            tree = ast.parse(content)
            new_body = []
            for node in tree.body:
                if isinstance(node, ast.If) and self._is_redundant_if_else(node):
                    continue  # Skip redundant if-else
                new_body.append(node)
            return ast.unparse(ast.Module(body=new_body, type_ignores=[]))
        except SyntaxError:
            if self.options.verbose:
                print("Syntax error during redundant if-else removal, skipping")
            return content
        except Exception as e:
            if self.options.verbose:
                print(f"Error removing redundant if-else: {e}, skipping")
            return content

    def _is_redundant_if_else(self, node: ast.If) -> bool:
        """Check if both branches of an if-else are effectively empty."""
        if not node.orelse:  # No else clause
            return False
        return self._is_effectively_empty(node.body) and self._is_effectively_empty(node.orelse)

    def _is_effectively_empty(self, statements: List[ast.stmt]) -> bool:
        """Check if a list of statements is effectively empty."""
        for stmt in statements:
            if isinstance(stmt, ast.Pass):
                continue
            if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) and stmt.value.value is None:
                continue  # Treat None expressions as empty
            return False
        return True

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
            
        if self.options.remove_redundant_if_else:
            content = self._remove_redundant_if_else(content)
        return content

    def _remove_docstrings(self, content: str) -> str:
        """Remove docstrings from the content while preserving functional strings
        
        Uses AST parsing to identify and remove only true docstrings, while
        preserving string literals that are part of the code's functionality.
        """
        try:
            # Parse the code to get the AST
            tree = ast.parse(content)
            
            # Identify docstring positions
            docstring_positions = []
            
            # Module docstring
            if (len(tree.body) > 0 and 
                isinstance(tree.body[0], ast.Expr) and 
                (isinstance(tree.body[0].value, ast.Constant) or 
                (hasattr(ast, 'Str') and isinstance(tree.body[0].value, ast.Str)))):
                docstring_positions.append((tree.body[0].lineno, tree.body[0].end_lineno))
            
            # Walk the tree to find class and function docstrings
            for node in ast.walk(tree):
                # Class docstrings
                if isinstance(node, ast.ClassDef):
                    if (len(node.body) > 0 and 
                        isinstance(node.body[0], ast.Expr) and 
                        (isinstance(node.body[0].value, ast.Constant) or 
                        (hasattr(ast, 'Str') and isinstance(node.body[0].value, ast.Str)))):
                        docstring_positions.append((node.body[0].lineno, node.body[0].end_lineno))
                
                # Function docstrings
                elif isinstance(node, ast.FunctionDef):
                    if (len(node.body) > 0 and 
                        isinstance(node.body[0], ast.Expr) and 
                        (isinstance(node.body[0].value, ast.Constant) or 
                        (hasattr(ast, 'Str') and isinstance(node.body[0].value, ast.Str)))):
                        docstring_positions.append((node.body[0].lineno, node.body[0].end_lineno))
            
            # If no docstrings found, return content unchanged
            if not docstring_positions:
                return content
                
            # Convert content to lines for processing
            lines = content.split('\n')
            result = []
            
            # Process lines, removing only those that are part of docstrings
            i = 0
            while i < len(lines):
                line_num = i + 1  # AST uses 1-indexed line numbers
                
                # Check if this line is part of a docstring
                is_docstring = False
                for start, end in docstring_positions:
                    if start <= line_num <= end:
                        is_docstring = True
                        break
                
                if is_docstring:
                    # Skip docstring lines
                    if line_num == end:
                        i += 1  # Move to next line after docstring
                    else:
                        i += 1  # Move through the docstring
                else:
                    # Keep non-docstring lines
                    result.append(lines[i])
                    i += 1
            
            return '\n'.join(result)
            
        except SyntaxError:
            # If parsing fails, don't attempt to remove docstrings
            if self.options.verbose:
                print(colorize("Syntax error during AST parsing for docstrings, keeping all strings", Colors.YELLOW))
            return content
        except Exception as e:
            # If any error occurs, be safe and leave content unchanged
            if self.options.verbose:
                print(colorize(f"Error removing docstrings: {e}, keeping all strings", Colors.YELLOW))
            return content

    def _remove_line_comments(self, content: str) -> str:
        """Remove single-line comments while preserving strings"""
        try:
            tree = ast.parse(content)
            string_positions = []
            for node in ast.walk(tree):
                if (isinstance(node, ast.Constant) or (hasattr(ast, 'Str') and isinstance(node, ast.Str))) or (hasattr(ast, 'JoinedStr') and isinstance(node, ast.JoinedStr)):
                    if hasattr(node, 'lineno') and hasattr(node, 'end_lineno'):
                        string_positions.append((node.lineno, node.end_lineno))
            
            lines = content.split('\n')
            for i, line in enumerate(lines):
                line_num = i + 1  # AST uses 1-indexed line numbers
                # Skip lines entirely within a multi-line string
                if any(start < line_num < end for start, end in string_positions):
                    continue
                if '#' in line:
                    in_string_char = False
                    string_delim = None
                    escape = False
                    j = 0
                    while j < len(line):
                        char = line[j]
                        if char in "\"'" and not escape:
                            if not in_string_char:
                                in_string_char = True
                                string_delim = char
                            elif string_delim == char:
                                in_string_char = False
                        if char == '\\' and not escape:
                            escape = True
                        else:
                            escape = False
                        if char == '#' and not in_string_char:
                            lines[i] = line[:j].rstrip()
                            break
                        j += 1
            return '\n'.join(lines)
        except SyntaxError:
            if self.options.verbose:
                print(colorize("Syntax error during AST parsing for comments, using fallback method", Colors.YELLOW))
            lines = content.split('\n')
            result = []
            for line in lines:
                if line.strip().startswith('#'):
                    continue
                if '#' in line:
                    in_string = False
                    string_char = None
                    escape = False
                    comment_pos = -1
                    for k, char in enumerate(line):
                        if escape:
                            escape = False
                            continue
                        if char == '\\':
                            escape = True
                            continue
                        if char in "\"'":
                            if not in_string:
                                in_string = True
                                string_char = char
                            elif string_char == char:
                                in_string = False
                        if char == '#' and not in_string:
                            comment_pos = k
                            break
                    if comment_pos >= 0:
                        line = line[:comment_pos].rstrip()
                result.append(line)
            return '\n'.join(result)
        except Exception as e:
            if self.options.verbose:
                print(colorize(f"Error removing comments: {e}, preserving code", Colors.YELLOW))
            return content

    def _remove_print_statements(self, content: str) -> str:
        """Remove or replace print statements ensuring code remains syntactically valid
        
        Uses AST parsing to identify blocks where print is the only statement,
        ensuring all control structures remain syntactically valid.
        Only replaces prints with 'pass' when they are the only statement in a block.
        """
        if self.options.safe_mode:
            # In safe mode, just replace all print statements with 'pass'
            return self._safe_replace_prints_with_pass(content)
            
        try:
            # Parse the code with AST to identify all print statements
            tree = ast.parse(content)
            
            # Create collections for tracking
            pass_replacements = []  # Lines to replace with 'pass'
            print_lines = set()      # All print statement lines
            non_print_lines = set()  # Lines with statements other than print
            blocks = {}              # Maps block start line to end line
            
            # Find all print statements
            for node in ast.walk(tree):
                # Track print statements
                if (isinstance(node, ast.Expr) and
                    isinstance(node.value, ast.Call) and
                    isinstance(node.value.func, ast.Name) and
                    node.value.func.id == 'print'):
                    print_lines.add(node.lineno)
                
                # Track non-print statements
                elif isinstance(node, ast.stmt) and not isinstance(node, (ast.Expr, ast.Pass)):
                    if hasattr(node, 'lineno'):
                        non_print_lines.add(node.lineno)
                        
                # Track control blocks to know their ranges
                if isinstance(node, (ast.If, ast.For, ast.While, ast.With, ast.Try,
                                    ast.ExceptHandler, ast.FunctionDef, ast.ClassDef)):
                    if hasattr(node, 'lineno') and hasattr(node, 'end_lineno'):
                        blocks[node.lineno] = node.end_lineno
            
            # Find blocks where print is the only statement
            for node in ast.walk(tree):
                # Handle all block types that have a body
                if hasattr(node, 'body') and isinstance(node.body, list):
                    # If body is non-empty
                    if len(node.body) > 0:
                        # Get line range of this block
                        start_line = node.lineno if hasattr(node, 'lineno') else None
                        
                        # Count non-print statements in this block
                        non_print_count = 0
                        
                        # Check each statement in the body
                        for stmt in node.body:
                            if not (isinstance(stmt, ast.Expr) and 
                                    isinstance(stmt.value, ast.Call) and
                                    isinstance(stmt.value.func, ast.Name) and
                                    stmt.value.func.id == 'print'):
                                non_print_count += 1
                        
                        # If block has only one statement and it's a print, mark for replacement
                        if len(node.body) == 1 and non_print_count == 0:
                            stmt = node.body[0]
                            if (isinstance(stmt, ast.Expr) and
                                isinstance(stmt.value, ast.Call) and
                                isinstance(stmt.value.func, ast.Name) and
                                stmt.value.func.id == 'print'):
                                pass_replacements.append(stmt.lineno)
                
                # Also check orelse blocks (else/elif parts)
                if hasattr(node, 'orelse') and isinstance(node.orelse, list):
                    # If there's exactly one statement and it's a print
                    if len(node.orelse) == 1:
                        stmt = node.orelse[0]
                        # Check if it's a print statement (not an elif)
                        if (isinstance(stmt, ast.Expr) and
                            isinstance(stmt.value, ast.Call) and
                            isinstance(stmt.value.func, ast.Name) and
                            stmt.value.func.id == 'print'):
                            pass_replacements.append(stmt.lineno)
            
            # Now split the content into lines
            lines = content.split('\n')
            result = []
            
            i = 0
            while i < len(lines):
                line = lines[i]
                stripped = line.strip()
                line_num = i + 1  # AST uses 1-indexed line numbers
                
                # If this is a print that should be replaced with 'pass'
                if line_num in pass_replacements:
                    # Replace with 'pass' maintaining indentation
                    indent = line[:len(line) - len(stripped)]
                    result.append(f"{indent}pass")
                    i += 1
                    continue
                
                # If this is a regular print statement (not the only statement in a block)
                elif line_num in print_lines and line_num not in pass_replacements:
                    # Check if it's a simple print statement
                    if stripped.count('(') == stripped.count(')'):
                        i += 1
                        continue
                    
                    # Handle multi-line print statements
                    else:
                        paren_count = stripped.count('(') - stripped.count(')')
                        j = i + 1
                        
                        # Find the end of the print statement
                        while j < len(lines) and paren_count > 0:
                            paren_count += lines[j].count('(') - lines[j].count(')')
                            j += 1
                            
                        # Skip all these lines
                        i = j
                        continue
                
                # Handle block start markers (else, etc.)
                elif re.match(r'^\s*(else|except|finally)\s*:', stripped):
                    result.append(line)
                    
                    # Look ahead to see if next line is just a print statement
                    if i+1 < len(lines):
                        next_line = lines[i+1].strip()
                        if re.match(r'^print\s*\(', next_line):
                            # Check if it's a single print
                            if next_line.count('(') == next_line.count(')'):
                                # Now check if there's anything else in this block
                                has_other_content = False
                                
                                # Get indentation level of current and next line
                                curr_indent = len(line) - len(stripped)
                                next_indent = len(lines[i+1]) - len(next_line)
                                
                                # Only if next line is properly indented
                                if next_indent > curr_indent:
                                    # Check subsequent lines to see if there's more content
                                    k = i + 2
                                    while k < len(lines):
                                        k_line = lines[k].strip()
                                        if not k_line:  # Skip empty lines
                                            k += 1
                                            continue
                                            
                                        k_indent = len(lines[k]) - len(k_line)
                                        
                                        # If same or deeper indentation, this is still in the block
                                        if k_indent >= next_indent:
                                            has_other_content = True
                                            break
                                        # If less indentation, we've exited the block
                                        else:
                                            break
                                            
                                        k += 1
                                
                                # If this is the only content in the block, replace with pass
                                if not has_other_content:
                                    indent = lines[i+1][:len(lines[i+1]) - len(next_line)]
                                    result.append(f"{indent}pass")
                                # Otherwise, just skip the print (don't replace with pass)
                                i += 2
                                continue
                    
                    i += 1
                    continue
                
                # Handle other control blocks
                elif re.match(r'^\s*(if|for|while|with|def|class|try)\s+.*:', stripped):
                    result.append(line)
                    
                    # Look ahead to see if next line is just a print statement
                    if i+1 < len(lines):
                        next_line = lines[i+1].strip()
                        if re.match(r'^print\s*\(', next_line):
                            # Only if it's a simple print
                            if next_line.count('(') == next_line.count(')'):
                                # Now check if there's anything else in this block
                                has_other_content = False
                                
                                # Get indentation level of current and next line
                                curr_indent = len(line) - len(stripped)
                                next_indent = len(lines[i+1]) - len(next_line)
                                
                                # Only if next line is properly indented
                                if next_indent > curr_indent:
                                    # Check subsequent lines to see if there's more content
                                    k = i + 2
                                    while k < len(lines):
                                        k_line = lines[k].strip()
                                        if not k_line:  # Skip empty lines
                                            k += 1
                                            continue
                                            
                                        k_indent = len(lines[k]) - len(k_line)
                                        
                                        # If same indentation as print, this is still in the block
                                        if k_indent == next_indent:
                                            has_other_content = True
                                            break
                                        # If deeper indentation, this is a nested block
                                        elif k_indent > next_indent:
                                            # Skip over the nested block
                                            while k < len(lines):
                                                if not lines[k].strip():
                                                    k += 1
                                                    continue
                                                    
                                                curr_k_indent = len(lines[k]) - len(lines[k].strip())
                                                if curr_k_indent <= next_indent:
                                                    break
                                                k += 1
                                        # If less indentation, we've exited the block
                                        else:
                                            break
                                            
                                        k += 1
                                
                                # If this is the only content in the block, replace with pass
                                # Otherwise, just skip the print (don't replace with pass)
                                if not has_other_content:
                                    indent = lines[i+1][:len(lines[i+1]) - len(next_line)]
                                    result.append(f"{indent}pass")
                                i += 2
                                continue
                    
                    i += 1
                    continue
                
                # Keep all other lines
                else:
                    result.append(line)
                    i += 1
            
            return '\n'.join(result)
            
        except SyntaxError:
            # If parsing fails, fall back to the safer method
            if self.options.verbose:
                print(colorize("Syntax error during AST parsing, falling back to safe method", Colors.YELLOW))
            return self._safe_replace_prints_with_pass(content)
        except Exception as e:
            if self.options.verbose:
                print(colorize(f"AST parsing error, falling back to safe method: {e}", Colors.YELLOW))
            return self._safe_replace_prints_with_pass(content)
            
    def _safe_replace_prints_with_pass(self, content: str) -> str:
        """Safely replace print statements with 'pass' to maintain code structure
        
        More conservative approach that preserves syntactic validity
        """
        lines = content.split('\n')
        result = []
        
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            
            # Simple print statement on a single line
            if re.match(r'^\s*print\s*\(', stripped) and stripped.count('(') == stripped.count(')'):
                # Replace with 'pass' maintaining indentation
                indent = line[:len(line) - len(stripped)]
                result.append(f"{indent}pass")
                i += 1
                continue
                
            # Handle multi-line print statements
            if re.match(r'^\s*print\s*\(', stripped) and stripped.count('(') > stripped.count(')'):
                # Replace first line with 'pass'
                indent = line[:len(line) - len(stripped)]
                result.append(f"{indent}pass")
                
                # Skip all lines in this print statement
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
    
    # Change these to named arguments with help text to clarify
    parser.add_argument('--input', help="Input file or directory (not needed with --manifest)")
    parser.add_argument('--output', help="Output file or directory (defaults to input)")
    
    # Add positional arguments as fallbacks for backward compatibility
    parser.add_argument('input_pos', nargs='?', help=argparse.SUPPRESS)  # Hide in help
    parser.add_argument('output_pos', nargs='?', help=argparse.SUPPRESS) # Hide in help
    
    parser.add_argument('--manifest', help="Path to manifest.json file to identify files to optimize")
    parser.add_argument('--safe-mode', action='store_true', help="Replace print statements with 'pass' instead of removing them")
    parser.add_argument('--no-backup', action='store_true', help="Don't create backup files")
    parser.add_argument('--keep-docstrings', action='store_true', help="Keep docstrings")
    parser.add_argument('--keep-prints', action='store_true', help="Keep print statements")
    parser.add_argument('--keep-comments', action='store_true', help="Keep regular comments")
    parser.add_argument('--preserve-header', action='store_true', help="Preserve file header comments")
    parser.add_argument('--remove-imports', action='store_true', help="Remove unused imports (experimental)")
    parser.add_argument('--stats-only', action='store_true', help="Show statistics without modifying files")
    parser.add_argument('--verbose', action='store_true', help="Show detailed information")
    parser.add_argument('--exclude', help="Comma-separated list of files to exclude")
    parser.add_argument(
        '--remove-redundant-if-else',
        action='store_true',
        help="Experimental: Remove if-else blocks where both branches are empty or pass"
    )
    
    args = parser.parse_args()
    
    # Support both positional and named arguments
    # Named arguments take precedence
    if args.input is None and args.input_pos is not None:
        args.input = args.input_pos
    if args.output is None and args.output_pos is not None:
        args.output = args.output_pos
    
    return args


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
        
    # Ensure output_dir exists
    os.makedirs(output_dir, exist_ok=True)
        
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
        
        # Construct output path - importantly, use output_dir as the base
        output_path = os.path.normpath(os.path.join(output_dir, file_path))
        
        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
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
        
        # Make sure output directory exists
        os.makedirs(output_path, exist_ok=True)
        
        # Print info about paths
        if args.verbose:
            print(f"Manifest directory: {manifest_dir}")
            print(f"Output directory: {output_path}")
        
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
    elif args.safe_mode:
        print(colorize("\nSafe mode: Print statements were replaced with 'pass'", Colors.BLUE))


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