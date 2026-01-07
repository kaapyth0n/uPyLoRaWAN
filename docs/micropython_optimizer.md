# MicroPython Code Optimizer

Tool for optimizing MicroPython code files for deployment on constrained devices like the Raspberry Pi Pico W.

## What It Does

The optimizer reduces code size by:
- Removing docstrings (module, class, and function documentation)
- Removing single-line comments (`# comment`)
- Removing print statements (optional)
- Removing empty lines and trailing whitespace
- Optionally removing unused imports (experimental)

Typical size reduction: **30-50%**

## Basic Usage

### Single File

```bash
# Optimize a single file (creates backup .bak file)
python micropython_optimizer.py main.py

# Optimize without backup
python micropython_optimizer.py --no-backup main.py

# Optimize to a different output file
python micropython_optimizer.py main.py optimized/main.py
```

### Using Manifest (Recommended)

Process all files listed in `manifest.json`:

```bash
# Optimize all manifest files in place
python micropython_optimizer.py --manifest=manifest.json

# Optimize to a separate directory
python micropython_optimizer.py --manifest=manifest.json optimized/

# Show statistics without modifying files
python micropython_optimizer.py --manifest=manifest.json --stats-only
```

### Directory

```bash
# Optimize all .py files in a directory
python micropython_optimizer.py src/ optimized/
```

## Command Line Options

| Option | Description |
|--------|-------------|
| `--input=FILE` | Input file or directory (alternative to positional argument, not needed with --manifest) |
| `--output=DIR` | Output file or directory (alternative to positional argument, defaults to input) |
| `--manifest=FILE` | Use manifest.json to identify files to optimize |
| `--no-backup` | Don't create .bak backup files |
| `--keep-docstrings` | Preserve docstrings (class/function documentation) |
| `--keep-prints` | Keep print statements |
| `--keep-comments` | Keep regular comments |
| `--preserve-header` | Keep the first comment block at file start |
| `--safe-mode` | Replace print statements with `pass` instead of removing |
| `--remove-imports` | Attempt to remove unused imports (experimental) |
| `--stats-only` | Show statistics without modifying files |
| `--verbose` | Show detailed processing information |
| `--exclude=FILE1,FILE2` | Comma-separated list of files to exclude |
| `--remove-redundant-if-else` | Experimental: Remove if-else blocks where both branches are empty or pass |
| `--spaces-to-tabs` | Convert spaces used for indentation to tabs |
| `--tab-size=N` | Number of spaces that represent one tab when using --spaces-to-tabs (default: 4) |

## Typical Workflow

### Creating an Optimized Release Branch

1. **Ensure source branch is ready**:
   ```bash
   git checkout lora_2512
   # Make sure all changes are committed
   ```

2. **Update manifest** (tracks file versions/hashes):
   ```bash
   python manifest_generator.py
   ```

3. **Create optimized branch from existing optimized base**:
   ```bash
   git checkout testing_o2
   git checkout -b lora_2512_o
   ```

4. **Copy source files to optimized branch**:
   ```bash
   git checkout lora_2512 -- main.py config_manager.py constants.py ...
   ```

5. **Run optimizer**:
   ```bash
   python micropython_optimizer.py --manifest=manifest.json --verbose
   ```

6. **Update manifest with optimized file hashes**:
   ```bash
   python manifest_generator.py
   ```

7. **Commit and push**:
   ```bash
   git add -A
   git commit -m "Optimized build for lora_2512"
   git push -u origin lora_2512_o
   ```

## Branch Naming Convention

| Branch Type | Naming | Example |
|-------------|--------|---------|
| Source (development) | `feature_name` | `lora_2512` |
| Optimized (deployment) | `feature_name_o` | `lora_2512_o` |
| Base optimized | `testing_o2` | Fork optimized branches from here |

## Example Output

```
Processing 25 files from manifest
Optimizing: main.py
Optimizing: config_manager.py
...

Manifest File Optimization Results
Files processed: 25
Total original size: 306.38 KB
Total optimized size: 189.10 KB
Total bytes saved: 117.28 KB
Average reduction: 38.28%

File Details:
--------------------------------------------------------------------------------
Filename                    Original   Optimized  Saved      Reduction
--------------------------------------------------------------------------------
main.py                     39.91 KB   25.49 KB   14.42 KB   36.14%
lora_handler.py             32.86 KB   19.70 KB   13.16 KB   40.06%
config_manager.py           18.88 KB   12.01 KB   6.88 KB    36.41%
...
```

## Notes

- **Python 3.8+ compatible**: Uses `ast.Constant` for string detection (replaces deprecated `ast.Str`)
- **Safe defaults**: Creates backup files unless `--no-backup` is specified
- **Preserves functionality**: Only removes documentation and whitespace, not code logic
- **Manifest integration**: Works with `manifest.json` for OTA update tracking
