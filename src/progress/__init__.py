"""
Progress Tracking Module

Provides rich, hierarchical progress tracking for the Salesforce attachments extraction tool.
Supports multiple display modes (rich, tqdm, off) and stage-specific progress information.
"""

from src.progress.core.tracker import ProgressTracker, ProgressRenderer, ProgressMode
from src.progress.core.stage import ProgressStage, StageStatus, StageProgress
from src.progress.display.rich_renderer import RichProgressRenderer, is_rich_available
from src.progress.display.tqdm_renderer import TqdmProgressRenderer, is_tqdm_available
from src.progress.stages.csv_stage import CsvProcessingStage
from src.progress.stages.soql_stage import SoqlQueryStage
from src.progress.stages.download_stage import DownloadStage
from src.progress.config import (
    ProgressConfig,
    get_config,
    set_config,
    update_config,
    get_renderer_registry,
    auto_select_renderer
)
from src.progress.utils import (
    create_progress_tracker,
    setup_progress_tracker,
    log_progress_setup,
    check_progress_dependencies
)

__all__ = [
    'ProgressTracker',
    'ProgressRenderer',
    'ProgressMode',
    'ProgressStage', 
    'StageStatus',
    'StageProgress',
    'RichProgressRenderer',
    'TqdmProgressRenderer',
    'is_rich_available',
    'is_tqdm_available',
    'CsvProcessingStage',
    'SoqlQueryStage', 
    'DownloadStage',
    'ProgressConfig',
    'get_config',
    'set_config',
    'update_config',
    'get_renderer_registry',
    'auto_select_renderer',
    'create_progress_tracker',
    'setup_progress_tracker',
    'log_progress_setup',
    'check_progress_dependencies',
]