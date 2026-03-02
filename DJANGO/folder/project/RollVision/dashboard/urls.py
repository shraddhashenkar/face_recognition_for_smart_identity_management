from django.urls import path
from . import views, session_views
from .views import custom_login

urlpatterns = [
    path('', views.index, name='index'),
    path("login/", custom_login, name="login"),

    path("api/subjects/", views.ajax_subjects, name="ajax_subjects"),


    path('faculty/', views.faculty, name='faculty'),
    path('faculty/delete/<int:pk>/', views.delete_faculty, name='delete_faculty'),
    path('faculty/export/', views.export_employees_pdf, name='export_employees_pdf'),
    path('export/excel/', views.export_reports_excel, name='export_reports_excel'),
    path('export/csv/', views.export_reports_csv, name='export_reports_csv'),

    path('students/', views.students, name='students'),
    path('students/delete/<int:pk>/', views.delete_student, name='delete_student'),
    
    # Face detection and attendance
    path('api/save-face/', views.save_face_encoding, name='save_face'),
    
    # Session-based attendance
    path('attendance/start-session/', session_views.start_attendance_session_view, name='start_attendance_session'),
    path('attendance/live/<int:session_id>/', session_views.mark_attendance_live, name='mark_attendance_live'),
    path('api/auto-mark-attendance/', session_views.auto_mark_attendance, name='auto_mark_attendance'),
    path('attendance/end-session/<int:session_id>/', session_views.end_attendance_session, name='end_attendance_session'),
    path('attendance/session/<int:session_id>/summary/', session_views.session_summary, name='session_summary'),
    path('attendance/session/<int:session_id>/export-pdf/', session_views.export_session_pdf, name='export_session_pdf'),
    
    # Legacy attendance endpoints (for backward compatibility)
    path('attendance/mark/', views.mark_attendance_view, name='mark_attendance'),
    path('api/process-attendance/', views.process_attendance, name='process_attendance'),
    path('attendance/history/', views.attendance_history, name='attendance_history'),
    path('attendance/export/pdf/', views.export_attendance_pdf, name='export_attendance_pdf'),
    
    path('reports/', views.reports, name='reports'),
    path('reports/export/pdf/', views.export_reports_pdf, name='export_reports_pdf'),
    path('settings/', views.settings_view, name='settings'),
]
