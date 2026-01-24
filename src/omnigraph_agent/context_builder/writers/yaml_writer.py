"""YAML context file writer."""

import yaml
from pathlib import Path
from typing import Any
from .base import BaseContextWriter


class YAMLContextWriter(BaseContextWriter):
    """Writes context files in YAML format."""
    
    def write(self, data: Any, output_path: Path) -> Path:
        """
        Write context data to YAML file.
        
        Args:
            data: Context data (dict or Pydantic model)
            output_path: Path to output file
            
        Returns:
            Path to written file
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Convert Pydantic model to dict if needed
        if hasattr(data, 'model_dump'):
            data_dict = data.model_dump(exclude_none=True)
        else:
            data_dict = data
        
        with open(output_path, 'w') as f:
            yaml.dump(data_dict, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
        
        return output_path
