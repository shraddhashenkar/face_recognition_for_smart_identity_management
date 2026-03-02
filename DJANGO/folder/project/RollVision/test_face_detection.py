"""
Test script to diagnose face detection issues
"""
import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'RollVision.settings')
django.setup()

from dashboard.models import Student, FaceEncoding
from dashboard.face_utils import face_recognizer
import cv2
import numpy as np

print("="*60)
print("FACE DETECTION DIAGNOSTIC TEST")
print("="*60)

# Check students
students = Student.objects.filter(is_trained=True)
print(f"\n✓ Found {students.count()} trained students:")
for s in students:
    print(f"  - {s.name} ({s.student_id})")

# Check face encodings
encodings = FaceEncoding.objects.filter(is_active=True)
print(f"\n✓ Found {encodings.count()} active face encodings")

# Try to train the recognizer
print("\n" + "="*60)
print("TRAINING RECOGNIZER")
print("="*60)
try:
    face_encodings_data = list(FaceEncoding.objects.filter(is_active=True).values_list('student__id', 'encoding_data'))
    face_recognizer.train_recognizer(face_encodings_data, force_retrain=True)
    print(f"✓ Recognizer trained with {len(face_recognizer.known_face_encodings)} encodings")
    print(f"✓ Student IDs loaded: {face_recognizer.known_face_ids}")
except Exception as e:
    print(f"✗ Error training recognizer: {e}")
    import traceback
    traceback.print_exc()

# Create a test image (pure white face-like shape for testing)
print("\n" + "="*60)
print("TESTING FACE DETECTION")
print("="*60)

# Create a simple test image
test_image = np.ones((480, 640, 3), dtype=np.uint8) * 200  # Gray background
cv2.circle(test_image, (320, 240), 80, (255, 220, 177), -1)  # Face-like circle

try:
    faces = face_recognizer.detect_faces(test_image)
    print(f"✓ Detected {len(faces)} face(s) in test image")
    for i, face in enumerate(faces):
        print(f"  Face {i+1}: {face}")
except Exception as e:
    print(f"✗ Error detecting faces: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*60)
print("CHECKING FACE RECOGNITION LIBRARY")
print("="*60)
try:
    import face_recognition
    print(f"✓ face_recognition library: INSTALLED")
    print(f"  Version: {face_recognition.__version__ if hasattr(face_recognition, '__version__') else 'unknown'}")
    
    # Test basic detection
    import face_recognition
    locations = face_recognition.face_locations(test_image)
    print(f"✓ Direct library test: Found {len(locations)} faces")
    
except ImportError as e:
    print(f"✗ face_recognition library: NOT INSTALLED")
    print(f"  Error: {e}")

print("\n" + "="*60)
print("CONCLUSION")
print("="*60)
print("If you see errors above, that's the root cause.")
print("If no errors, the issue might be:")
print("  1. Camera permissions in browser")
print("  2. Image quality from camera")
print("  3. No actual face in camera frame")
print("="*60)
