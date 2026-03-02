from django import forms
from .models import Faculty, SystemSettings, Student, Department, Division, Subject, LecturePeriod, AttendanceSession

class FacultyForm(forms.ModelForm):
    class Meta:
        model = Faculty
        fields = ['name', 'department', 'subject']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter name'}),
            'department': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter department'}),
            'subject': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter subject'}),
        }


class StudentForm(forms.ModelForm):
    """Form for student registration with validation"""
    photo = forms.ImageField(
        required=False,
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': 'image/*',
            'id': 'id_photo'
        }),
        help_text="Upload a photo (alternative to camera capture)"
    )
    
    class Meta:
        model = Student
        fields = ['student_id', 'name', 'email', 'phone_number', 'class_year', 'department', 'division', 'roll_number', 'photo']
        widgets = {
            'student_id': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter Student ID',
                'required': True,
                'pattern': '[A-Za-z0-9]+',
            }),
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter Full Name',
                'required': True,
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter Email',
                'required': True,
            }),
            'phone_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '+1234567890 (optional)',
            }),
            'class_year': forms.Select(attrs={
                'class': 'form-select',
                'required': True,
            }),
            'department': forms.Select(attrs={
                'class': 'form-select',
            }),
            'division': forms.Select(attrs={
                'class': 'form-select',
            }),
            'roll_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Roll Number (optional)',
            }),
        }

    def clean_student_id(self):
        """Validate student ID is unique"""
        student_id = self.cleaned_data.get('student_id')
        if self.instance.pk:  # If editing existing student
            if Student.objects.filter(student_id=student_id).exclude(pk=self.instance.pk).exists():
                raise forms.ValidationError('Student ID already exists.')
        else:  # If creating new student
            if Student.objects.filter(student_id=student_id).exists():
                raise forms.ValidationError('Student ID already exists.')
        return student_id


class AttendanceSessionForm(forms.Form):
    """Form for starting an attendance session"""
    class_year = forms.ChoiceField(
        choices=[
            ('FE', 'FE'),
            ('SE', 'SE'),
            ('TE', 'TE'),
            ('BE', 'BE'),
        ],
        widget=forms.Select(attrs={'class': 'form-select', 'required': True})
    )
    division = forms.ModelChoiceField(
        queryset=Division.objects.all(),
        widget=forms.Select(attrs={'class': 'form-select', 'required': True}),
        empty_label="Select Division"
    )
    subject = forms.ModelChoiceField(
        queryset=Subject.objects.all(),
        widget=forms.Select(attrs={'class': 'form-select', 'required': True}),
        empty_label="Select Subject"
    )
    lecture_period = forms.ModelChoiceField(
        queryset=LecturePeriod.objects.filter(is_active=True),
        widget=forms.Select(attrs={'class': 'form-select', 'required': True}),
        empty_label="Select Lecture Period"
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 2,
            'placeholder': 'Optional notes about this session'
        })
    )


class SettingsForm(forms.ModelForm):
    class Meta:
        model = SystemSettings
        fields = [
            "theme", "timezone",
            "min_attendance", "grace_period", "auto_absent",
            "notify_parents", "faculty_reminder", "hod_summary"
        ]
        widgets = {
            # Theme selection
            "theme": forms.Select(attrs={'class': 'form-select'}),

            # Timezone selection
            "timezone": forms.Select(
                choices=[
                    ("Asia/Kolkata", "Asia/Kolkata"),
                    ("UTC", "UTC"),
                    ("Asia/Dubai", "Asia/Dubai"),
                ],
                attrs={'class': 'form-select'}
            ),

            # Attendance rules
            "min_attendance": forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'max': 100}),
            "grace_period": forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            "auto_absent": forms.CheckboxInput(attrs={'class': 'form-check-input'}),

            # Notifications
            "notify_parents": forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            "faculty_reminder": forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            "hod_summary": forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

