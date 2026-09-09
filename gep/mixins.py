from functools import wraps

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied

from .models import ClassGroup


class AdminRequiredMixin(UserPassesTestMixin):
    """For class-based views that only Admin (is_superuser) may access."""

    def test_func(self):
        return self.request.user.is_superuser

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return super().handle_no_permission()
        raise PermissionDenied("Only an Admin account can access this page.")


def admin_required(view_func):
    """For function-based views that only Admin (is_superuser) may access."""

    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not request.user.is_superuser:
            raise PermissionDenied("Only an Admin account can access this page.")
        return view_func(request, *args, **kwargs)

    return wrapper


def get_allowed_classes(user):
    """Admin can see every class. A Teacher can only see classes they are
    explicitly assigned to via TeacherAssignment."""
    if user.is_superuser:
        return ClassGroup.objects.all()
    teacher = getattr(user, 'teacher', None)
    if not teacher:
        return ClassGroup.objects.none()
    return teacher.classes.all()


def resolve_current_class(request):
    """Resolves the "current class" for a class-scoped page from (in order):
    an explicit ?class_id=, the session's remembered choice, or simply the
    first class this user is allowed to see. Raises PermissionDenied if a
    Teacher explicitly requests a class_id they are not assigned to -- this
    is what stops a Teacher from viewing another class by guessing an id in
    the URL.
    """
    allowed = get_allowed_classes(request.user)
    class_id = request.GET.get('class_id') or request.session.get('current_class_id')
    cls = None
    if class_id:
        cls = allowed.filter(pk=class_id).first()
        if not cls and not request.user.is_superuser:
            raise PermissionDenied("You are not assigned to this class.")
    if not cls:
        cls = allowed.first()
    if cls:
        request.session['current_class_id'] = cls.pk
    return cls, allowed


def class_scoped(view_func):
    """For function-based views. Populates request.current_class and
    request.allowed_classes before the view runs."""

    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        request.current_class, request.allowed_classes = resolve_current_class(request)
        return view_func(request, *args, **kwargs)

    return wrapper


class ClassScopedViewMixin(LoginRequiredMixin):
    """For class-based views. Same behaviour as @class_scoped."""

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            request.current_class, request.allowed_classes = resolve_current_class(request)
            self.current_class = request.current_class
            self.allowed_classes = request.allowed_classes
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['current_class'] = self.current_class
        ctx['allowed_classes'] = self.allowed_classes
        return ctx
