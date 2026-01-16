"""
Base Workflow Stage

Generic base class for workflow stages with configuration-based customization.
"""

from dataclasses import dataclass
from typing import Dict, Any, List, Optional

from src.progress.core.stage import ProgressStage, StageStatus


@dataclass
class StageConfig:
    """Configuration for a workflow stage."""
    name: str
    description: str
    message_template: str
    details_fields: List[str]
    
    def format_message(self, **kwargs) -> str:
        """Format message using template and kwargs."""
        try:
            return self.message_template.format(**kwargs)
        except KeyError:
            return self.message_template
    
    def extract_details(self, **kwargs) -> Dict[str, Any]:
        """Extract relevant details from kwargs."""
        return {
            field: kwargs.get(field) 
            for field in self.details_fields 
            if field in kwargs
        }


class WorkflowStage(ProgressStage):
    """
    Configurable workflow stage with common patterns.
    
    Eliminates duplication by using configuration for message formatting
    and detail extraction logic.
    """
    
    def __init__(self, stage_config: StageConfig) -> None:
        """
        Initialize workflow stage with configuration.
        
        Args:
            stage_config: StageConfig instance with customization
        """
        super().__init__(stage_config.name, stage_config.description)
        self.config = stage_config
    
    def update(self, **kwargs) -> None:
        """
        Update progress using configuration-driven formatting.
        
        Args:
            **kwargs: Key-value pairs for message and detail formatting
        """
        message = self.config.format_message(**kwargs)
        details = self.config.extract_details(**kwargs)
        
        self.update_progress(
            current=kwargs.get('current'),
            total=kwargs.get('total'),
            message=message if message else self.progress.message,
            details=details if details else None,
            error=kwargs.get('error')
        )
    
    def get_display_info(self) -> Dict[str, Any]:
        """Get stage-specific information for display."""
        progress = self.progress
        return {
            'name': self.name,
            'description': self.description,
            'status': progress.status.value,
            'current': progress.current,
            'total': progress.total,
            'message': progress.message,
            'error': progress.error,
            'details': progress.details
        }
