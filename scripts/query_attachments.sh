#!/bin/bash

# Salesforce Attachments Query Script (CSV Mode Only)
# Queries attachments with WHERE clause filter and exports to CSV

# Required Parameters
ORG_ALIAS="${1}"
OUTPUT_DIR="${2}"
WHERE_CLAUSE="${3}"

# Validate required parameters
if [ -z "$ORG_ALIAS" ] || [ -z "$OUTPUT_DIR" ] || [ -z "$WHERE_CLAUSE" ]; then
    echo "Error: Missing required parameters"
    echo ""
    echo "Usage: $0 <org_alias> <output_dir> <where_clause>"
    echo ""
    echo "Example:"
    echo "  $0 my-org ./output/metadata \"WHERE ParentId IN ('001xxx','002yyy')\""
    echo ""
    exit 1
fi

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTPUT_FILE="${OUTPUT_DIR}/attachments_${TIMESTAMP}.csv"

# Create output directory if it doesn't exist
mkdir -p "$OUTPUT_DIR"

# SOQL Query for attachments with WHERE clause
# Fields:
# - Id: Unique identifier
# - Name: File name
# - ContentType: MIME type
# - BodyLength: File size in bytes
# - ParentId: ID of parent record
# - CreatedDate: Creation timestamp
# - LastModifiedDate: Last modification timestamp
# - Description: Optional description

QUERY="SELECT Id, Name, ContentType, BodyLength, ParentId, CreatedDate, LastModifiedDate, Description FROM Attachment ${WHERE_CLAUSE} ORDER BY ParentId, CreatedDate DESC"

# Execute query and export to CSV
echo "========================================"
echo "Salesforce Attachments Query (CSV Mode)"
echo "========================================"
echo "Org: $ORG_ALIAS"
echo "Output: $OUTPUT_FILE"
echo "Filter: ${WHERE_CLAUSE:0:100}..."
echo ""

sf data query \
  --query "$QUERY" \
  --target-org "$ORG_ALIAS" \
  --result-format csv \
  > "$OUTPUT_FILE"

# Check if successful
if [ $? -eq 0 ]; then
    RECORD_COUNT=$(($(wc -l < "$OUTPUT_FILE") - 1))
    echo ""
    echo "✓ Success! Metadata saved to: $OUTPUT_FILE"
    echo "✓ Total records: $RECORD_COUNT"
    exit 0
else
    echo ""
    echo "✗ Error: Failed to query attachments"
    echo "  Check that:"
    echo "  - Salesforce CLI is installed"
    echo "  - You are authenticated (run: sf org display --target-org $ORG_ALIAS)"
    echo "  - The org alias '$ORG_ALIAS' is correct"
    echo "  - The WHERE clause is valid SOQL syntax"
    exit 1
fi
