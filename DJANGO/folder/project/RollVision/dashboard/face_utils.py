"""
Face Detection and Recognition Utilities for RollVision Attendance System
Uses face_recognition (dlib) for high accuracy
"""

import cv2
import numpy as np
import os
import json
import base64
import secrets
#import imghdr
import time
from pathlib import Path
from django.conf import settings
import logging

try:
    import face_recognition
except ImportError:
    face_recognition = None

logger = logging.getLogger(__name__)

# ==================== Enhanced Face Detection Configuration ====================

# Face detection model selection
FACE_DETECTION_MODEL = "hog"  # "hog" (faster, good for close-range webcam) or "cnn" (slower, more accurate for distant faces)
FACE_DETECTION_FALLBACK = True  # Fallback to HOG if CNN is too slow
FACE_UPSAMPLE_TIMES = 0  # Number of times to upsample for detecting smaller/distant faces (0-2) - 0 is fastest

# Recognition thresholds
FACE_CONFIDENCE_THRESHOLD = 0.6  # Distance threshold (lower is stricter). 0.6 is typical, good for HOG
FACE_MIN_SIZE = (80, 80)  # Minimum face size in pixels (reduced for faster processing)
FACE_MAX_BLUR_THRESHOLD = 80.0  # Maximum acceptable blur variance (reduced to be less strict)

# Performance and quality settings
ENABLE_PREPROCESSING = False  # Disabled for speed - webcam has good lighting
ENABLE_QUALITY_CHECKS = False  # Disabled for speed - rely on confidence threshold only
CNN_PERFORMANCE_THRESHOLD = 2.0  # Auto-fallback to HOG if CNN takes > 2 seconds per frame



class FaceDetectionError(Exception):
    """Custom exception for face detection errors"""
    pass


class FaceRecognizer:
    """Handle face detection, encoding, and recognition using face_recognition (dlib)"""
    
    def __init__(self):
        if face_recognition is None:
            logger.warning("face_recognition library not installed. Face features will not work.")
        
        # In-memory storage for active encodings (replaces LBPH training)
        self.known_face_encodings = []
        self.known_face_ids = []
        self._is_trained = False
        
        # Distance threshold (lower is more confident)
        self.distance_threshold = FACE_CONFIDENCE_THRESHOLD
        
        # Detection model (adaptive)
        self.detection_model = self.detection_model = FACE_DETECTION_MODEL
        self._last_detection_time = 0
        self._last_encodings_hash = None
        
        logger.info(f"FaceRecognizer initialized with model: {self.detection_model}")
    
    def preprocess_image(self, image):
        """
        Preprocess image for better face detection in varying lighting conditions
        
        Args:
            image: numpy array (BGR image)
            
        Returns:
            preprocessed image (BGR)
        """
        if not ENABLE_PREPROCESSING:
            return image
        
        # Convert to LAB color space for better lighting adjustment
        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        
        # Apply CLAHE (Contrast Limited Adaptive Histogram Equalization) to L channel
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        l = clahe.apply(l)
        
        # Merge channels and convert back to BGR
        lab = cv2.merge([l, a, b])
        enhanced = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
        
        # Apply slight Gaussian blur to reduce noise
        enhanced = cv2.GaussianBlur(enhanced, (3, 3), 0)
        
        return enhanced
    
    def calculate_blur(self, image, face_rect=None):
        """
        Calculate blur amount in image or face region using Laplacian variance
        
        Args:
            image: numpy array (BGR image)
            face_rect: optional (x, y, w, h) to check only face region
            
        Returns:
            blur variance (higher = sharper, lower = blurrier)
        """
        # Extract face region if provided
        if face_rect:
            x, y, w, h = face_rect
            region = image[y:y+h, x:x+w]
        else:
            region = image
        
        # Convert to grayscale
        gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
        
        # Calculate Laplacian variance
        laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        
        return laplacian_var
    
    def detect_faces(self, image, preprocess=True):
        """
        Enhanced face detection with adaptive model selection and preprocessing
        
        Args:
            image: numpy array (BGR image from OpenCV)
            preprocess: whether to preprocess image (default True)
            
        Returns:
            list of (x, y, w, h) tuples for detected faces
        """
        if face_recognition is None:
            raise FaceDetectionError("face_recognition library missing")
        
        # Preprocess image for better detection
        if preprocess:
            processed_image = self.preprocess_image(image)
        else:
            processed_image = image
        
        # Convert BGR (OpenCV) to RGB (face_recognition)
        rgb_image = cv2.cvtColor(processed_image, cv2.COLOR_BGR2RGB)
        
        # Adaptive model selection with performance monitoring
        start_time = time.time()
        
        try:
            # Detect faces with selected model and upsampling for better small face detection
            face_locations = face_recognition.face_locations(
                rgb_image, 
                number_of_times_to_upsample=FACE_UPSAMPLE_TIMES,
                model=self.detection_model
            )
            
            detection_time = time.time() - start_time
            self._last_detection_time = detection_time
            
            # Auto-fallback to HOG if CNN is too slow
            if (self.detection_model == "cnn" and 
                detection_time > CNN_PERFORMANCE_THRESHOLD and 
                FACE_DETECTION_FALLBACK):
                logger.warning(f"CNN detection took {detection_time:.2f}s, falling back to HOG")
                self.detection_model = "hog"
                # Re-detect with HOG
                face_locations = face_recognition.face_locations(
                    rgb_image, 
                    number_of_times_to_upsample=FACE_UPSAMPLE_TIMES,
                    model="hog"
                )
        except Exception as e:
            # Fallback to HOG on any error with CNN
            if self.detection_model == "cnn" and FACE_DETECTION_FALLBACK:
                logger.warning(f"CNN detection failed: {e}, falling back to HOG")
                self.detection_model = "hog"
                face_locations = face_recognition.face_locations(
                    rgb_image, 
                    number_of_times_to_upsample=FACE_UPSAMPLE_TIMES,
                    model="hog"
                )
            else:
                raise
        
        # Convert to (x, y, w, h) and filter by minimum size
        faces = []
        for (top, right, bottom, left) in face_locations:
            x = left
            y = top
            w = right - left
            h = bottom - top
            
            # Filter by minimum size
            if w >= FACE_MIN_SIZE[0] and h >= FACE_MIN_SIZE[1]:
                faces.append((x, y, w, h))
            else:
                logger.debug(f"Rejected small face: {w}x{h}")
            
        logger.debug(f"Detected {len(faces)} valid faces in {detection_time:.3f}s using {self.detection_model}")
        return faces
    
    def extract_face_region(self, image, face_rect):
        """
        Extract face region from image (helper for display)
        
        Args:
            image: numpy array (BGR image)
            face_rect: tuple (x, y, w, h)
            
        Returns:
            face image
        """
        x, y, w, h = face_rect
        # detailed extraction not strictly needed for dlib encoding, 
        # but useful for saving "thumbnails"
        face = image[y:y+h, x:x+w]
        return face
    
    def verify_face_quality(self, image, allow_multiple=False):
        """
        Enhanced face quality verification with blur and size checks
        
        Args:
            image: numpy array or base64 string
            allow_multiple: whether to allow multiple faces
            
        Returns:
            tuple (success: bool, message: str, faces: list of rects)
        """
        # Convert base64 to image if needed
        if isinstance(image, str):
            image = self.base64_to_image(image)
        
        faces = self.detect_faces(image)
        
        if len(faces) == 0:
            return False, "No face detected. Please ensure your face is visible and well-lit.", []
        elif len(faces) > 1 and not allow_multiple:
            return False, "Multiple faces detected. Please ensure only one person is in frame.", []
        
        # Perform quality checks if enabled
        if ENABLE_QUALITY_CHECKS:
            valid_faces = []
            for face_rect in faces:
                x, y, w, h = face_rect
                
                # Check face size
                if w < FACE_MIN_SIZE[0] or h < FACE_MIN_SIZE[1]:
                    logger.debug(f"Face too small: {w}x{h}")
                    continue
                
                # Check blur
                blur_score = self.calculate_blur(image, face_rect)
                if blur_score < FACE_MAX_BLUR_THRESHOLD:
                    logger.debug(f"Face too blurry: {blur_score:.2f}")
                    return False, f"Image is too blurry (score: {blur_score:.0f}). Please ensure the camera is focused.", []
                
                valid_faces.append(face_rect)
            
            if not valid_faces:
                return False, "No valid faces detected. Please ensure good lighting and focus.", []
            
            faces = valid_faces
        
        return True, f"{len(faces)} high-quality face(s) detected!", faces
    
    def encode_face(self, image, face_rect):
        """
        Generate 128-d face encoding from image
        
        Args:
            image: numpy array (BGR image)
            face_rect: tuple (x, y, w, h)
            
        Returns:
            dict with encoding data
        """
        if face_recognition is None:
            raise FaceDetectionError("face_recognition library missing")

        # Convert coords to (top, right, bottom, left)
        x, y, w, h = face_rect
        top, right, bottom, left = y, x + w, y + h, x
        known_locations = [(top, right, bottom, left)]
        
        # Convert BGR to RGB
        rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        
        # Generate encoding
        encodings = face_recognition.face_encodings(rgb_image, known_locations)
        
        if not encodings:
            raise FaceDetectionError("Could not generate encoding for face")
            
        # We expect exactly one encoding since we passed one location
        encoding_128d = encodings[0]
        
        return {
            'encoding': encoding_128d.tolist(),
            'version': 'dlib_v1'
        }
    
    def save_face_image(self, image, student_id, face_rect):
        """
        Save face image to filesystem
        """
        # Validate student_id
        if not student_id.isalnum() or len(student_id) > 50:
            raise FaceDetectionError("Invalid student ID")
        
        # Create directory
        face_dir = os.path.join(settings.MEDIA_ROOT, 'faces', f'student_{student_id}')
        os.makedirs(face_dir, exist_ok=True)
        
        # Extract face
        face_region = self.extract_face_region(image, face_rect)
        
        # Save
        filename = f'face_{secrets.token_hex(8)}.jpg'
        filepath = os.path.join(face_dir, filename)
        
        # Security check
        filepath = os.path.normpath(filepath)
        if not filepath.startswith(os.path.normpath(settings.MEDIA_ROOT)):
            raise FaceDetectionError("Invalid file path detected")
        
        cv2.imwrite(filepath, face_region)
        
        return os.path.join('faces', f'student_{student_id}', filename)
    
    def train_recognizer(self, face_encodings_data, force_retrain=False):
        """
        Load known faces into memory (replaces 'training')
        
        Args:
            face_encodings_data: list of tuples (student_id, encoding_json_string)
        """
        if not face_encodings_data:
            if self._is_trained:  # Clear if empty
                self.known_face_encodings = []
                self.known_face_ids = []
                self._is_trained = False
                self._last_encodings_hash = None
            return

        # Calculate a simple hash/fingerprint of the input data to avoid retraining if identical
        # We use the tuple of (student_id, encoding_data) for hashing
        current_hash = hash(tuple(face_encodings_data))
        
        if self._is_trained and self._last_encodings_hash == current_hash and not force_retrain:
            return
            
        self.known_face_encodings = []
        self.known_face_ids = []
        
        valid_count = 0
        
        for student_id, encoding_json in face_encodings_data:
            try:
                data = json.loads(encoding_json)
                
                # Check for 'encoding' key (dlib 128d vector)
                if 'encoding' in data:
                    self.known_face_encodings.append(np.array(data['encoding']))
                    self.known_face_ids.append(student_id)
                    valid_count += 1
            except Exception as e:
                logger.error(f"Error loading encoding for student {student_id}: {e}")
                continue
        
        if valid_count > 0:
            self._is_trained = True
            self._last_encodings_hash = current_hash
            logger.info(f"Loaded {valid_count} face encodings into memory (Hash: {current_hash})")
        else:
            self._is_trained = False
            self._last_encodings_hash = None
            logger.warning("No valid dlib encodings found in the provided data.")
    
    def recognize_faces(self, image):
        """
        Enhanced multi-face recognition with duplicate filtering
        """
        if face_recognition is None:
            raise FaceDetectionError("face_recognition library missing")

        # Convert BGR to RGB
        rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        
        # Detect faces with preprocessing
        face_locations = []
        start_time = time.time()
        
        try:
            face_locations = face_recognition.face_locations(
                rgb_image,
                number_of_times_to_upsample=FACE_UPSAMPLE_TIMES,
                model=self.detection_model
            )
        except Exception as e:
            if self.detection_model == "cnn" and FACE_DETECTION_FALLBACK:
                logger.warning(f"CNN failed, using HOG: {e}")
                self.detection_model = "hog"
                face_locations = face_recognition.face_locations(
                    rgb_image,
                    number_of_times_to_upsample=FACE_UPSAMPLE_TIMES,
                    model="hog"
                )
            else:
                raise
        
        detection_time = time.time() - start_time
        
        if not face_locations:
            return []
            
        # Get encodings for all faces in image
        face_encodings = face_recognition.face_encodings(rgb_image, face_locations)
        
        # If we have no known faces, we can't recognize, but we can return detection
        if not self.known_face_encodings:
            results = []
            for (top, right, bottom, left) in face_locations:
                x, y, w, h = left, top, right - left, bottom - top
                results.append({
                    'rect': (x, y, w, h),
                    'student_id': None,
                    'confidence': 0.0,
                    'distance': 1.0
                })
            return results
        
        # Initialize after checks to save resources
        results = []
        recognized_students = set()  # Track recognized students to filter duplicates
        
        # Compare each face
        for (top, right, bottom, left), face_encoding in zip(face_locations, face_encodings):
            x, y, w, h = left, top, right - left, bottom - top
            
            # Skip if face is too small (additional check)
            if w < FACE_MIN_SIZE[0] or h < FACE_MIN_SIZE[1]:
                continue
            
            # Calculate distances to all known faces
            distances = face_recognition.face_distance(self.known_face_encodings, face_encoding)
            
            # Find best match
            best_match_index = np.argmin(distances)
            min_distance = distances[best_match_index]
            
            # Improved confidence mapping
            # Using exponential decay for better range: conf = 100 * exp(-3 * distance)
            # This gives: dist=0->100%, dist=0.4->30%, dist=0.6->16%, dist=1.0->5%
            confidence_score = 100 * np.exp(-3 * min_distance)
            
            result = {
                'rect': (x, y, w, h),
                'confidence': round(confidence_score, 2),
                'distance': round(min_distance, 4)  # For debugging
            }
            
            # Check if face matches a known student
            if min_distance < self.distance_threshold:
                student_id = self.known_face_ids[best_match_index]
                
                # Filter duplicates - if same student detected multiple times,
                # keep the one with best confidence
                if student_id in recognized_students:
                    # Find existing result for this student
                    existing_idx = next(
                        (i for i, r in enumerate(results) if r.get('student_id') == student_id),
                        None
                    )
                    if existing_idx is not None:
                        # Keep the one with better confidence
                        if confidence_score > results[existing_idx]['confidence']:
                            results[existing_idx] = result
                            results[existing_idx]['student_id'] = student_id
                        # Skip adding this duplicate
                        continue
                
                result['student_id'] = student_id
                recognized_students.add(student_id)
            else:
                result['student_id'] = None
                
            results.append(result)
        
        logger.info(f"Recognized {len(recognized_students)} unique students from {len(face_locations)} faces in {detection_time:.3f}s")
        return results

    def recognize_face(self, image):
        """
        Convenience method to recognize a single face (best match)
        Returns: (student_id, confidence, face_rect)
        """
        results = self.recognize_faces(image)
        
        if not results:
            return None, 0.0, None
            
        # Return the first result (assuming single face logic for now)
        # or find best confidence? recognize_faces already sorts logic? No.
        # But for auto-mark, we usually expect one face.
        
        best_result = results[0]
        # logic in recognize_faces already finds best match for each face
        # We just return the first detected face's result
        
        return best_result['student_id'], best_result['confidence'], best_result['rect']
    
    @staticmethod
    def base64_to_image(base64_string):
        """
        Convert base64 string to OpenCV image (BGR)
        """
        if not isinstance(base64_string, str):
            raise FaceDetectionError("Invalid image data format")
        
        if ',' in base64_string:
            base64_string = base64_string.split(',')[1]
            
        try:
            img_data = base64.b64decode(base64_string, validate=True)
        except Exception:
            raise FaceDetectionError("Invalid base64 encoding")
            
        nparr = np.frombuffer(img_data, np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if image is None:
            raise FaceDetectionError("Failed to decode image")
            
        return image
    
    @staticmethod
    def image_to_base64(image):
        _, buffer = cv2.imencode('.jpg', image)
        return f"data:image/jpeg;base64,{base64.b64encode(buffer).decode('utf-8')}"


# Global instance
face_recognizer = FaceRecognizer()
