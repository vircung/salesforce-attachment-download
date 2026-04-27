"""
Error Handler Module

Centralized error handling for workflow phases with fail-fast strategy.
Coordinates error responses and progress stage updates across all phases.
"""

import logging
from typing import List

from src.exceptions import SFAuthError, SFQueryError, SFAPIError
from src.progress.stages import CsvProcessingStage, SoqlQueryStage, DownloadStage
from src.progress.core.stage import StageStatus

logger = logging.getLogger(__name__)


class WorkflowErrorHandler:
    """
    Centralize error handling and progress stage updates.
    
    Implements fail-fast strategy: any error causes immediate workflow termination.
    All phase errors update appropriate progress stages.
    """
    
    def __init__(
        self,
        csv_stage: CsvProcessingStage,
        soql_stage: SoqlQueryStage,
        download_stage: DownloadStage
    ) -> None:
        """
        Initialize error handler with progress stages.
        
        Args:
            csv_stage: Progress stage for CSV processing phase
            soql_stage: Progress stage for SOQL query phase
            download_stage: Progress stage for download phase
        """
        self.csv_stage = csv_stage
        self.soql_stage = soql_stage
        self.download_stage = download_stage
        self.failed_files: List[str] = []
        logger.info("WorkflowErrorHandler initialized")
    
    def handle_csv_error(
        self,
        csv_name: str,
        error: Exception
    ) -> None:
        """
        Handle errors during CSV processing phase (Phase 1).
        
        Behavior (fail-fast):
          - Log error with type and details
          - Add csv_name to failed_files list
          - Mark CSV stage as FAILED
          - Stop workflow (fail-fast)
        
        Args:
            csv_name: Name of CSV being processed when error occurred
            error: Exception that was raised
        
        """
        logger.error(f"✗ CSV processing failed for {csv_name}: {error}")
        
        # Determine error type for more detailed logging
        if isinstance(error, FileNotFoundError):
            logger.error("  Issue: File or directory not found")
            logger.debug("  Details:", exc_info=True)
        elif isinstance(error, ValueError):
            logger.error("  Issue: Invalid CSV data or format")
            logger.debug("  Details:", exc_info=True)
        elif isinstance(error, PermissionError):
            logger.error("  Issue: Permission denied accessing files")
            logger.debug("  Details:", exc_info=True)
        else:
            logger.error("  Issue: Unexpected error during CSV processing")
            logger.debug("  Details:", exc_info=True)
        
        # Record failure
        self.failed_files.append(csv_name)
        
        # Update stage
        if self.csv_stage.progress.status != StageStatus.FAILED:
            self.csv_stage.fail(str(error))
        
        logger.info("Workflow stopping due to CSV phase error (fail-fast)")
    
    def handle_query_error(
        self,
        csv_name: str,
        error: Exception
    ) -> None:
        """
        Handle errors during SOQL query phase (Phase 2).
        
        Behavior (fail-fast):
          - Determine error type (auth vs query vs API vs other)
          - Log error with appropriate context
          - Add csv_name to failed_files list
          - Mark CSV stage as FAILED
          - Mark SOQL stage as FAILED
          - Stop workflow (fail-fast)
        
        Args:
            csv_name: CSV being queried when error occurred
            error: Exception that was raised
        
        """
        logger.error(f"✗ Query failed for {csv_name}: {error}")
        
        # Determine error type for context-specific logging
        if isinstance(error, SFAuthError):
            logger.error("  Type: Salesforce Authentication Error")
            logger.error("  Action: Check Salesforce CLI authentication (run: sf org list)")
            logger.debug("  Details:", exc_info=True)
        elif isinstance(error, SFQueryError):
            logger.error("  Type: SOQL Query Error")
            logger.error("  Action: Check query syntax and record IDs")
            logger.debug("  Details:", exc_info=True)
        elif isinstance(error, SFAPIError):
            logger.error("  Type: Salesforce API Error")
            logger.error("  Action: Check network connection and API access")
            logger.debug("  Details:", exc_info=True)
        else:
            logger.error("  Type: Unexpected error during query phase")
            logger.debug("  Details:", exc_info=True)
        
        # Record failure
        self.failed_files.append(csv_name)
        
        # Update stages
        if self.csv_stage.progress.status not in [StageStatus.FAILED, StageStatus.COMPLETED]:
            self.csv_stage.fail(str(error))
        
        if self.soql_stage.progress.status != StageStatus.FAILED:
            self.soql_stage.fail(str(error))
        
        logger.info("Workflow stopping due to query phase error (fail-fast)")
    
    def handle_download_error(
        self,
        csv_name: str,
        error: Exception
    ) -> None:
        """
        Handle errors during download phase (Phase 3).
        
        Behavior (fail-fast):
          - Log error with type and details
          - Add csv_name to failed_files list
          - Mark CSV stage as FAILED
          - Mark download stage as FAILED
          - Stop workflow (fail-fast)
        
        Args:
            csv_name: CSV being downloaded when error occurred
            error: Exception that was raised
        
        """
        logger.error(f"✗ Download failed for {csv_name}: {error}")
        
        # Determine error type
        if isinstance(error, SFAuthError):
            logger.error("  Type: Salesforce Authentication Error")
            logger.error("  Action: Check Salesforce CLI authentication")
            logger.debug("  Details:", exc_info=True)
        elif isinstance(error, SFAPIError):
            logger.error("  Type: Salesforce API Error")
            logger.error("  Action: Check network connection and API access")
            logger.debug("  Details:", exc_info=True)
        else:
            logger.error("  Type: Unexpected error during download phase")
            logger.debug("  Details:", exc_info=True)
        
        # Record failure
        self.failed_files.append(csv_name)
        
        # Update stages
        if self.csv_stage.progress.status not in [StageStatus.FAILED, StageStatus.COMPLETED]:
            self.csv_stage.fail(str(error))
        
        if self.download_stage.progress.status != StageStatus.FAILED:
            self.download_stage.fail(str(error))
        
        logger.info("Workflow stopping due to download phase error (fail-fast)")
    
    def get_failed_files(self) -> List[str]:
        """
        Return list of CSV files that failed during processing.
        
        Returns:
            List[str] of CSV file names that encountered errors
        """
        return self.failed_files.copy()
    
    def is_failed(self) -> bool:
        """
        Check if any files failed during processing.
        
        Returns:
            bool: True if any files failed, False if all succeeded
        """
        return len(self.failed_files) > 0