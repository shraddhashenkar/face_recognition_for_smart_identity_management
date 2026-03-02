from django.core.management.base import BaseCommand
from dashboard.models import Department, Division, Subject, LecturePeriod
from datetime import time


class Command(BaseCommand):
    help = 'Setup initial data for RollVision (Departments, Divisions, Subjects, Lecture Periods)'

    def handle(self, *args, **options):
        self.stdout.write("=" * 60)
        self.stdout.write(self.style.SUCCESS("Setting up initial data for RollVision..."))
        self.stdout.write("=" * 60)

        # Create Departments
        self.stdout.write("\n1. Creating Departments...")
        departments = [
            {"code": "CS", "name": "Computer Science", "description": "Computer Science & Engineering"},
            {"code": "EC", "name": "Electronics", "description": "Electronics & Communication Engineering"},
            {"code": "ME", "name": "Mechanical", "description": "Mechanical Engineering"},
        ]

        for dept_data in departments:
            dept, created = Department.objects.get_or_create(
                code=dept_data["code"],
                defaults={"name": dept_data["name"], "description": dept_data["description"]}
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f"   ✓ Created: {dept}"))
            else:
                self.stdout.write(f"   - Already exists: {dept}")

        # Create Divisions
        self.stdout.write("\n2. Creating Divisions...")
        divisions = [
            {"name": "A", "max_students": 60},
            {"name": "B", "max_students": 60},
            {"name": "C", "max_students": 60},
        ]

        for div_data in divisions:
            div, created = Division.objects.get_or_create(
                name=div_data["name"],
                defaults={"max_students": div_data["max_students"]}
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f"   ✓ Created: Division {div}"))
            else:
                self.stdout.write(f"   - Already exists: Division {div}")

        # Create Subjects
        self.stdout.write("\n3. Creating Subjects...")
        cs_dept = Department.objects.get(code="CS")
        subjects = [
            {"code": "CS301", "name": "Database Management System", "department": cs_dept, "semester": 3, "credits": 3},
            {"code": "CS302", "name": "Data Structures & Algorithms", "department": cs_dept, "semester": 3, "credits": 4},
            {"code": "CS303", "name": "Computer Networks", "department": cs_dept, "semester": 3, "credits": 3},
            {"code": "CS401", "name": "Operating Systems", "department": cs_dept, "semester": 4, "credits": 4},
            {"code": "CS402", "name": "Software Engineering", "department": cs_dept, "semester": 4, "credits": 3},
        ]

        for subj_data in subjects:
            subj, created = Subject.objects.get_or_create(
                code=subj_data["code"],
                defaults={
                    "name": subj_data["name"],
                    "department": subj_data["department"],
                    "semester": subj_data["semester"],
                    "credits": subj_data["credits"]
                }
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f"   ✓ Created: {subj}"))
            else:
                self.stdout.write(f"   - Already exists: {subj}")

        # Create Lecture Periods
        self.stdout.write("\n4. Creating Lecture Periods...")
        periods = [
            {"number": 1, "name": "Lecture 1", "start": time(9, 0), "end": time(10, 0)},
            {"number": 2, "name": "Lecture 2", "start": time(10, 0), "end": time(11, 0)},
            {"number": 3, "name": "Lecture 3", "start": time(11, 0), "end": time(12, 0)},
            {"number": 4, "name": "Lunch Break", "start": time(12, 0), "end": time(13, 0)},
            {"number": 5, "name": "Lecture 4", "start": time(13, 0), "end": time(14, 0)},
            {"number": 6, "name": "Lecture 5", "start": time(14, 0), "end": time(15, 0)},
            {"number": 7, "name": "Lab Session 1", "start": time(15, 0), "end": time(17, 0)},
        ]

        for period_data in periods:
            period, created = LecturePeriod.objects.get_or_create(
                period_number=period_data["number"],
                defaults={
                    "name": period_data["name"],
                    "start_time": period_data["start"],
                    "end_time": period_data["end"],
                    "is_active": True
                }
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f"   ✓ Created: {period}"))
            else:
                self.stdout.write(f"   - Already exists: {period}")

        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.SUCCESS("✓ Initial data setup complete!"))
        self.stdout.write("=" * 60)
        self.stdout.write("\nYou can now:")
        self.stdout.write("1. Register students at: http://localhost:8000/students/")
        self.stdout.write("2. Start attendance at: http://localhost:8000/attendance/start-session/")
        self.stdout.write("3. Access admin panel at: http://localhost:8000/admin/")
        self.stdout.write("")
