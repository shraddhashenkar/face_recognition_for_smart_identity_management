from django.contrib import admin
from .models import (
    Faculty, SystemSettings, Student, FaceEncoding, AttendanceRecord,
    Department, Division, Subject, LecturePeriod, LectureSchedule, AttendanceSession
)


@admin.register(Faculty)
class FacultyAdmin(admin.ModelAdmin):
    list_display = ['name', 'department', 'subject']
    search_fields = ['name', 'department', 'subject']


@admin.register(SystemSettings)
class SystemSettingsAdmin(admin.ModelAdmin):
    list_display = ['theme', 'timezone', 'min_attendance']


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ['student_id', 'name', 'class_year', 'division', 'department', 'is_trained', 'is_active']
    list_filter = ['class_year', 'division', 'department', 'is_trained', 'is_active']
    search_fields = ['student_id', 'name', 'email']
    list_per_page = 50


@admin.register(FaceEncoding)
class FaceEncodingAdmin(admin.ModelAdmin):
    list_display = ['student', 'created_at', 'is_active']
    list_filter = ['is_active', 'created_at']
    search_fields = ['student__name', 'student__student_id']


@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display = ['student', 'subject', 'lecture_period', 'date', 'status', 'marked_by_face']
    list_filter = ['status', 'marked_by_face', 'date', 'subject', 'lecture_period']
    search_fields = ['student__name', 'student__student_id']
    date_hierarchy = 'date'
    list_per_page = 100


# Lecture Management Models

@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'created_at']
    search_fields = ['name', 'code']


@admin.register(Division)
class DivisionAdmin(admin.ModelAdmin):
    list_display = ['name', 'max_students', 'created_at']
    search_fields = ['name']


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'department', 'semester', 'credits']
    list_filter = ['department', 'semester']
    search_fields = ['name', 'code']


@admin.register(LecturePeriod)
class LecturePeriodAdmin(admin.ModelAdmin):
    list_display = ['period_number', 'name', 'start_time', 'end_time', 'is_active']
    list_filter = ['is_active']
    ordering = ['period_number']


@admin.register(LectureSchedule)
class LectureScheduleAdmin(admin.ModelAdmin):
    list_display = ['class_year', 'division', 'subject', 'lecture_period', 'weekday', 'faculty', 'is_active']
    list_filter = ['class_year', 'division', 'weekday', 'is_active']
    search_fields = ['subject__name', 'subject__code', 'faculty__name']


@admin.register(AttendanceSession)
class AttendanceSessionAdmin(admin.ModelAdmin):
    list_display = ['id', 'class_year', 'division', 'subject', 'lecture_period', 'date', 'status', 'present_count', 'total_students', 'get_attendance_percentage']
    list_filter = ['status', 'class_year', 'division', 'date']
    search_fields = ['subject__name', 'subject__code']
    date_hierarchy = 'date'
    readonly_fields = ['started_at', 'ended_at', 'present_count', 'absent_count', 'total_students']
    
    def get_attendance_percentage(self, obj):
        return f"{obj.get_attendance_percentage()}%"
    get_attendance_percentage.short_description = 'Attendance %'
