import os
import re

# Directory containing templates
templates_dir = r"c:\Users\levono\OneDrive\Desktop\DJANGO - Copy\folder\project\RollVision\dashboard\templates\dashboard"

# Files to process (excluding _sidebar.html itself)
files_to_process = [
    "index.html",
    "faculty.html",
    "students.html",
    "start_session.html",
    "attendance_history.html",
    "mark_attendance.html",
    "settings.html",
    "session_summary.html",
    "mark_attendance_live.html"
]

# Pattern to match the hardcoded sidebar block
# Matches from <div class="sidebar"> to its closing </div>
sidebar_pattern = r'<!-- ================= SIDEBAR ================= -->.*?<div class="sidebar">.*?</div>\s*(?=<!--|\s*<div class="content">)'

replacement = "<!-- Sidebar -->\n    {% include 'dashboard/_sidebar.html' %}\n\n    "

for filename in files_to_process:
    filepath = os.path.join(templates_dir, filename)
    if not os.path.exists(filepath):
        print(f"Skipping {filename} - file not found")
        continue
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Replace the hardcoded sidebar with include
    new_content = re.sub(sidebar_pattern, replacement, content, flags=re.DOTALL)
    
    if new_content != content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"✓ Updated {filename}")
    else:
        print(f"- No change needed for {filename}")

print("\n✅ Sidebar replacement complete!")
