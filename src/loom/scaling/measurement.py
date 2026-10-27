import numpy as np

def calculate_reconstructed_distance(point1: np.ndarray, point2: np.ndarray) -> float:
    """Calculates Euclidean distance between two 3D points in arbitrary reconstruction units."""
    return float(np.linalg.norm(np.array(point1) - np.array(point2)))