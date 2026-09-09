import csv
from datetime import date
from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView

from .forms import (
    AcademicYearForm, ClassGroupForm, CommentBankForm, EnrollmentForm,
    ScoreItemForm, StudentProfileForm, TeacherForm, TermForm,
)
from .grading import GRADE_LEGEND, PERFORMANCE_LEGEND, compute_breakdown, compute_class_ranking
from .mixins import (
    AdminRequiredMixin, ClassScopedViewMixin, admin_required, class_scoped,
    get_allowed_classes, resolve_current_class,
)
from .models import (
    AcademicYear, AttendanceRecord, ClassGroup, CommentBank, Enrollment,
    ExamResult, ReportRemark, Score, ScoreCategory, ScoreItem, StudentProfile,
    Teacher, TeacherAssignment, Term,
)

CATEGORY_SLUGS = {
    'quiz': ScoreCategory.QUIZ,
    'participation': ScoreCategory.CLASS_PARTICIPATION,
    'homework': ScoreCategory.HOMEWORK,
    'assignment': ScoreCategory.ASSIGNMENT,
}
EXAM_SLUGS = {'midterm': ExamResult.MIDTERM, 'final': ExamResult.FINAL}


def base_template(request):
    return 'gep/_partial_base.html' if getattr(request, 'htmx', False) else 'gep/base.html'


def _decimal_or(raw, fallback, lo=None, hi=None):
    try:
        val = Decimal(str(raw).strip())
    except (InvalidOperation, ValueError, TypeError):
        return fallback
    if lo is not None:
        val = max(val, lo)
    if hi is not None:
        val = min(val, hi)
    return val


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@login_required
def dashboard(request):
    if request.user.is_superuser:
        context = {
            'is_admin': True,
            'class_count': ClassGroup.objects.count(),
            'teacher_count': Teacher.objects.filter(status='Active').count(),
            'student_count': StudentProfile.objects.count(),
            'classes': ClassGroup.objects.select_related('term', 'term__academic_year'),
        }
    else:
        teacher = getattr(request.user, 'teacher', None)
        classes = teacher.classes.select_related('term', 'term__academic_year').all() if teacher else ClassGroup.objects.none()
        context = {'is_admin': False, 'teacher': teacher, 'classes': classes}
    context['base_template'] = base_template(request)
    return render(request, 'gep/dashboard.html', context)


# ---------------------------------------------------------------------------
# Admin: Teachers
# ---------------------------------------------------------------------------

class TeacherListView(AdminRequiredMixin, LoginRequiredMixin, ListView):
    model = Teacher
    template_name = 'gep/teachers_list.html'
    context_object_name = 'teachers'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['base_template'] = base_template(self.request)
        return ctx


class TeacherCreateView(AdminRequiredMixin, LoginRequiredMixin, CreateView):
    model = Teacher
    form_class = TeacherForm
    template_name = 'gep/form_page.html'
    success_url = reverse_lazy('teacher-list')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['form_title'] = 'Add Teacher'
        ctx['cancel_url'] = self.success_url
        ctx['base_template'] = base_template(self.request)
        return ctx

    def form_valid(self, form):
        with transaction.atomic():
            user = User.objects.create_user(
                username=form.cleaned_data['username'],
                email=form.cleaned_data.get('email') or '',
                password=form.cleaned_data['password'],
            )
            teacher = form.save(commit=False)
            teacher.user = user
            teacher.save()
        return redirect(self.success_url)


class TeacherUpdateView(AdminRequiredMixin, LoginRequiredMixin, UpdateView):
    model = Teacher
    form_class = TeacherForm
    template_name = 'gep/form_page.html'
    success_url = reverse_lazy('teacher-list')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['form_title'] = f'Edit {self.object.teacher_id} \u2014 {self.object.english_name}'
        ctx['cancel_url'] = self.success_url
        ctx['base_template'] = base_template(self.request)
        return ctx

    def form_valid(self, form):
        response = super().form_valid(form)
        user = self.object.user
        user.username = form.cleaned_data['username']
        user.email = form.cleaned_data.get('email') or user.email
        if form.cleaned_data.get('password'):
            user.set_password(form.cleaned_data['password'])
        user.save()
        return response


@admin_required
def teacher_toggle_status(request, pk):
    teacher = get_object_or_404(Teacher, pk=pk)
    if request.method == 'POST':
        teacher.status = 'Inactive' if teacher.status == 'Active' else 'Active'
        teacher.save(update_fields=['status'])
    return redirect('teacher-list')


# ---------------------------------------------------------------------------
# Admin: Class Teachers
# ---------------------------------------------------------------------------

@admin_required
def class_teachers(request):
    classes = ClassGroup.objects.select_related('term').all()
    class_id = request.GET.get('class_id') or request.POST.get('class_id')
    current = classes.filter(pk=class_id).first() if class_id else classes.first()

    if request.method == 'POST' and current:
        action = request.POST.get('action')
        teacher = get_object_or_404(Teacher, pk=request.POST.get('teacher_id'))
        if action == 'add':
            TeacherAssignment.objects.get_or_create(teacher=teacher, class_group=current)
        elif action == 'remove':
            TeacherAssignment.objects.filter(teacher=teacher, class_group=current).delete()
        panel_ctx = {
            'current': current,
            'assigned': current.teachers.all(),
            'available': Teacher.objects.filter(status='Active').exclude(pk__in=current.teachers.values('pk')),
        }
        if getattr(request, 'htmx', False):
            return render(request, 'gep/_class_teachers_panel.html', panel_ctx)
        return redirect(f"{reverse('class-teachers')}?class_id={current.pk}")

    context = {
        'classes': classes,
        'current': current,
        'assigned': current.teachers.all() if current else Teacher.objects.none(),
        'available': (Teacher.objects.filter(status='Active').exclude(pk__in=current.teachers.values('pk')))
                     if current else Teacher.objects.none(),
        'base_template': base_template(request),
    }
    return render(request, 'gep/class_teachers.html', context)


# ---------------------------------------------------------------------------
# Admin: Classes / Terms / Academic Years
# ---------------------------------------------------------------------------

class ClassGroupListView(AdminRequiredMixin, LoginRequiredMixin, ListView):
    model = ClassGroup
    template_name = 'gep/classes_list.html'
    context_object_name = 'classes'

    def get_queryset(self):
        return ClassGroup.objects.select_related('term', 'term__academic_year')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['base_template'] = base_template(self.request)
        return ctx


class ClassGroupCreateView(AdminRequiredMixin, LoginRequiredMixin, CreateView):
    model = ClassGroup
    form_class = ClassGroupForm
    template_name = 'gep/form_page.html'
    success_url = reverse_lazy('classgroup-list')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['form_title'] = 'Add Class'
        ctx['cancel_url'] = self.success_url
        ctx['base_template'] = base_template(self.request)
        return ctx


class ClassGroupUpdateView(AdminRequiredMixin, LoginRequiredMixin, UpdateView):
    model = ClassGroup
    form_class = ClassGroupForm
    template_name = 'gep/form_page.html'
    success_url = reverse_lazy('classgroup-list')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['form_title'] = f'Edit {self.object.name}'
        ctx['cancel_url'] = self.success_url
        ctx['base_template'] = base_template(self.request)
        return ctx


class TermListView(AdminRequiredMixin, LoginRequiredMixin, ListView):
    model = Term
    template_name = 'gep/terms_list.html'
    context_object_name = 'terms'

    def get_queryset(self):
        return Term.objects.select_related('academic_year')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['base_template'] = base_template(self.request)
        return ctx


class TermCreateView(AdminRequiredMixin, LoginRequiredMixin, CreateView):
    model = Term
    form_class = TermForm
    template_name = 'gep/form_page.html'
    success_url = reverse_lazy('term-list')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['form_title'] = 'Add Term'
        ctx['cancel_url'] = self.success_url
        ctx['base_template'] = base_template(self.request)
        return ctx


class TermUpdateView(AdminRequiredMixin, LoginRequiredMixin, UpdateView):
    model = Term
    form_class = TermForm
    template_name = 'gep/form_page.html'
    success_url = reverse_lazy('term-list')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['form_title'] = f'Edit {self.object}'
        ctx['cancel_url'] = self.success_url
        ctx['base_template'] = base_template(self.request)
        return ctx


class AcademicYearListView(AdminRequiredMixin, LoginRequiredMixin, ListView):
    model = AcademicYear
    template_name = 'gep/academic_years_list.html'
    context_object_name = 'academic_years'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['base_template'] = base_template(self.request)
        return ctx


class AcademicYearCreateView(AdminRequiredMixin, LoginRequiredMixin, CreateView):
    model = AcademicYear
    form_class = AcademicYearForm
    template_name = 'gep/form_page.html'
    success_url = reverse_lazy('academicyear-list')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['form_title'] = 'Add Academic Year'
        ctx['cancel_url'] = self.success_url
        ctx['base_template'] = base_template(self.request)
        return ctx


class AcademicYearUpdateView(AdminRequiredMixin, LoginRequiredMixin, UpdateView):
    model = AcademicYear
    form_class = AcademicYearForm
    template_name = 'gep/form_page.html'
    success_url = reverse_lazy('academicyear-list')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['form_title'] = f'Edit {self.object.name}'
        ctx['cancel_url'] = self.success_url
        ctx['base_template'] = base_template(self.request)
        return ctx


# ---------------------------------------------------------------------------
# Students (class-scoped roster)
# ---------------------------------------------------------------------------

@class_scoped
def students_list(request):
    cls = request.current_class
    enrollments = Enrollment.objects.none()
    q = request.GET.get('q', '').strip()
    if cls:
        enrollments = Enrollment.objects.filter(class_group=cls).select_related('student')
        if q:
            enrollments = enrollments.filter(
                Q(student__english_name__icontains=q) |
                Q(student__khmer_name__icontains=q) |
                Q(student__student_code__icontains=q)
            )
    context = {
        'current_class': cls,
        'allowed_classes': request.allowed_classes,
        'enrollments': enrollments,
        'q': q,
        'base_template': base_template(request),
    }
    return render(request, 'gep/students_list.html', context)


@login_required
def student_create(request):
    cls, allowed = resolve_current_class(request)
    if not cls:
        raise PermissionDenied('Create a class before adding students.')
    if request.method == 'POST':
        pform = StudentProfileForm(request.POST)
        eform = EnrollmentForm(request.POST)
        if pform.is_valid() and eform.is_valid():
            with transaction.atomic():
                student = pform.save()
                enrollment = eform.save(commit=False)
                enrollment.student = student
                enrollment.class_group = cls
                enrollment.save()
            return redirect(f"{reverse('students')}?class_id={cls.pk}")
    else:
        pform = StudentProfileForm()
        eform = EnrollmentForm(initial={'course': 'GEP', 'status': 'Active'})
    context = {
        'pform': pform, 'eform': eform, 'current_class': cls,
        'form_title': f'Add Student to {cls.name}',
        'cancel_url': f"{reverse('students')}?class_id={cls.pk}",
        'base_template': base_template(request),
    }
    return render(request, 'gep/student_form.html', context)


@login_required
def student_update(request, enrollment_id):
    enrollment = get_object_or_404(Enrollment.objects.select_related('student', 'class_group'), pk=enrollment_id)
    if enrollment.class_group not in get_allowed_classes(request.user):
        raise PermissionDenied
    if request.method == 'POST':
        pform = StudentProfileForm(request.POST, instance=enrollment.student)
        eform = EnrollmentForm(request.POST, instance=enrollment)
        if pform.is_valid() and eform.is_valid():
            pform.save()
            eform.save()
            return redirect(f"{reverse('students')}?class_id={enrollment.class_group_id}")
    else:
        pform = StudentProfileForm(instance=enrollment.student)
        eform = EnrollmentForm(instance=enrollment)
    context = {
        'pform': pform, 'eform': eform, 'current_class': enrollment.class_group,
        'form_title': f'Edit {enrollment.student.english_name}',
        'cancel_url': f"{reverse('students')}?class_id={enrollment.class_group_id}",
        'base_template': base_template(request),
    }
    return render(request, 'gep/student_form.html', context)


@login_required
def student_toggle_status(request, enrollment_id):
    enrollment = get_object_or_404(Enrollment, pk=enrollment_id)
    if enrollment.class_group not in get_allowed_classes(request.user):
        raise PermissionDenied
    if request.method == 'POST':
        enrollment.status = 'Inactive' if enrollment.status == 'Active' else 'Active'
        enrollment.save(update_fields=['status'])
    return redirect(f"{reverse('students')}?class_id={enrollment.class_group_id}")


@login_required
def student_delete(request, enrollment_id):
    """Removes a student from this class's roster (deletes their Enrollment,
    which cascades to their Scores/Attendance/Exam results/Remarks for this
    class only). The StudentProfile itself, and any enrollment the same
    student has in a different class or term, are untouched."""
    enrollment = get_object_or_404(Enrollment, pk=enrollment_id)
    if enrollment.class_group not in get_allowed_classes(request.user):
        raise PermissionDenied
    class_id = enrollment.class_group_id
    if request.method == 'POST':
        enrollment.delete()
    return redirect(f"{reverse('students')}?class_id={class_id}")


# ---------------------------------------------------------------------------
# Score entry grids: Quiz / Class Participation / Homework / Assignment
# ---------------------------------------------------------------------------

@class_scoped
def score_entry(request, category_slug):
    category_name = CATEGORY_SLUGS.get(category_slug)
    if not category_name:
        raise Http404
    category = get_object_or_404(ScoreCategory, name=category_name)
    cls = request.current_class
    items, rows = [], []
    if cls:
        items = list(ScoreItem.objects.filter(class_group=cls, category=category).order_by('id'))
        enrollments = Enrollment.objects.filter(class_group=cls, status='Active').select_related('student')
        scores_map = {
            (s.score_item_id, s.enrollment_id): s
            for s in Score.objects.filter(score_item__in=items, enrollment__in=enrollments)
        }
        for e in enrollments:
            cells = [{'item': it, 'score': scores_map.get((it.id, e.id))} for it in items]
            rows.append({'enrollment': e, 'cells': cells})
    context = {
        'category_slug': category_slug,
        'category': category,
        'items': items,
        'rows': rows,
        'current_class': cls,
        'allowed_classes': request.allowed_classes,
        'item_form': ScoreItemForm(),
        'base_template': base_template(request),
    }
    return render(request, 'gep/score_entry.html', context)


@login_required
def score_item_add(request, category_slug):
    category_name = CATEGORY_SLUGS.get(category_slug)
    if not category_name:
        raise Http404
    cls, allowed = resolve_current_class(request)
    if not cls:
        raise PermissionDenied
    category = get_object_or_404(ScoreCategory, name=category_name)
    if request.method == 'POST':
        form = ScoreItemForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                item = form.save(commit=False)
                item.class_group = cls
                item.category = category
                item.save()
                # Start every currently-enrolled student at 0 for this new
                # item, rather than leaving the column blank until each
                # score is entered by hand.
                enrollments = Enrollment.objects.filter(class_group=cls, status='Active')
                Score.objects.bulk_create(
                    [Score(score_item=item, enrollment=e, points=Decimal('0')) for e in enrollments],
                    ignore_conflicts=True,
                )
    return redirect(f"{reverse('score-entry', args=[category_slug])}?class_id={cls.pk}")


@login_required
def score_cell_save(request, item_id, enrollment_id):
    item = get_object_or_404(ScoreItem, pk=item_id)
    enrollment = get_object_or_404(Enrollment, pk=enrollment_id)
    allowed = get_allowed_classes(request.user)
    if item.class_group_id not in allowed.values_list('pk', flat=True) or enrollment.class_group_id != item.class_group_id:
        raise PermissionDenied
    score, _ = Score.objects.get_or_create(score_item=item, enrollment=enrollment)
    error = False
    if request.method == 'POST':
        raw = request.POST.get('points', '').strip()
        if raw == '':
            score.points = None
        else:
            try:
                value = Decimal(raw)
                if value < 0 or value > item.max_points:
                    error = True
                else:
                    score.points = value
            except (InvalidOperation, ValueError):
                error = True
        if not error:
            score.save()
    return render(request, 'gep/_score_cell.html', {'item': item, 'enrollment': enrollment, 'score': score, 'error': error})


# ---------------------------------------------------------------------------
# Attendance grid
# ---------------------------------------------------------------------------

@class_scoped
def attendance(request):
    cls = request.current_class
    dates, rows = [], []
    if cls:
        dates = list(
            AttendanceRecord.objects.filter(enrollment__class_group=cls)
            .values_list('date', flat=True).distinct().order_by('date')
        )
        enrollments = Enrollment.objects.filter(class_group=cls, status='Active').select_related('student')
        records = {
            (r.enrollment_id, r.date): r
            for r in AttendanceRecord.objects.filter(enrollment__class_group=cls)
        }
        for e in enrollments:
            counts = {'Present': 0, 'Absent': 0, 'Tardy': 0, 'Excused': 0}
            cells = []
            for d in dates:
                rec = records.get((e.id, d))
                if rec:
                    counts[rec.status] += 1
                cells.append({'date': d, 'record': rec, 'enrollment': e})
            penalty = counts['Absent'] * Decimal('1.0') + counts['Excused'] * Decimal('0.5') + counts['Tardy'] * Decimal('0.25')
            total_days = cls.total_class_days or 1
            pct = max(Decimal('0'), (Decimal(total_days) - penalty) / Decimal(total_days) * 100)
            rows.append({'enrollment': e, 'cells': cells, 'counts': counts, 'pct': round(pct, 1)})
    context = {
        'current_class': cls,
        'allowed_classes': request.allowed_classes,
        'dates': dates,
        'rows': rows,
        'today': date.today().isoformat(),
        'base_template': base_template(request),
    }
    return render(request, 'gep/attendance.html', context)


@login_required
def attendance_add_date(request):
    cls, allowed = resolve_current_class(request)
    if not cls:
        raise PermissionDenied
    if request.method == 'POST':
        try:
            d = date.fromisoformat(request.POST.get('date', ''))
        except ValueError:
            d = date.today()
        for e in Enrollment.objects.filter(class_group=cls, status='Active'):
            AttendanceRecord.objects.get_or_create(enrollment=e, date=d, defaults={'status': AttendanceRecord.PRESENT})
    return redirect(f"{reverse('attendance')}?class_id={cls.pk}")


@login_required
def attendance_set(request, enrollment_id, date_str, status):
    enrollment = get_object_or_404(Enrollment, pk=enrollment_id)
    if enrollment.class_group not in get_allowed_classes(request.user):
        raise PermissionDenied
    valid_statuses = dict(AttendanceRecord.STATUS_CHOICES)
    if status not in valid_statuses:
        raise Http404('Unknown attendance status.')
    d = date.fromisoformat(date_str)
    record, _ = AttendanceRecord.objects.get_or_create(enrollment=enrollment, date=d, defaults={'status': status})
    if request.method == 'POST':
        record.status = status
        record.save()
    return render(request, 'gep/_attendance_cell.html', {'enrollment': enrollment, 'date': d, 'record': record})


# ---------------------------------------------------------------------------
# Midterm / Final entry
# ---------------------------------------------------------------------------

@class_scoped
def exam_entry(request, exam_type_slug):
    exam_type = EXAM_SLUGS.get(exam_type_slug)
    if not exam_type:
        raise Http404
    cls = request.current_class
    rows = []
    if cls:
        enrollments = Enrollment.objects.filter(class_group=cls, status='Active').select_related('student')
        results = {r.enrollment_id: r for r in ExamResult.objects.filter(enrollment__in=enrollments, exam_type=exam_type)}
        rows = [{'enrollment': e, 'result': results.get(e.id)} for e in enrollments]
    context = {
        'current_class': cls,
        'allowed_classes': request.allowed_classes,
        'exam_type': exam_type,
        'exam_type_slug': exam_type_slug,
        'rows': rows,
        'base_template': base_template(request),
    }
    return render(request, 'gep/exam_entry.html', context)


@login_required
def exam_save(request, enrollment_id, exam_type_slug):
    exam_type = EXAM_SLUGS.get(exam_type_slug)
    enrollment = get_object_or_404(Enrollment, pk=enrollment_id)
    if not exam_type or enrollment.class_group not in get_allowed_classes(request.user):
        raise PermissionDenied
    result, _ = ExamResult.objects.get_or_create(enrollment=enrollment, exam_type=exam_type)
    if request.method == 'POST':
        for field in ['listening', 'speaking', 'reading', 'writing']:
            setattr(result, field, _decimal_or(request.POST.get(field, ''), Decimal('0'), Decimal('0'), Decimal('30')))
        result.save()
    return render(request, 'gep/_exam_row.html', {'enrollment': enrollment, 'result': result, 'exam_type_slug': exam_type_slug})


# ---------------------------------------------------------------------------
# Score Record / Final Result (computed views)
# ---------------------------------------------------------------------------

@class_scoped
def score_record(request):
    cls = request.current_class
    rows = compute_class_ranking(cls) if cls else []
    context = {
        'current_class': cls,
        'allowed_classes': request.allowed_classes,
        'rows': rows,
        'base_template': base_template(request),
    }
    return render(request, 'gep/score_record.html', context)


@class_scoped
def final_result(request):
    cls = request.current_class
    rows = compute_class_ranking(cls) if cls else []
    context = {
        'current_class': cls,
        'allowed_classes': request.allowed_classes,
        'rows': rows,
        'base_template': base_template(request),
    }
    return render(request, 'gep/final_result.html', context)


@login_required
def final_result_csv(request):
    cls, allowed = resolve_current_class(request)
    if not cls:
        raise Http404
    rows = compute_class_ranking(cls)
    response = HttpResponse(content_type='text/csv')
    safe_name = cls.name.replace(' ', '_')
    response['Content-Disposition'] = f'attachment; filename="FinalResults_{safe_name}.csv"'
    writer = csv.writer(response)
    writer.writerow(['Rank', 'Student Code', 'English Name', 'Khmer Name', 'Sex', 'Total', 'Grade', 'Overall Performance', 'Final Result'])
    for r in rows:
        e = r['enrollment']
        writer.writerow([r['rank'], e.student.student_code, e.student.english_name, e.student.khmer_name,
                          e.student.get_gender_display(), r['total'], r['grade'], r['performance'], r['final_result']])
    return response


@login_required
def final_result_pdf(request):
    cls, allowed = resolve_current_class(request)
    if not cls:
        raise Http404
    rows = compute_class_ranking(cls)
    html_string = render_to_string('gep/final_result_pdf.html', {'class_group': cls, 'rows': rows})
    from weasyprint import HTML
    pdf_bytes = HTML(string=html_string, base_url=request.build_absolute_uri('/')).write_pdf()
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    safe_name = cls.name.replace(' ', '_')
    response['Content-Disposition'] = f'inline; filename="FinalResults_{safe_name}.pdf"'
    return response


# ---------------------------------------------------------------------------
# Report Card
# ---------------------------------------------------------------------------

def _report_card_context(request, enrollment_id):
    enrollment = get_object_or_404(
        Enrollment.objects.select_related('student', 'class_group', 'class_group__term', 'class_group__term__academic_year'),
        pk=enrollment_id,
    )
    if enrollment.class_group not in get_allowed_classes(request.user):
        raise PermissionDenied
    breakdown = compute_breakdown(enrollment)
    remark, _ = ReportRemark.objects.get_or_create(enrollment=enrollment, term=enrollment.class_group.term)
    teachers = enrollment.class_group.teachers.all()
    return enrollment, breakdown, remark, teachers


@login_required
def report_card(request, enrollment_id):
    enrollment, breakdown, remark, teachers = _report_card_context(request, enrollment_id)
    context = {
        'enrollment': enrollment,
        'breakdown': breakdown,
        'remark': remark,
        'teachers': teachers,
        'comment_categories': [c[0] for c in CommentBank.CATEGORY_CHOICES],
        'grade_legend': GRADE_LEGEND,
        'performance_legend': PERFORMANCE_LEGEND,
        'base_template': base_template(request),
    }
    return render(request, 'gep/report_card.html', context)


@login_required
def report_card_pdf(request, enrollment_id):
    enrollment, breakdown, remark, teachers = _report_card_context(request, enrollment_id)
    html_string = render_to_string('gep/report_card_pdf.html', {
        'enrollment': enrollment, 'breakdown': breakdown, 'remark': remark, 'teachers': teachers,
    })
    from weasyprint import HTML
    pdf_bytes = HTML(string=html_string, base_url=request.build_absolute_uri('/')).write_pdf()
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    filename = f"ReportCard_{enrollment.student.student_code}_{enrollment.class_group.term.name}".replace(' ', '_')
    response['Content-Disposition'] = f'inline; filename="{filename}.pdf"'
    return response


@login_required
def report_card_comment_options(request, enrollment_id):
    enrollment = get_object_or_404(Enrollment, pk=enrollment_id)
    if enrollment.class_group not in get_allowed_classes(request.user):
        raise PermissionDenied
    category = request.GET.get('category') or 'Excellent'
    comments = CommentBank.objects.filter(category=category)
    return render(request, 'gep/_comment_options.html', {'comments': comments, 'category': category})


@login_required
def report_card_save_remark(request, enrollment_id):
    enrollment = get_object_or_404(Enrollment, pk=enrollment_id)
    if enrollment.class_group not in get_allowed_classes(request.user):
        raise PermissionDenied
    remark, _ = ReportRemark.objects.get_or_create(enrollment=enrollment, term=enrollment.class_group.term)
    if request.method == 'POST':
        remark.text = request.POST.get('text', '')
        remark.save()
        if getattr(request, 'htmx', False):
            return HttpResponse('<span class="text-success small">Saved.</span>')
    return redirect(reverse('report-card', args=[enrollment.id]))


# ---------------------------------------------------------------------------
# Comment Bank (shared, not class-scoped)
# ---------------------------------------------------------------------------

@login_required
def comment_bank_list(request):
    category = request.GET.get('category', '')
    comments = CommentBank.objects.all()
    if category:
        comments = comments.filter(category=category)
    context = {
        'comments': comments,
        'category': category,
        'categories': [c[0] for c in CommentBank.CATEGORY_CHOICES],
        'base_template': base_template(request),
    }
    return render(request, 'gep/comment_bank_list.html', context)


class CommentBankCreateView(LoginRequiredMixin, CreateView):
    model = CommentBank
    form_class = CommentBankForm
    template_name = 'gep/form_page.html'
    success_url = reverse_lazy('comment-bank')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['form_title'] = 'Add Comment'
        ctx['cancel_url'] = self.success_url
        ctx['base_template'] = base_template(self.request)
        return ctx


class CommentBankUpdateView(LoginRequiredMixin, UpdateView):
    model = CommentBank
    form_class = CommentBankForm
    template_name = 'gep/form_page.html'
    success_url = reverse_lazy('comment-bank')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['form_title'] = 'Edit Comment'
        ctx['cancel_url'] = self.success_url
        ctx['base_template'] = base_template(self.request)
        return ctx


@login_required
def comment_bank_delete(request, pk):
    comment = get_object_or_404(CommentBank, pk=pk)
    if request.method == 'POST':
        comment.delete()
    return redirect('comment-bank')