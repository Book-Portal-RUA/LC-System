from django import forms
from django.contrib.auth.models import User

from .models import (
    AcademicYear, ClassGroup, CommentBank, Enrollment, ScoreItem,
    StudentProfile, Teacher, Term,
)


class BootstrapFormMixin:
    """Adds Bootstrap 5 classes to every field's widget automatically, so
    individual ModelForms don't need to repeat widget attrs field by field."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                css = 'form-check-input'
            elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
                css = 'form-select'
            else:
                css = 'form-control'
            existing = widget.attrs.get('class', '')
            widget.attrs['class'] = f'{existing} {css}'.strip()


class BootstrapModelForm(BootstrapFormMixin, forms.ModelForm):
    pass


class TeacherForm(BootstrapModelForm):
    username = forms.CharField(max_length=150, label='Username')
    password = forms.CharField(max_length=128, required=False, widget=forms.PasswordInput, label='Password')

    class Meta:
        model = Teacher
        fields = ['english_name', 'khmer_name', 'sex', 'email', 'phone', 'subject', 'status']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Field order: login fields first, then profile fields.
        self.order_fields(['username', 'password', 'english_name', 'khmer_name',
                            'sex', 'email', 'phone', 'subject', 'status'])
        if self.instance and self.instance.pk:
            self.fields['username'].initial = self.instance.user.username
            self.fields['password'].help_text = 'Leave blank to keep the current password.'
        else:
            self.fields['password'].required = True
            self.fields['password'].help_text = "Set this teacher's initial login password."

    def clean_username(self):
        username = self.cleaned_data['username']
        qs = User.objects.filter(username=username)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.user_id)
        if qs.exists():
            raise forms.ValidationError('This username is already taken.')
        return username


class ClassGroupForm(BootstrapModelForm):
    class Meta:
        model = ClassGroup
        fields = ['name', 'room', 'term', 'book', 'subject', 'total_class_days']
        help_texts = {
            'total_class_days': 'Planned instructional days this term, used to calculate attendance %.',
        }


class TermForm(BootstrapModelForm):
    class Meta:
        model = Term
        fields = ['academic_year', 'name', 'order']


class AcademicYearForm(BootstrapModelForm):
    class Meta:
        model = AcademicYear
        fields = ['name']
        help_texts = {'name': 'e.g. 2025-2026'}


class StudentProfileForm(BootstrapModelForm):
    class Meta:
        model = StudentProfile
        fields = ['english_name', 'khmer_name', 'gender', 'date_of_birth', 'phone', 'email']
        widgets = {'date_of_birth': forms.DateInput(attrs={'type': 'date'})}


class EnrollmentForm(BootstrapModelForm):
    class Meta:
        model = Enrollment
        fields = ['course', 'status']


class ScoreItemForm(BootstrapModelForm):
    class Meta:
        model = ScoreItem
        fields = ['label', 'max_points', 'date']
        widgets = {'date': forms.DateInput(attrs={'type': 'date'})}


class CommentBankForm(BootstrapModelForm):
    class Meta:
        model = CommentBank
        fields = ['category', 'text']
        widgets = {'text': forms.Textarea(attrs={'rows': 3})}
