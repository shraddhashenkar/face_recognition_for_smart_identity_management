/**
 * Face Capture Utilities for RollVision
 * Handles webcam access, face detection, and image capture
 */

class FaceCapture {
    constructor() {
        this.stream = null;
        this.videoElement = null;
        this.canvasElement = null;
    }

    /**
     * Initialize webcam and start video stream
     */
    async startWebcam(videoElementId) {
        try {
            this.videoElement = document.getElementById(videoElementId);

            // Request camera access
            this.stream = await navigator.mediaDevices.getUserMedia({
                video: {
                    width: { ideal: 640 },
                    height: { ideal: 480 },
                    facingMode: 'user'
                },
                audio: false
            });

            this.videoElement.srcObject = this.stream;
            await this.videoElement.play();

            return { success: true, message: 'Webcam started successfully' };
        } catch (error) {
            console.error('Error accessing webcam:', error);
            let message = 'Failed to access webcam. ';

            if (error.name === 'NotAllowedError') {
                message += 'Please grant camera permissions.';
            } else if (error.name === 'NotFoundError') {
                message += 'No camera found on this device.';
            } else {
                message += error.message;
            }

            return { success: false, message: message };
        }
    }

    /**
     * Stop webcam stream
     */
    stopWebcam() {
        if (this.stream) {
            this.stream.getTracks().forEach(track => track.stop());
            this.stream = null;
        }
        if (this.videoElement) {
            this.videoElement.srcObject = null;
        }

        // 🔥 Clear overlay when camera stops
        const overlay = document.getElementById('detectionOverlay');
        if (overlay) overlay.innerHTML = "";
    }

    /**
     * Capture current frame from video as base64 image
     */
    captureFrame() {
        if (!this.videoElement || !this.videoElement.srcObject) {
            throw new Error('Webcam not started');
        }

        const canvas = document.createElement('canvas');
        canvas.width = this.videoElement.videoWidth;
        canvas.height = this.videoElement.videoHeight;

        const context = canvas.getContext('2d');
        context.drawImage(this.videoElement, 0, 0, canvas.width, canvas.height);

        return canvas.toDataURL('image/jpeg', 0.8);
    }

    /**
     * Display captured image in an img element
     */
    displayCapturedImage(imageData, imgElementId) {
        const imgElement = document.getElementById(imgElementId);
        if (imgElement) {
            imgElement.src = imageData;
            imgElement.style.display = 'block';
        }
    }
}

// Global instance
const faceCapture = new FaceCapture();

/**
 * Draw face bounding boxes (FIXES FREEZE ISSUE)
 */
function drawFaceBoxes(faceRects) {
    const overlay = document.getElementById('detectionOverlay');
    if (!overlay) return;

    // 🔥🔥🔥 CRITICAL FIX: clear old boxes every frame
    overlay.innerHTML = "";

    faceRects.forEach(rect => {
        const box = document.createElement('div');

        box.style.position = 'absolute';
        box.style.left = rect.x + 'px';
        box.style.top = rect.y + 'px';
        box.style.width = rect.w + 'px';
        box.style.height = rect.h + 'px';
        box.style.border = rect.recognized ? '2px solid #00ff00' : '2px solid red';
        box.style.boxSizing = 'border-box';

        if (rect.recognized) {
            const label = document.createElement('div');
            label.textContent = `Recognized`;
            label.style.position = 'absolute';
            label.style.top = '-18px';
            label.style.left = '0';
            label.style.background = '#00ff00';
            label.style.color = '#000';
            label.style.fontSize = '12px';
            label.style.padding = '2px 6px';
            box.appendChild(label);
        }

        overlay.appendChild(box);
    });
}

/**
 * Get CSRF token from cookie
 */
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

function getCSRFToken() {
    return getCookie('csrftoken');
}

/**
 * Send captured face to backend for registration
 */
async function saveFaceEncoding(studentId, faceImageBase64) {
    try {
        const csrftoken = getCSRFToken();
        const response = await fetch('/api/save-face/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrftoken,
            },
            body: JSON.stringify({
                student_id: studentId,
                face_image: faceImageBase64
            })
        });

        const data = await response.json();
        return data;
    } catch (error) {
        console.error('Error saving face:', error);
        return {
            success: false,
            message: 'Network error: ' + error.message
        };
    }
}

/**
 * Process face for attendance marking
 */
async function processAttendance(faceImageBase64) {
    try {
        const csrftoken = getCSRFToken();
        const response = await fetch('/api/process-attendance/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrftoken,
            },
            body: JSON.stringify({
                face_image: faceImageBase64
            })
        });

        const data = await response.json();

        /* ================= FIX FOR FREEZING BOX ================= */
        // Auto-clear detection overlay after 1.5 seconds
        const overlay = document.getElementById('detectionOverlay');
        if (overlay) {
            setTimeout(() => {
                overlay.innerHTML = '';
            }, 1500);
        }
        /* ========================================================= */

        return data;

    } catch (error) {
        console.error('Error processing attendance:', error);
        return {
            success: false,
            message: 'Network error: ' + error.message
        };
    }
}


/**
 * Show notification message
 */
function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `alert alert-${type} alert-dismissible fade show position-fixed top-0 start-50 translate-middle-x mt-3`;
    notification.style.zIndex = '9999';
    notification.style.minWidth = '300px';
    notification.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;

    document.body.appendChild(notification);

    setTimeout(() => {
        notification.remove();
    }, 5000);
}
