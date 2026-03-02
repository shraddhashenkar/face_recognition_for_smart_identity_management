
import os
import django
import json
import numpy as np
import cv2
from pathlib import Path

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'RollVision.settings')
django.setup()

from dashboard.models import Student, FaceEncoding
from dashboard.face_utils import face_recognizer, FaceDetectionError
from django.conf import settings

def migrate_encodings():
    print("=" * 60)
    print("MIGRATING FACE ENCODINGS TO HIGH ACCURACY FORMAT")
    print("=" * 60)

    try:
        import face_recognition
    except ImportError:
        print("[ERROR] face_recognition library not installed. Cannot migrate.")
        return

    encodings = FaceEncoding.objects.all()
    total = encodings.count()
    print(f"Found {total} encodings to process.")

    success_count = 0
    fail_count = 0

    for i, encoding_obj in enumerate(encodings):
        student = encoding_obj.student
        print(f"[{i+1}/{total}] Processing Student: {student.name} ({student.student_id})")

        # Get image path
        # image_path is relative to MEDIA_ROOT, stored as 'faces/student_X/face_Y.jpg'
        # But wait, logic in save_face_image returns relative path.
        # Let's verify if it's stored relative or absolute or what.
        # Looking at save_face_image: returns os.path.join('faces', ...) -> relative.
        
        full_image_path = os.path.join(settings.MEDIA_ROOT, encoding_obj.image_path)
        
        if not os.path.exists(full_image_path):
             print(f"   [WARN] Image file missing: {full_image_path}")
             fail_count += 1
             continue

        # Load image with OpenCV
        try:
             # cv2.imread doesn't handle paths with special chars well on Windows if not careful, but usually fine
             image = cv2.imread(full_image_path)
             if image is None:
                 print(f"   [ERROR] Failed to read image: {full_image_path}")
                 fail_count += 1
                 continue
        except Exception as e:
             print(f"   [ERROR] Exception reading image: {e}")
             fail_count += 1
             continue

        # Re-encode
        try:
             # We need to find the face in the image again.
             # Ideally we use the whole image and find the face.
             # The stored image IS the cropped face? 
             # Let's check face_utils.py code I just replaced.
             # save_face_image saves `face_region` which IS the cropped face.
             # BUT face_recognition.face_encodings expects a full image or we can pass known location.
             # If the image IS the face, we can just say the face is the whole image.
             
             h, w = image.shape[:2]
             # face_rect = (x, y, w, h) -> (0, 0, w, h)
             face_rect = (0, 0, w, h)
             
             # Wait, encode_face in my new implementation converts rect to (top, right, bottom, left)
             # and then calls face_recognition.face_encodings(rgb, [location]).
             # This should work perfectly on the cropped face image.
             
             new_encoding_data = face_recognizer.encode_face(image, face_rect)
             
             # Update DB
             encoding_obj.encoding_data = json.dumps(new_encoding_data)
             encoding_obj.save()
             
             print(f"   [SUCCESS] Re-encoded.")
             success_count += 1

        except FaceDetectionError as e:
             print(f"   [ERROR] Face detection error: {e}")
             fail_count += 1
        except Exception as e:
             print(f"   [ERROR] Unexpected error: {e}")
             fail_count += 1

    print("\n" + "=" * 60)
    print(f"MIGRATION COMPLETE")
    print(f"Success: {success_count}")
    print(f"Failed:  {fail_count}")
    print("=" * 60)

if __name__ == "__main__":
    migrate_encodings()
