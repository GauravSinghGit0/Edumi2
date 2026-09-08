#!/usr/bin/env python3
"""
load_testing/users.py
=====================
Generates and manages 1000 load-testing accounts (test1 through test1000) with password 'test'.
Also creates 10 test classrooms with 10 enrolled students each and active meetings.

Roles:
  - test1  to test10   (10 users):  Admin / Superuser (0.5% - 1%)
  - test11 to test50   (40 users):  Teachers (4%)
  - test51 to test1000 (950 users): Students (95%)

Classrooms:
  - 10 classrooms (TESTCLASS01 to TESTCLASS10)
  - Each assigned to a test teacher (test11 to test20)
  - Each has 10 approved student memberships (100 students total: test51 to test150)
  - Each has an active live Meeting (TESTMEET01 to TESTMEET10)

Usage:
  python load_testing/users.py             # Create/update users and classrooms
  python load_testing/users.py --verify    # Verify existing fixtures
  python load_testing/users.py --cleanup   # Delete all test fixtures cleanly
"""

import os
import sys
import json
import argparse
from pathlib import Path

# Setup Django environment
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'school_project.settings')

import django
django.setup()

from django.db import transaction
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password, check_password
from django.utils import timezone
from accounts.models import UserProfile
from meetings.models import Classroom, ClassroomMembership, Meeting

User = get_user_model()

# Configuration
TOTAL_USERS = 1000
PASSWORD = "test"
NUM_ADMINS = 10          # test1  .. test10
NUM_TEACHERS = 40        # test11 .. test50
NUM_STUDENTS = 950       # test51 .. test1000

NUM_CLASSROOMS = 10
STUDENTS_PER_CLASSROOM = 10

CREDENTIALS_FILE = BASE_DIR / 'load_testing' / 'credentials.json'


def get_role_for_index(idx: int) -> str:
    """Determine role based on user index (1-indexed)."""
    if 1 <= idx <= NUM_ADMINS:
        return 'admin'
    elif NUM_ADMINS < idx <= (NUM_ADMINS + NUM_TEACHERS):
        return 'teacher'
    else:
        return 'student'


def create_or_update_users():
    """Create or update 1000 test users idempotently."""
    print("=" * 60)
    print("  EduMi Load Testing: User & Classroom Provisioner")
    print("=" * 60)
    print(f"[*] Target: {TOTAL_USERS} test users (test1 .. test{TOTAL_USERS})")
    print(f"    - Admins:   {NUM_ADMINS}  (test1 - test{NUM_ADMINS})")
    print(f"    - Teachers: {NUM_TEACHERS}  (test{NUM_ADMINS+1} - test{NUM_ADMINS+NUM_TEACHERS})")
    print(f"    - Students: {NUM_STUDENTS} (test{NUM_ADMINS+NUM_TEACHERS+1} - test{TOTAL_USERS})")
    print(f"[*] Password: '{PASSWORD}' for all accounts")

    t_start = timezone.now()
    print("[*] Generating PBKDF2 password hash (single pass)...")
    hashed_password = make_password(PASSWORD)
    print("    Done.")

    usernames = [f"test{i}" for i in range(1, TOTAL_USERS + 1)]
    existing_users = {u.username: u for u in User.objects.filter(username__in=usernames)}
    print(f"[*] Found {len(existing_users)} existing test users in database.")

    users_to_create = []
    users_to_update = []
    
    for i in range(1, TOTAL_USERS + 1):
        username = f"test{i}"
        role = get_role_for_index(i)
        is_admin = (role == 'admin')
        
        if username in existing_users:
            user = existing_users[username]
            user.password = hashed_password
            user.is_active = True
            user.is_staff = is_admin
            user.is_superuser = is_admin
            user.first_name = "Test"
            user.last_name = f"User{i}"
            user.email = f"{username}@example.com"
            users_to_update.append(user)
        else:
            user = User(
                username=username,
                email=f"{username}@example.com",
                first_name="Test",
                last_name=f"User{i}",
                password=hashed_password,
                is_active=True,
                is_staff=is_admin,
                is_superuser=is_admin,
            )
            users_to_create.append(user)

    with transaction.atomic():
        if users_to_create:
            print(f"[*] Bulk creating {len(users_to_create)} new User records...")
            User.objects.bulk_create(users_to_create, batch_size=500)
            print("    Done.")
            
        if users_to_update:
            print(f"[*] Bulk updating {len(users_to_update)} existing User records...")
            User.objects.bulk_update(
                users_to_update,
                fields=['password', 'is_active', 'is_staff', 'is_superuser', 'first_name', 'last_name', 'email'],
                batch_size=500
            )
            print("    Done.")

    print("[*] Ensuring UserProfiles and verified status...")
    all_users = {u.username: u for u in User.objects.filter(username__in=usernames)}
    existing_profiles = {p.user_id: p for p in UserProfile.objects.filter(user__in=all_users.values())}

    profiles_to_create = []
    profiles_to_update = []
    now = timezone.now()

    for i in range(1, TOTAL_USERS + 1):
        username = f"test{i}"
        user = all_users[username]
        role = get_role_for_index(i)
        
        if user.id in existing_profiles:
            profile = existing_profiles[user.id]
            profile.user_type = role
            profile.is_verified = True
            if not profile.email_verified_at:
                profile.email_verified_at = now
            profile.display_name = f"Test {role.capitalize()} {i}"
            if role == 'student':
                profile.student_id = f"STU{i:04d}"
            elif role == 'teacher':
                profile.employee_id = f"EMP{i:04d}"
            profiles_to_update.append(profile)
        else:
            profile = UserProfile(
                user=user,
                user_type=role,
                is_verified=True,
                email_verified_at=now,
                display_name=f"Test {role.capitalize()} {i}",
                student_id=f"STU{i:04d}" if role == 'student' else None,
                employee_id=f"EMP{i:04d}" if role == 'teacher' else None,
            )
            profiles_to_create.append(profile)

    with transaction.atomic():
        if profiles_to_create:
            print(f"[*] Bulk creating {len(profiles_to_create)} UserProfiles...")
            UserProfile.objects.bulk_create(profiles_to_create, batch_size=500)
            print("    Done.")
            
        if profiles_to_update:
            print(f"[*] Bulk updating {len(profiles_to_update)} UserProfiles...")
            UserProfile.objects.bulk_update(
                profiles_to_update,
                fields=['user_type', 'is_verified', 'email_verified_at', 'display_name', 'student_id', 'employee_id'],
                batch_size=500
            )
            print("    Done.")

    print("[*] Creating 10 classrooms with 10 students each...")
    classrooms_meta = []
    
    with transaction.atomic():
        for c_idx in range(1, NUM_CLASSROOMS + 1):
            class_code = f"TESTCLASS{c_idx:02d}"
            title = f"Test Classroom {c_idx:02d}"
            teacher_username = f"test{NUM_ADMINS + c_idx}"  # test11 to test20
            teacher = all_users[teacher_username]

            classroom, created = Classroom.objects.get_or_create(
                class_code=class_code,
                defaults={
                    'title': title,
                    'password': hashed_password,
                    'teacher': teacher,
                    'description': f"Load testing classroom #{c_idx} (managed by {teacher_username})",
                    'auto_approve': True,
                    'is_active': True,
                }
            )
            if not created:
                classroom.title = title
                classroom.password = hashed_password
                classroom.teacher = teacher
                classroom.auto_approve = True
                classroom.is_active = True
                classroom.save()

            student_start = (NUM_ADMINS + NUM_TEACHERS) + (c_idx - 1) * STUDENTS_PER_CLASSROOM + 1
            student_end = student_start + STUDENTS_PER_CLASSROOM
            classroom_students = []

            for s_idx in range(student_start, student_end):
                student_user = all_users[f"test{s_idx}"]
                classroom_students.append(student_user.username)
                
                membership, m_created = ClassroomMembership.objects.get_or_create(
                    classroom=classroom,
                    student=student_user,
                    defaults={
                        'status': 'approved',
                        'approved_at': now,
                        'approved_by': teacher,
                    }
                )
                if not m_created and membership.status != 'approved':
                    membership.status = 'approved'
                    membership.approved_at = now
                    membership.approved_by = teacher
                    membership.save(update_fields=['status', 'approved_at', 'approved_by'])

            meeting_code = f"TESTMEET{c_idx:02d}"
            meeting, meet_created = Meeting.objects.get_or_create(
                meeting_code=meeting_code,
                defaults={
                    'classroom': classroom,
                    'teacher': teacher,
                    'title': f"Live Lecture - Classroom {c_idx:02d}",
                    'description': f"Active load test meeting for {class_code}",
                    'meeting_type': 'classroom',
                    'scheduled_time': now,
                    'duration_minutes': 180,
                    'status': 'live',
                    'sleep_status': 'active',
                    'max_participants': 250,
                    'allow_chat': True,
                    'allow_screen_share': True,
                }
            )
            if not meet_created:
                meeting.classroom = classroom
                meeting.teacher = teacher
                meeting.status = 'live'
                meeting.sleep_status = 'active'
                meeting.save(update_fields=['classroom', 'teacher', 'status', 'sleep_status'])

            classrooms_meta.append({
                'id': classroom.id,
                'class_code': class_code,
                'title': title,
                'teacher': teacher.username,
                'meeting_id': meeting.id,
                'meeting_code': meeting_code,
                'students': classroom_students,
            })

    credentials_payload = {
        'generated_at': now.isoformat(),
        'password': PASSWORD,
        'summary': {
            'total_users': TOTAL_USERS,
            'admins': NUM_ADMINS,
            'teachers': NUM_TEACHERS,
            'students': NUM_STUDENTS,
            'classrooms': NUM_CLASSROOMS,
            'students_per_classroom': STUDENTS_PER_CLASSROOM,
        },
        'roles': {
            'admins': [f"test{i}" for i in range(1, NUM_ADMINS + 1)],
            'teachers': [f"test{i}" for i in range(NUM_ADMINS + 1, NUM_ADMINS + NUM_TEACHERS + 1)],
            'students': [f"test{i}" for i in range(NUM_ADMINS + NUM_TEACHERS + 1, TOTAL_USERS + 1)],
        },
        'classrooms': classrooms_meta,
    }

    with open(CREDENTIALS_FILE, 'w', encoding='utf-8') as f:
        json.dump(credentials_payload, f, indent=2)

    elapsed = (timezone.now() - t_start).total_seconds()
    print("=" * 60)
    print(f"[+] SUCCESS: 1000 users and 10 classrooms provisioned in {elapsed:.2f}s!")
    print(f"[+] Credentials metadata saved to: {CREDENTIALS_FILE.name}")
    print("=" * 60)


def cleanup_test_data():
    """Clean up all load test users, classrooms, memberships, and meetings."""
    print("=" * 60)
    print("  EduMi Load Testing: Cleanup Routine")
    print("=" * 60)
    
    usernames = [f"test{i}" for i in range(1, TOTAL_USERS + 1)]
    class_codes = [f"TESTCLASS{i:02d}" for i in range(1, NUM_CLASSROOMS + 1)]
    meeting_codes = [f"TESTMEET{i:02d}" for i in range(1, NUM_CLASSROOMS + 1)]

    with transaction.atomic():
        deleted_meetings, _ = Meeting.objects.filter(meeting_code__in=meeting_codes).delete()
        print(f"[-] Deleted {deleted_meetings} test meetings ({meeting_codes[0]}..{meeting_codes[-1]}).")

        deleted_classes, _ = Classroom.objects.filter(class_code__in=class_codes).delete()
        print(f"[-] Deleted {deleted_classes} test classrooms ({class_codes[0]}..{class_codes[-1]}).")

        deleted_users, _ = User.objects.filter(username__in=usernames).delete()
        print(f"[-] Deleted {deleted_users} test users (test1..test{TOTAL_USERS}).")

    if CREDENTIALS_FILE.exists():
        CREDENTIALS_FILE.unlink()
        print(f"[-] Removed {CREDENTIALS_FILE.name}.")

    print("=" * 60)
    print("[+] Cleanup complete. Database is restored to clean state.")
    print("=" * 60)


def verify_test_data():
    """Verify that all 1000 users and 10 classrooms are correctly provisioned."""
    print("=" * 60)
    print("  EduMi Load Testing: Verification Check")
    print("=" * 60)
    
    usernames = [f"test{i}" for i in range(1, TOTAL_USERS + 1)]
    users = {u.username: u for u in User.objects.filter(username__in=usernames).select_related('userprofile')}
    
    user_count = len(users)
    print(f"[*] Test users found: {user_count} / {TOTAL_USERS}")
    if user_count != TOTAL_USERS:
        print(f"    [!] Warning: Missing {TOTAL_USERS - user_count} users!")
        return False

    sample_indices = [1, 10, 11, 50, 51, 500, 1000]
    all_ok = True
    
    for idx in sample_indices:
        u = users.get(f"test{idx}")
        if not u:
            print(f"    [!] User test{idx} not found")
            all_ok = False
            continue
        pwd_ok = check_password(PASSWORD, u.password)
        prof_ok = hasattr(u, 'userprofile') and u.userprofile.is_verified
        role = u.userprofile.user_type if hasattr(u, 'userprofile') else None
        print(f"    - test{idx:<4} (Role: {role:<7}) | Password valid: {pwd_ok} | Email verified: {prof_ok}")
        if not (pwd_ok and prof_ok):
            all_ok = False

    class_codes = [f"TESTCLASS{i:02d}" for i in range(1, NUM_CLASSROOMS + 1)]
    classrooms = Classroom.objects.filter(class_code__in=class_codes).prefetch_related('memberships')
    print(f"[*] Test classrooms found: {classrooms.count()} / {NUM_CLASSROOMS}")
    
    for c in classrooms:
        approved_count = c.memberships.filter(status='approved').count()
        meeting = Meeting.objects.filter(classroom=c, status='live').first()
        meet_status = f"Live ({meeting.meeting_code})" if meeting else "None"
        print(f"    - {c.class_code:<12} (Teacher: {c.teacher.username:<8}) | Students: {approved_count}/10 | Meeting: {meet_status}")
        if approved_count != STUDENTS_PER_CLASSROOM:
            all_ok = False

    print("=" * 60)
    if all_ok:
        print("[+] ALL VERIFICATION CHECKS PASSED SUCCESSFULLY!")
    else:
        print("[!] SOME CHECKS FAILED. Please review above output.")
    print("=" * 60)
    return all_ok


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="EduMi Load Testing User & Classroom Provisioner")
    parser.add_argument('--cleanup', action='store_true', help="Delete all test users, classrooms, and fixtures")
    parser.add_argument('--verify', action='store_true', help="Verify test users and fixtures without modifying")
    args = parser.parse_args()

    if args.cleanup:
        cleanup_test_data()
    elif args.verify:
        verify_test_data()
    else:
        create_or_update_users()
        verify_test_data()
