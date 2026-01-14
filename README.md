# Salesforce Attachments Extract

Proof of concept tool to download Salesforce Attachment records and files.

## Features

- Query Attachment records using Salesforce CLI (configurable limit, default: 100)
- **Automatic pagination** to fetch target number of records using SOQL OFFSET
- **Filter attachments by ParentId** (prefix-based or exact ID matching)
- Export metadata to CSV
- Download attachment files via REST API
- Reuse sf CLI authentication (no separate OAuth)
- Progress indicators and logging
- Error handling for common failures
- Flexible configuration via CLI arguments or .env file
- Backward compatible (pagination is opt-in)

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

3. Make scripts executable:
   ```bash
   chmod +x scripts/query_attachments.sh
   ```

## Usage

### Quick Start (Full Workflow)

Run both query and download in one command:

```bash
python main.py --org your-org --output ./output
```

### Using Existing Metadata CSV

Skip the Salesforce query step and use an existing CSV file:

```bash
# Use a previously generated CSV
python main.py --metadata ./output/metadata/attachments_20250113_120000.csv

# Or provide your own CSV file
python main.py --metadata /path/to/my/attachments.csv --output ./downloads
```

**Via .env file:**
```bash
# Set in .env
METADATA_CSV=./output/metadata/attachments_20250113_120000.csv

# Then run without arguments
python main.py
```

**CSV Requirements:**
- Must be UTF-8 encoded
- Must have a header row with column names
- Must contain required columns: `Id`, `Name`
- Should contain `ParentId` column if using filters
- Must have at least one data row

**When to use this:**
- Re-download files after a previous run
- Process metadata from a different source
- Test download logic without querying Salesforce
- Resume after a failed download

### Step-by-Step

#### Step 1: Query Attachments

```bash
bash scripts/query_attachments.sh your-org ./output/metadata
```

This creates: `./output/metadata/attachments_YYYYMMDD_HHMMSS.csv`

#### Step 2: Download Files

```bash
python -m src.downloader \
  --metadata ./output/metadata/attachments_20260113_150000.csv \
  --output ./output/files \
  --org your-org
```

## Output Structure

```
output/
├── metadata/
│   └── attachments_20260113_150000.csv  # Attachment metadata
└── files/
    ├── 00P1234567890ABC_document.pdf
    ├── 00P1234567890DEF_image.png
    └── ...
```

## Configuration

### Environment Variables (.env file)

The tool supports loading configuration from a `.env` file in the project root directory. This is optional and provides default values that can be overridden by command-line arguments.

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

   # Log file path
   LOG_FILE=./logs/download.log

   # Download chunk size (bytes)
   CHUNK_SIZE=8192
   ```

3. **IMPORTANT**: Never commit the `.env` file to version control!

**Supported Variables:**

| Variable | Description | Default | CLI Override |
|----------|-------------|---------|--------------|
| `SF_ORG_ALIAS` | Salesforce org alias from sf CLI | None (use default org) | `--org` |
| `OUTPUT_DIR` | Base output directory | `./output` | `--output` |
| `LOG_FILE` | Log file path | `./logs/download.log` | N/A |
| `CHUNK_SIZE` | Download chunk size in bytes | `8192` | N/A |
| `QUERY_LIMIT` | Batch size per query (legacy: max records) | `100` | `--query-limit` |
| `TARGET_COUNT` | Target number of records (enables pagination) | None (disabled) | `--target-count` |
| `TARGET_MODE` | Pagination mode (exact/minimum) | `exact` | `--target-mode` |
| `PARENT_ID_PREFIX` | Comma-separated ParentId prefixes | None | `--parent-id-prefix` |
| `PARENT_IDS` | Comma-separated specific ParentIds | None | `--parent-ids` |
| `FILTER_STRATEGY` | Filtering strategy (python/soql) | `python` | `--filter-strategy` |

**Configuration Precedence:**

1. Command-line arguments (highest priority)
2. Environment variables from `.env` file
3. Built-in defaults (lowest priority)

Example: If you set `OUTPUT_DIR=./data` in `.env` but run `python main.py --output ./custom`, the tool will use `./custom`.

### Filtering Attachments by ParentId

You can filter attachments to download only those related to specific Salesforce objects. This is useful when Salesforce doesn't allow filtering by ParentId in the SOQL query.

#### Filter by Object Type (Prefix Matching)

Filter attachments by Salesforce object type using the 3-character ID prefix:

**Common Salesforce ID Prefixes:**
- `001` - Account
- `003` - Contact
- `006` - Opportunity
- `aBo` - EMS_Attachment__c (custom object example)

**Via .env file:**
```bash
PARENT_ID_PREFIX=aBo,001
```

**Via CLI:**
```bash
python main.py --org your-org --parent-id-prefix "aBo,001"
```

This will download only attachments where ParentId starts with `aBo` or `001`.

#### Filter by Exact ParentId

Filter attachments for specific parent records:

**Via .env file:**
```bash
PARENT_IDS=aBo1234567890ABC,aBo9876543210XYZ
```

**Via CLI:**
```bash
python main.py --org your-org --parent-ids "aBo1234567890ABC,aBo9876543210XYZ"
```

#### Filtering Strategies

**Python Strategy (Default):**
- Queries all attachments, then filters in Python
- Supports both prefix and exact ID filtering
- More flexible but queries more data

```bash
python main.py --org your-org --parent-id-prefix "aBo" --filter-strategy python
```

**SOQL Strategy:**
- Filters in the SOQL query itself
- Only supports exact ID filtering (no prefix matching)
- More efficient for large datasets

```bash
python main.py --org your-org --parent-ids "aBo123...,aBo456..." --filter-strategy soql
```

#### Empty Results Handling

If no attachments match your filter criteria:
- A warning message is logged
- The download phase is skipped gracefully
- The tool exits with code 0 (success)

### Query Limit Configuration

Control the maximum number of attachment records queried from Salesforce:

**Via .env file:**
```bash
QUERY_LIMIT=200
```

**Via CLI:**
```bash
python main.py --org your-org --query-limit 200
```

**Default:** 100 records

**Note:** When pagination is enabled (see below), `QUERY_LIMIT` becomes the batch size for each query.

### Pagination (Automatic Multi-Query Fetching)

Fetch more than the single-query limit by enabling pagination. The system will automatically execute multiple SOQL queries with OFFSET to retrieve your target number of records.

#### Configuration

**Via .env file:**
```bash
# Enable pagination by setting a target count
TARGET_COUNT=1000

# Target mode: 'exact' or 'minimum'
TARGET_MODE=exact

# Batch size for each query (optional, defaults to QUERY_LIMIT)
QUERY_LIMIT=200
```

**Via CLI:**
```bash
python main.py --org your-org --target-count 1000 --target-mode exact --query-limit 200
```

#### Target Modes

- **`exact`** (default): Fetches exactly `TARGET_COUNT` records (or all available if less)
  - Final result is trimmed to match the target precisely
  - Example: `TARGET_COUNT=1000` → exactly 1000 records returned

- **`minimum`**: Fetches at least `TARGET_COUNT` records (may fetch slightly more)
  - Keeps all records from all batches
  - Final count may exceed target by up to one batch size
  - Example: `TARGET_COUNT=1000`, `QUERY_LIMIT=200` → 1000-1200 records returned

#### How Pagination Works

1. **Batch Calculation**: System calculates required batches: `ceil(TARGET_COUNT / QUERY_LIMIT)`
2. **Query Execution**: Executes SOQL queries with OFFSET:
   - Query 1: `LIMIT 200 OFFSET 0`
   - Query 2: `LIMIT 200 OFFSET 200`
   - Query 3: `LIMIT 200 OFFSET 400`
   - Continues until target reached or no more records available
3. **CSV Merging**: All batches are merged into a single CSV file
4. **Trimming** (exact mode only): Final results are trimmed to exactly `TARGET_COUNT`

#### Pagination with Filters

Pagination works seamlessly with both filter strategies:

- **Python Strategy** (default): Pagination continues until `TARGET_COUNT` **filtered** matches are found
  - May fetch more batches if match rate is low
  - Filters are applied during pagination, not in downloader
  - Example: `TARGET_COUNT=100`, 20% match rate → fetches ~500 raw records across multiple batches

- **SOQL Strategy**: WHERE clause applied in each paginated query
  - More efficient for large datasets
  - Pagination stops when `TARGET_COUNT` matching records are fetched

#### SOQL Limits

- **Single query LIMIT**: 2000 records maximum
- **OFFSET maximum**: 2000
- **Maximum retrievable**: ~4000 records total using pagination

If you need more than 4000 records, consider filtering by date ranges or ParentId.

#### Examples

**Fetch 1000 records with exact count:**
```bash
python main.py --org your-org --target-count 1000 --target-mode exact --query-limit 200
# Executes 5 queries (200 × 5 = 1000), returns exactly 1000 records
```

**Fetch at least 500 records with minimum count:**
```bash
python main.py --org your-org --target-count 500 --target-mode minimum --query-limit 200
# Executes 3 queries (200 × 3 = 600), returns 600 records (full last batch kept)
```

**Pagination with Python filters:**
```bash
python main.py --org your-org --target-count 100 --parent-id-prefix aBo --filter-strategy python
# Continues querying until 100 filtered matches found
```

**Pagination disabled (legacy mode):**
```bash
python main.py --org your-org --query-limit 100
# Single query, 100 records maximum (TARGET_COUNT not set)
```

#### Backward Compatibility

Pagination is **opt-in** and fully backward compatible:
- If `TARGET_COUNT` is not configured: Uses legacy single-query mode
- Existing `.env` files work without changes
- Existing command-line invocations work unchanged

### Attachment Query

The query script automatically uses the configured query limit (default: 100). Attachments are always sorted by CreatedDate DESC (newest first).

### Download Behavior

Customize via `.env` file or edit `src/downloader.py`:
- Chunk size for streaming (configurable via `CHUNK_SIZE`, default: 8192 bytes)
- Filename sanitization rules
- Error handling behavior

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

Failed downloads are logged but don't stop the process.

## Command-Line Options

### main.py

```
--org                   Salesforce org alias (default: from .env or default org)
--output                Base output directory (default: ./output)
--query-limit           Maximum records to query (default: 100)
--parent-id-prefix      Comma-separated ParentId prefixes (e.g., "aBo,001")
--parent-ids            Comma-separated specific ParentIds
--filter-strategy       Filtering strategy: python or soql (default: python)
--skip-query            Skip query step and use existing metadata CSV
--metadata              Path to existing CSV (used with --skip-query)
```

### src/downloader.py

```
--metadata      Path to CSV file with attachment metadata (required)
--output        Directory to save downloaded files (default: ./output/files)
--org           Salesforce org alias (default: use default org)
--log-file      Log file path (default: ./logs/download.log)
```

## Limitations (POC)

- Configurable query limit (default: 100 records, adjustable)
- No pagination for very large result sets (increase --query-limit as needed)
- No parallel downloads
- No resume capability
- Basic error handling (no exponential backoff)
- No support for ContentDocument (newer file storage)
- SOQL filtering strategy only supports exact IDs (use Python strategy for prefix filtering)

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

### Script not executable

Make the script executable:
```bash
chmod +x scripts/query_attachments.sh
```

## Examples

**Download from specific org**:
```bash
python main.py --org production --output ./prod-attachments
```

**Filter by ParentId prefix (EMS_Attachment__c objects)**:
```bash
python main.py --org your-org --parent-id-prefix "aBo"
```

**Filter by multiple object types (Accounts and Opportunities)**:
```bash
python main.py --org your-org --parent-id-prefix "001,006"
```

**Filter by specific ParentIds**:
```bash
python main.py --org your-org --parent-ids "aBo1234567890ABC,aBo9876543210XYZ"
```

**Custom query limit (query 500 records)**:
```bash
python main.py --org your-org --query-limit 500
```

**Combine filtering with custom limit**:
```bash
python main.py --org your-org --parent-id-prefix "aBo" --query-limit 200
```

**Reuse existing CSV**:
```bash
python main.py --skip-query --metadata ./output/metadata/attachments_20260113_150000.csv
```

**Query only (no download)**:
```bash
bash scripts/query_attachments.sh my-org ./output/metadata 100
```

## Future Enhancements

- Support for ContentDocument/ContentVersion
- Parallel downloads
- Resume capability
- Pagination for large datasets
- Progress bars
- Retry with exponential backoff
- Advanced filtering (date range, content type, file size)
- SOQL prefix filtering (if Salesforce adds support)

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
│   ├── sf_auth.py              # SF CLI authentication
│   ├── sf_client.py            # REST API client
│   ├── downloader.py           # Download orchestration
│   └── filters.py              # ParentId filtering logic
├── scripts/
│   └── query_attachments.sh    # SOQL query script
├── output/
│   ├── metadata/               # CSV files
│   └── files/                  # Downloaded attachments
└── logs/
    └── download.log            # Execution logs
```

## License

This is a proof-of-concept tool. Adapt as needed for your use case.
