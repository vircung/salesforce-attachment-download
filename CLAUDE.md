# Salesforce Attachments Extract

Python project to extract Salesforce Attachment records and download their associated files using Salesforce CLI.

## Overview

This tool uses the Salesforce CLI (`@salesforce/cli`) to:
1. Query Attachment records via SOQL
2. Save Attachment metadata for reference
3. Download attachment files based on the metadata

## Requirements

- Python
- Node.js and npm
- `@salesforce/cli` npm package
- Authenticated Salesforce CLI session

## Workflow

1. **Query Attachments**: Execute SOQL queries to retrieve Attachment metadata
2. **Filter Records**: Apply filters to target specific attachments
3. **Save Metadata**: Store attachment metadata (JSON/CSV) for reference
4. **Download Files**: Use metadata to download attachment files via Salesforce CLI

## Setup

```bash
# Install Salesforce CLI
npm install -g @salesforce/cli

# Authenticate with Salesforce
sf org login web --alias your-org

# Install Python dependencies
pip install -r requirements.txt
```

## Usage

```bash
# Query and download attachments
python main.py --org your-org --output ./attachments
```
