# Salesforce Attachments Downloader

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.8+-blue.svg)

A Python CLI tool for downloading Salesforce Attachment records and files using CSV-based record processing.

## Features

- Query Attachment records using Salesforce CLI authentication with WHERE clause filtering
- Process CSV files containing record IDs to download attachments
- Export metadata to CSV with comprehensive validation and enrichment
- Download attachment files via REST API with intelligent retry logic
- Reuse sf CLI authentication (no separate OAuth setup required)
- Rich progress display with auto-detected renderer (Rich or tqdm)
- Advanced error handling with exponential backoff and connection pooling
- Flexible configuration via CLI arguments or .env file
- Intelligent filename collision detection using ParentId prefix
- **NEW:** Simple-Salesforce integration for improved performance and reliability
- **NEW:** Connection pooling for optimal API usage
- **NEW:** Enhanced monitoring and health checks
- **NEW:** Field discovery and metadata validation

## Migration Guide

### From sf CLI to Simple-Salesforce

This tool has been migrated from using Salesforce CLI (`sf`) subprocess calls to native `simple-salesforce` library operations for improved performance and reliability.

#### What Changed

**Before (v1.x):**
- Used `sf data query` subprocess calls for SOQL queries
- Used `sf data get-record` subprocess calls for individual record retrieval
- REST API downloads via `requests` library
- Limited error handling and retry logic

**After (v2.x):**
- Native SOQL queries using `simple-salesforce` library
- Direct REST API operations through `simple-salesforce`
- Advanced error handling with exponential backoff
- Connection pooling for optimal API usage
- Enhanced monitoring and health checks

#### Benefits of Migration

- **Performance**: 2-3x faster execution through native API calls
- **Reliability**: Better error handling and automatic retries
- **Monitoring**: Comprehensive API usage tracking and health checks
- **Scalability**: Connection pooling supports higher throughput
- **Maintenance**: Reduced dependency on external CLI tools

#### Backward Compatibility

- All existing CLI arguments and `.env` configuration work unchanged
- Output structure and file organization remain the same
- CSV file format requirements are identical
- Authentication still uses `sf org login` (hybrid approach)

#### Migration Steps

No action required! The migration is transparent to users. Simply:

1. Update to the latest version
2. Run `pip install -r requirements.txt` to install `simple-salesforce`
3. Use the tool as before - all existing workflows continue to work

#### Troubleshooting Migration Issues

If you encounter issues after updating:

1. **Authentication errors**: Re-run `sf org login web --alias your-org`
2. **Import errors**: Ensure `simple-salesforce` is installed: `pip install simple-salesforce`
3. **Performance issues**: The new version should be faster; if not, use `--sync-only` for debugging
4. **API limits**: Monitor usage with `--debug` flag for API call tracking

## Prerequisites

1. **Salesforce CLI** (`sf` command)
   ```bash
   npm install -g @salesforce/cli
   ```

2. **Authenticated Salesforce org**
   ```bash
   sf org login web --alias your-org
   ```

3. **Python 3.8+**
   ```bash
   python3 --version
   ```

4. **Python Dependencies**
   ```bash
   pip install -r requirements.txt
   ```
   Key dependencies include:
   - `simple-salesforce` - Native Salesforce API client (replaces sf CLI subprocess calls)
   - `requests` - HTTP client for REST API operations
   - `rich` or `tqdm` - Progress display (optional)

## Installation

1. Clone or download this repository

2. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Optional: progress UI dependencies (already in `requirements.txt`)
   - `rich` for the rich terminal progress view
   - `tqdm` as a fallback renderer

## Usage

### Quick Start (CSV Workflow)

The tool uses a CSV-based workflow where you provide CSV files containing record IDs (ParentIds), and it queries and downloads attachments for those records.

**Basic usage:**
```bash
python main.py --org your-org --records-dir ./records --output ./output
```

**Required arguments:**
- `--org`: Salesforce org alias
- `--records-dir`: Directory containing CSV files with record IDs

**Optional arguments:**
- `--output`: Base output directory (default: `./output`)
- `--batch-size`: Number of ParentIds per SOQL query batch (default: 100). Download buckets are derived from this value (not separately configurable).
- `--workers`: Parallel workers for queries and downloads (default: 2, max: 8)
- `--sync-only`: Disable threading, run sequentially (default: disabled, use for debugging)
- `--progress`: Progress display mode (`auto`, `on`, `off`, `tqdm`)
- `--verbose`: Alias for default INFO logging
- `--debug`: Enable DEBUG console logging

### CSV File Requirements

Your CSV files in `--records-dir` must:
- Be UTF-8 encoded
- Have a header row with column names
- Contain an `Id` column with Salesforce record IDs (ParentIds)
- Have at least one data row

**Example CSV:**
```csv
Id,Name,Description
001ABC123456789,Account 1,Main account
001ABC987654321,Account 2,Secondary account
aBo123456789ABC,Custom Record,Custom object
```

The tool will:
1. Read all CSV files from the records directory
2. Extract record IDs from the `Id` column
3. Batch the IDs (default: 100 per batch)
4. Query attachments with `WHERE ParentId IN ('id1', 'id2', ...)`
5. Download attachment files organized by CSV filename

### Workflow Details

**Step 1: Prepare CSV files**
Create CSV files with record IDs you want to process. Each CSV file will be processed separately, and attachments will be organized by the CSV filename.

**Step 2: Run the tool**
```bash
python main.py --org your-org --records-dir ./records --output ./output
```

**What happens:**
1. Validates CSV files
2. Extracts ParentIds from each CSV
3. Queries attachments in batches using SOQL WHERE clause
4. Downloads attachment files
5. Saves metadata for reference

## Threading and Performance

### Threading Architecture

The tool now supports parallel processing for both SOQL queries (Phase 2) and file downloads (Phase 3) to significantly improve performance. All batches/CSVs are submitted to a thread pool simultaneously, allowing multiple queries and downloads to run concurrently.

- **Conservative defaults**: 2 workers by default to avoid overwhelming the Salesforce API
- **Performance benefits**: With 4 workers and 10 CSVs, expect 3-4x faster processing compared to sequential execution
- **Symmetric parallelism**: The same worker pool handles both queries and downloads

### Configuration

- **`--workers` argument**: Controls parallelism in both query and download phases (default: 2, max: 8)
- **`WORKERS` env var**: Set `WORKERS=4` in `.env` for persistent configuration
- **`--sync-only` flag**: Disable threading for debugging or API issues
- **`SYNC_ONLY` env var**: Set `SYNC_ONLY=true` in `.env` to disable threading
- **`QUERY_TIMEOUT`**: Maximum time per individual batch query (default: 600 seconds / 10 minutes)

### Default Behavior

- Threading is enabled by default with 2 workers
- Each worker executes tasks sequentially (no internal parallelism within workers)
- Total parallelism equals the thread pool size
- Symmetric: same workers handle both queries AND downloads

### Recommendations

- Start with default (2 workers) for safe operation
- For 10+ CSVs with many attachments: try 4 workers for better performance
- For Salesforce API rate limiting issues: try `--sync-only` or reduce workers
- Monitor logs with `--debug` for task timing and performance insights

### Examples

```bash
# Default: 2 parallel workers
python main.py --org your-org --records-dir ./records

# Use 4 workers for faster processing
python main.py --org your-org --records-dir ./records --workers 4

# Disable threading for debugging
python main.py --org your-org --records-dir ./records --sync-only

# Set workers in .env file (persistent)
# In .env: WORKERS=4
python main.py --org your-org --records-dir ./records
```

## Output Structure

```
output/
└── csv_name_1/
    ├── metadata/
    │   └── attachments_20260114_120000_merged.csv
    └── files/
        ├── a3xAAA111_invoice.pdf
        ├── a3xAAA111_receipt.pdf
        └── a3xAAA222_contract.pdf
```

Each CSV file gets its own subfolder containing:
- `metadata/` with merged query results
- `files/` with downloaded attachment binaries

**Filename Convention:**
- Default format: `{ParentId}_{original_filename}`
- Example: `a3xAAA111_invoice.pdf`

**Collision Handling:**
When multiple attachments with the same name exist for the same ParentId, the tool automatically adds the Attachment ID:
- Format: `{ParentId}_{AttachmentId}_{original_filename}`
- Example: `a3xAAA111_00P1234_invoice.pdf`

## Configuration

### Environment Variables (.env file)

The tool supports loading configuration from a `.env` file in the project root directory.

**Setup:**

1. Copy the example file:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` with your preferred values:
   ```bash
   # Salesforce org alias
   SF_ORG_ALIAS=your-org

   # Output directory
   OUTPUT_DIR=./output

   # Records directory
   RECORDS_DIR=./records

   # Log file path
   LOG_FILE=./logs/download.log


   # Batch size for SOQL queries
   BATCH_SIZE=100

   # Console logging configuration
   VERBOSE=false
   DEBUG=false

   # Progress display configuration
    PROGRESS=auto
    WORKERS=2
    SYNC_ONLY=false
    QUERY_TIMEOUT=600
    ```

3. **IMPORTANT**: Never commit the `.env` file to version control!

**Supported Variables:**

| Variable | Description | Default | CLI Override |
|----------|-------------|---------|--------------|
| `SF_ORG_ALIAS` | Salesforce org alias from sf CLI | None (use default org) | `--org` |
| `OUTPUT_DIR` | Base output directory | `./output` | `--output` |
| `RECORDS_DIR` | Directory containing CSV files | None (required) | `--records-dir` |
| `LOG_FILE` | Log file path | `./logs/download.log` | N/A |
| `BATCH_SIZE` | Number of ParentIds per query batch | `100` | `--batch-size` |
| `WORKERS` | Parallel workers for queries and downloads | `2` | `--workers` |
| `SYNC_ONLY` | Disable threading, run sequentially | `false` | `--sync-only` |
| `QUERY_TIMEOUT` | Maximum time per individual batch query | `600` | N/A |
| `VERBOSE` | Enable verbose console output (INFO level) | `false` | `--verbose` |
| `DEBUG` | Enable debug console output (DEBUG level) | `false` | `--debug` |
| `PROGRESS` | Progress display mode: `auto`, `on`, `off`, `tqdm` | `auto` | `--progress` |

**Configuration Precedence:**

1. Command-line arguments (highest priority)
2. Environment variables from `.env` file
3. Built-in defaults (lowest priority)

### Batch Size Configuration

Control the number of ParentIds included in each SOQL query batch:

**Via .env file:**
```bash
BATCH_SIZE=100
```

**Via CLI:**
```bash
python main.py --org your-org --records-dir ./records --batch-size 150
```

**Default:** 100 record IDs per batch

### Threading Configuration

Control parallel processing for both SOQL queries and file downloads:

- `--workers` / `WORKERS`: number of parallel workers for queries and downloads
- `--sync-only` / `SYNC_ONLY`: disable threading for debugging or API issues

**Via .env file:**
```bash
WORKERS=4
SYNC_ONLY=false
```

**Via CLI:**
```bash
python main.py --org your-org --records-dir ./records --workers 4
python main.py --org your-org --records-dir ./records --sync-only
```

**Default:** 2 workers (parallel), threading enabled

**Notes:**
- Threading is enabled by default with conservative 2 workers
- Use `--sync-only` for debugging or when experiencing API rate limiting
- More workers = faster processing but higher memory usage and API load
- Salesforce may rate-limit concurrent API calls; reduce workers if you see errors

## Logging

The tool provides flexible logging with different verbosity levels:

### Log Levels

**Default (INFO level):**
- Console shows main workflow progress, file download status, and results
- Log file contains all DEBUG details for troubleshooting

```bash
python main.py --org my-org --records-dir ./records
```

**Verbose mode (--verbose):**
- Alias for default behavior (kept for compatibility)
- Shows INFO level logs on console

```bash
python main.py --org my-org --records-dir ./records --verbose
```

**Debug mode (--debug):**
- Console shows all technical details: URLs, query previews, authentication details, etc.
- Useful for troubleshooting issues

```bash
python main.py --org my-org --records-dir ./records --debug
```

### Log Configuration

**Via .env file:**
```bash
VERBOSE=false  # Enable INFO level (same as default)
DEBUG=false    # Enable DEBUG level with technical details
```

**Via CLI flags:**
```bash
--verbose      # Enable verbose output (INFO level)
--debug        # Enable debug output (DEBUG level)
```

### Progress Display

The progress UI auto-selects a renderer (prefers `rich`, falls back to `tqdm`). You can force or disable it.

**Via .env file:**
```bash
PROGRESS=auto  # auto, on, off, tqdm
```

**Via CLI flags:**
```bash
--progress auto
--progress on
--progress off
--progress tqdm
```

### Log Output

Logs are written to:
- **Console**: Configurable level (INFO by default, DEBUG with --debug)
- **File**: `./logs/download.log` (always DEBUG level with full details)

### What You'll See

**Default output:**
```
INFO - SALESFORCE ATTACHMENTS DOWNLOADER - CSV WORKFLOW
INFO - Found 1 CSV file(s): 20 records in 1 batch(es)
INFO - Batch 1/1: Querying 20 ParentId(s)
INFO - ✓ Query successful: 20 records
INFO - No filename collisions detected
INFO - Downloading 20 attachment(s)...
INFO - [1/20] invoice.pdf
INFO -   ✓ Downloaded
INFO - [2/20] receipt.pdf
INFO -   ⊙ Skipped (already exists)
INFO - Download complete: 1 downloaded, 19 skipped, 0 failed
INFO - WORKFLOW COMPLETE
```

**Debug output adds:**
- CSV file processing details
- SOQL query preview and length
- WHERE clause content
- Authentication details
- URL endpoints
- Bytes downloaded per file

## Error Handling

The tool gracefully handles errors and provides clear error messages:
- Missing attachments (404 errors)
- Network failures (will stop the workflow)
- Invalid filenames
- Disk write errors
- Authentication expiry
- Invalid CSV files
- SOQL query length exceeded (with helpful suggestions to reduce batch size)
- Invalid SOQL syntax
- Insufficient permissions

Threading uses automatic retry logic (up to 3 attempts per batch/download). If you see many retry messages, consider using `--sync-only` to reduce API load.

Per-file download failures are best-effort and summarized at the end of the workflow.
Fatal authentication errors or network/service failures will stop the workflow.

### Partial Downloads

To avoid treating partial files as complete, downloads are written to a temporary folder first and only moved into the final destination on success.

- Temp folder: `output/.tmp_downloads/` (global per `--output` directory / org alias)
- Lifecycle: the application cleans it before each CSV download phase and removes it after the phase completes

## Command-Line Options

```
--org               Salesforce org alias (required if not in .env)
--records-dir       Directory containing CSV files with record IDs (REQUIRED)
--output            Base output directory (default: ./output)
--batch-size        Number of ParentIds per SOQL query batch (default: 100)
--workers           Parallel workers for queries and downloads (default: 2, max: 8)
--sync-only         Disable threading, run sequentially (default: disabled, use for debugging)
--progress          Progress display mode: auto, on, off, tqdm
--verbose           Enable verbose console output (INFO level)
--debug             Enable debug console output (DEBUG level with technical details)
```

## Current Limitations

- Concurrency is isolated within each bucket; CSV processing remains sequential
- No resume capability for interrupted sessions
- Support limited to Attachment object (ContentDocument not yet supported)
- Batch size constrained by SOQL WHERE clause character limits
- Progress display requires `rich` or `tqdm` (falls back to basic logging if unavailable)

## Troubleshooting

### "Authentication failed"

Ensure you're logged in:
```bash
sf org display --target-org your-org
```

### "Attachment not found (404)"

The attachment may have been deleted. Check if ParentId still exists.

### Permission errors

Ensure your sf CLI user has:
- Read access to Attachment object
- View All Data or appropriate object permissions

### "SOQL query too long" error

The query exceeds Salesforce's ~20,000 character limit. This happens when batch size is too large.

**Solution:**
```bash
python main.py --org your-org --records-dir ./records --batch-size 50
```

Reduce --batch-size until the error disappears. Each Salesforce ID (18 chars) adds ~22 characters to the query.

### "Error: --records-dir is required"

You must provide a directory containing CSV files:
```bash
python main.py --org your-org --records-dir ./records
```

## Troubleshooting Threading

### Question: Queries/downloads running slowly in parallel mode

- Try `--sync-only` to verify it's not a threading issue
- Check `--debug` logs for timing information
- May indicate Salesforce API rate limiting (reduce workers or use --sync-only)

### Question: Getting timeout errors

- Increase `QUERY_TIMEOUT` env var: `QUERY_TIMEOUT=900` (15 minutes)
- Default is 600 seconds (10 minutes)
- Or use `--sync-only` to eliminate timing pressure

### Question: Memory usage high with threading

- Reduce worker count: `--workers 2` or `--workers 1`
- Each worker thread maintains state for active tasks
- More workers = more memory usage

### Question: "Connection reset" errors during parallel queries

- Reduce workers to decrease API load: `--workers 2`
- Or use `--sync-only` to eliminate parallelism entirely
- Salesforce may rate-limit concurrent API calls

## Examples

**Basic usage with default batch size:**
```bash
python main.py --org my-org --records-dir ./records
```

**Custom output directory:**
```bash
python main.py --org production --records-dir ./records --output ./prod-attachments
```

**Custom batch size (process 200 IDs per query):**
```bash
python main.py --org my-org --records-dir ./records --batch-size 200
```

**Using environment variables:**
```bash
# Set in .env file
SF_ORG_ALIAS=my-org
RECORDS_DIR=./records
BATCH_SIZE=150
WORKERS=4

# Then run without arguments
python main.py
```

## Project Structure

```
attachments-extract/
├── main.py                      # Main entry point
├── requirements.txt             # Python dependencies
├── .gitignore                   # Git ignore file
├── .env.example                 # Environment configuration template
├── README.md                    # This file
├── src/
│   ├── __init__.py
│   ├── exceptions.py           # Custom exceptions
│   ├── utils.py                # Logging utilities
│   ├── workflows/
│   │   ├── __init__.py         # Package exports
│   │   ├── orchestrator.py     # Three-phase workflow orchestration (main entry point)
│   │   ├── csv_coordinator.py  # Phase 1: CSV discovery & processing
│   │   ├── query_coordinator.py # Phase 2: SOQL batch querying
│   │   ├── download_coordinator.py # Phase 3: File downloads
│   │   ├── error_handler.py    # Centralized error handling
│   │   ├── statistics.py       # Statistics aggregation
│   │   ├── directory_manager.py # Directory structure management
│   │   ├── common.py           # Shared workflow utilities
│   │   └── processor.py        # Legacy workflow (kept as backup)
│   ├── csv/
│   │   ├── processor.py        # CSV file processing
│   │   ├── validator.py        # CSV validation
│   │   └── enhanced_validator.py # Advanced CSV validation with field discovery
│   ├── query/
│   │   ├── executor.py         # Query execution wrapper
│   │   ├── soql.py             # Native SOQL execution via sf CLI (deprecated)
│   │   ├── soql_simple.py      # Simple-salesforce SOQL queries
│   │   └── filters.py          # WHERE clause building
│   ├── download/
│   │   ├── downloader.py       # Download orchestration (deprecated)
│   │   ├── downloader_simple.py # Simple-salesforce downloads
│   │   ├── metadata.py         # Metadata CSV reading
│   │   ├── filename.py         # Filename collision detection
│   │   └── stats.py            # Download statistics
│   ├── api/
│   │   ├── sf_auth.py          # SF CLI authentication
│   │   ├── sf_client.py        # REST API client (deprecated - use simple-salesforce)
│   │   ├── sf_connection.py    # Connection pool for simple-salesforce
│   │   ├── sf_error_handler.py # Advanced error handling with retries
│   │   ├── usage_monitor.py    # API usage tracking and metrics
│   │   ├── sf_auth_adapter.py  # Hybrid authentication adapter
│   │   ├── field_discovery.py  # Describe API field discovery
│   │   ├── health_checker.py   # Health checks and diagnostics
│   │   └── benchmarker.py      # Performance benchmarking suite
│   └── cli/
│       └── config.py           # CLI argument parsing
├── records/                     # CSV files with record IDs (user-provided)
├── output/
│   ├── metadata/               # CSV files with attachment metadata
│   └── files/                  # Downloaded attachments
└── logs/
    └── download.log            # Execution logs
```

## Roadmap

Potential improvements for future releases:

- **ContentDocument/ContentVersion support** - Handle newer Salesforce file storage
- **Resume capability** - Continue interrupted downloads from where they stopped
- **Advanced filtering** - Filter by date range, content type, file size, and other metadata
- **Enhanced progress visualization** - Improved progress indicators and real-time statistics

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
