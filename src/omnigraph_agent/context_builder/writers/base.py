"""Base context writer interface."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class BaseContextWriter(ABC):
    """Base class for context file writers."""
    
    @abstractmethod
    def write(self, data: Any, output_path: Path) -> Path:
        """
        Write context data to file.
        
        Args:
            data: Context data (dict or Pydantic model)
            output_path: Path to output file
            
        Returns:
            Path to written file
        """
        pass
