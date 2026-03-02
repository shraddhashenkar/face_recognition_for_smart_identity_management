
try:
    import face_recognition
    print("FACE_LIB_STATUS: OK")
except Exception as e:
    print(f"FACE_LIB_STATUS: ERROR {e}")
