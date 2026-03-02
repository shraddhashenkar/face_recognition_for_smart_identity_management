"""
Session-based attendance views for RollVision
Handles starting/ending attendance sessions and continuous face detection
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import ensure_csrf_cookie, csrf_exempt
from django.utils import timezone
from django.db import transaction
from django.db.models import Q
from django.db.utils import OperationalError
from django.core.cache import cache
from datetime import date, datetime, timedelta
import json
import logging
import time

from .models import (
    Student, AttendanceRecord, AttendanceSession,
    Division, Subject, LecturePeriod, FaceEncoding , Department
)
from .forms import AttendanceSessionForm
from .face_utils import face_recognizer, FaceDetectionError
from .decorators import audit_log, validate_json_request

logger = logging.getLogger(__name__)


@login_required
def start_attendance_session_view(request):
    """View to start a new attendance session with lecture selection"""
    
    if request.method == 'POST':
        form = AttendanceSessionForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    # Create new attendance session
                    session = AttendanceSession.objects.create(
                        class_year=form.cleaned_data['class_year'],
                        division=form.cleaned_data['division'],
                        subject=form.cleaned_data['subject'],
                        lecture_period=form.cleaned_data['lecture_period'],
                        faculty=None,  # Can be linked to logged-in faculty later
                        date=date.today(),
                        status='active',
                        notes=form.cleaned_data.get('notes', '')
                    )
                    
                    logger.info(f"Attendance session {session.id} started for {session.class_year}-{session.division.name}")
                    
                    # Redirect to attendance marking page with session ID
                    return redirect('mark_attendance_live', session_id=session.id)
                    
            except Exception as e:
                logger.error(f"Error starting attendance session: {str(e)}")
                form.add_error(None, f"Error creating session: {str(e)}")
    else:
        form = AttendanceSessionForm()
    
    # Get active sessions for display
    active_sessions = AttendanceSession.objects.filter(
        status='active',
        date=date.today()
    ).select_related('division', 'subject', 'lecture_period')[:10]
    
    departments = Department.objects.all().order_by("name")

    context = {
        'form': form,
        'active_sessions': active_sessions,
        "departments": departments,
    }
    return render(request, 'dashboard/start_session.html', context)


@login_required
def mark_attendance_live(request, session_id):
    """Live attendance marking page with continuous detection"""
    session = get_object_or_404(AttendanceSession, pk=session_id)
    
    if session.status != 'active':
        return render(request, 'dashboard/session_closed.html', {'session': session})
    
    # Get ALL students for this class/division (trained and untrained)
    # Include students with no division assigned OR matching division
    all_students = Student.objects.filter(
        class_year=session.class_year,
        is_active=True
    ).filter(
        Q(division=session.division) | Q(division__isnull=True)
    ).order_by('roll_number')
    
    # Separate trained and untrained students
    trained_students = all_students.filter(is_trained=True)
    untrained_students = all_students.filter(is_trained=False)
    
    # Get already marked students
    marked_students = AttendanceRecord.objects.filter(
        session=session
    ).select_related('student').values_list('student__id', flat=True)
    
    context = {
        'session': session,
        'all_students': all_students,
        'trained_students': trained_students,
        'untrained_students': untrained_students,
        'students': all_students,  # For template compatibility
        'total_students': all_students.count(),
        'trained_count': trained_students.count(),
        'untrained_count': untrained_students.count(),
        'present_count': len(marked_students),
        'marked_students': marked_students,
    }
    return render(request, 'dashboard/mark_attendance_live.html', context)


@require_http_methods(["POST"])
@login_required
@csrf_exempt  # CSRF handled in JavaScript via X-CSRFToken header
def auto_mark_attendance(request):
    """API endpoint for continuous/automatic face detection and attendance marking"""
    logger.info("Auto attendance marking requested")
    
    try:
        data = json.loads(request.body)
        session_id = data.get('session_id')
        face_image_base64 = data.get('face_image')
        
        if not session_id or not face_image_base64:
            return JsonResponse({
                'success': False,
                'message': 'Missing session_id or face_image'
            }, status=400)
        
        # Get session
        try:
            session = AttendanceSession.objects.get(pk=session_id, status='active')
        except AttendanceSession.DoesNotExist:
            return JsonResponse({
                'success': False,
                'message': 'Session not found or already closed'
            }, status=404)
        
        # Get all active face encodings for this class/division
        # Note: If student has FaceEncoding, they ARE trained
        # Include students with no division OR matching division
        cache_key = f"face_encodings_{session.class_year}_{session.division_id}"
        face_encodings = cache.get(cache_key)
        
        if face_encodings is None:
            logger.info(f"Cache miss for face encodings: {cache_key}")
            face_encodings = list(FaceEncoding.objects.filter(
                is_active=True,
                student__class_year=session.class_year,
                student__is_active=True
            ).filter(
                Q(student__division=session.division) | Q(student__division__isnull=True)
            ).values_list('student__id', 'encoding_data'))
            
            # Cache for 1 hour
            cache.set(cache_key, face_encodings, 3600)
        else:
            logger.info(f"Cache hit for face encodings: {cache_key}")
        
        if not face_encodings:
            return JsonResponse({
                'success': False,
                'message': 'No students registered in this class/division'
            }, status=400)
        
        # Train recognizer with relevant faces only
        face_recognizer.train_recognizer(face_encodings)
        
        # Convert base64 to image
        image = face_recognizer.base64_to_image(face_image_base64)
        
        # Recognize face
        student_id, confidence, face_rect = face_recognizer.recognize_face(image)
        
        if student_id is None:
            return JsonResponse({
                'success': False,
                'message': 'No face recognized',
                'confidence': confidence,
                'face_rect': face_rect # Provide rect even if unknown
            })
        
        # Get student
        try:
            student = Student.objects.get(id=student_id)
        except Student.DoesNotExist:
            return JsonResponse({
                'success': False,
                'message': 'Student not found'
            }, status=404)
        
        # FIX 1: Prevent duplicate attendance - Check per SESSION
        existing_record = AttendanceRecord.objects.filter(
            student=student,
            session=session
        ).first()
        
        if existing_record:
            return JsonResponse({
                'success': False,
                'message': f'Attendance already marked for {student.name} in this session',
                'already_marked': True,
                'student': {
                    'name': student.name,
                    'student_id': student.student_id,
                    'class_year': student.class_year,
                }
            })
        
        # Mark attendance with retry logic for database locks
        max_retries = 3
        retry_delay = 0.1  # Start with 100ms
        
        for attempt in range(max_retries):
            try:
                with transaction.atomic():
                    attendance = AttendanceRecord.objects.create(
                        student=student,
                        session=session,
                        subject=session.subject,
                        lecture_period=session.lecture_period,
                        date=session.date,
                        status='present',
                        marked_by_face=True,
                        confidence_score=confidence
                    )
                    
                    # Update session present count
                    session.present_count = AttendanceRecord.objects.filter(
                        session=session,
                        status='present'
                    ).count()
                    session.save(update_fields=['present_count'])
                
                logger.info(f"Attendance marked for {student.name} (ID: {student.student_id}) in session {session.id}")
                
                return JsonResponse({
                    'success': True,
                    'message': f'Attendance marked for {student.name}!',
                    'student': {
                        'id': student.id,  # Database ID
                        'student_id': student.student_id,  # Text ID (for template matching)
                        'name': student.name,
                        'class_year': student.class_year,
                        'roll_number': student.roll_number or 'N/A',
                    },
                    'attendance': {
                        'time': attendance.time.strftime('%H:%M:%S'),
                        'confidence': round(confidence * 100, 2),
                        'face_rect': face_rect
                    },
                    'session_stats': {
                        'present_count': session.present_count,
                        'total_students': Student.objects.filter(
                            class_year=session.class_year,
                            is_active=True
                        ).filter(
                            Q(division=session.division) | Q(division__isnull=True)
                        ).count()
                    }
                })
                
            except OperationalError as e:
                if 'database is locked' in str(e).lower() and attempt < max_retries - 1:
                    logger.warning(f"Database locked, retrying (attempt {attempt + 1}/{max_retries})...")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                    continue
                else:
                    # Final attempt failed or different error
                    raise
        
    except FaceDetectionError as e:
        logger.warning(f"Face detection error: {str(e)}")
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=400)
    except OperationalError as e:
        logger.error(f"Database error after retries: {str(e)}")
        return JsonResponse({
            'success': False,
            'message': 'Database is busy. Please try again.'
        }, status=503)
    except Exception as e:
        logger.error(f"Error in auto attendance marking: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'message': 'An error occurred while processing attendance'
        }, status=500)


@require_http_methods(["POST"])
@login_required
@csrf_exempt  # CSRF handled in JavaScript, safety for API
def end_attendance_session(request, session_id):
    """End an active attendance session"""
    session = get_object_or_404(AttendanceSession, pk=session_id)
    
    if session.status != 'active':
        return JsonResponse({
            'success': False,
            'message': 'Session is not active'
        }, status=400)
    
    try:
        with transaction.atomic():
            # FIX 3: Auto-mark absent students when session ends
            registered_students = Student.objects.filter(
                class_year=session.class_year,
                division=session.division,
                is_trained=True,
                is_active=True
            )
            
            already_marked = AttendanceRecord.objects.filter(
                session=session
            ).values_list('student_id', flat=True)
            
            absent_students = registered_students.exclude(id__in=already_marked)
            
            # Create absent records for unmarked students
            absent_records = [
                AttendanceRecord(
                    student=student,
                    session=session,
                    subject=session.subject,
                    lecture_period=session.lecture_period,
                    date=session.date,
                    status='absent',
                    marked_by_face=False,
                    confidence_score=0.0
                )
                for student in absent_students
            ]
            
            if absent_records:
                AttendanceRecord.objects.bulk_create(absent_records)
                logger.info(f"Auto-marked {len(absent_records)} students as absent")
            
            session.end_session()
            logger.info(f"Attendance session {session.id} ended. Present: {session.present_count}/{session.total_students}")
        
        return JsonResponse({
            'success': True,
            'message': 'Session ended successfully',
            'session': {
                'id': session.id,
                'total_students': session.total_students,
                'present_count': session.present_count,
                'absent_count': session.absent_count,
                'attendance_percentage': session.get_attendance_percentage()
            }
        })
    except Exception as e:
        logger.error(f"Error ending session: {str(e)}")
        return JsonResponse({
            'success': False,
            'message': f'Error ending session: {str(e)}'
        }, status=500)


@login_required
def session_summary(request, session_id):
    """View session summary after completion"""
    session = get_object_or_404(AttendanceSession, pk=session_id)
    
    # Get all attendance records for this session
    present_students = AttendanceRecord.objects.filter(
        session=session,
        status='present'
    ).select_related('student').order_by('student__roll_number')
    
    # Get absent students
    # Include students with no division OR matching division
    all_students = Student.objects.filter(
        class_year=session.class_year,
        is_active=True
    ).filter(
        Q(division=session.division) | Q(division__isnull=True)
    )
    
    present_ids = present_students.values_list('student__id', flat=True)
    absent_students = all_students.exclude(id__in=present_ids).order_by('roll_number')
    
    context = {
        'session': session,
        'present_students': present_students,
        'absent_students': absent_students,
        'attendance_percentage': session.get_attendance_percentage()
    }
    return render(request, 'dashboard/session_summary.html', context)


# ------------------ Export Session PDF ------------------
@login_required
def export_session_pdf(request, session_id):
    """Export session attendance to PDF"""
    import io
    from django.http import HttpResponse
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import inch

    session = get_object_or_404(AttendanceSession, pk=session_id)
    
    # Get attendance data
    present_records = AttendanceRecord.objects.filter(
        session=session,
        status='present'
    ).select_related('student').order_by('student__roll_number')
    
    # Get absent students
    all_students = Student.objects.filter(
        class_year=session.class_year,
        is_active=True
    ).filter(
        Q(division=session.division) | Q(division__isnull=True)
    )
    
    present_ids = present_records.values_list('student__id', flat=True)
    absent_students = all_students.exclude(id__in=present_ids).order_by('roll_number')
    
    # Create Response
    response = HttpResponse(content_type='application/pdf')
    filename = f"Attendance_{session.class_year}_{session.division.name}_{session.subject.name}_{session.date}.pdf"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    # Create Document
    doc = SimpleDocTemplate(response, pagesize=letter)
    elements = []
    styles = getSampleStyleSheet()
    
    # Title
    title = Paragraph(f"Attendance Report - {session.date}", styles['Title'])
    elements.append(title)
    elements.append(Spacer(1, 0.2 * inch))
    
    # Session Details
    details_data = [
        ["Class:", f"{session.class_year} - {session.division.name}"],
        ["Subject:", f"{session.subject.name} ({session.subject.code})"],
        ["Period:", session.lecture_period.name],
        ["Time:", f"{session.started_at.strftime('%H:%M')} - {session.ended_at.strftime('%H:%M') if session.ended_at else 'Ongoing'}"],
        ["Total Students:", str(all_students.count())],
        ["Present:", f"{present_records.count()} ({session.get_attendance_percentage()}%)"],
        ["Absent:", str(absent_students.count())]
    ]
    
    details_table = Table(details_data, colWidths=[2 * inch, 4 * inch])
    details_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(details_table)
    elements.append(Spacer(1, 0.3 * inch))
    
    # PRESENT STUDENTS SECTION
    if present_records.exists():
        elements.append(Paragraph("Present Students", styles['Heading2']))
        elements.append(Spacer(1, 0.1 * inch))
        
        present_data = [["ID", "Name", "Roll No", "Time", "Status"]]
        for record in present_records:
            present_data.append([
                record.student.student_id,
                record.student.name,
                record.student.roll_number or "-",
                record.time.strftime('%H:%M'),
                "Present"
            ])
            
        t_present = Table(present_data, colWidths=[1.5*inch, 2.5*inch, 1*inch, 1*inch, 1*inch])
        t_present.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#28a745")),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ]))
        elements.append(t_present)
        elements.append(Spacer(1, 0.3 * inch))

    # ABSENT STUDENTS SECTION
    if absent_students.exists():
        elements.append(Paragraph("Absent Students", styles['Heading2']))
        elements.append(Spacer(1, 0.1 * inch))
        
        absent_data = [["ID", "Name", "Roll No", "Status"]]
        for student in absent_students:
            absent_data.append([
                student.student_id,
                student.name,
                student.roll_number or "-",
                "Absent"
            ])
            
        t_absent = Table(absent_data, colWidths=[1.5*inch, 2.5*inch, 1*inch, 1.5*inch])
        t_absent.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#dc3545")),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ]))
        elements.append(t_absent)

    doc.build(elements)
    return response

@login_required
def ajax_subjects(request):
    department_id = request.GET.get("department")
    class_year = request.GET.get("class_year")

    CLASS_YEAR_TO_SEM = {
        "FE": [1, 2],
        "SE": [3, 4],
        "TE": [5, 6],
        "BE": [7, 8],
    }

    semesters = CLASS_YEAR_TO_SEM.get(class_year, [])

    subjects = Subject.objects.filter(
        department_id=department_id,
        semester__in=semesters
    )

    data = [
        {"id": s.id, "name": s.name}
        for s in subjects
    ]

    return JsonResponse(data, safe=False)
