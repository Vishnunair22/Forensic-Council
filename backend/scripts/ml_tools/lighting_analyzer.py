#!/usr/bin/env python3
"""
lighting_analyzer.py
====================
Analyzes lighting consistency using shadow direction detection.

Uses Canny edge detection and Hough transform to find dominant line angles
(shadow directions). Real photos have shadows clustering around one direction,
while composited images may show shadows going in multiple directions.

Usage:
    python lighting_analyzer.py --input /path/to/image.jpg

Output JSON:
    {
        "lighting_consistent": true,
        "shadow_angle_std_deg": 12.5,
        "dominant_shadow_angles_deg": [45.2, 46.1, 44.8],
        "highlight_direction": [0.3, -0.2],
        "confidence": 0.85,
        "available": true
    }
"""

import argparse
import json
import numpy as np
import cv2
from skimage.feature import canny
from skimage.transform import hough_line, hough_line_peaks


def analyze_lighting(image_path: str, num_peaks: int = 10) -> dict:
    """
    Analyze lighting consistency via shadow direction detection.
    
    Args:
        image_path: Path to the image file
        num_peaks: Number of dominant lines to detect
    
    Returns:
        Dictionary with lighting analysis results
    """
    img = cv2.imread(image_path)
    if img is None:
        return {"error": "Cannot read image", "available": False}
    
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # Detect shadow edges via Canny
    edges = canny(gray.astype(float) / 255.0, sigma=2.0)
    
    # Hough transform to find dominant line angles (shadow directions)
    h_space, angles, distances = hough_line(edges)
    
    if h_space.size == 0:
        return {
            "lighting_consistent": True,
            "confidence": 0.5,
            "available": True,
            "note": "No edges detected for analysis"
        }
    
    _, peak_angles, _ = hough_line_peaks(h_space, angles, distances, num_peaks=num_peaks)
    
    if len(peak_angles) < 2:
        return {
            "lighting_consistent": True,
            "confidence": 0.5,
            "available": True,
            "note": "Insufficient edge structure"
        }
    
    # Shadow lines should cluster around one direction in a real photo
    angle_std = float(np.std(np.degrees(peak_angles)))
    
    # If shadows go in multiple directions > 30° apart = compositing signal
    lighting_consistent = angle_std < 25.0

    # Confidence: when consistent, confidence should be high (the tool did its job
    # and found no issue).  Only reduce confidence when there IS an inconsistency.
    # The old formula 1.0 - angle_std/90.0 produced ~9% confidence for screenshots
    # with naturally scattered Hough lines even when lighting IS consistent.
    if lighting_consistent:
        confidence = round(max(0.70, 1.0 - angle_std / 120.0), 3)
    else:
        confidence = round(max(0.15, 0.50 - angle_std / 180.0), 3)

    # Specular highlight direction — find brightest regions
    _, thresh = cv2.threshold(gray, 230, 255, cv2.THRESH_BINARY)
    moments = cv2.moments(thresh)
    
    if moments["m00"] > 0:
        highlight_cx = int(moments["m10"] / moments["m00"])
        highlight_cy = int(moments["m01"] / moments["m00"])
        h, w = gray.shape
        # Normalise to -1..1
        highlight_direction = [
            round((highlight_cx - w/2) / (w/2), 3),
            round((highlight_cy - h/2) / (h/2), 3),
        ]
    else:
        highlight_direction = None
    
    return {
        "lighting_consistent": lighting_consistent,
        "shadow_angle_std_deg": round(angle_std, 2),
        "dominant_shadow_angles_deg": [round(float(np.degrees(a)), 1)
                                       for a in peak_angles[:3]],
        "highlight_direction": highlight_direction,
        "confidence": confidence,
        "available": True,
    }


def visualize_lighting(image_path: str, output_path: str, angles: list) -> bool:
    """
    Create a visualization of detected shadow directions.
    
    Args:
        image_path: Path to input image
        output_path: Path to save visualization
        angles: List of dominant angles in degrees
    
    Returns:
        True if visualization was created successfully
    """
    img = cv2.imread(image_path)
    if img is None:
        return False
    
    h, w = img.shape[:2]
    center = (w // 2, h // 2)
    
    # Draw lines representing shadow directions
    vis_img = img.copy()
    colors = [(0, 0, 255), (0, 255, 0), (255, 0, 0)]
    
    for i, angle_deg in enumerate(angles[:3]):
        color = colors[i % len(colors)]
        angle_rad = np.radians(angle_deg)
        
        # Draw line from center in the direction of the shadow
        length = min(w, h) // 3
        end_x = int(center[0] + length * np.cos(angle_rad))
        end_y = int(center[1] + length * np.sin(angle_rad))
        
        cv2.line(vis_img, center, (end_x, end_y), color, 2)
        cv2.putText(vis_img, f"{angle_deg:.1f}°", (end_x + 10, end_y), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
    
    try:
        cv2.imwrite(output_path, vis_img)
        return True
    except Exception:
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyze lighting consistency")
    parser.add_argument("--input", required=True, help="Path to input image")
    parser.add_argument("--output", help="Path to save visualization")
    parser.add_argument("--peaks", type=int, default=10, 
                        help="Number of dominant lines to detect")
    args = parser.parse_args()

    try:
        result = analyze_lighting(args.input, num_peaks=args.peaks)
        
        # Create visualization if requested
        if args.output and result.get("available") and result.get("dominant_shadow_angles_deg"):
            success = visualize_lighting(
                args.input, 
                args.output, 
                result["dominant_shadow_angles_deg"]
            )
            result["visualization_created"] = success
            
    except Exception as e:
        result = {"error": str(e), "available": False}

    print(json.dumps(result))
