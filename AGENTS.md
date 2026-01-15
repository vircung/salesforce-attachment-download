# AGENTS.md

> **Read `README.md` for full documentation** (usage, configuration, troubleshooting).

## Project
Python CLI to batch download Salesforce attachments via CSV-based workflow.

## Stack
Python 3.8+ | requests, python-dotenv | Salesforce CLI (`sf`) required

## Commands
```bash
python main.py                                          # Run (args from .env)
python main.py --org <alias> --records-dir ./records   # Run with explicit args
pip install -r requirements.txt                         # Install deps
cp .env.example .env                                    # Setup config
sf org login web --alias <org>                          # Auth prerequisite
```

## Structure
```
main.py                    # Entry point
src/
  workflows/csv_records.py # Main workflow (reference for patterns)
  csv/                     # CSV processing
  query/                   # SOQL execution via sf CLI
  download/                # REST API file downloads
  api/                     # SF auth & client
  cli/config.py            # CLI argument parsing
  exceptions.py            # Custom exception hierarchy
```

## Critical Rules
- **NO git commits** - stage files only, user commits manually
- **NEVER commit .env** - contains credentials
- **Keep README.md updated** - sync docs when changing CLI args, features, or structure
- No tests or linting configured

## Quick Reference
| Task | Command |
|------|---------|
| Run | `python main.py` |
| Debug | Add `--debug` flag |
| Check auth | `sf org display --target-org <alias>` |
