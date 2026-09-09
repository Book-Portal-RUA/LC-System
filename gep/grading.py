"""
Grading engine for the GEP Student Assessment System.

Score Record, Report Cards, and Final Result are *computed views*, not
stored tables -- everything here is derived on request from Score,
AttendanceRecord and ExamResult rows so grades can never drift out of sync
with what a teacher actually entered.

The formulas below (in particular the attendance penalty weights) were
reverse-engineered from the real numbers in the source workbook so that,
given the same inputs, this engine reproduces the exact same totals, grades
and ranks the spreadsheet produced.
"""
from decimal import Decimal, ROUND_HALF_UP

from .models import AttendanceRecord, ExamResult, Score, ScoreCategory, ScoreItem

# Fixed structural weights (percentage points out of 100). Quiz / Class
# Participation / Homework / Assignment weights live in the ScoreCategory
# table instead, so an Admin can retune them from Django admin without a
# code change.
ATTENDANCE_WEIGHT = Decimal('10')
MIDTERM_WEIGHT = Decimal('30')
FINAL_WEIGHT = Decimal('35')

# Per-day attendance penalty, relative to a fully-present day. An absence
# costs a full day, an excused absence costs half a day, and a tardy costs a
# quarter of a day -- matching the original workbook exactly.
ATTENDANCE_PENALTY = {
    AttendanceRecord.ABSENT: Decimal('1.00'),
    AttendanceRecord.EXCUSED: Decimal('0.50'),
    AttendanceRecord.TARDY: Decimal('0.25'),
    AttendanceRecord.PRESENT: Decimal('0.00'),
}

GRADE_BANDS = [
    (Decimal('97'), 'A+'), (Decimal('93'), 'A'), (Decimal('90'), 'A-'),
    (Decimal('87'), 'B+'), (Decimal('83'), 'B'), (Decimal('80'), 'B-'),
    (Decimal('77'), 'C+'), (Decimal('73'), 'C'), (Decimal('70'), 'C-'),
    (Decimal('67'), 'D+'), (Decimal('63'), 'D'), (Decimal('60'), 'D-'),
    (Decimal('50'), 'F (Make up)'), (Decimal('0'), 'F (Repeat)'),
]

GRADE_LEGEND = [
    ('97 \u2013 100', 'A+'), ('93 \u2013 96', 'A'), ('90 \u2013 92', 'A-'),
    ('87 \u2013 89', 'B+'), ('83 \u2013 86', 'B'), ('80 \u2013 82', 'B-'),
    ('77 \u2013 79', 'C+'), ('73 \u2013 76', 'C'), ('70 \u2013 72', 'C-'),
    ('67 \u2013 69', 'D+'), ('63 \u2013 66', 'D'), ('60 \u2013 62', 'D-'),
    ('50 \u2013 59', 'F (Make up)'), ('\u2264 49', 'F (Repeat)'),
]

PERFORMANCE_LEGEND = [
    ('90 \u2013 100', 'Excellent Performance'),
    ('80 \u2013 89', 'Very Good Performance'),
    ('70 \u2013 79', 'Good Performance'),
    ('60 \u2013 69', 'Fair Performance'),
    ('Below 60', 'Needs Improvement'),
]

Q1 = Decimal('0.1')


def _q(value):
    return Decimal(value).quantize(Q1, rounding=ROUND_HALF_UP)


def letter_grade(total):
    t = Decimal(total)
    for lo, label in GRADE_BANDS:
        if t >= lo:
            return label
    return 'F (Repeat)'


def overall_performance(total):
    t = Decimal(total)
    if t >= 90:
        return 'Excellent Performance'
    if t >= 80:
        return 'Very Good Performance'
    if t >= 70:
        return 'Good Performance'
    if t >= 60:
        return 'Fair Performance'
    return 'Needs Improvement'


def final_result_label(total):
    t = Decimal(total)
    if t >= 60:
        return 'Promotion'
    if t >= 50:
        return 'Make Up'
    return 'Repetition'


def get_category_weight(name, default):
    cat = ScoreCategory.objects.filter(name=name).first()
    return cat.weight_percent if cat else Decimal(default)


def category_percent(enrollment, category_name):
    """Average of (points / max_points * 100) across every scored item in
    this category for this class. Items with no recorded score are excluded
    entirely, rather than counted as zero, so an unfinished gradebook
    doesn't unfairly tank a student's percentage."""
    items = ScoreItem.objects.filter(class_group=enrollment.class_group_id, category__name=category_name)
    scores = Score.objects.filter(score_item__in=items, enrollment=enrollment, points__isnull=False)
    total_pct = Decimal('0')
    count = 0
    for s in scores.select_related('score_item'):
        if s.score_item.max_points:
            total_pct += (s.points / s.score_item.max_points) * 100
            count += 1
    if not count:
        return Decimal('0.0')
    return _q(total_pct / count)


def attendance_breakdown(enrollment):
    """Returns (percent, counts_dict). See module docstring for the formula."""
    total_days = enrollment.class_group.total_class_days or 1
    records = AttendanceRecord.objects.filter(enrollment=enrollment)
    counts = {'present': 0, 'absent': 0, 'tardy': 0, 'excused': 0}
    penalty = Decimal('0')
    for r in records:
        penalty += ATTENDANCE_PENALTY.get(r.status, Decimal('0'))
        key = {
            AttendanceRecord.PRESENT: 'present',
            AttendanceRecord.ABSENT: 'absent',
            AttendanceRecord.TARDY: 'tardy',
            AttendanceRecord.EXCUSED: 'excused',
        }.get(r.status)
        if key:
            counts[key] += 1
    pct = (Decimal(total_days) - penalty) / Decimal(total_days) * 100
    pct = max(Decimal('0'), min(pct, Decimal('100')))
    counts['total_days'] = total_days
    counts['days_recorded'] = records.count()
    return _q(pct), counts


def exam_breakdown(enrollment, exam_type):
    result = ExamResult.objects.filter(enrollment=enrollment, exam_type=exam_type).first()
    if not result:
        return Decimal('0.0'), None
    return _q(result.percent), result


def compute_breakdown(enrollment):
    """Full grading breakdown for a single enrollment (one student, one class/term)."""
    quiz_w = get_category_weight(ScoreCategory.QUIZ, '5')
    cp_w = get_category_weight(ScoreCategory.CLASS_PARTICIPATION, '5')
    hw_w = get_category_weight(ScoreCategory.HOMEWORK, '5')
    asn_w = get_category_weight(ScoreCategory.ASSIGNMENT, '10')

    att_pct, att_counts = attendance_breakdown(enrollment)
    cp_pct = category_percent(enrollment, ScoreCategory.CLASS_PARTICIPATION)
    hw_pct = category_percent(enrollment, ScoreCategory.HOMEWORK)
    quiz_pct = category_percent(enrollment, ScoreCategory.QUIZ)
    asn_pct = category_percent(enrollment, ScoreCategory.ASSIGNMENT)
    mid_pct, mid_result = exam_breakdown(enrollment, ExamResult.MIDTERM)
    fin_pct, fin_result = exam_breakdown(enrollment, ExamResult.FINAL)

    components = [
        {'key': 'attendance', 'label': 'Attendance', 'short': 'ATT', 'weight': ATTENDANCE_WEIGHT, 'percent': att_pct},
        {'key': 'participation', 'label': 'Class Participation', 'short': 'CP', 'weight': cp_w, 'percent': cp_pct},
        {'key': 'homework', 'label': 'Homework', 'short': 'HW', 'weight': hw_w, 'percent': hw_pct},
        {'key': 'quiz', 'label': 'Quiz', 'short': 'Q', 'weight': quiz_w, 'percent': quiz_pct},
        {'key': 'assignment', 'label': 'Assignment', 'short': 'A/P', 'weight': asn_w, 'percent': asn_pct},
        {'key': 'midterm', 'label': 'Midterm', 'short': 'Mid', 'weight': MIDTERM_WEIGHT, 'percent': mid_pct},
        {'key': 'final', 'label': 'Final', 'short': 'Fin', 'weight': FINAL_WEIGHT, 'percent': fin_pct},
    ]
    # Sum full-precision contributions for the Total so per-component display
    # rounding (1 decimal place) can't compound into a visibly wrong total --
    # only the final total is rounded, each component's *displayed* figure
    # is rounded separately and purely cosmetic.
    total_exact = Decimal('0')
    for c in components:
        contribution_exact = c['weight'] * c['percent'] / 100
        total_exact += contribution_exact
        c['contribution'] = _q(contribution_exact)
    total = _q(total_exact)

    return {
        'enrollment': enrollment,
        'components': components,
        'total': total,
        'grade': letter_grade(total),
        'performance': overall_performance(total),
        'final_result': final_result_label(total),
        'attendance_counts': att_counts,
        'midterm': mid_result,
        'final': fin_result,
    }


def compute_class_ranking(class_group, active_only=True):
    """Breakdown for every enrollment in a class, sorted and ranked by Total
    (standard competition ranking: ties share a rank, e.g. 1, 2, 2, 4)."""
    enrollments = class_group.enrollments.select_related('student', 'class_group')
    if active_only:
        enrollments = enrollments.filter(status='Active')
    rows = [compute_breakdown(e) for e in enrollments]
    rows.sort(key=lambda r: (-r['total'], r['enrollment'].student.english_name))

    rank = 0
    last_total = None
    for i, row in enumerate(rows, start=1):
        if row['total'] != last_total:
            rank = i
        row['rank'] = rank
        last_total = row['total']
    return rows
