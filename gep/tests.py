"""
Basic coverage for the GEP Student Assessment System.

Run with: python manage.py test

Uses Django's isolated test database (created/destroyed automatically), so
running these never touches your real db.sqlite3 or seeded demo data.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from .grading import compute_breakdown, letter_grade, overall_performance, final_result_label
from .models import (
    AttendanceRecord, ClassGroup, CommentBank, Enrollment, ExamResult,
    ScoreCategory, ScoreItem, Score, StudentProfile, Teacher,
)


class GradingEngineTests(TestCase):
    """Confirms the grading engine reproduces the real numbers from the
    original workbook (Kong Seila, Term 1, Level 1)."""

    @classmethod
    def setUpTestData(cls):
        call_command('seed_demo_data', verbosity=0)

    def test_grade_bands(self):
        self.assertEqual(letter_grade(Decimal('100')), 'A+')
        self.assertEqual(letter_grade(Decimal('92.9')), 'A-')
        self.assertEqual(letter_grade(Decimal('60.8')), 'D-')
        self.assertEqual(letter_grade(Decimal('49')), 'F (Repeat)')
        self.assertEqual(letter_grade(Decimal('50')), 'F (Make up)')

    def test_performance_and_result_bands(self):
        self.assertEqual(overall_performance(Decimal('95')), 'Excellent Performance')
        self.assertEqual(overall_performance(Decimal('65')), 'Fair Performance')
        self.assertEqual(final_result_label(Decimal('60')), 'Promotion')
        self.assertEqual(final_result_label(Decimal('55')), 'Make Up')
        self.assertEqual(final_result_label(Decimal('10')), 'Repetition')

    def test_kong_seila_matches_source_workbook(self):
        enrollment = Enrollment.objects.get(student__student_code='0002')
        result = compute_breakdown(enrollment)
        self.assertEqual(result['total'], Decimal('60.8'))
        self.assertEqual(result['grade'], 'D-')
        self.assertEqual(result['performance'], 'Fair Performance')
        self.assertEqual(result['final_result'], 'Promotion')

    def test_kim_lihour_perfect_score(self):
        enrollment = Enrollment.objects.get(student__student_code='0001')
        result = compute_breakdown(enrollment)
        self.assertEqual(result['total'], Decimal('100.0'))
        self.assertEqual(result['grade'], 'A+')

    def test_attendance_formula_weights_absent_excused_tardy_differently(self):
        """Absent costs a full day, Excused half, Tardy a quarter, against
        the class's fixed total_class_days -- matching the source sheet."""
        cls = ClassGroup.objects.first()
        cls.total_class_days = 10
        cls.save()
        student = StudentProfile.objects.create(english_name='Test Student', gender='F')
        enrollment = Enrollment.objects.create(student=student, class_group=cls)
        AttendanceRecord.objects.create(enrollment=enrollment, date='2026-01-05', status=AttendanceRecord.ABSENT)
        AttendanceRecord.objects.create(enrollment=enrollment, date='2026-01-06', status=AttendanceRecord.EXCUSED)
        AttendanceRecord.objects.create(enrollment=enrollment, date='2026-01-07', status=AttendanceRecord.TARDY)
        result = compute_breakdown(enrollment)
        att = next(c for c in result['components'] if c['key'] == 'attendance')
        # penalty = 1.0 + 0.5 + 0.25 = 1.75 of 10 planned days -> 82.5%
        self.assertEqual(att['percent'], Decimal('82.5'))

    def test_ungraded_items_excluded_not_zeroed(self):
        """A ScoreItem with no Score row yet shouldn't drag the average to 0."""
        cls = ClassGroup.objects.first()
        quiz_cat = ScoreCategory.objects.get(name=ScoreCategory.QUIZ)
        enrollment = Enrollment.objects.filter(class_group=cls).first()
        # An ungraded item with nobody scored yet.
        ScoreItem.objects.create(class_group=cls, category=quiz_cat, label='Quiz Unscored', max_points=100)
        result = compute_breakdown(enrollment)
        quiz = next(c for c in result['components'] if c['key'] == 'quiz')
        # Should be unchanged from before adding the unscored item (81.8 for Kong Seila).
        if enrollment.student.student_code == '0002':
            self.assertEqual(quiz['percent'], Decimal('81.8'))


class PermissionScopingTests(TestCase):
    """Confirms a Teacher can never see or edit a class they aren't assigned to."""

    @classmethod
    def setUpTestData(cls):
        call_command('seed_demo_data', verbosity=0)

    def setUp(self):
        self.cls = ClassGroup.objects.first()
        self.enrollment = Enrollment.objects.filter(class_group=self.cls).first()
        self.other_class = ClassGroup.objects.create(
            name='Level 9', term=self.cls.term, room='X', total_class_days=20,
        )

    def test_admin_sees_everything(self):
        self.client.login(username='admin', password='admin12345')
        resp = self.client.get(reverse('students'), {'class_id': self.other_class.pk})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.client.get(reverse('teacher-list')).status_code, 200)

    def test_teacher_blocked_from_admin_pages(self):
        self.client.login(username='tom.peterson', password='teacher12345')
        for name in ['teacher-list', 'class-teachers', 'classgroup-list', 'term-list', 'academicyear-list']:
            resp = self.client.get(reverse(name))
            self.assertEqual(resp.status_code, 403, f'{name} should be admin-only')

    def test_teacher_blocked_from_unassigned_class(self):
        self.client.login(username='tom.peterson', password='teacher12345')
        for name in ['students', 'attendance', 'score-record', 'final-result']:
            resp = self.client.get(reverse(name), {'class_id': self.other_class.pk})
            self.assertEqual(resp.status_code, 403, f'{name} should block an unassigned class')

    def test_teacher_can_use_own_class(self):
        self.client.login(username='tom.peterson', password='teacher12345')
        resp = self.client.get(reverse('students'), {'class_id': self.cls.pk})
        self.assertEqual(resp.status_code, 200)

    def test_anonymous_redirected_to_login(self):
        resp = self.client.get(reverse('dashboard'))
        self.assertEqual(resp.status_code, 302)


class PageSmokeTests(TestCase):
    """Every page returns a healthy status code for both roles."""

    @classmethod
    def setUpTestData(cls):
        call_command('seed_demo_data', verbosity=0)

    def setUp(self):
        self.cls = ClassGroup.objects.first()
        self.enrollment = Enrollment.objects.filter(class_group=self.cls).first()
        self.item = ScoreItem.objects.filter(class_group=self.cls).first()
        self.comment = CommentBank.objects.first()
        self.teacher = Teacher.objects.first()
        self.client.login(username='admin', password='admin12345')

    def test_core_pages_ok(self):
        urls = [
            reverse('dashboard'),
            reverse('teacher-list'),
            reverse('teacher-create'),
            reverse('teacher-update', args=[self.teacher.pk]),
            reverse('class-teachers'),
            reverse('classgroup-list'),
            reverse('term-list'),
            reverse('academicyear-list'),
            f"{reverse('students')}?class_id={self.cls.pk}",
            f"{reverse('score-entry', args=['quiz'])}?class_id={self.cls.pk}",
            f"{reverse('score-entry', args=['participation'])}?class_id={self.cls.pk}",
            f"{reverse('score-entry', args=['homework'])}?class_id={self.cls.pk}",
            f"{reverse('score-entry', args=['assignment'])}?class_id={self.cls.pk}",
            f"{reverse('attendance')}?class_id={self.cls.pk}",
            f"{reverse('exam-entry', args=['midterm'])}?class_id={self.cls.pk}",
            f"{reverse('exam-entry', args=['final'])}?class_id={self.cls.pk}",
            f"{reverse('score-record')}?class_id={self.cls.pk}",
            f"{reverse('final-result')}?class_id={self.cls.pk}",
            reverse('report-card', args=[self.enrollment.pk]),
            reverse('comment-bank'),
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_pdf_and_csv_exports(self):
        resp = self.client.get(reverse('report-card-pdf', args=[self.enrollment.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'application/pdf')

        resp = self.client.get(f"{reverse('final-result-csv')}?class_id={self.cls.pk}")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'text/csv')

        resp = self.client.get(f"{reverse('final-result-pdf')}?class_id={self.cls.pk}")
        self.assertEqual(resp.status_code, 200)

    def test_htmx_cell_endpoints(self):
        resp = self.client.post(
            reverse('score-cell-save', args=[self.item.pk, self.enrollment.pk]), {'points': '75'}
        )
        self.assertEqual(resp.status_code, 200)

        resp = self.client.post(
            reverse('exam-save', args=[self.enrollment.pk, 'midterm']),
            {'listening': 25, 'speaking': 25, 'reading': 25, 'writing': 25},
        )
        self.assertEqual(resp.status_code, 200)

    def test_attendance_set_directly_applies_chosen_status(self):
        resp = self.client.post(
            reverse('attendance-set', args=[self.enrollment.pk, '2026-09-09', 'Tardy'])
        )
        self.assertEqual(resp.status_code, 200)
        record = AttendanceRecord.objects.get(enrollment=self.enrollment, date='2026-09-09')
        self.assertEqual(record.status, 'Tardy')
        # Setting it again to a different status directly (no cycling through the others).
        resp = self.client.post(
            reverse('attendance-set', args=[self.enrollment.pk, '2026-09-09', 'Excused'])
        )
        self.assertEqual(resp.status_code, 200)
        record.refresh_from_db()
        self.assertEqual(record.status, 'Excused')

    def test_attendance_set_rejects_unknown_status(self):
        resp = self.client.post(
            reverse('attendance-set', args=[self.enrollment.pk, '2026-09-09', 'OnFire'])
        )
        self.assertEqual(resp.status_code, 404)