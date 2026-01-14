"""File download operations"""
from src.download.downloader import download_attachments
from src.download.stats import DownloadStats
from src.download.filename import (
    FilenameInfo,
    sanitize_filename,
    detect_filename_collisions,
    DEFAULT_PARENT_ID,
    MAX_FILENAME_LENGTH,
)
from src.download.metadata import read_metadata_csv

__all__ = [
    "download_attachments",
    "DownloadStats",
    "FilenameInfo",
    "sanitize_filename",
    "detect_filename_collisions",
    "read_metadata_csv",
    "DEFAULT_PARENT_ID",
    "MAX_FILENAME_LENGTH",
]
