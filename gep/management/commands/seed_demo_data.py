from datetime import date, timedelta

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction

from gep.models import (
    AcademicYear, AttendanceRecord, ClassGroup, CommentBank, Enrollment,
    ExamResult, ScoreCategory, ScoreItem, Score, StudentProfile, Teacher,
    TeacherAssignment, Term, ReportRemark,
)

# Comment Bank content, transcribed verbatim from the "Comment" sheet of the
# original workbook.
COMMENT_BANK = {
    'Excellent': [
        'Demonstrates outstanding performance throughout the course.',
        'Shows excellent understanding of the lesson objectives.',
        'Participates actively in all classroom activities.',
        'Completes all assignments with excellent quality.',
        'Shows strong confidence in using English.',
        'Demonstrates excellent communication skills.',
        'Is a responsible and hardworking student.',
        'Shows great enthusiasm for learning.',
        'Maintains excellent attendance and punctuality.',
        'Keeps up the excellent work.',
    ],
    'Very Good': [
        'Shows very good progress throughout the course.',
        'Demonstrates a good understanding of the lessons.',
        'Participates actively in class discussions.',
        'Completes assignments on time.',
        'Works well with classmates.',
        'Shows a positive attitude toward learning.',
        'Continues to improve in all language skills.',
        'Demonstrates good communication skills.',
        'Maintains good attendance.',
        'Continue working hard to achieve even greater success.',
    ],
    'Good': [
        'Shows good progress this term.',
        'Demonstrates a satisfactory understanding of the lessons.',
        'Participates well during classroom activities.',
        'Completes most assignments on time.',
        'Shows good learning potential.',
        'Continues to improve gradually.',
        'Should continue practicing English regularly.',
        'Shows a positive attitude toward learning.',
        'Keeps making steady progress.',
        'Keep up the good work.',
    ],
    'Satisfactory': [
        'Demonstrates satisfactory performance.',
        'Shows some progress throughout the course.',
        'Participates when encouraged.',
        'Needs more confidence during classroom activities.',
        'Should review lessons more regularly.',
        'Should practice speaking English more often.',
        'Can achieve better results with consistent effort.',
        'Needs to participate more actively in class.',
        'Should complete assignments more consistently.',
        'Continue practicing to improve overall performance.',
    ],
    'Needs Improvement': [
        'Needs to improve classroom participation.',
        'Should attend class more regularly.',
        'Should complete homework more consistently.',
        'Needs additional practice in English communication.',
        'Should pay closer attention during lessons.',
        'Requires more effort to improve academic performance.',
        'Should review lesson materials regularly.',
        'Needs to develop greater confidence in speaking English.',
        'Attendance should be improved.',
        'More consistent effort is needed for better results.',
    ],
    'Attendance': [
        'Shows excellent attendance throughout the course.',
        'Maintains very good attendance.',
        'Maintains good attendance.',
        'Attendance is satisfactory.',
        'Attendance should be improved.',
        'Frequent absences have affected learning progress.',
        'Regular attendance is encouraged.',
        'Punctuality should be improved.',
        'Attendance has impacted academic performance.',
        'Excellent punctuality throughout the course.',
    ],
    'Participation': [
        'Participates actively in every lesson.',
        'Participates confidently during classroom activities.',
        'Works well in pair and group activities.',
        'Contributes positively during discussions.',
        'Shows enthusiasm for learning.',
        'Participates when encouraged.',
        'Needs to participate more actively.',
        'Should contribute more during class discussions.',
        'Shows good teamwork skills.',
        'Demonstrates leadership during group activities.',
    ],
    'Homework': [
        'Always completes homework on time.',
        'Homework is completed consistently.',
        'Completes homework with good quality.',
        'Usually completes homework on time.',
        'Homework should be completed more consistently.',
        'Homework is occasionally incomplete.',
        'Homework is often incomplete.',
        'Should spend more time on homework.',
        'Needs to improve assignment completion.',
        'Shows responsibility in completing assignments.',
    ],
    'Speaking': [
        'Demonstrates excellent speaking skills.',
        'Speaks English confidently.',
        'Communicates clearly and effectively.',
        'Shows good pronunciation.',
        'Shows improvement in speaking skills.',
        'Should practice speaking more frequently.',
        'Needs to improve pronunciation.',
        'Should build greater confidence when speaking.',
        'Additional speaking practice is recommended.',
        'Continues to improve oral communication skills.',
    ],
    'Reading': [
        'Demonstrates strong reading comprehension skills.',
        'Reads confidently and accurately.',
        'Shows good understanding of written texts.',
        'Continues to improve reading fluency.',
        'Should practice reading more regularly.',
        'Needs to improve reading comprehension.',
        'Additional reading practice is recommended.',
        'Shows steady improvement in reading skills.',
        'Reads with increasing confidence.',
        'Should read English materials outside the classroom.',
    ],
    'Writing': [
        'Demonstrates excellent writing skills.',
        'Writes clearly and accurately.',
        'Produces well-organized written work.',
        'Shows good grammar and vocabulary usage.',
        'Continues to improve writing skills.',
        'Should review grammar more carefully.',
        'Needs additional writing practice.',
        'Should expand vocabulary usage in writing.',
        'Shows gradual improvement in written communication.',
        'Writing skills will improve with regular practice.',
    ],
    'Listening': [
        'Demonstrates excellent listening comprehension skills.',
        'Shows excellent understanding during listening activities.',
        'Listens attentively and responds appropriately.',
        'Shows good listening comprehension.',
        'Understands most spoken English with confidence.',
        'Continues to improve listening skills.',
        'Shows steady improvement in listening comprehension.',
        'Can understand the main ideas of spoken English.',
        'Should practice listening to English more frequently.',
        'Needs additional practice to improve listening comprehension.',
        'Has difficulty understanding spoken English at times.',
        'Should pay closer attention during listening activities.',
        'Should practice listening to English outside the classroom.',
        'Listening skills are developing steadily.',
        'Continues to build confidence in listening activities.',
        'Additional listening practice is recommended.',
    ],
    'Encouragement': [
        'Keep up the excellent work!',
        'Continue working hard toward your goals.',
        'Keep practicing English every day.',
        'Success comes through consistent effort.',
        'Continue building your confidence.',
        'Every lesson is an opportunity to improve.',
        'Never stop learning and growing.',
        'Your effort is appreciated.',
        'Wishing you continued success in your studies.',
        'Keep striving for excellence.',
    ],
}

# Real Term 1 / Level 1 roster + scores, transcribed from the source workbook
# so a fresh install reproduces the same computed grades the school already
# knows -- an easy way to double check this rebuild's grading logic.
STUDENTS = [
    {
        'code': '0001', 'english_name': 'Kim Lihour', 'khmer_name': 'គីម លីហួ',
        'gender': 'M', 'dob': '2002-02-12', 'phone': '011 220033', 'email': 'k.lihour.99@gmail.com',
        'quiz': [100, 100, 100, 100, 100], 'cp': [100, 100],
        'hw': [100, 100, 100, 100, 100, 100, 100, 100, 100, 100, 100],
        'assignment': [100, 100, 100], 'attendance': ['Present', 'Present'],
        'midterm': [30, 30, 30, 30], 'final': [30, 30, 30, 30],
    },
    {
        'code': '0002', 'english_name': 'Kong Seila', 'khmer_name': 'គង សីលា',
        'gender': 'F', 'dob': '2009-02-11', 'phone': '011 889922', 'email': 'kong.seila1@gmail.com',
        'quiz': [82, 82, 90, 80, 75], 'cp': [75, 75],
        'hw': [80, 100, 100, 80, 100, 100, 90, 60, 80, 80, 90],
        'assignment': [70, 54, 56], 'attendance': ['Excused', 'Absent'],
        'midterm': [15, 17, 16, 15], 'final': [15, 17, 16, 15],
        'remark': ('Shows some progress throughout the course. Should practice reading more '
                   'regularly. Listening skills are developing steadily.'),
    },
    {
        'code': '0003', 'english_name': 'Koe Pheara', 'khmer_name': 'កែវ ភារ៉ា',
        'gender': 'M', 'dob': '2008-09-03', 'phone': '012 998 778', 'email': 'k.phra@gmial.com',
        'quiz': [0, 78, 0, 80, 70], 'cp': [70, 65],
        'hw': [0, 75, 80, 53, 100, 60, 70, 50, 80, 60, 70],
        'assignment': [20, 30, 55], 'attendance': ['Present', 'Tardy'],
        'midterm': [6, 12, 18, 6], 'final': [21, 13, 18, 6],
    },
    {
        'code': '0005', 'english_name': 'Jet Chanda', 'khmer_name': 'ចិត ចន្តា',
        'gender': 'F', 'dob': '2005-01-04', 'phone': '099 998 889', 'email': 'J.Chd.1@gmail.com',
        'quiz': [73, 64, 71, 60, 70], 'cp': [70, 65],
        'hw': [100, 75, 100, 60, 75, 60, 90, 90, 60, 70, 90],
        'assignment': [50, 100, 100], 'attendance': ['Present', 'Excused'],
        'midterm': [11, 12, 18, 10], 'final': [11, 12, 18, 10],
    },
]


def recent_weekdays(n):
    """Returns the n most recent weekdays up to and including today, oldest first."""
    days = []
    d = date.today()
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d)
        d -= timedelta(days=1)
    return list(reversed(days))


class Command(BaseCommand):
    help = 'Seed demo data for the GEP Student Assessment System (admin, a teacher, one class, 4 students, scores, and the full Comment Bank).'

    def handle(self, *args, **options):
        with transaction.atomic():
            self.seed_users()
            class_group = self.seed_academic_structure()
            self.seed_students_and_scores(class_group)
            self.seed_comment_bank()
        self.stdout.write(self.style.SUCCESS('\nDemo data ready. Log in with:'))
        self.stdout.write('  Admin:   username=admin         password=admin12345')
        self.stdout.write('  Teacher: username=tom.peterson  password=teacher12345')

    def seed_users(self):
        if not User.objects.filter(username='admin').exists():
            User.objects.create_superuser('admin', 'admin@example.com', 'admin12345')
            self.stdout.write('Created admin user.')
        else:
            self.stdout.write('Admin user already exists, skipping.')

        if not Teacher.objects.filter(user__username='tom.peterson').exists():
            user, _ = User.objects.get_or_create(username='tom.peterson', defaults={'email': 'tom.peterson@example.com'})
            user.set_password('teacher12345')
            user.save()
            Teacher.objects.create(
                user=user, english_name='Tom Peterson', khmer_name='',
                sex='M', email='tom.peterson@example.com', phone='099 090 001',
                subject='GEP', status='Active',
            )
            self.stdout.write('Created teacher tom.peterson.')
        else:
            self.stdout.write('Teacher tom.peterson already exists, skipping.')

    def seed_academic_structure(self):
        year, _ = AcademicYear.objects.get_or_create(name='2025-2026')
        term1, _ = Term.objects.get_or_create(academic_year=year, name='Term 1', defaults={'order': 1})
        Term.objects.get_or_create(academic_year=year, name='Term 2', defaults={'order': 2})

        class_group, _ = ClassGroup.objects.get_or_create(
            name='Level 1', term=term1,
            defaults={'room': 'U4', 'book': 'English File Beginner', 'subject': 'GEP', 'total_class_days': 10},
        )

        teacher = Teacher.objects.filter(user__username='tom.peterson').first()
        if teacher:
            TeacherAssignment.objects.get_or_create(teacher=teacher, class_group=class_group)

        for name, weight in [
            (ScoreCategory.QUIZ, 5), (ScoreCategory.CLASS_PARTICIPATION, 5),
            (ScoreCategory.HOMEWORK, 5), (ScoreCategory.ASSIGNMENT, 10),
        ]:
            ScoreCategory.objects.get_or_create(name=name, defaults={'weight_percent': weight})

        return class_group

    def seed_students_and_scores(self, class_group):
        quiz_cat = ScoreCategory.objects.get(name=ScoreCategory.QUIZ)
        cp_cat = ScoreCategory.objects.get(name=ScoreCategory.CLASS_PARTICIPATION)
        hw_cat = ScoreCategory.objects.get(name=ScoreCategory.HOMEWORK)
        asn_cat = ScoreCategory.objects.get(name=ScoreCategory.ASSIGNMENT)
        att_dates = recent_weekdays(2)

        item_cache = {}

        def get_item(category, label, max_points=100):
            key = (category.id, label)
            if key not in item_cache:
                item_cache[key] = ScoreItem.objects.get_or_create(
                    class_group=class_group, category=category, label=label,
                    defaults={'max_points': max_points},
                )[0]
            return item_cache[key]

        if StudentProfile.objects.filter(student_code__in=[s['code'] for s in STUDENTS]).exists():
            self.stdout.write('Demo students already exist, skipping student/score seeding.')
            return

        for s in STUDENTS:
            profile = StudentProfile.objects.create(
                student_code=s['code'], english_name=s['english_name'], khmer_name=s['khmer_name'],
                gender=s['gender'], date_of_birth=s['dob'], phone=s['phone'], email=s['email'],
            )
            enrollment = Enrollment.objects.create(student=profile, class_group=class_group, course='GEP', status='Active')

            for i, points in enumerate(s['quiz'], start=1):
                item = get_item(quiz_cat, f'Quiz {i}')
                Score.objects.create(score_item=item, enrollment=enrollment, points=points)
            for i, points in enumerate(s['cp'], start=1):
                item = get_item(cp_cat, str(i))
                Score.objects.create(score_item=item, enrollment=enrollment, points=points)
            for i, points in enumerate(s['hw'], start=1):
                item = get_item(hw_cat, f'Homework {i}')
                Score.objects.create(score_item=item, enrollment=enrollment, points=points)
            for i, points in enumerate(s['assignment'], start=1):
                item = get_item(asn_cat, f'A{i}')
                Score.objects.create(score_item=item, enrollment=enrollment, points=points)

            for att_date, status in zip(att_dates, s['attendance']):
                AttendanceRecord.objects.create(enrollment=enrollment, date=att_date, status=status)

            l, sp, r, w = s['midterm']
            ExamResult.objects.create(enrollment=enrollment, exam_type=ExamResult.MIDTERM,
                                       listening=l, speaking=sp, reading=r, writing=w)
            l, sp, r, w = s['final']
            ExamResult.objects.create(enrollment=enrollment, exam_type=ExamResult.FINAL,
                                       listening=l, speaking=sp, reading=r, writing=w)

            if s.get('remark'):
                ReportRemark.objects.create(enrollment=enrollment, term=class_group.term, text=s['remark'])

        self.stdout.write(f'Seeded {len(STUDENTS)} students with quiz/CP/homework/assignment/attendance/exam scores.')

    def seed_comment_bank(self):
        if CommentBank.objects.exists():
            self.stdout.write('Comment bank already has entries, skipping.')
            return
        created = 0
        for category, texts in COMMENT_BANK.items():
            for text in texts:
                CommentBank.objects.create(category=category, text=text)
                created += 1
        self.stdout.write(f'Seeded {created} comment bank entries.')
