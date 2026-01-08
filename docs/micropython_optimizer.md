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

| Option                       | Description                                                                              |
| ---------------------------- | ---------------------------------------------------------------------------------------- |
| `--input=FILE`               | Input file or directory (alternative to positional argument, not needed with --manifest) |
| `--output=DIR`               | Output file or directory (alternative to positional argument, defaults to input)         |
| `--manifest=FILE`            | Use manifest.json to identify files to optimize                                          |
| `--no-backup`                | Don't create .bak backup files                                                           |
| `--keep-docstrings`          | Preserve docstrings (class/function documentation)                                       |
| `--keep-prints`              | Keep print statements                                                                    |
| `--keep-comments`            | Keep regular comments                                                                    |
| `--preserve-header`          | Keep the first comment block at file start                                               |
| `--safe-mode`                | Replace print statements with `pass` instead of removing                                 |
| `--remove-imports`           | Attempt to remove unused imports (experimental)                                          |
| `--stats-only`               | Show statistics without modifying files                                                  |
| `--verbose`                  | Show detailed processing information                                                     |
| `--exclude=FILE1,FILE2`      | Comma-separated list of files to exclude                                                 |
| `--remove-redundant-if-else` | Experimental: Remove if-else blocks where both branches are empty or pass                |
| `--spaces-to-tabs`           | Convert spaces used for indentation to tabs                                              |
| `--tab-size=N`               | Number of spaces that represent one tab when using --spaces-to-tabs (default: 4)         |

## Typical Workflow

### Creating an Optimized Release Branch

1. **Ensure source branch is ready**:

   ```bash
   git checkout lora_2512
   # Make sure all changes are committed
   ```

2. **Switch to optimized branch** (create from base or update existing):

   ```bash
   # If branch doesn't exist, create from optimized base:
   git checkout lora_latest_o
   git checkout -b lora_2512_o

   # If branch exists, fast-forward to latest:
   git checkout lora_2512_o
   git reset --hard origin/lora_2512_o
   ```

3. **Copy source files and tools to optimized branch**:

   ```bash
   # Copy all files listed in manifest + the optimizer itself
   git checkout lora_2512 -- main.py config_manager.py constants.py module_detector.py \
       boot.py lora_handler.py mqtt_handler.py ... micropython_optimizer.py
   ```

4. **Run optimizer** (use Python 3.9+):

   ```bash
   python micropython_optimizer.py \
       --manifest=manifest.json --no-backup --remove-imports --spaces-to-tabs --verbose
   ```

5. **Review and stage changes** (excluding manifest.json):

   ```bash
   git add *.py ttn/*.py umqtt/*.py
   git diff --staged  # Review changes
   ```

   Discard changes in all the files that were not modified in the original branch since last optimized commit.

6. **Update manifest with optimized file hashes**:

   ```bash
   python manifest_generator.py
   git add manifest.json
   ```

   The manifest should show that only the originally modified files were changed

7. **Commit and push**:
   ```bash
   git commit -m "Copy the last commit message(s) from original branch"
   git push -u origin lora_2512_o
   ```

## Branch Naming Convention

| Branch Type            | Naming              | Example                           |
| ---------------------- | ------------------- | --------------------------------- |
| Source (development)   | `feature_name`      | `lora_2512`                       |
| Optimized (deployment) | `feature_name_o`    | `lora_2512_o`                     |
| Base optimized         | `lora_[lastYYMM]_o` | Fork optimized branches from here |

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

- **Python 3.9+ required**: The optimizer uses AST features (`end_lineno`, `ast.unparse`) that require Python 3.8+, but 3.9+ is recommended for full functionality. If your project uses an older Python version locally (e.g., via `.python-version`), run the optimizer explicitly with a newer version:
  ```bash
  ~/.pyenv/versions/3.12.1/bin/python micropython_optimizer.py ...
  ```
- **Safe defaults**: Creates backup files unless `--no-backup` is specified
- **Preserves functionality**: Only removes documentation and whitespace, not code logic
- **Manifest integration**: Works with `manifest.json` for OTA update tracking

## Known Issues

| Option                       | Issue                                                                                                                      | Recommendation            |
| ---------------------------- | -------------------------------------------------------------------------------------------------------------------------- | ------------------------- |
| `--remove-redundant-if-else` | Uses `ast.unparse` which normalizes quotes, breaking f-strings like `f"text{'.' * n}"` → `f'text{'.' * n}'` (syntax error) | **Don't use this option** |

## Recommended Options

For best results, use:

```bash
python micropython_optimizer.py --manifest=manifest.json --no-backup --remove-imports --spaces-to-tabs --verbose
```

This achieves ~50% size reduction while avoiding known issues.

## Automation Possibility

The entire workflow could be automated by adding a `--create-release` option to the optimizer:

```bash
python micropython_optimizer.py --create-release=lora_2512
```

This would:

1. Detect the source branch name (`lora_2512`)
2. Switch to/create the optimized branch (`lora_2512_o`)
3. Fast-forward to `origin/lora_2512_o` if it exists
4. Copy all files from manifest + `micropython_optimizer.py` from source branch
5. Run optimization with recommended options
6. Stage optimized files (excluding `manifest.json`)
7. Optionally run `manifest_generator.py` and commit

Implementation would require:

- Reading file list from `manifest.json`
- Git operations via `subprocess` or `gitpython`
- Python version detection (warn if < 3.9)
- Interactive confirmation before committing
