#!/bin/bash

# Salesforce Attachments Query Script
# Queries attachments and exports to CSV using Salesforce CLI

# Configuration
ORG_ALIAS="${1:-ems-prod}"
OUTPUT_DIR="${2:-./output/metadata}"
QUERY_LIMIT="${3:-100}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTPUT_FILE="${OUTPUT_DIR}/attachments_${TIMESTAMP}.csv"

# Create output directory if it doesn't exist
mkdir -p "$OUTPUT_DIR"

# SOQL Query for attachments
# Fields:
# - Id: Unique identifier
# - Name: File name
# - ContentType: MIME type
# - BodyLength: File size in bytes
# - ParentId: ID of parent record
# - CreatedDate: Creation timestamp
# - LastModifiedDate: Last modification timestamp
# - Description: Optional description
#
# Query limit: Configurable via parameter (default: 100)

QUERY="SELECT Id, Name, ContentType, BodyLength, ParentId, CreatedDate, LastModifiedDate, Description FROM Attachment ORDER BY CreatedDate DESC LIMIT ${QUERY_LIMIT}"

# Execute query and export to CSV
echo "========================================"
echo "Salesforce Attachments Query"
echo "========================================"
echo "Org: $ORG_ALIAS"
echo "Query Limit: $QUERY_LIMIT"
echo "Output: $OUTPUT_FILE"
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
    exit 1
fi
