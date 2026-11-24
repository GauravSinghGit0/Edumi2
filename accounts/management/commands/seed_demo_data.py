"""
accounts/management/commands/seed_demo_data.py
Populates high-fidelity, realistic Indian demonstration data across all modules:
- 3 Admins (Super Admin, Academic Admin, IT Admin)
- 8 Faculty/Teachers with realistic Indian names & departments
- 60 Students with realistic Indian names, enrollment numbers, branches & CGPA
- 10 Academic Courses (Classrooms) with student memberships
- 30 Live & Past Sessions (Meetings) across the last 30 days (including 1 live session now)
- Comprehensive Face-Recognition Attendance Records & Meeting Participants
- Course Assignments & Student Submissions
- 45+ Administrative Audit Trail logs spread across the last 30 days with before/after diffs
- Safe cleanup of test accounts so demo presentations look pristine.
"""
import random
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db import transaction

from accounts.models import UserProfile
from academics.models import Classroom, ClassroomMembership
from meetings.models import Meeting, MeetingParticipant
from attendance.models import AttendanceRecord
from assignments.models import Assignment, AssignmentSubmission
from common.models import AdminRole, AdminAuditTrail

User = get_user_model()


class Command(BaseCommand):
    help = "Seeds comprehensive, realistic demo data (admins, teachers, students, courses, sessions, attendance, audit)."

    def add_arguments(self, parser):
        parser.add_argument(
            '--clean-test-users',
            action='store_true',
            help='Removes transient test accounts (starting with test_ or ending in @example.com).',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("==> Initializing Seed Demo Data for EduMi Presentation..."))

        # 1. Clean transient test accounts if requested
        if options.get('clean_test_users'):
            test_users = User.objects.filter(username__startswith='test_')
            cleaned_cnt = 0
            for tu in test_users:
                if tu.created_classrooms.exists():
                    tu.is_active = False
                    tu.save(update_fields=['is_active'])
                    cleaned_cnt += 1
                else:
                    try:
                        tu.delete()
                        cleaned_cnt += 1
                    except Exception:
                        tu.is_active = False
                        tu.save(update_fields=['is_active'])
                        cleaned_cnt += 1
            self.stdout.write(self.style.WARNING(f"Deactivated / cleaned {cleaned_cnt} transient test users."))

        # 2. Seed Default Admin Roles
        AdminRole.seed_default_roles()
        super_role = AdminRole.objects.filter(name='Super Admin').first()
        academic_role = AdminRole.objects.filter(name='Academic Admin').first()
        it_role = AdminRole.objects.filter(name='IT Admin').first()
        auditor_role = AdminRole.objects.filter(name='Attendance Auditor').first()

        now = timezone.now()

        # 3. Seed 3 Administrators
        admin_specs = [
            {
                'username': 'rajesh.sharma',
                'first_name': 'Rajesh',
                'last_name': 'Sharma',
                'email': 'rajesh.sharma@edumi.internal',
                'role': super_role,
                'is_super': True,
                'dept': 'Institutional Governance',
                'phone': '+91 98201 12345',
            },
            {
                'username': 'priya.patel',
                'first_name': 'Priya',
                'last_name': 'Patel',
                'email': 'priya.patel@edumi.internal',
                'role': academic_role,
                'is_super': False,
                'dept': 'Academic Affairs & Curriculum',
                'phone': '+91 98202 23456',
            },
            {
                'username': 'vikram.singh',
                'first_name': 'Vikram',
                'last_name': 'Singh',
                'email': 'vikram.singh@edumi.internal',
                'role': it_role,
                'is_super': False,
                'dept': 'IT Infrastructure & Security',
                'phone': '+91 98203 34567',
            },
        ]

        admins = []
        for spec in admin_specs:
            u, created = User.objects.get_or_create(
                username=spec['username'],
                defaults={
                    'first_name': spec['first_name'],
                    'last_name': spec['last_name'],
                    'email': spec['email'],
                    'is_staff': True,
                    'is_superuser': spec['is_super'],
                    'is_active': True,
                }
            )
            u.set_password('Demo@1234')
            u.first_name = spec['first_name']
            u.last_name = spec['last_name']
            u.email = spec['email']
            u.is_staff = True
            u.is_superuser = spec['is_super']
            u.is_active = True
            u.save()

            profile, _ = UserProfile.objects.get_or_create(user=u)
            profile.user_type = 'admin'
            profile.admin_role = spec['role']
            profile.department = spec['dept']
            profile.phone = spec['phone']
            profile.is_verified = True
            profile.save()
            admins.append(u)

        self.stdout.write(self.style.SUCCESS(f"Seeded 3 Administrators: {[a.username for a in admins]}"))

        # 4. Seed 8 Teachers (Realistic Indian Faculty)
        teacher_specs = [
            ('amit.verma', 'Dr. Amit', 'Verma', 'amit.verma@edumi.internal', 'Computer Science', 'Distributed Systems & Cloud Computing'),
            ('sunita.rao', 'Prof. Sunita', 'Rao', 'sunita.rao@edumi.internal', 'Computer Science', 'Advanced Data Structures & Algorithms'),
            ('ananya.iyer', 'Dr. Ananya', 'Iyer', 'ananya.iyer@edumi.internal', 'Artificial Intelligence', 'Deep Learning & Neural Architectures'),
            ('rohan.gupta', 'Prof. Rohan', 'Gupta', 'rohan.gupta@edumi.internal', 'Artificial Intelligence', 'Natural Language Processing & LLMs'),
            ('kavita.nair', 'Dr. Kavita', 'Nair', 'kavita.nair@edumi.internal', 'Data Science', 'Big Data Engineering & Database Systems'),
            ('manoj.desai', 'Prof. Manoj', 'Desai', 'manoj.desai@edumi.internal', 'Cybersecurity', 'Network Security & Applied Cryptography'),
            ('meera.reddy', 'Dr. Meera', 'Reddy', 'meera.reddy@edumi.internal', 'Mathematics', 'Linear Algebra & Optimization Techniques'),
            ('suresh.joshi', 'Prof. Suresh', 'Joshi', 'suresh.joshi@edumi.internal', 'Electronics & Comm', 'Embedded Systems & Real-time IoT'),
        ]

        teachers = []
        for uname, fname, lname, email, dept, spec in teacher_specs:
            u, _ = User.objects.get_or_create(
                username=uname,
                defaults={
                    'first_name': fname,
                    'last_name': lname,
                    'email': email,
                    'is_staff': False,
                    'is_superuser': False,
                    'is_active': True,
                }
            )
            u.set_password('Demo@1234')
            u.first_name = fname
            u.last_name = lname
            u.email = email
            u.is_active = True
            u.save()

            profile, _ = UserProfile.objects.get_or_create(user=u)
            profile.user_type = 'teacher'
            profile.department = dept
            profile.specialization = spec
            profile.is_verified = True
            profile.save()
            teachers.append(u)

        self.stdout.write(self.style.SUCCESS(f"Seeded 8 Teachers: {[t.username for t in teachers]}"))

        # 5. Seed 60 Students (Realistic Indian Names)
        indian_names = [
            ("Aarav", "Sharma"), ("Vihaan", "Patel"), ("Aditya", "Verma"), ("Ishaan", "Iyer"),
            ("Sai", "Rao"), ("Reyansh", "Gupta"), ("Diya", "Nair"), ("Ananya", "Desai"),
            ("Aadhya", "Reddy"), ("Saanvi", "Joshi"), ("Pari", "Kumar"), ("Kabir", "Singh"),
            ("Ayaan", "Chatterjee"), ("Krishna", "Kulkarni"), ("Riya", "Mehta"), ("Anika", "Agarwal"),
            ("Advait", "Bansal"), ("Tanvi", "Nambiar"), ("Shaurya", "Pillai"), ("Avni", "Choudhury"),
            ("Atharv", "Bhattacharya"), ("Dhruv", "Mukherjee"), ("Pranav", "Saxena"), ("Navya", "Malhotra"),
            ("Arjun", "Kapoor"), ("Vedant", "Mishra"), ("Yash", "Pandey"), ("Ishani", "Trivedi"),
            ("Aryan", "Bhat"), ("Bhavya", "Hegde"), ("Kian", "Acharya"), ("Myra", "Menon"),
            ("Samar", "Bose"), ("Sanjana", "Dutta"), ("Dev", "Sengupta"), ("Kiara", "Ghosh"),
            ("Neil", "Srivastava"), ("Mira", "Tripathi"), ("Ritvik", "Dubey"), ("Alisha", "Chauhan"),
            ("Rithvik", "Yadav"), ("Sara", "Thakur"), ("Yuvan", "Gowda"), ("Shanaya", "Shetty"),
            ("Harsh", "Patil"), ("Siya", "Shinde"), ("Armaan", "Pawar"), ("Trisha", "Sawant"),
            ("Shivam", "More"), ("Tara", "Kadam"), ("Manan", "Rane"), ("Ira", "Salvi"),
            ("Rehan", "Gokhale"), ("Disha", "Chitnis"), ("Siddharth", "Apte"), ("Mehek", "Gadgil"),
            ("Tejas", "Bapat"), ("Pooja", "Kelkar"), ("Varun", "Puranik"), ("Neha", "Pendse")
        ]

        branches = ['Computer Science', 'Artificial Intelligence', 'Data Science', 'Electronics & Comm']
        students = []
        for i, (fn, ln) in enumerate(indian_names, start=1):
            uname = f"{fn.lower()}.{ln.lower()}{i}"
            email = f"{uname}@student.edumi.internal"
            u, _ = User.objects.get_or_create(
                username=uname,
                defaults={
                    'first_name': fn,
                    'last_name': ln,
                    'email': email,
                    'is_staff': False,
                    'is_superuser': False,
                    'is_active': True,
                    'date_joined': now - timedelta(days=random.randint(15, 60)),
                }
            )
            u.set_password('Demo@1234')
            u.first_name = fn
            u.last_name = ln
            u.email = email
            u.is_active = True
            u.save()

            profile, _ = UserProfile.objects.get_or_create(user=u)
            profile.user_type = 'student'
            profile.student_id = f"STU-2024-{i:03d}"
            profile.branch = branches[(i - 1) % len(branches)]
            profile.grade = "Semester 4" if i % 2 == 0 else "Semester 6"
            profile.cgpa = round(random.uniform(7.4, 9.7), 2)
            profile.is_verified = True
            profile.save()
            students.append(u)

        self.stdout.write(self.style.SUCCESS(f"Seeded 60 Students with enrollment IDs and academic profiles."))

        # 6. Seed 10 Courses (Classrooms)
        course_specs = [
            ("CS101", "Introduction to Computer Science & Python", teachers[0], "Foundations of computational thinking, algorithms, and Python programming."),
            ("CS201", "Data Structures & Algorithmic Analysis", teachers[1], "Advanced data structures, trees, graphs, sorting, and time complexity analysis."),
            ("AI301", "Artificial Intelligence & Neural Architectures", teachers[2], "Supervised learning, deep neural networks, CNNs, and backpropagation models."),
            ("AI402", "Natural Language Processing & Transformers", teachers[3], "Tokenization, word vectors, attention mechanisms, and Transformer architectures."),
            ("DS202", "Database Management Systems & SQL Optimization", teachers[4], "Relational schema design, normalization, ACID properties, and indexing."),
            ("CYB303", "Network Security & Applied Cryptography", teachers[5], "Public-key cryptography, TLS/SSL protocols, intrusion detection, and zero trust."),
            ("MATH104", "Linear Algebra & Discrete Optimization", teachers[6], "Vector spaces, eigenvalues, matrix decompositions, and linear programming."),
            ("EE205", "Digital Electronics & Embedded Microprocessors", teachers[7], "Logic gates, microcontroller architecture, embedded C, and hardware interfaces."),
            ("DS304", "Big Data Analytics & Cloud Architecture", teachers[4], "Distributed computing with Apache Spark, Kafka streaming, and data lakes."),
            ("CS404", "Distributed Cloud Computing & Microservices", teachers[0], "Containerization with Docker, Kubernetes orchestration, and cloud resiliency."),
        ]

        courses = []
        for code, title, teacher, desc in course_specs:
            c, _ = Classroom.objects.get_or_create(
                class_code=code,
                defaults={
                    'title': title,
                    'password': 'CoursePassword123',
                    'teacher': teacher,
                    'description': desc,
                    'auto_approve': True,
                    'is_active': True,
                    'created_at': now - timedelta(days=35),
                }
            )
            c.title = title
            c.teacher = teacher
            c.description = desc
            c.is_active = True
            c.save()
            courses.append(c)

        # Enroll students into courses
        for idx, course in enumerate(courses):
            # Pick 28-36 students for each course
            cohort = students[(idx * 5) % len(students):] + students[:(idx * 5) % len(students)]
            enrolled_slice = cohort[:32]
            for stu in enrolled_slice:
                ClassroomMembership.objects.get_or_create(
                    classroom=course,
                    student=stu,
                    defaults={'status': 'approved', 'approved_at': now - timedelta(days=25)}
                )

            # Add 2 pending enrollment requests for each course so Approvals page is populated
            pending_candidates = cohort[32:34]
            for pstu in pending_candidates:
                mem, _ = ClassroomMembership.objects.get_or_create(
                    classroom=course,
                    student=pstu,
                    defaults={'status': 'pending'}
                )
                mem.status = 'pending'
                mem.save()

        self.stdout.write(self.style.SUCCESS(f"Seeded 10 Courses with student cohorts & pending approval queues."))

        # 7. Seed 30 Sessions (Meetings) across the last 30 days
        # 26 Ended, 1 Live right now, 3 Upcoming
        sessions = []

        # (A) 1 Live Meeting right now
        live_meeting, _ = Meeting.objects.get_or_create(
            meeting_code="LIVE-CS101-01",
            defaults={
                'classroom': courses[0],
                'title': "Live Workshop: Scalable Microservices Architecture",
                'description': "Interactive hands-on session on container orchestration and LiveKit audio/video mesh.",
                'teacher': courses[0].teacher,
                'meeting_type': 'classroom',
                'scheduled_time': now - timedelta(minutes=15),
                'duration_minutes': 60,
                'status': 'live',
                'started_at': now - timedelta(minutes=15),
            }
        )
        live_meeting.status = 'live'
        live_meeting.started_at = now - timedelta(minutes=15)
        live_meeting.save()
        sessions.append(live_meeting)

        # Add active participants to live meeting
        live_enrolled = list(courses[0].get_approved_students()[:16])
        for s in live_enrolled:
            MeetingParticipant.objects.get_or_create(
                meeting=live_meeting,
                user=s,
                defaults={
                    'joined_at': now - timedelta(minutes=random.randint(5, 14)),
                    'is_active': True,
                    'total_duration_seconds': 750,
                }
            )

        # (B) 3 Upcoming Meetings
        upcoming_specs = [
            (courses[1], "Lab Session: Balanced Binary Search Trees", now + timedelta(days=1, hours=2)),
            (courses[2], "Lecture: Convolutional Networks for Vision", now + timedelta(days=2, hours=4)),
            (courses[4], "Seminar: High-throughput Query Indexing", now + timedelta(days=3, hours=1)),
        ]
        for c, m_title, sched_t in upcoming_specs:
            code = f"UP-{c.class_code}-{random.randint(100, 999)}"
            m, _ = Meeting.objects.get_or_create(
                meeting_code=code,
                defaults={
                    'classroom': c,
                    'title': m_title,
                    'description': "Scheduled curriculum session with automated face attendance.",
                    'teacher': c.teacher,
                    'meeting_type': 'classroom',
                    'scheduled_time': sched_t,
                    'duration_minutes': 60,
                    'status': 'scheduled',
                }
            )
            m.status = 'scheduled'
            m.scheduled_time = sched_t
            m.save()
            sessions.append(m)

        # (C) 26 Completed / Past Meetings (Past 28 days)
        for i in range(1, 27):
            course = courses[i % len(courses)]
            days_ago = 28 - i
            sched_time = now - timedelta(days=days_ago, hours=random.randint(1, 6), minutes=random.randint(0, 45))
            duration = random.choice([50, 55, 60])
            code = f"PAST-{course.class_code}-{i:02d}"

            past_m, _ = Meeting.objects.get_or_create(
                meeting_code=code,
                defaults={
                    'classroom': course,
                    'title': f"{course.title}: Session #{i}",
                    'description': f"Comprehensive session covering core syllabus milestones for {course.class_code}.",
                    'teacher': course.teacher,
                    'meeting_type': 'classroom',
                    'scheduled_time': sched_time,
                    'duration_minutes': duration,
                    'status': 'ended',
                    'started_at': sched_time,
                    'ended_at': sched_time + timedelta(minutes=duration),
                }
            )
            past_m.status = 'ended'
            past_m.started_at = sched_time
            past_m.ended_at = sched_time + timedelta(minutes=duration)
            past_m.save()
            sessions.append(past_m)

            # Seed Attendance Records & Participants for past meeting
            enrolled = list(course.get_approved_students())
            for stu in enrolled:
                # 88% attendance rate
                is_present = random.random() < 0.88
                status = 'present' if is_present else random.choice(['absent', 'late'])

                if is_present:
                    join_dt = sched_time + timedelta(minutes=random.randint(0, 5))
                    leave_dt = sched_time + timedelta(minutes=duration - random.randint(0, 3))
                    dur_sec = int((leave_dt - join_dt).total_seconds())

                    MeetingParticipant.objects.get_or_create(
                        meeting=past_m,
                        user=stu,
                        defaults={
                            'joined_at': join_dt,
                            'left_at': leave_dt,
                            'is_active': False,
                            'total_duration_seconds': max(dur_sec, 600),
                        }
                    )

                    AttendanceRecord.objects.get_or_create(
                        student=stu,
                        meeting=past_m,
                        defaults={
                            'classroom': course,
                            'date': sched_time.date(),
                            'status': 'present',
                            'verification_method': 'face_recognition',
                            'face_match_confidence': round(random.uniform(0.88, 0.98), 3),
                            'face_verified_at': join_dt,
                            'marked_present_at': join_dt,
                        }
                    )
                else:
                    AttendanceRecord.objects.get_or_create(
                        student=stu,
                        meeting=past_m,
                        defaults={
                            'classroom': course,
                            'date': sched_time.date(),
                            'status': status,
                            'verification_method': 'face_recognition',
                            'face_match_confidence': 0.0,
                        }
                    )

        self.stdout.write(self.style.SUCCESS(f"Seeded 30 Sessions (1 Live, 3 Upcoming, 26 Past) with verified Attendance."))

        # 8. Seed Course Assignments & Submissions
        for idx, course in enumerate(courses):
            assgn, _ = Assignment.objects.get_or_create(
                classroom=course,
                title=f"{course.class_code}: Practical Project & Lab Milestone",
                defaults={
                    'description': "Implement algorithmic modules and submit verified test runs.",
                    'instructions': "Upload your source files and documentation.",
                    'total_marks': 100,
                    'due_date': now + timedelta(days=random.randint(5, 14)),
                    'status': 'published',
                    'created_by': course.teacher,
                }
            )

            # Submissions from enrolled students
            enrolled = list(course.get_approved_students()[:18])
            for s in enrolled:
                sub, _ = AssignmentSubmission.objects.get_or_create(
                    assignment=assgn,
                    student=s,
                    defaults={
                        'status': 'returned',
                        'marks_obtained': random.randint(72, 98),
                        'feedback': "Well-structured solution with optimal complexity analysis.",
                        'evaluated_at': now - timedelta(days=random.randint(1, 10)),
                        'evaluated_by': course.teacher,
                    }
                )

        self.stdout.write(self.style.SUCCESS(f"Seeded Assignments and Student Submissions for performance metrics."))

        # 9. Seed 45 Realistic AdminAuditTrail Logs across the last 30 days
        audit_templates = [
            (AdminAuditTrail.ACTION_USER_CREATED, 'User', 101, 'Created user @{target}', {'action': 'user_create', 'role': 'student', 'dept': 'Computer Science'}),
            (AdminAuditTrail.ACTION_ROLE_CHANGED, 'UserProfile', 102, 'Assigned role Academic Admin to @priya.patel', {'role': {'before': 'None', 'after': 'Academic Admin'}}),
            (AdminAuditTrail.ACTION_ROLE_CHANGED, 'UserProfile', 103, 'Assigned role IT Admin to @vikram.singh', {'role': {'before': 'None', 'after': 'IT Admin'}}),
            (AdminAuditTrail.ACTION_CLASSROOM_CREATED, 'Classroom', 201, 'Created classroom catalog course CS101', {'title': 'CS101: Intro to CS', 'teacher': 'Dr. Amit Verma'}),
            (AdminAuditTrail.ACTION_ENROLLMENT_APPROVED, 'Classroom', 202, 'Approved course enrollment for @{target}', {'course': 'CS101', 'status': 'approved'}),
            (AdminAuditTrail.ACTION_DATA_EXPORTED, 'Export', 301, 'Exported Attendance Report (CSV)', {'format': 'csv', 'report': 'attendance', 'rows': 240}),
            (AdminAuditTrail.ACTION_DATA_EXPORTED, 'Export', 302, 'Exported User Directory (CSV)', {'format': 'csv', 'count': 71}),
            (AdminAuditTrail.ACTION_SETTINGS_CHANGED, 'SiteSetting', 401, 'Updated Attendance late-join threshold', {'late_join_minutes': {'before': 10, 'after': 15}}),
            (AdminAuditTrail.ACTION_SETTINGS_CHANGED, 'SiteSetting', 402, 'Configured Institutional Branding', {'institution_name': {'before': 'Default', 'after': 'EduMi Institute of Technology'}}),
            (AdminAuditTrail.ACTION_BULK_ACTION, 'BulkImport', 501, 'Bulk imported 24 students via CSV wizard', {'success': 24, 'failed': 0, 'file': 'batch_2024_admissions.csv'}),
            (AdminAuditTrail.ACTION_CLASSROOM_ARCHIVED, 'Classroom', 601, 'Archived semester course CS200-OLD', {'room': 'CS200-OLD', 'reason': 'Curriculum cycle completed'}),
        ]

        for i in range(45):
            act_type, target_t, target_i, label_pat, changes = random.choice(audit_templates)
            adm = random.choice(admins)
            dt = now - timedelta(days=random.randint(0, 29), hours=random.randint(0, 23), minutes=random.randint(0, 59))
            tgt_username = random.choice(students).username if students else 'student'
            label = label_pat.replace('{target}', tgt_username)

            AdminAuditTrail.objects.create(
                timestamp=dt,
                admin_user=adm,
                action_type=act_type,
                target_type=target_t,
                target_id=target_i + i,
                target_label=label,
                ip_address=f"192.168.1.{random.randint(10, 85)}",
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/128.0.0.0 Safari/537.36",
                changes_json=changes
            )

        self.stdout.write(self.style.SUCCESS(f"Seeded 45 AdminAuditTrail records across the last 30 days."))

        self.stdout.write(self.style.SUCCESS(
            "\n=======================================================\n"
            " DEMO DATA SEEDED SUCCESSFULLY FOR PRESENTATION!\n"
            " - 3 Administrators (rajesh.sharma, priya.patel, vikram.singh)\n"
            " - 8 Faculty Teachers across CS, AI, DS, Math, EE, Cyber\n"
            " - 60 Enrolled Students with Indian names & verified metrics\n"
            " - 10 Academic Classrooms with student cohorts & pending queues\n"
            " - 30 Sessions (1 Live now, 3 Upcoming, 26 Past with Attendance)\n"
            " - Assignments & Evaluated Submissions\n"
            " - 45 Audit Trail entries for charts & telemetry feed\n"
            " Default Password for all demo accounts: Demo@1234\n"
            "======================================================="
        ))
