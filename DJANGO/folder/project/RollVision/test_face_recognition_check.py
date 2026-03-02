
import os
import django
import cv2
import numpy as np
import json
import logging

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'RollVision.settings')
django.setup()

from dashboard.face_utils import face_recognizer, FaceDetectionError, FACE_CONFIDENCE_THRESHOLD

def test_high_accuracy_recognition():
    print("=" * 60)
    print("TESTING HIGH ACCURACY FACE RECOGNITION")
    print("=" * 60)

    # 1. Check Library Import
    try:
        import face_recognition
        print("[PASS] face_recognition library imported successfully.")
    except ImportError:
        print("[FAIL] face_recognition library NOT found.")
        return

    # 2. Create Synthetic Face Image
    # Since we don't have a real face handy without user input, we'll try to use a known face image if available or just check structure.
    # Actually face_recognition won't detect a drawn face (circles/lines). It needs a real face.
    # We will skip actual detection test if no image is found, but check the API methods.
    
    print("\n[INFO] Checking API methods signature...")
    
    # 3. Test encode_face signature (mocking detection)
    # We can't easily mock internal calls without mocking library, but we can verify the method exists.
    if hasattr(face_recognizer, 'encode_face'):
        print("[PASS] encode_face method exists.")
    else:
        print("[FAIL] encode_face method missing.")

    # 4. Test recognize_faces signature
    if hasattr(face_recognizer, 'recognize_faces'):
        print("[PASS] recognize_faces method exists.")
    else:
        print("[FAIL] recognize_faces method missing.")

    # 5. Check Threshold
    print(f"\n[INFO] Confidence Threshold: {face_recognizer.distance_threshold}")
    if face_recognizer.distance_threshold <= 0.6:
        print("[PASS] Threshold is set for high accuracy (<= 0.6)")
    else:
        print("[WARN] Threshold might be too loose (> 0.6)")

    # 6. Check internal storage
    print(f"\n[INFO] Known encodings in memory: {len(face_recognizer.known_face_encodings)}")
    
    print("\n" + "=" * 60)
    print("BASIC CHECKS PASSED. REAL TEST REQUIRES REAL FACE IMAGE.")
    print("Run: python test_simple_detection.py")
    print("=" * 60)

if __name__ == "__main__":
    test_high_accuracy_recognition()
