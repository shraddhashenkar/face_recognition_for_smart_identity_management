"""
Lecture Management Models for RollVision
These models handle lecture periods, schedules, and attendance sessions
"""
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone


class Department(models.Model):
    """Academic departments in the college"""
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=10, unique=True, help_text="Short code (e.g., CS, EC, ME)")
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.code} - {self.name}"

    class Meta:
        ordering = ['name']


class Division(models.Model):
    """Class divisions (A, B, C, etc.)"""
    name = models.CharField(max_length=10, unique=True, help_text="Division name (A, B, C, etc.)")
    max_students = models.IntegerField(
        default=60,
        validators=[MinValueValidator(1), MaxValueValidator(100)],
        help_text="Maximum students in this division"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']


class Subject(models.Model):
    """Subjects taught in the college"""
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20, unique=True, help_text="Subject code (e.g., CS301)")
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name='subjects')
    credits = models.IntegerField(
        default=3,
        validators=[MinValueValidator(1), MaxValueValidator(6)],
        help_text="Credit hours"
    )
    semester = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(8)],
        help_text="Semester number"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.code} - {self.name}"

    class Meta:
        ordering = ['semester', 'code']


class LecturePeriod(models.Model):
    """Configured lecture time slots"""
    name = models.CharField(max_length=50, help_text="Period name (e.g., Lecture 1, Lab Session 1)")
    period_number = models.IntegerField(
        unique=True,
        validators=[MinValueValidator(1), MaxValueValidator(10)],
        help_text="Period number in daily sequence"
    )
    start_time = models.TimeField()
    end_time = models.TimeField()
    is_active = models.BooleanField(default=True, help_text="Whether this period is currently in use")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.start_time.strftime('%H:%M')} - {self.end_time.strftime('%H:%M')})"

    class Meta:
        ordering = ['period_number']

    def clean(self):
        """Validate that end_time is after start_time"""
        from django.core.exceptions import ValidationError
        if self.start_time >= self.end_time:
            raise ValidationError('End time must be after start time')


class LectureSchedule(models.Model):
    """Maps subjects to periods for specific class/division combinations"""
    WEEKDAY_CHOICES = [
        (0, 'Monday'),
        (1, 'Tuesday'),
        (2, 'Wednesday'),
        (3, 'Thursday'),
        (4, 'Friday'),
        (5, 'Saturday'),
        (6, 'Sunday'),
    ]

    class_year = models.CharField(
        max_length=2,
        choices=[
            ('FE', 'FE'),
            ('SE', 'SE'),
            ('TE', 'TE'),
            ('BE', 'BE'),
        ]
    )
    division = models.ForeignKey(Division, on_delete=models.CASCADE, related_name='schedules')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='schedules')
    lecture_period = models.ForeignKey(LecturePeriod, on_delete=models.CASCADE, related_name='schedules')
    weekday = models.IntegerField(choices=WEEKDAY_CHOICES)
    faculty = models.ForeignKey('Faculty', on_delete=models.SET_NULL, null=True, blank=True, related_name='schedules')
    room_number = models.CharField(max_length=20, blank=True, help_text="Classroom/Lab number")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.class_year}-{self.division.name} | {self.subject.code} | {self.lecture_period.name}"

    class Meta:
        ordering = ['class_year', 'division', 'weekday', 'lecture_period']
        unique_together = ['class_year', 'division', 'lecture_period', 'weekday']


class AttendanceSession(models.Model):
    """Tracks each attendance-taking session"""
    SESSION_STATUS = [
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    class_year = models.CharField(
        max_length=2,
        choices=[
            ('FE', 'FE'),
            ('SE', 'SE'),
            ('TE', 'TE'),
            ('BE', 'BE'),
        ]
    )
    division = models.ForeignKey(Division, on_delete=models.CASCADE, related_name='attendance_sessions')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='attendance_sessions')
    lecture_period = models.ForeignKey(LecturePeriod, on_delete=models.CASCADE, related_name='attendance_sessions')
    faculty = models.ForeignKey('Faculty', on_delete=models.SET_NULL, null=True, related_name='attendance_sessions')
    
    date = models.DateField(default=timezone.now)
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=SESSION_STATUS, default='active')
    
    total_students = models.IntegerField(default=0, help_text="Total students in this class/division")
    present_count = models.IntegerField(default=0, help_text="Students marked present")
    absent_count = models.IntegerField(default=0, help_text="Students marked absent")
    
    notes = models.TextField(blank=True, help_text="Optional notes about this session")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Session {self.id} | {self.class_year}-{self.division.name} | {self.subject.code} | {self.date}"

    class Meta:
        ordering = ['-date', '-started_at']
        indexes = [
            models.Index(fields=['date', 'class_year', 'division']),
            models.Index(fields=['status']),
        ]

    def end_session(self):
        """Mark session as completed and calculate statistics"""
        from .models import Student, AttendanceRecord
        
        self.ended_at = timezone.now()
        self.status = 'completed'
        
        # Get total students in this class/division
        total_students = Student.objects.filter(
            class_year=self.class_year,
            division=self.division,
            is_trained=True
        ).count()
        
        self.total_students = total_students
        
        # Count present students
        self.present_count = AttendanceRecord.objects.filter(
            session=self,
            status='present'
        ).count()
        
        self.absent_count = self.total_students - self.present_count
        self.save()

    def get_attendance_percentage(self):
        """Calculate attendance percentage for this session"""
        if self.total_students == 0:
            return 0
        return round((self.present_count / self.total_students) * 100, 2)
