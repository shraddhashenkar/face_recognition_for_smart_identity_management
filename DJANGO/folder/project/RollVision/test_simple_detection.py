#!/usr/bin/env python
"""
Simple Face Detection Test
Tests if OpenCV can detect faces in a test image
"""
import os
import django
import cv2
import numpy as np

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'RollVision.settings')
django.setup()

from dashboard.face_utils import face_recognizer

print("=" * 60)
print("FACE DETECTION TEST")
print("=" * 60)

# Create a simple test image (gray square - should NOT detect face)
print("\n[Test 1] Empty Image")
test_img = np.zeros((480, 640, 3), dtype=np.uint8)
faces = face_recognizer.detect_faces(test_img)
print(f"Faces detected: {len(faces)}")
print(f"Expected: 0")

# Try to verify empty image quality
print("\n[Test 2] Verify Face Quality (Empty)")
success, message, rect = face_recognizer.verify_face_quality(test_img)
print(f"Success: {success}")
print(f"Message: {message}")
print(f"Expected: False (no face found)")

# Check model is loaded
print("\n[Test 3] Library Check")
try:
    import face_recognition
    print("face_recognition library: Loaded")
except ImportError:
    print("face_recognition library: Missing")
print(f"Expected: Loaded")

# Check if we can create a simple face pattern
print("\n[Test 4] Simple Pattern")
# Create image with face-like pattern (two eyes, nose, mouth)
pattern_img = np.ones((480, 640, 3), dtype=np.uint8) * 200
# Draw two circles for "eyes"
cv2.circle(pattern_img, (200, 200), 30, (0, 0, 0), -1)
cv2.circle(pattern_img, (400, 200), 30, (0, 0, 0), -1)
# Draw "mouth"
cv2.ellipse(pattern_img, (300, 350), (80, 40), 0, 0, 180, (0, 0, 0), -1)

faces = face_recognizer.detect_faces(pattern_img)
print(f"Faces detected in pattern: {len(faces)}")
print("(May or may not detect - this is just a crude pattern)")

print("\n" + "=" * 60)
print("NEXT STEP: Test with actual webcam/photo")
print("=" * 60)
print("\nTo test properly:")
print("1. Take a photo with your webcam")
print("2. Save as test_face.jpg")
print("3. Run:")
print("   python -c \"from dashboard.face_utils import face_recognizer; import cv2;")
print("   img = cv2.imread('test_face.jpg'); print(face_recognizer.verify_face_quality(img))\"")
