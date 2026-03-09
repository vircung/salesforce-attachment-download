# AGENTS.md

> **Read `README.md` for full documentation** (usage, configuration, troubleshooting).

## Project
Python CLI to batch download Salesforce attachments via CSV-based workflow.
In-memory pipeline: SOQL results stay in memory, downloads run per-batch in parallel.

## Stack
Python 3.14 (via mise) | simple-salesforce, requests, python-dotenv | Salesforce CLI (`sf`) for auth

## Commands
```bash
mise exec -- python main.py                                        # Run (args from .env)
mise exec -- python main.py --org <alias> --records-dir ./records  # Run with explicit args
mise exec -- python main.py --save-metadata                        # Write SOQL result CSVs
mise run verify                                                    # Verify downloaded files
mise exec -- pip install -r requirements.txt                       # Install deps
sf org login web --alias <org>                                     # Auth prerequisite
```

## Structure
```
main.py                    # Entry point
src/
  models.py                # AttachmentRecord, BatchResult, ObjectQueryResult
  workflows/
    orchestrator.py        # Three-phase workflow orchestration
    csv_coordinator.py     # Phase 1: CSV discovery
    query_coordinator.py   # Phase 2: SOQL querying (in-memory results)
    download_coordinator.py # Phase 3: Per-batch parallel downloads + cleanup
    thread_pool.py         # Thread pool with retry logic
    common.py              # ensure_directories()
  csv/                     # CSV processing
  query/                   # SOQL execution (simple-salesforce)
  download/
    downloader_simple.py   # download_batch() + single-file download
    filename.py            # Collision detection, sanitization
    scan.py                # Pre-scan for resume
    stats.py               # Download statistics
  report/
    writer.py              # Execution reports (report_downloaded.json, report_missing.json)
  api/                     # SF auth, connection pool, error handler
  cli/config.py            # CLI argument parsing
  exceptions.py            # Custom exception hierarchy
verify_report.py           # Verify downloaded files against report
```

## Critical Rules
- **NEVER commit .env** - contains credentials
- **Don't override .env with .env.example** - update only if needed
- **Keep README.md updated** - sync docs when changing CLI args, features, or structure
- No tests or linting configured

## Quick Reference
| Task | Command |
|------|---------|
| Run | `mise exec -- python main.py` |
| Verify | `mise run verify` |
| Debug | Add `--debug` flag |
| Check auth | `sf org display --target-org <alias>` |
