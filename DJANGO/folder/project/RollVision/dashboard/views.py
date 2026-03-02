from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse
from django.db.models import Q, Count, Sum, Avg
from django.contrib import messages
from django.core.mail import send_mail
from django.conf import settings
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import ensure_csrf_cookie
from django.contrib.auth.decorators import login_required, permission_required
from django.utils import timezone
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db import transaction, IntegrityError
from datetime import date, datetime, timedelta
import json
import logging
import cv2
import io
import csv
import pandas as pd
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch

from .models import Faculty, SystemSettings, Student, FaceEncoding, AttendanceRecord, AttendanceSession, Division, Department , Subject 
from .forms import FacultyForm, SettingsForm, StudentForm , AttendanceSessionForm
from .face_utils import face_recognizer, FaceDetectionError
from .decorators import audit_log, validate_json_request, require_staff, sanitize_input


logger = logging.getLogger(__name__)



# ------------------ Dashboard ------------------
@login_required
def index(request):
    """Dashboard home page with comprehensive statistics"""
    from .models import AttendanceSession
    from datetime import timedelta
    from django.db.models import Avg, Count
    
    total_staff = Faculty.objects.count()
    total_students = Student.objects.count()
    
    # Calculate today's attendance
    today = date.today()
    present_today = AttendanceRecord.objects.filter(date=today, status='present').count()
    absent_today = AttendanceRecord.objects.filter(date=today, status='absent').count()
    
    # Total sessions today
    total_sessions = AttendanceSession.objects.filter(date=today).count()
    
    # Calculate attendance rate
    # Use total students as base for simple daily metric
    if total_students > 0:
        attendance_rate = round((present_today / total_students) * 100, 1)
    else:
        attendance_rate = 0

    # Recent sessions (last 5)
    recent_sessions_qs = AttendanceSession.objects.select_related(
        'division', 'subject', 'lecture_period'
    ).filter(status='completed').order_by('-date', '-started_at')[:5]

    recent_sessions = []
    for session in recent_sessions_qs:
        # Pre-format strings to concise attributes to prevent wrapper issues in template
        session.display_title = f"{session.class_year}-{session.division.name} | {session.subject.code}"
        session.display_date = f"{session.date.strftime('%b %d, %Y')} - {session.lecture_period.name}"
        session.display_badge = f"{session.present_count}/{session.total_students}"
        recent_sessions.append(session)
    
    # --- 1. Attendance Trend (Last 7 Days) ---
    attendance_trend_labels = []
    attendance_trend_data = []
    
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        label = day.strftime("%a") # Mon, Tue...
        
        # Get all sessions for this day
        day_sessions = AttendanceSession.objects.filter(date=day, status='completed')
        
        if day_sessions.exists():
            # Calculate average attendance % for this day across all sessions
            # Formula: (Sum of present_count / Sum of total_students) * 100
            stats = day_sessions.aggregate(
                total_present=Sum('present_count'),
                total_capacity=Sum('total_students')
            )
            
            day_present = stats['total_present'] or 0
            day_capacity = stats['total_capacity'] or 1 # Avoid division by zero
            
            day_pct = round((day_present / day_capacity) * 100, 1)
            attendance_trend_data.append(day_pct)
        else:
            attendance_trend_data.append(0)
            
        attendance_trend_labels.append(label)
    
    # --- 2. Defaulters (Attendance < 75%) ---
    # We need to aggregate attendance for all students
    all_students_stats = Student.objects.filter(is_active=True).annotate(
        total_presents=Count('attendance_records', filter=Q(attendance_records__status='present')),
        # We can approximate total sessions by counting distinct sessions they could have attended or just all their records
        # For simplicity and accuracy with current model, we count their total attendance records
        total_records=Count('attendance_records')
    )
    
    defaulters = []
    for s in all_students_stats:
        if s.total_records >= 5: # Only consider students with at least 5 records to avoid noise
            pct = (s.total_presents / s.total_records) * 100
            if pct < 75:
                s.attendance_percentage = round(pct, 1) # Add attribute for template
                # Format subtitle for template
            s.display_subtitle = f"{s.student_id} | {s.class_year}-{s.division.name}"
            defaulters.append(s)
    
    # limit to top 10 defaulters
    defaulters = defaulters[:10]
    
    return render(request, 'dashboard/index.html', {
        "total_staff": total_staff,
        "total_students": total_students,
        "attendance_rate": attendance_rate,
        "total_sessions": total_sessions,
        "total_present": present_today,
        "total_absent": absent_today,
        "recent_sessions": recent_sessions,
        "defaulters": defaulters,
        "attendance_trend_labels": json.dumps(attendance_trend_labels),
        "attendance_trend_data": json.dumps(attendance_trend_data),
    })


# ------------------ Faculty ------------------
@login_required
@require_staff
def faculty(request):
    query = request.GET.get("q", "")
    employees = Faculty.objects.all()

    if query:
        employees = Faculty.objects.filter(
            Q(name__icontains=query) |
            Q(department__icontains=query) |
            Q(subject__icontains=query)
        )

    form = FacultyForm()

    if request.method == "POST":
        form = FacultyForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "✅ Employee added successfully!")
            return redirect("faculty")

    return render(request, "dashboard/faculty.html", {
        "employees": employees,
        "form": form,
        "query": query,
    })


# ------------------ Delete Faculty ------------------
@login_required
@require_staff
def delete_faculty(request, pk):
    """Delete a faculty member"""
    faculty_member = get_object_or_404(Faculty, pk=pk)
    faculty_member.delete()
    messages.success(request, "🗑️ Faculty deleted successfully!")
    return redirect("faculty")


# ------------------ Export Faculty PDF ------------------
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet

@login_required
@require_staff
def export_employees_pdf(request):
    query = request.GET.get("q", "")
    employees = Faculty.objects.all()

    if query:
        employees = Faculty.objects.filter(
            Q(name__icontains=query) |
            Q(department__icontains=query) |
            Q(subject__icontains=query)
        )

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = 'attachment; filename="faculty_list.pdf"'

    doc = SimpleDocTemplate(response, pagesize=letter)
    elements = []

    styles = getSampleStyleSheet()
    elements.append(Paragraph("Faculty & Staff List", styles["Heading1"]))
    elements.append(Spacer(1, 20))

    data = [["Name", "Department", "Subject"]]
    for emp in employees:
        data.append([emp.name, emp.department, emp.subject])

    table = Table(data, colWidths=[200, 150, 150])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#4F81BD")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))

    elements.append(table)
    doc.build(elements)

    return response

def export_reports_excel(request):
    data = _get_report_data(request)
    sessions = data['sessions']

    # Convert sessions to DataFrame
    rows = []
    for s in sessions:
        rows.append({
            "Date": s.date,
            "Class": f"{s.class_year} - {s.division.name}",
            "Subject": s.subject.code,
            "Period": s.lecture_period.name,
            "Present": s.present_count,
            "Absent": s.absent_count,
            "Attendance %": s.get_attendance_percentage(),
        })

    df = pd.DataFrame(rows)

    # Create Excel file in memory
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    filename = f"Attendance_Report_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    with pd.ExcelWriter(response, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name="Attendance")

    return response

def export_reports_csv(request):
    data = _get_report_data(request)
    sessions = data['sessions']

    response = HttpResponse(content_type='text/csv')
    filename = f"Attendance_Report_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)
    writer.writerow(["Date", "Class", "Subject", "Period", "Present", "Absent", "Attendance %"])

    for s in sessions:
        writer.writerow([
            s.date,
            f"{s.class_year} - {s.division.name}",
            s.subject.code,
            s.lecture_period.name,
            s.present_count,
            s.absent_count,
            s.get_attendance_percentage(),
        ])

    return response


# ------------------ Students ------------------
@login_required
def students(request):
    """Student registration and management - SIMPLIFIED SINGLE-TRANSACTION APPROACH"""
    if request.method == "POST":
        # Get form data directly from POST
        student_id = request.POST.get('student_id', '').strip()
        roll_number = request.POST.get('roll_number', '').strip()
        name = request.POST.get('name', '').strip()
        email = request.POST.get('email', '').strip()
        phone_number = request.POST.get('phone_number', '').strip()
        secondary_phone = request.POST.get('secondary_phone', '').strip()
        class_year = request.POST.get('class_year', '').strip()
        department_id = request.POST.get('department', '').strip()
        division_id = request.POST.get('division', '').strip()
        photo = request.FILES.get('photo')  # Uploaded photo file
        face_method = request.POST.get('face_method')
        face_data = request.POST.get('face_data', '').strip() if face_method == "camera" else None  # Base64 from camera
        
        # Validate required inputs
        if not all([student_id, roll_number, name, email, phone_number, class_year, department_id, division_id]):
            messages.error(request, "❌ All required fields must be filled")
            return redirect("students")
        
        # Check if student already exists
        if Student.objects.filter(student_id=student_id).exists():
            messages.error(request, f"❌ Student ID {student_id} already exists")
            return redirect("students")
        
        # Validate student_id format (alphanumeric only)
        if not student_id.isalnum() or len(student_id) > 50:
            messages.error(request, "❌ Student ID should contain only letters and numbers (max 50 characters)")
            return redirect("students")
        
        # Get department (required)
        department = None
        if department_id:
            try:
                from .models import Department
                department = Department.objects.get(id=department_id)
            except Department.DoesNotExist:
                messages.error(request, "❌ Invalid department selected")
                return redirect("students")
        else:
            messages.error(request, "❌ Department is required")
            return redirect("students")
        
        # Get division (required)
        division = None
        if division_id:
            try:
                from .models import Division
                division = Division.objects.get(id=division_id)
            except Division.DoesNotExist:
                messages.error(request, "❌ Invalid division selected")
                return redirect("students")
        else:
            messages.error(request, "❌ Division is required")
            return redirect("students")
        
        # Create student and process face in SINGLE ATOMIC TRANSACTION
        try:
            with transaction.atomic():  # ALL OR NOTHING!
                # Step 1: Create student record
                student = Student.objects.create(
                    student_id=student_id,
                    roll_number=roll_number,
                    name=name,
                    email=email,
                    phone_number=phone_number,
                    secondary_phone=secondary_phone if secondary_phone else None,
                    class_year=class_year,
                    department=department,
                    division=division,
                    photo=photo if photo else None,
                    is_trained=False  # Will be updated if face succeeds
                )
                logger.info(f"Student created: {student_id} - {name} | Roll: {roll_number} | Dept: {department.code if department else 'None'} | Division: {division.name if division else 'None'}")
                
                # Step 2: Process face (camera OR upload)
                face_success = False
                face_error_message = None
                
                # CAMERA CAPTURE METHOD
                if face_data:
                    try:
                        logger.info(f"Processing camera face for {student_id}")
                        
                        # Convert base64 to image
                        image = face_recognizer.base64_to_image(face_data)
                        
                        # Verify face quality
                        success, message, faces = face_recognizer.verify_face_quality(image)
                        
                        if not success:
                            face_error_message = message
                            logger.warning(f"Face quality check failed for {student_id}: {message}")
                        else:
                            # Get the first detected face (should be only one for registration)
                            face_rect = faces[0]
                            
                            # Extract and save face encoding
                            encoding = face_recognizer.encode_face(image, face_rect)
                            image_path = face_recognizer.save_face_image(image, student_id, face_rect)
                            
                            FaceEncoding.objects.create(
                                student=student,
                                encoding_data=json.dumps(encoding),
                                image_path=image_path,
                                is_active=True
                            )
                            
                            student.is_trained = True
                            student.save()
                            face_success = True
                            
                            logger.info(f"✅ Camera face encoding saved for {student_id}")
                            
                    except FaceDetectionError as e:
                        face_error_message = str(e)
                        logger.warning(f"Face detection error for {student_id}: {str(e)}")
                    except Exception as e:
                        face_error_message = f"Unexpected error: {str(e)}"
                        logger.error(f"Error processing camera face for {student_id}: {str(e)}")
                
                # PHOTO UPLOAD METHOD
                elif photo:
                    try:
                        logger.info(f"Processing uploaded photo for {student_id}")
                        
                        # Read uploaded photo
                        from PIL import Image, ImageOps
                        import io
                        
                        photo.seek(0)
                        
                        image_data = photo.read()
                        image = Image.open(io.BytesIO(image_data))
                        
                        # Handle EXIF rotation (iPhone/Android photos)
                        image = ImageOps.exif_transpose(image)
                        
                        # Convert to RGB if needed
                        if image.mode != 'RGB':
                            image = image.convert('RGB')
                        
                        # Convert to numpy array
                        import numpy as np
                        image_np = np.array(image)
                        
                        # Convert RGB (PIL) to BGR (OpenCV)
                        # face_utils.py expects BGR images (standard OpenCV format)
                        image_array = cv2.cvtColor(image_np, cv2.COLOR_RGB2BGR)
                        
                        # Verify face quality
                        success, message, faces = face_recognizer.verify_face_quality(image_array)
                        
                        if not success:
                            face_error_message = message
                            logger.warning(f"Face quality check failed for uploaded photo: {message}")
                        else:
                            # Get the first detected face (should be only one for upload)
                            face_rect = faces[0]
                            
                            # Extract and save face encoding
                            encoding = face_recognizer.encode_face(image_array, face_rect)
                            image_path = face_recognizer.save_face_image(image_array, student_id, face_rect)
                            
                            FaceEncoding.objects.create(
                                student=student,
                                encoding_data=json.dumps(encoding),
                                image_path=image_path,
                                is_active=True
                            )
                            
                            student.is_trained = True
                            student.save()
                            face_success = True
                            
                            logger.info(f"✅ Photo upload face encoding saved for {student_id}")
                            
                    except Exception as e:
                        face_error_message = f"Photo processing error: {str(e)}"
                        logger.error(f"Error processing uploaded photo for {student_id}: {str(e)}")
                
                # TRANSACTION COMMITTED HERE (atomic - all or nothing!)
                
                # Show appropriate message based on result
                if face_success:
                    messages.success(request, f"✅ Student {name} ({student_id}) registered with face recognition successfully!")
                elif face_error_message:
                    messages.warning(request, f"⚠️ Student {name} registered but face detection failed: {face_error_message}. Please retrain face.")
                else:
                    messages.success(request, f"✅ Student {name} ({student_id}) registered successfully! Now capture their face using camera option.")
                
        except IntegrityError:
            logger.error(f"IntegrityError creating student: {student_id}")
            messages.error(request, f"❌ Database error - Student ID may already exist")
        except Exception as e:
            logger.error(f"Error creating student: {str(e)}")
            messages.error(request, f"❌ Error creating student: {str(e)}")
        
        return redirect("students")
    
    # GET request - show form and students list
    from .models import Division, Department
    all_students = Student.objects.all().order_by('-created_at')
    divisions = Division.objects.all().order_by('name')
    departments = Department.objects.all().order_by('name')
    
    # Calculate stats
    total_students = all_students.count()
    today = date.today()
    present_today = AttendanceRecord.objects.filter(date=today, status='present').count()
    absent_today = total_students - present_today
    
    # Calculate attendance rate
    attendance_rate = 0
    if total_students > 0:
        attendance_rate = round((present_today / total_students) * 100, 1)
    
    return render(request, "dashboard/students.html", {
        "total_students": total_students,
        "present_today": present_today,
        "absent_today": absent_today,
        "attendance_rate": attendance_rate,
        "students": all_students[:100],  # Show recent 100 students
        "divisions": divisions,  # Add divisions for form dropdown
        "departments": departments,  # Add departments for form dropdown
    })


@login_required
@require_staff
def start_attendance_session(request):

    # 🔴 ADD THIS LINE (CRITICAL)
    departments = Department.objects.all().order_by("name")
    print("🔥 Departments count:", departments.count())

    # existing logic
    form = AttendanceSessionForm()
    active_sessions = AttendanceSession.objects.filter(status="active")

    return render(request, "dashboard/start_session.html", {
        "form": form,
        "active_sessions": active_sessions,
        "departments": departments,  # ✅ THIS WAS MISSING
    })

# ------------------ Reports ------------------
def _get_report_data(request):
    """Helper to extract report data based on filters"""
    # Base QuerySets
    sessions = AttendanceSession.objects.filter(status='completed').select_related('division', 'subject', 'lecture_period').order_by('-date')
    all_students = Student.objects.filter(is_active=True)
    
    # --- FILTERS ---
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    class_year = request.GET.get('class_year')
    division_id = request.GET.get('division')
    
    if start_date:
        sessions = sessions.filter(date__gte=start_date)
    if end_date:
        sessions = sessions.filter(date__lte=end_date)
    if class_year:
        sessions = sessions.filter(class_year=class_year)
    
    division_obj = None
    if division_id:
        sessions = sessions.filter(division_id=division_id)
        division_obj = Division.objects.filter(id=division_id).first()
        
    # 1. Stats Cards (Based on Filtered Data)
    total_sessions = sessions.count()
    total_students = all_students.count() 
    
    # 2. Average Attendance (Overall for filtered sessions)
    total_present = sessions.aggregate(Sum('present_count'))['present_count__sum'] or 0
    total_capacity = sessions.aggregate(Sum('total_students'))['total_students__sum'] or 0
    
    avg_attendance = 0
    if total_capacity > 0:
        avg_attendance = round((total_present / total_capacity) * 100, 1)
        
    # 3. Defaulters (Students < 75%)
    student_stats = all_students.annotate(
        total_recs=Count('attendance_records'),
        present_recs=Count('attendance_records', filter=Q(attendance_records__status='present'))
    )
    
    defaulters_count = 0
    for s in student_stats:
        if s.total_recs > 0:
            pct = (s.present_recs / s.total_recs) * 100
            if pct < 75:
                defaulters_count += 1
    
    divisions = Division.objects.all().order_by('name')
    
    return {
        "sessions": sessions,
        "total_sessions": total_sessions,
        "total_students": total_students,
        "avg_attendance": avg_attendance,
        "defaulters_count": defaulters_count,
        "divisions": divisions,
        "start_date": start_date,
        "end_date": end_date,
        "class_filter": class_year,
        "division_filter": int(division_id) if division_id else None,
        "division_obj": division_obj
    }

@login_required
def reports(request):
    """Analytics and Reports Dashboard"""
    data = _get_report_data(request)
    
    # Limit sessions for web preview
    context = data.copy()
    context['sessions'] = data['sessions'][:100]
    
    return render(request, "dashboard/reports.html", context)

@login_required
def export_reports_pdf(request):
    """Generate professional PDF report"""
    data = _get_report_data(request)
    sessions = data['sessions']
    
    response = HttpResponse(content_type='application/pdf')
    filename = f"Attendance_Report_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []
    
    styles = getSampleStyleSheet()
    title_style = styles['Heading1']
    title_style.alignment = 1 
    
    # Title
    elements.append(Paragraph("RollVision - Attendance Report", title_style))
    elements.append(Spacer(1, 12))
    
    # Filter Summary
    filter_text = []
    if data['start_date'] or data['end_date']:
        filter_text.append(f"Date: {data['start_date'] or 'Start'} to {data['end_date'] or 'End'}")
    if data['class_filter']:
        filter_text.append(f"Class: {data['class_filter']}")
    if data['division_obj']:
        filter_text.append(f"Division: {data['division_obj'].name}")
             
    if filter_text:
        elements.append(Paragraph(" | ".join(filter_text), styles['Normal']))
    else:
        elements.append(Paragraph("Filters: All Records", styles['Normal']))
    elements.append(Spacer(1, 12))
    
    # Statistics Summary Table
    stats_data = [
        ["Total Sessions", "Total Students", "Avg Attendance", "Low Attendance"],
        [str(data['total_sessions']), str(data['total_students']), f"{data['avg_attendance']}%", str(data['defaulters_count'])]
    ]
    t_stats = Table(stats_data, colWidths=[1.5*inch]*4)
    t_stats.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.grey),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0,0), (-1,0), 6),
        ('GRID', (0,0), (-1,-1), 1, colors.black)
    ]))
    elements.append(t_stats)
    elements.append(Spacer(1, 24))
    
    # Session Data Table
    data_table = [['Date', 'Class', 'Subject', 'Period', 'Present', 'Absent', '%']]
    
    for s in sessions:
        row = [
            s.date.strftime('%Y-%m-%d'),
            f"{s.class_year} - {s.division.name}",
            s.subject.code,
            s.lecture_period.name,
            str(s.present_count),
            str(s.absent_count),
            f"{s.get_attendance_percentage()}%"
        ]
        data_table.append(row)
        
    t_data = Table(data_table, repeatRows=1)
    t_data.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.darkblue),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.whitesmoke, colors.lightgrey]),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey)
    ]))
    
    elements.append(t_data)
    
    doc.build(elements)
    pdf = buffer.getvalue()
    buffer.close()
    response.write(pdf)
    return response


@login_required
def delete_student(request, pk):
    """Delete a student and all associated records"""
    try:
        student = get_object_or_404(Student, pk=pk)
        student_name = student.name
        student_id = student.student_id
        
        # Delete student (face encodings will cascade automatically due to FK)
        student.delete()
        
        messages.success(request, f"✅ Student {student_name} ({student_id}) deleted successfully!")
        logger.info(f"Student deleted: {student_id} - {student_name}")
    except Exception as e:
        logger.error(f"Error deleting student: {str(e)}")
        messages.error(request, f"❌ Error deleting student: {str(e)}")
    
    return redirect('students')


# ------------------ Settings (SYSTEM + FEEDBACK) ------------------
@login_required
@require_staff
def settings_view(request):
    settings_obj, created = SystemSettings.objects.get_or_create(id=1)

    # ---------- FEEDBACK ----------
    if request.method == "POST" and request.POST.get("form_type") == "feedback":
        feedback = request.POST.get("feedback", "").strip()

        if feedback:
            send_mail(
                subject="RollVision Feedback",
                message=feedback,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=["samarth.rollvision@gmail.com"],
                fail_silently=False,
            )
            messages.success(request, "Feedback submitted successfully!")

        return redirect("settings")

    # ---------- SYSTEM SETTINGS ----------
    if request.method == "POST":
        form = SettingsForm(request.POST, instance=settings_obj)
        if form.is_valid():
            form.save()
            messages.success(request, "Settings saved successfully!")
            return redirect("settings")
    else:
        form = SettingsForm(instance=settings_obj)

    return render(request, "dashboard/settings.html", {
        "form": form,
        "theme": settings_obj.theme,
    })


# ------------------ Face Detection & Attendance Views ------------------

@require_http_methods(["POST"])
@ensure_csrf_cookie
@login_required
@audit_log
@validate_json_request
def save_face_encoding(request):
    """API endpoint to save face encoding during student registration"""
    logger.info("Face encoding save requested")
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            student_id = data.get('student_id', '').strip()
            face_image_base64 = data.get('face_image', '').strip()
            
            logger.info(f"Received face encoding request for student: {student_id}")
            
            # Validate inputs
            if not student_id or not face_image_base64:
                logger.warning(f"Missing required fields for student {student_id}")
                return JsonResponse({'success': False, 'message': 'Missing required fields'}, status=400)
            
            # Sanitize student_id to prevent path traversal
            if not student_id.isalnum() or len(student_id) > 50:
                logger.warning(f"Invalid student ID format: {student_id}")
                return JsonResponse({'success': False, 'message': 'Invalid student ID format'}, status=400)
            
            try:
                student = Student.objects.get(student_id=student_id)
                logger.info(f"Found student: {student.name} ({student_id})")
            except Student.DoesNotExist:
                logger.error(f"Student not found: {student_id}")
                return JsonResponse({'success': False, 'message': 'Student not found'}, status=404)
            
            image = face_recognizer.base64_to_image(face_image_base64)
            success, message, faces = face_recognizer.verify_face_quality(image)
            
            if not success:
                logger.warning(f"Face quality check failed for {student_id}: {message}")
                return JsonResponse({'success': False, 'message': message}, status=400)
            
            # Get the first detected face (should be only one for training)
            face_rect = faces[0]
            
            encoding = face_recognizer.encode_face(image, face_rect)
            image_path = face_recognizer.save_face_image(image, student_id, face_rect)
            
            FaceEncoding.objects.create(
                student=student,
                encoding_data=json.dumps(encoding),
                image_path=image_path,
                is_active=True
            )
            
            student.is_trained = True
            student.save()
            
            logger.info(f"✅ Face encoding saved successfully for {student.name} ({student_id})")
            
            return JsonResponse({'success': True, 'message': 'Face registered successfully!', 'image_path': image_path})
            
        except FaceDetectionError as e:
            logger.warning(f"Face detection error: {str(e)}")
            return JsonResponse({'success': False, 'message': str(e)}, status=400)
        except Exception as e:
            logger.error(f"Error saving face encoding: {str(e)}")
            return JsonResponse({'success': False, 'message': 'An error occurred while processing your request'}, status=500)
    
    return JsonResponse({'success': False, 'message': 'Invalid request method'}, status=405)


@login_required
def mark_attendance_view(request):
    """Page for marking attendance using face recognition"""
    today = date.today()
    total_students = Student.objects.filter(is_trained=True).count()
    present_today = AttendanceRecord.objects.filter(date=today, status='present').count()
    
    context = {
        'total_students': total_students,
        'present_today': present_today,
        'absent_today': total_students - present_today,
        'today': today
    }
    return render(request, 'dashboard/mark_attendance.html', context)


@require_http_methods(["POST"])
@ensure_csrf_cookie
@login_required
@audit_log
@validate_json_request
def process_attendance(request):
    """API endpoint to process face recognition for attendance (supports multiple faces)"""
    logger.info("Attendance processing requested")
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            face_image_base64 = data.get('face_image')
            
            if not face_image_base64:
                return JsonResponse({
                    'success': False,
                    'message': 'No face image provided'
                }, status=400)
            
            # Get all active face encodings for training
            face_encodings = FaceEncoding.objects.filter(is_active=True).values_list(
                'student__id', 'encoding_data'
            )
            
            if not face_encodings:
                return JsonResponse({
                    'success': False,
                    'message': 'No students registered yet. Please register students first.'
                }, status=400)
            
            # Train recognizer with all faces
            face_recognizer.train_recognizer(list(face_encodings))
            
            # Convert base64 to image
            image = face_recognizer.base64_to_image(face_image_base64)
            
            # Recognize faces using multi-face detection
            try:
                results = face_recognizer.recognize_faces(image)
            except FaceDetectionError as e:
                return JsonResponse({
                    'success': False,
                    'message': str(e)
                }, status=400)
            
            if not results:
                return JsonResponse({
                    'success': False,
                    'message': 'No faces detected. Please ensure your face is visible and well-lit.',
                    'face_count': 0
                }, status=200)
            
            processed_students = []
            all_face_rects = []  # For visual feedback
            
            for result in results:
                student_id = result['student_id']
                confidence = result['confidence']
                face_rect = result['rect']
                
                # Add face rectangle for visual feedback (even for unrecognized faces)
                all_face_rects.append({
                    'x': face_rect[0],
                    'y': face_rect[1],
                    'w': face_rect[2],
                    'h': face_rect[3],
                    'recognized': student_id is not None,
                    'confidence': confidence
                })
                
                if student_id is None:
                    continue  # Skip unrecognized faces for attendance
                
                # Get student
                try:
                    student = Student.objects.get(id=student_id)
                except Student.DoesNotExist:
                    continue
                
                # Check if already marked today
                today = date.today()
                existing_record = AttendanceRecord.objects.filter(
                    student=student,
                    date=today
                ).first()
                
                student_data = {
                    'name': student.name,
                    'student_id': student.student_id,
                    'class_year': student.class_year,
                    'confidence': confidence,
                    'face_rect': {
                        'x': face_rect[0],
                        'y': face_rect[1],
                        'w': face_rect[2],
                        'h': face_rect[3]
                    }
                }
                
                if existing_record:
                    student_data['status'] = 'already_marked'
                    student_data['time'] = existing_record.time.strftime("%H:%M:%S")
                else:
                    # Create attendance record
                    attendance = AttendanceRecord.objects.create(
                        student=student,
                        status='present',
                        marked_by_face=True,
                        confidence_score=confidence,
                        date=today
                    )
                    student_data['status'] = 'marked'
                    student_data['time'] = attendance.time.strftime("%H:%M:%S")
                
                processed_students.append(student_data)
            
            if not processed_students:
                return JsonResponse({
                    'success': False,
                    'message': f'Detected {len(results)} face(s), but none were recognized. Please ensure registered students are in view.',
                    'face_count': len(results),
                    'face_rects': all_face_rects,
                    'detection_model': face_recognizer.detection_model
                }, status=200)
            
            return JsonResponse({
                'success': True,
                'message': f'Successfully processed {len(processed_students)} student(s).',
                'results': processed_students,
                'face_count': len(results),
                'face_rects': all_face_rects,
                'detection_model': face_recognizer.detection_model,
                'detection_time': getattr(face_recognizer, '_last_detection_time', 0)
            })
            
        except Exception as e:
            import traceback
            logger.error(f"Attendance processing error: {str(e)}\n{traceback.format_exc()}")
            return JsonResponse({
                'success': False,
                'message': f'Server error: {str(e)}'
            }, status=500)
    
    return JsonResponse({'success': False, 'message': 'Invalid request method'}, status=405)


@login_required
def attendance_history(request):
    """View attendance history with filters and pagination"""
    search_query = request.GET.get('q', '')
    date_filter = request.GET.get('date', '')
    class_filter = request.GET.get('class', '')
    page_number = request.GET.get('page', 1)
    
    records = AttendanceRecord.objects.select_related('student').all()
    
    # Apply filters
    if search_query:
        records = records.filter(
            Q(student__name__icontains=search_query) | 
            Q(student__student_id__icontains=search_query)
        )
    if date_filter:
        records = records.filter(date=date_filter)
    if class_filter:
        records = records.filter(student__class_year=class_filter)
    
    # Calculate statistics
    total_records = records.count()
    present_count = records.filter(status='present').count()
    
    # Paginate results
    paginator = Paginator(records, 50)  # Show 50 records per page
    
    try:
        paginated_records = paginator.page(page_number)
    except PageNotAnInteger:
        paginated_records = paginator.page(1)
    except EmptyPage:
        paginated_records = paginator.page(paginator.num_pages)
    
    context = {
        'records': paginated_records,
        'total_records': total_records,
        'present_count': present_count,
        'search_query': search_query,
        'date_filter': date_filter,
        'class_filter': class_filter,
    }
    
    return render(request, 'dashboard/attendance_history.html', context)


@login_required
def export_attendance_pdf(request):
    """Export filtered attendance records as PDF"""
    # Get filter parameters
    search_query = request.GET.get('q', '')
    date_filter = request.GET.get('date', '')
    class_filter = request.GET.get('class', '')
    
    # Apply same filters as attendance_history view
    records = AttendanceRecord.objects.select_related('student').all()
    
    if search_query:
        records = records.filter(
            Q(student__name__icontains=search_query) | 
            Q(student__student_id__icontains=search_query)
        )
    if date_filter:
        records = records.filter(date=date_filter)
    if class_filter:
        records = records.filter(student__class_year=class_filter)
    
    # Calculate statistics
    total_records = records.count()
    present_count = records.filter(status='present').count()
    absent_count = records.filter(status='absent').count()
    
    # Create PDF response
    response = HttpResponse(content_type='application/pdf')
    
    # Generate filename based on filters
    filename_parts = ['attendance_records']
    if date_filter:
        filename_parts.append(date_filter)
    if class_filter:
        filename_parts.append(class_filter)
    filename = '_'.join(filename_parts) + '.pdf'
    
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    # Create PDF document in buffer
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []
    
    styles = getSampleStyleSheet()
    
    # Title
    title = Paragraph("Attendance Records", styles['Heading1'])
    elements.append(title)
    elements.append(Spacer(1, 12))
    
    # Filter information
    if search_query or date_filter or class_filter:
        filter_text = "Filters Applied: "
        filter_parts = []
        if search_query:
            filter_parts.append(f"Search: {search_query}")
        if date_filter:
            filter_parts.append(f"Date: {date_filter}")
        if class_filter:
            filter_parts.append(f"Class: {class_filter}")
        filter_text += ", ".join(filter_parts)
        filter_para = Paragraph(filter_text, styles['Normal'])
        elements.append(filter_para)
        elements.append(Spacer(1, 12))
    
    # Summary statistics
    summary_text = f"Total Records: {total_records} | Present: {present_count} | Absent: {absent_count}"
    summary_para = Paragraph(summary_text, styles['Normal'])
    elements.append(summary_para)
    elements.append(Spacer(1, 20))
    
    # Table data
    if records.exists():
        data = [['Student ID', 'Name', 'Class', 'Date', 'Time', 'Status', 'Method']]
        
        for record in records[:500]:  # Limit to 500 records for PDF performance
            method = 'Face Recognition' if record.marked_by_face else 'Manual'
            data.append([
                record.student.student_id,
                record.student.name[:20],  # Truncate long names
                record.student.class_year,
                record.date.strftime('%Y-%m-%d'),
                record.time.strftime('%H:%M'),
                record.status.capitalize(),
                method
            ])
        
        # Create table
        table = Table(data, colWidths=[70, 100, 50, 70, 50, 60, 100])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4F81BD')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F0F0F0')])
        ]))
        
        elements.append(table)
        
        if total_records > 500:
            elements.append(Spacer(1, 12))
            note = Paragraph(f"Note: Showing first 500 of {total_records} records", styles['Italic'])
            elements.append(note)
    else:
        no_data_para = Paragraph("No attendance records found matching the selected filters.", styles['Normal'])
        elements.append(no_data_para)
    
    # Build PDF
    doc.build(elements)
    
    # Get the value of the BytesIO buffer and write it to the response.
    pdf = buffer.getvalue()
    buffer.close()
    
    response.write(pdf)
    return response

from django.contrib.auth import authenticate, login

def custom_login(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")

        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            return redirect("index")  # your dashboard
        else:
            messages.error(request, "Invalid username or password")

    return render(request, "auth/login.html")

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