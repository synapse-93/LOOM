from dataclasses import dataclass
from typing import Optional, Tuple

@dataclass
class ScaleConfig:
    """Configuration settings for metric scaling."""
    marker_size_mm: float = 50.0  # Real-world physical size of printed marker (in mm)
    marker_id: int = 0             # Target ArUco marker ID

@dataclass
class ScaleResult:
    """Stores output status and measurement metrics after scaling."""
    scale_factor: float
    original_bounding_box: Tuple[float, float, float]
    scaled_bounding_box: Tuple[float, float, float]
    success: bool
    error_message: Optional[str] = None