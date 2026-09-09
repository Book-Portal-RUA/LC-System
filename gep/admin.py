from django.contrib import admin

from .models import (
    AcademicYear, AttendanceRecord, ClassGroup, CommentBank, Enrollment,
    ExamResult, ReportRemark, Score, ScoreCategory, ScoreItem, StudentProfile,
    Teacher, TeacherAssignment, Term,
)


@admin.register(AcademicYear)
class AcademicYearAdmin(admin.ModelAdmin):
    list_display = ['name']


@admin.register(Term)
class TermAdmin(admin.ModelAdmin):
    list_display = ['name', 'academic_year', 'order']
    list_filter = ['academic_year']


@admin.register(ClassGroup)
class ClassGroupAdmin(admin.ModelAdmin):
    list_display = ['name', 'term', 'room', 'book', 'total_class_days']
    list_filter = ['term']
    search_fields = ['name', 'room']


@admin.register(Teacher)
class TeacherAdmin(admin.ModelAdmin):
    list_display = ['teacher_id', 'english_name', 'khmer_name', 'subject', 'status']
    list_filter = ['status', 'subject']
    search_fields = ['teacher_id', 'english_name', 'khmer_name']


@admin.register(TeacherAssignment)
class TeacherAssignmentAdmin(admin.ModelAdmin):
    list_display = ['teacher', 'class_group']
    list_filter = ['class_group']


@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = ['student_code', 'english_name', 'khmer_name', 'gender', 'date_of_birth']
    search_fields = ['student_code', 'english_name', 'khmer_name']


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ['student', 'class_group', 'course', 'status']
    list_filter = ['class_group', 'status']
    search_fields = ['student__english_name', 'student__student_code']


@admin.register(ScoreCategory)
class ScoreCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'weight_percent']


@admin.register(ScoreItem)
class ScoreItemAdmin(admin.ModelAdmin):
    list_display = ['label', 'class_group', 'category', 'max_points', 'date']
    list_filter = ['class_group', 'category']


@admin.register(Score)
class ScoreAdmin(admin.ModelAdmin):
    list_display = ['enrollment', 'score_item', 'points']
    list_filter = ['score_item__class_group', 'score_item__category']


@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display = ['enrollment', 'date', 'status']
    list_filter = ['status', 'enrollment__class_group']


@admin.register(ExamResult)
class ExamResultAdmin(admin.ModelAdmin):
    list_display = ['enrollment', 'exam_type', 'listening', 'speaking', 'reading', 'writing']
    list_filter = ['exam_type', 'enrollment__class_group']


@admin.register(CommentBank)
class CommentBankAdmin(admin.ModelAdmin):
    list_display = ['category', 'text']
    list_filter = ['category']
    search_fields = ['text']


@admin.register(ReportRemark)
class ReportRemarkAdmin(admin.ModelAdmin):
    list_display = ['enrollment', 'term']
    list_filter = ['term']
