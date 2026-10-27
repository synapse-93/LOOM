import cv2
import numpy as np

def detect_aruco_corners(image_path: str, marker_id: int = 0):
    """
    Detects 2D pixel corners of an ArUco reference marker in a given frame.
    Returns 4 corner points if detected, otherwise None.
    """
    image = cv2.imread(image_path)
    if image is None:
        return None

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    
    # Initialize OpenCV ArUco detector
    aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    parameters = cv2.aruco.DetectorParameters()
    detector = cv2.aruco.ArucoDetector(aruco_dict, parameters)
    
    corners, ids, _ = detector.detectMarkers(gray)
    
    if ids is not None and marker_id in ids:
        idx = np.where(ids == marker_id)[0][0]
        return corners[idx][0]  # Returns np.ndarray shape (4, 2)
    return None