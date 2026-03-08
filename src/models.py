"""Data models for in-memory pipeline."""

from dataclasses import dataclass
from typing import List


@dataclass
class AttachmentRecord:
    """All 8 SOQL fields preserved for --save-metadata CSV compatibility."""
    id: str
    name: str
    content_type: str
    body_length: int
    parent_id: str
    created_date: str
    last_modified_date: str
    description: str


@dataclass
class BatchResult:
    batch_idx: int
    attachments: List[AttachmentRecord]


@dataclass
class ObjectQueryResult:
    csv_name: str
    batches: List[BatchResult]

    @property
    def total_attachments(self) -> int:
        return sum(len(b.attachments) for b in self.batches)
