# Progress Tracking System

The Salesforce Attachments Extraction tool includes a comprehensive progress tracking system that provides real-time visual feedback during the extraction workflow.

## Features

### Multi-Stage Progress Tracking
- **CSV Processing**: Tracks CSV file discovery, processing, and record extraction
- **SOQL Querying**: Shows batch execution progress and attachment discovery
- **File Downloads**: Displays download progress with speed and status counts

### Multiple Display Modes

#### Rich Display (Preferred)
- Hierarchical tree-style progress display
- Individual progress bars for each stage
- Detailed sub-information (current files, speeds, counts)
- Color-coded status indicators
- Real-time updates

#### tqdm Fallback
- Simple progress bars for broader compatibility
- Works in environments where Rich is not available
- Minimal terminal requirements

#### Disabled Mode
- No progress display for non-interactive environments
- Suitable for CI/CD, cron jobs, or when output needs to be clean

## Configuration

### CLI Arguments
```bash
# Auto-detect best display mode (default)
python main.py --progress auto

# Force progress display (prefer Rich)
python main.py --progress on

# Disable progress display
python main.py --progress off
```

### Environment Variables
```bash
# In .env file
PROGRESS=auto   # auto, on, off
```

### Automatic Detection
The `auto` mode (default) automatically selects the best available renderer:
1. **Rich** - If available and terminal supports it
2. **tqdm** - Fallback if Rich is not available
3. **None** - If no renderers are available

## Installation

The progress system requires additional dependencies:

```bash
pip install rich tqdm
```

These are automatically included when installing from `requirements.txt`.

## Stage Details

### 1. CSV Processing Stage
**Tracks:**
- CSV files discovered in the records directory
- Current CSV file being processed
- Record extraction progress
- Total records across all CSV files

**Display Information:**
- `Processing: filename.csv`
- `Files found: N`
- `Total records: N`
- `Current: N records`

### 2. SOQL Query Stage
**Tracks:**
- Total query batches to execute
- Current batch being processed
- Attachments found per batch
- Cumulative attachment count

**Display Information:**
- `Batch: N/Total`
- `CSV: current_file.csv`
- `Batch size: N`
- `Batch records: N`
- `Total attachments: N`

### 3. Download Stage
**Tracks:**
- Total files to download
- Current file being downloaded
- Download speed/throughput
- Success/failure/skip counts
- Bytes transferred

**Display Information:**
- `File: filename.ext`
- `Speed: XX.X MB/s`
- `Size: XX.X MB`
- `Status: ✓N/✗N/⊙N` (success/failed/skipped)
- `Transferred: XX.X MB`

## Error Handling

The progress system is designed to be non-intrusive:

- **Renderer Errors**: Falls back to simpler display or no progress
- **Stage Errors**: Individual stages can fail without affecting others
- **Thread Safety**: All progress updates are thread-safe using RLock
- **Graceful Degradation**: Works even if progress libraries are missing

## Thread Safety

The progress tracking system is fully thread-safe:
- All stage updates use RLock for synchronization
- Renderer updates are queued and batched
- Callback mechanisms prevent deadlocks
- Safe for future concurrent download implementations

## Integration

### In Workflows
```python
from src.progress import setup_progress_tracker
from src.progress.stages import CsvProcessingStage, SoqlQueryStage, DownloadStage

# Setup progress tracker
progress_tracker = setup_progress_tracker(mode="auto")

# Create and add stages
csv_stage = CsvProcessingStage()
progress_tracker.add_stage(csv_stage)

# Use context manager for automatic cleanup
with progress_tracker:
    # Update progress during workflow
    csv_stage.start_discovery(records_dir)
    csv_stage.update_discovery(files_found)
    # ... workflow continues
```

### In Download Functions
```python
from src.progress.download_wrapper import download_attachments_with_progress

# Use progress-aware download function
download_stats = download_attachments_with_progress(
    metadata_csv=csv_path,
    output_dir=output_dir,
    progress_stage=download_stage,
    org_alias=org_alias
)
```

## Dependencies

### Required
- **Python 3.8+**: Modern type hints and features

### Optional (for progress display)
- **rich>=13.0.0**: Primary progress renderer
- **tqdm>=4.64.0**: Fallback progress renderer

### Graceful Degradation
The tool works without progress dependencies but provides better user experience with them:

```bash
# Full experience
pip install rich tqdm

# Basic experience (no progress display)
# (dependencies missing - tool still works)
```

## Demo

Test the progress system with a simulation:

```bash
# Test with Rich display
python demo_progress.py auto

# Test with tqdm fallback  
python demo_progress.py on

# Test without progress
python demo_progress.py off
```

## Troubleshooting

### Progress Not Showing
1. Check that `--progress` is not set to `off`
2. Verify Rich or tqdm are installed: `pip install rich tqdm`
3. Ensure terminal supports progress display (TTY)

### Rich Display Issues
- Falls back to tqdm automatically
- Check terminal color support
- Verify Rich version: `pip install "rich>=13.0.0"`

### Performance Impact
- Progress updates are batched and optimized
- Minimal performance overhead (<1% typical)
- Can be disabled with `--progress off` if needed

## Architecture

The progress system follows a clean, modular architecture:

```
src/progress/
├── __init__.py              # Main module exports
├── core/                    # Core tracking classes  
│   ├── tracker.py          # Main ProgressTracker
│   └── stage.py            # ProgressStage base class
├── display/                 # Display renderers
│   ├── rich_renderer.py    # Rich-based display
│   └── tqdm_renderer.py    # tqdm-based display  
├── stages/                  # Stage implementations
│   ├── csv_stage.py        # CSV processing stage
│   ├── soql_stage.py       # SOQL query stage
│   └── download_stage.py   # Download stage
├── utils.py                 # Helper utilities
└── download_wrapper.py     # Progress-aware downloads
```

This modular design allows for easy extension with new stages, renderers, or workflow types.