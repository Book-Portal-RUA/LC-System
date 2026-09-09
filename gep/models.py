from django.conf import settings
from django.db import models


class AcademicYear(models.Model):
    """e.g. '2025-2026'"""
    name = models.CharField(max_length=20, unique=True)

    class Meta:
        ordering = ['-name']

    def __str__(self):
        return self.name


class Term(models.Model):
    academic_year = models.ForeignKey(AcademicYear, related_name='terms', on_delete=models.CASCADE)
    name = models.CharField(max_length=50)  # "Term 1" / "Term 2"
    order = models.PositiveSmallIntegerField(default=1)

    class Meta:
        ordering = ['academic_year', 'order']
        unique_together = ('academic_year', 'name')

    def __str__(self):
        return f"{self.name} ({self.academic_year.name})"


class ClassGroup(models.Model):
    name = models.CharField(max_length=100)  # "Level 1"
    room = models.CharField(max_length=50, blank=True)
    term = models.ForeignKey(Term, related_name='classes', on_delete=models.CASCADE)
    book = models.CharField(max_length=150, blank=True)
    subject = models.CharField(max_length=100, default='GEP')
    # Total instructional days for this class this term, used as the fixed
    # denominator for the attendance percentage (see grading.py). Matches the
    # original workbook's behaviour, where the attendance % is calculated
    # against a fixed planned day-count rather than "days recorded so far".
    total_class_days = models.PositiveIntegerField(default=20)

    class Meta:
        ordering = ['term', 'name']

    def __str__(self):
        return f"{self.name} \u2014 {self.term.name} ({self.term.academic_year.name})"


class Teacher(models.Model):
    SEX_CHOICES = [('M', 'Male'), ('F', 'Female')]
    STATUS_CHOICES = [('Active', 'Active'), ('Inactive', 'Inactive')]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='teacher')
    teacher_id = models.CharField(max_length=10, unique=True, editable=False, blank=True)
    english_name = models.CharField(max_length=150)
    khmer_name = models.CharField(max_length=150, blank=True)
    sex = models.CharField(max_length=1, choices=SEX_CHOICES)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    subject = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='Active')

    classes = models.ManyToManyField(ClassGroup, through='TeacherAssignment', related_name='teachers', blank=True)

    class Meta:
        ordering = ['teacher_id']

    def save(self, *args, **kwargs):
        if not self.teacher_id:
            last = Teacher.objects.exclude(teacher_id='').order_by('-teacher_id').first()
            next_num = 1
            if last and last.teacher_id.startswith('TLC'):
                try:
                    next_num = int(last.teacher_id[3:]) + 1
                except ValueError:
                    pass
            self.teacher_id = f"TLC{next_num:03d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.teacher_id} - {self.english_name}"


class TeacherAssignment(models.Model):
    teacher = models.ForeignKey(Teacher, related_name='assignments', on_delete=models.CASCADE)
    class_group = models.ForeignKey(ClassGroup, related_name='teacher_assignments', on_delete=models.CASCADE)

    class Meta:
        unique_together = ('teacher', 'class_group')

    def __str__(self):
        return f"{self.teacher} -> {self.class_group}"


class StudentProfile(models.Model):
    GENDER_CHOICES = [('M', 'Male'), ('F', 'Female')]

    student_code = models.CharField(max_length=10, unique=True, editable=False, blank=True)
    khmer_name = models.CharField(max_length=150, blank=True)
    english_name = models.CharField(max_length=150)
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES)
    date_of_birth = models.DateField(null=True, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)

    class Meta:
        ordering = ['student_code']

    def save(self, *args, **kwargs):
        if not self.student_code:
            last = StudentProfile.objects.exclude(student_code='').order_by('-student_code').first()
            next_num = 1
            if last and last.student_code.isdigit():
                next_num = int(last.student_code) + 1
            self.student_code = f"{next_num:04d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.student_code} - {self.english_name}"


class Enrollment(models.Model):
    """A student's presence in one specific class+term. A student can have a
    different enrollment (or none) in a different term, which is why a
    roster can legitimately differ between Term 1 and Term 2."""

    STATUS_CHOICES = [('Active', 'Active'), ('Inactive', 'Inactive')]

    student = models.ForeignKey(StudentProfile, related_name='enrollments', on_delete=models.CASCADE)
    class_group = models.ForeignKey(ClassGroup, related_name='enrollments', on_delete=models.CASCADE)
    course = models.CharField(max_length=50, default='GEP')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='Active')

    class Meta:
        unique_together = ('student', 'class_group')
        ordering = ['class_group', 'student__student_code']

    def __str__(self):
        return f"{self.student} in {self.class_group}"


class ScoreCategory(models.Model):
    QUIZ = 'Quiz'
    CLASS_PARTICIPATION = 'Class Participation'
    HOMEWORK = 'Homework'
    ASSIGNMENT = 'Assignment'
    NAME_CHOICES = [
        (QUIZ, 'Quiz'),
        (CLASS_PARTICIPATION, 'Class Participation'),
        (HOMEWORK, 'Homework'),
        (ASSIGNMENT, 'Assignment'),
    ]
    name = models.CharField(max_length=30, choices=NAME_CHOICES, unique=True)
    weight_percent = models.DecimalField(max_digits=5, decimal_places=2)

    class Meta:
        verbose_name_plural = 'Score categories'

    def __str__(self):
        return f"{self.name} ({self.weight_percent}%)"


class ScoreItem(models.Model):
    """One gradeable item, e.g. 'Quiz 3' or 'Homework 12', within a class."""

    class_group = models.ForeignKey(ClassGroup, related_name='score_items', on_delete=models.CASCADE)
    category = models.ForeignKey(ScoreCategory, related_name='items', on_delete=models.CASCADE)
    label = models.CharField(max_length=100)
    max_points = models.DecimalField(max_digits=6, decimal_places=2, default=100)
    date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ['category', 'id']

    def __str__(self):
        return f"{self.label} ({self.class_group})"


class Score(models.Model):
    score_item = models.ForeignKey(ScoreItem, related_name='scores', on_delete=models.CASCADE)
    enrollment = models.ForeignKey(Enrollment, related_name='scores', on_delete=models.CASCADE)
    points = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)

    class Meta:
        unique_together = ('score_item', 'enrollment')

    def __str__(self):
        return f"{self.enrollment} - {self.score_item}: {self.points}"


class AttendanceRecord(models.Model):
    PRESENT = 'Present'
    ABSENT = 'Absent'
    TARDY = 'Tardy'
    EXCUSED = 'Excused'
    STATUS_CHOICES = [
        (PRESENT, 'Present'),
        (ABSENT, 'Absent'),
        (TARDY, 'Tardy'),
        (EXCUSED, 'Excused'),
    ]

    enrollment = models.ForeignKey(Enrollment, related_name='attendance_records', on_delete=models.CASCADE)
    date = models.DateField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=PRESENT)

    class Meta:
        unique_together = ('enrollment', 'date')
        ordering = ['date']

    def __str__(self):
        return f"{self.enrollment} - {self.date}: {self.status}"


class ExamResult(models.Model):
    MIDTERM = 'Midterm'
    FINAL = 'Final'
    EXAM_CHOICES = [(MIDTERM, 'Midterm'), (FINAL, 'Final')]

    enrollment = models.ForeignKey(Enrollment, related_name='exam_results', on_delete=models.CASCADE)
    exam_type = models.CharField(max_length=10, choices=EXAM_CHOICES)
    listening = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    speaking = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    reading = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    writing = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    class Meta:
        unique_together = ('enrollment', 'exam_type')

    @property
    def total(self):
        return self.listening + self.speaking + self.reading + self.writing

    @property
    def percent(self):
        return float(self.total) / 120 * 100

    def __str__(self):
        return f"{self.enrollment} - {self.exam_type}"


class CommentBank(models.Model):
    CATEGORY_CHOICES = [(c, c) for c in [
        'Excellent', 'Very Good', 'Good', 'Satisfactory', 'Needs Improvement',
        'Attendance', 'Participation', 'Homework', 'Speaking', 'Reading',
        'Writing', 'Listening', 'Encouragement',
    ]]
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES)
    text = models.TextField()

    class Meta:
        ordering = ['category', 'id']
        verbose_name_plural = 'Comment bank'

    def __str__(self):
        return f"[{self.category}] {self.text[:40]}"


class ReportRemark(models.Model):
    """The free-text teacher comment that actually prints on a student's report card."""

    enrollment = models.ForeignKey(Enrollment, related_name='remarks', on_delete=models.CASCADE)
    term = models.ForeignKey(Term, related_name='remarks', on_delete=models.CASCADE)
    text = models.TextField(blank=True)

    class Meta:
        unique_together = ('enrollment', 'term')

    def __str__(self):
        return f"Remark for {self.enrollment} ({self.term})"
