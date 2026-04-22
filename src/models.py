"""Data models for in-memory pipeline."""

from dataclasses import dataclass
from pathlib import Path
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


@dataclass
class CsvRecordInfo:
    """Information about a CSV file and its records."""
    csv_path: Path
    csv_name: str
    record_ids: List[str]
    total_records: int
    id_batches: List[List[str]]
    total_batches: int

    def __str__(self) -> str:
        return (
            f"CsvRecordInfo(csv_name='{self.csv_name}', "
            f"total_records={self.total_records}, "
            f"total_batches={self.total_batches})"
        )
