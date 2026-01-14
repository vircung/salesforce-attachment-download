# Salesforce Attachments Downloader

Tool to download Salesforce Attachment records and files using CSV-based record processing.

## Features

- Query Attachment records using Salesforce CLI with WHERE clause filtering
- Process CSV files containing record IDs to download attachments
- Export metadata to CSV
- Download attachment files via REST API
- Reuse sf CLI authentication (no separate OAuth)
- Progress indicators and logging
- Error handling for common failures
- Flexible configuration via CLI arguments or .env file
- Intelligent filename collision detection using ParentId prefix

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

## Installation

1. Clone or download this repository

2. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

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
- `--batch-size`: Number of ParentIds per SOQL query batch (default: 100)

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

## Output Structure

```
output/
├── metadata/
│   ├── csv_name_1_batch_1_20260114_120000.csv
│   ├── csv_name_1_batch_2_20260114_120030.csv
│   └── csv_name_2_batch_1_20260114_120100.csv
└── files/
    ├── csv_name_1/
    │   ├── a3xAAA111_invoice.pdf
    │   ├── a3xAAA111_receipt.pdf
    │   └── a3xAAA222_contract.pdf
    └── csv_name_2/
        ├── 001BBB333_report.xlsx
        └── 001BBB444_document.docx
```

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

   # Download chunk size (bytes)
   CHUNK_SIZE=8192

   # Batch size for SOQL queries
   BATCH_SIZE=100
   ```

3. **IMPORTANT**: Never commit the `.env` file to version control!

**Supported Variables:**

| Variable | Description | Default | CLI Override |
|----------|-------------|---------|--------------|
| `SF_ORG_ALIAS` | Salesforce org alias from sf CLI | None (use default org) | `--org` |
| `OUTPUT_DIR` | Base output directory | `./output` | `--output` |
| `RECORDS_DIR` | Directory containing CSV files | None (required) | `--records-dir` |
| `LOG_FILE` | Log file path | `./logs/download.log` | N/A |
| `CHUNK_SIZE` | Download chunk size in bytes | `8192` | N/A |
| `BATCH_SIZE` | Number of ParentIds per query batch | `100` | `--batch-size` |

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

**Notes:**
- Larger batches = fewer queries but longer query execution time
- Smaller batches = more queries but faster individual queries
- Salesforce has SOQL query length limits (~20,000 characters)
- If you get "query too long" errors, reduce --batch-size to 50 or lower

## Logging

Logs are written to:
- **Console**: INFO level and above
- **File**: `./logs/download.log` (all levels)

## Error Handling

The tool handles:
- Missing attachments (404 errors)
- Network failures
- Invalid filenames
- Disk write errors
- Authentication expiry
- Invalid CSV files
- SOQL query length exceeded (with helpful suggestions to reduce batch size)
- Invalid SOQL syntax
- Insufficient permissions

Failed downloads are logged but don't stop the process.

## Command-Line Options

```
--org               Salesforce org alias (required if not in .env)
--records-dir       Directory containing CSV files with record IDs (REQUIRED)
--output            Base output directory (default: ./output)
--batch-size        Number of ParentIds per SOQL query batch (default: 100)
```

## Limitations

- No parallel downloads (sequential processing)
- No resume capability
- Basic error handling (no exponential backoff)
- No support for ContentDocument (newer file storage)
- Batch size limited by SOQL WHERE clause limits

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

# Then run without arguments
python main.py
```

## Project Structure

```
attachments-extract/
├── main.py                      # Main entry point
├── requirements.txt             # Python dependencies
├── .gitignore                   # Git ignore file
├── README.md                    # This file
├── CLAUDE.md                    # Project specifications
├── src/
│   ├── __init__.py
│   ├── exceptions.py           # Custom exceptions
│   ├── workflows/
│   │   └── csv_records.py      # CSV workflow orchestration
│   ├── csv/
│   │   ├── processor.py        # CSV file processing
│   │   └── validator.py        # CSV validation
│   ├── query/
│   │   ├── executor.py         # Query execution wrapper
│   │   ├── soql.py             # Native SOQL execution via sf CLI
│   │   └── filters.py          # WHERE clause building
│   ├── download/
│   │   └── downloader.py       # Download orchestration
│   ├── api/
│   │   ├── sf_auth.py          # SF CLI authentication
│   │   └── sf_client.py        # REST API client
│   ├── cli/
│   │   └── config.py           # CLI argument parsing
│   └── utils.py                # Logging utilities
├── records/                     # CSV files with record IDs (user-provided)
├── output/
│   ├── metadata/               # CSV files with attachment metadata
│   └── files/                  # Downloaded attachments
└── logs/
    └── download.log            # Execution logs
```

## Future Enhancements

- Support for ContentDocument/ContentVersion
- Parallel downloads
- Resume capability
- Progress bars
- Retry with exponential backoff
- Advanced filtering (date range, content type, file size)

## License

This is a proof-of-concept tool. Adapt as needed for your use case.
