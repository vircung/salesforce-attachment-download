"""
Attachment Filtering Module

Provides filtering logic for Salesforce Attachments based on ParentId.
Supports both prefix-based filtering (by object type) and exact ID matching.
"""

import logging
import re
from dataclasses import dataclass
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

# Salesforce ID format: 15 or 18 characters, alphanumeric
SALESFORCE_ID_PATTERN = re.compile(r'^[a-zA-Z0-9]{15}$|^[a-zA-Z0-9]{18}$')
# Salesforce ID prefix: First 3 characters that identify object type
SALESFORCE_PREFIX_PATTERN = re.compile(r'^[a-zA-Z0-9]{3}$')


@dataclass
class ParentIdFilter:
    """
    Configuration for ParentId filtering.

    Attributes:
        prefixes: List of 3-character Salesforce ID prefixes to match
                  (e.g., ['aBo', '001'] for EMS_Attachment__c and Account)
        exact_ids: List of exact 15 or 18-character Salesforce IDs to match
        strategy: Filtering strategy ('python' or 'soql')
                  - 'python': Filter after querying all records
                  - 'soql': Filter in SOQL query (only works with exact_ids)
    """
    prefixes: List[str]
    exact_ids: List[str]
    strategy: str = 'python'

    def __post_init__(self):
        """Validate filter configuration."""
        # Validate prefixes
        for prefix in self.prefixes:
            if not SALESFORCE_PREFIX_PATTERN.match(prefix):
                logger.warning(
                    f"Invalid Salesforce ID prefix format: '{prefix}'. "
                    f"Expected 3 alphanumeric characters."
                )

        # Validate exact IDs
        for sf_id in self.exact_ids:
            if not SALESFORCE_ID_PATTERN.match(sf_id):
                logger.warning(
                    f"Invalid Salesforce ID format: '{sf_id}'. "
                    f"Expected 15 or 18 alphanumeric characters."
                )

        # Validate strategy
        if self.strategy not in ['python', 'soql']:
            raise ValueError(
                f"Invalid filter strategy: '{self.strategy}'. "
                f"Must be 'python' or 'soql'."
            )

        # Warn if using SOQL strategy with prefixes (not supported)
        if self.strategy == 'soql' and self.prefixes and not self.exact_ids:
            logger.warning(
                "SOQL strategy does not support prefix filtering. "
                "Prefix filters will be ignored. Use 'python' strategy for prefix filtering."
            )

    def has_filters(self) -> bool:
        """Check if any filters are configured."""
        return bool(self.prefixes or self.exact_ids)

    def __str__(self) -> str:
        """String representation for logging."""
        parts = []
        if self.prefixes:
            parts.append(f"prefixes={','.join(self.prefixes)}")
        if self.exact_ids:
            ids_preview = ','.join(self.exact_ids[:3])
            if len(self.exact_ids) > 3:
                ids_preview += f" (+{len(self.exact_ids) - 3} more)"
            parts.append(f"exact_ids={ids_preview}")
        parts.append(f"strategy={self.strategy}")
        return f"ParentIdFilter({', '.join(parts)})"


def parse_filter_config(
    prefix_str: Optional[str] = None,
    ids_str: Optional[str] = None,
    strategy: str = 'python'
) -> Optional[ParentIdFilter]:
    """
    Parse filter configuration from string inputs.

    Args:
        prefix_str: Comma-separated ParentId prefixes (e.g., "aBo,001")
        ids_str: Comma-separated exact ParentIds
        strategy: Filtering strategy ('python' or 'soql')

    Returns:
        ParentIdFilter if any filters specified, None otherwise

    Example:
        >>> filter_config = parse_filter_config(prefix_str="aBo,001", strategy="python")
        >>> print(filter_config.prefixes)
        ['aBo', '001']
    """
    prefixes = []
    exact_ids = []

    # Parse prefixes
    if prefix_str:
        prefixes = [p.strip() for p in prefix_str.split(',') if p.strip()]

    # Parse exact IDs
    if ids_str:
        exact_ids = [id.strip() for id in ids_str.split(',') if id.strip()]

    # Return None if no filters specified
    if not prefixes and not exact_ids:
        return None

    return ParentIdFilter(
        prefixes=prefixes,
        exact_ids=exact_ids,
        strategy=strategy
    )


def apply_parent_id_filter(
    attachments: List[Dict[str, str]],
    filter_config: ParentIdFilter
) -> List[Dict[str, str]]:
    """
    Filter attachments based on ParentId configuration.

    Args:
        attachments: List of attachment dictionaries with ParentId field
        filter_config: Filter configuration

    Returns:
        Filtered list of attachments

    Example:
        >>> attachments = [
        ...     {'Id': '001', 'Name': 'file1.pdf', 'ParentId': 'aBo1234567890ABC'},
        ...     {'Id': '002', 'Name': 'file2.pdf', 'ParentId': '0011234567890XYZ'}
        ... ]
        >>> config = ParentIdFilter(prefixes=['aBo'], exact_ids=[], strategy='python')
        >>> filtered = apply_parent_id_filter(attachments, config)
        >>> len(filtered)
        1
    """
    if not filter_config or not filter_config.has_filters():
        logger.info("No filters configured - returning all attachments")
        return attachments

    logger.info(f"Applying filter: {filter_config}")
    logger.info(f"Pre-filter count: {len(attachments)} attachments")

    filtered = []
    match_stats = {'prefix': 0, 'exact': 0, 'no_parent': 0}

    for attachment in attachments:
        parent_id = attachment.get('ParentId', '').strip()

        # Skip attachments without ParentId
        if not parent_id:
            match_stats['no_parent'] += 1
            logger.debug(f"Skipping attachment {attachment.get('Id')} - no ParentId")
            continue

        # Check exact ID match
        if filter_config.exact_ids and parent_id in filter_config.exact_ids:
            filtered.append(attachment)
            match_stats['exact'] += 1
            logger.debug(f"Matched exact ID: {parent_id} for {attachment.get('Name')}")
            continue

        # Check prefix match
        if filter_config.prefixes:
            parent_prefix = parent_id[:3] if len(parent_id) >= 3 else ''
            if parent_prefix in filter_config.prefixes:
                filtered.append(attachment)
                match_stats['prefix'] += 1
                logger.debug(f"Matched prefix: {parent_prefix} for {attachment.get('Name')}")
                continue

    logger.info(f"Post-filter count: {len(filtered)} attachments")
    logger.info(f"Match statistics: {match_stats['prefix']} by prefix, {match_stats['exact']} by exact ID")

    if match_stats['no_parent'] > 0:
        logger.info(f"Skipped {match_stats['no_parent']} attachments without ParentId")

    return filtered


def build_soql_where_clause(filter_config: ParentIdFilter) -> str:
    """
    Build SOQL WHERE clause for ParentId filtering.

    Note: SOQL does not support LIKE patterns for ID fields, so only
    exact ID matching is supported. Prefix filtering requires Python strategy.

    Args:
        filter_config: Filter configuration

    Returns:
        SOQL WHERE clause string (e.g., "WHERE ParentId IN ('id1','id2')")
        Returns empty string if no filters or only prefixes specified

    Example:
        >>> config = ParentIdFilter(prefixes=[], exact_ids=['a3x123', 'a3x456'], strategy='soql')
        >>> clause = build_soql_where_clause(config)
        >>> print(clause)
        WHERE ParentId IN ('a3x123','a3x456')
    """
    if not filter_config or not filter_config.has_filters():
        return ""

    # SOQL strategy only supports exact ID filtering
    if not filter_config.exact_ids:
        if filter_config.prefixes:
            logger.warning(
                "SOQL WHERE clause cannot be built for prefix filters. "
                "Use 'python' strategy for prefix-based filtering."
            )
        return ""

    # Build WHERE IN clause with exact IDs
    # Escape single quotes in IDs (though Salesforce IDs shouldn't have them)
    escaped_ids = [id.replace("'", "\\'") for id in filter_config.exact_ids]
    ids_list = "','".join(escaped_ids)
    where_clause = f"WHERE ParentId IN ('{ids_list}')"

    logger.info(f"Built SOQL WHERE clause with {len(filter_config.exact_ids)} IDs")
    return where_clause


def log_filter_summary(
    original_count: int,
    filtered_count: int,
    filter_config: Optional[ParentIdFilter]
) -> None:
    """
    Log a summary of filtering results.

    Args:
        original_count: Number of attachments before filtering
        filtered_count: Number of attachments after filtering
        filter_config: Filter configuration used
    """
    if not filter_config or not filter_config.has_filters():
        logger.info("No filtering applied")
        return

    logger.info("=" * 60)
    logger.info("FILTERING SUMMARY")
    logger.info("=" * 60)
    logger.info(f"Filter configuration: {filter_config}")
    logger.info(f"Total attachments (before): {original_count}")
    logger.info(f"Matching attachments (after): {filtered_count}")
    logger.info(f"Filtered out: {original_count - filtered_count}")

    if filtered_count == 0:
        logger.warning(
            "No attachments matched the filter criteria. "
            "Check your ParentId prefixes/IDs and try again."
        )
    elif filtered_count < original_count * 0.1 and original_count > 10:
        logger.info(
            f"Only {filtered_count}/{original_count} attachments matched. "
            f"This may indicate a very specific filter or possible configuration issue."
        )
