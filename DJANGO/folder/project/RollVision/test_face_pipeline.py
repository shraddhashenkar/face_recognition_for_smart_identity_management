#!/usr/bin/env python
"""
Test Face Recognition Pipeline
Run: python test_face_pipeline.py
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'RollVision.settings')
django.setup()

from dashboard.models import Student, FaceEncoding, AttendanceSession
from dashboard.face_utils import face_recognizer
from django.db.models import Q

print("=" * 60)
print("FACE RECOGNITION PIPELINE TEST")
print("=" * 60)

# Test 1: Check Students
print("\n[1] STUDENTS")
students = Student.objects.all()
print(f"Total: {students.count()}")
for s in students:
    print(f"  • {s.student_id} - {s.name}")
    print(f"    Class: {s.class_year}, Division: {s.division}, Trained: {s.is_trained}")
    print(f"    Encodings: {s.face_encodings.count()}")

# Test 2: Check Face Encodings
print("\n[2] FACE ENCODINGS")
encodings = FaceEncoding.objects.all()
print(f"Total: {encodings.count()}")
for e in encodings:
    print(f"  • Student: {e.student.name}, Active: {e.is_active}")
    print(f"    Image: {e.image_path}")

# Test 3: Check Active Sessions
print("\n[3] ATTENDANCE SESSIONS")
active_sessions = AttendanceSession.objects.filter(status='active')
print(f"Active sessions: {active_sessions.count()}")
for session in active_sessions:
    print(f"  • {session.class_year}-{session.division.name if session.division else 'No Division'}")
    print(f"    Subject: {session.subject}, Period: {session.lecture_period}")
    print(f"    Started: {session.started_at}")
    
    # Check matching students
    matching_students = Student.objects.filter(
        class_year=session.class_year,
        is_active=True
    ).filter(
        Q(division=session.division) | Q(division__isnull=True)
    )
    print(f"    Matching students: {matching_students.count()}")
    for s in matching_students:
        print(f"      - {s.name} (Trained: {s.is_trained})")

# Test 4: Train Recognizer
print("\n[4] TRAINING RECOGNIZER")
try:
    face_data = FaceEncoding.objects.filter(is_active=True).values_list('student__id', 'encoding_data')
    if face_data:
        print(f"Training with {len(face_data)} face encodings...")
        face_recognizer.train_recognizer(list(face_data))
        print("✅ Recognizer trained successfully!")
    else:
        print("❌ No face encodings to train!")
except Exception as e:
    print(f"❌ Training failed: {e}")

# Test 5: Check OpenCV
print("\n[5] OPENCV CHECK")
import cv2
print(f"OpenCV version: {cv2.__version__}")
print(f"Confidence threshold: {face_recognizer.distance_threshold}")

print("\n" + "=" * 60)
print("TEST COMPLETE")
print("=" * 60)
print("\n📝 NEXT STEPS:")
print("1. If students exist but not trained → Check face registration")
print("2. If no active session → Start attendance session")
print("3. If recognizer trained → Try face recognition")
print("4. Check server logs during registration/attendance")
print("\n💡 For detailed diagnostics, see diagnostic_guide.md")
