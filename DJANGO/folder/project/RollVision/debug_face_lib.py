
import sys
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'RollVision.settings')
django.setup()

print("DEBUG: Python executable:", sys.executable)
try:
    import face_recognition
    print("DEBUG: face_recognition imported successfully")
    print("DEBUG: face_recognition version:", face_recognition.__version__)
except ImportError as e:
    print("DEBUG: ImportError importing face_recognition:", e)

from dashboard.face_utils import face_recognizer
print("DEBUG: face_recognizer initialized")
print("DEBUG: face_recognizer.face_recognition is", "SET" if face_recognizer.detect_faces.__globals__['face_recognition'] else "NONE")

if getattr(face_recognizer, 'detect_faces', None):
   print("DEBUG: checking internal state")
   # We can check if the module level face_recognition is None in face_utils
   # Inspecting the module directly
   import dashboard.face_utils as fu
   print("DEBUG: dashboard.face_utils.face_recognition is", fu.face_recognition)
