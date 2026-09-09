from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path('accounts/login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('accounts/logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),

    path('', views.dashboard, name='dashboard'),

    # Admin: Teachers
    path('teachers/', views.TeacherListView.as_view(), name='teacher-list'),
    path('teachers/add/', views.TeacherCreateView.as_view(), name='teacher-create'),
    path('teachers/<int:pk>/edit/', views.TeacherUpdateView.as_view(), name='teacher-update'),
    path('teachers/<int:pk>/toggle/', views.teacher_toggle_status, name='teacher-toggle'),

    # Admin: Class Teachers
    path('class-teachers/', views.class_teachers, name='class-teachers'),

    # Admin: Classes / Terms / Academic Years
    path('classes/', views.ClassGroupListView.as_view(), name='classgroup-list'),
    path('classes/add/', views.ClassGroupCreateView.as_view(), name='classgroup-create'),
    path('classes/<int:pk>/edit/', views.ClassGroupUpdateView.as_view(), name='classgroup-update'),

    path('terms/', views.TermListView.as_view(), name='term-list'),
    path('terms/add/', views.TermCreateView.as_view(), name='term-create'),
    path('terms/<int:pk>/edit/', views.TermUpdateView.as_view(), name='term-update'),

    path('academic-years/', views.AcademicYearListView.as_view(), name='academicyear-list'),
    path('academic-years/add/', views.AcademicYearCreateView.as_view(), name='academicyear-create'),
    path('academic-years/<int:pk>/edit/', views.AcademicYearUpdateView.as_view(), name='academicyear-update'),

    # Students
    path('students/', views.students_list, name='students'),
    path('students/add/', views.student_create, name='student-create'),
    path('students/<int:enrollment_id>/edit/', views.student_update, name='student-update'),
    path('students/<int:enrollment_id>/toggle/', views.student_toggle_status, name='student-toggle'),
    path('students/<int:enrollment_id>/delete/', views.student_delete, name='student-delete'),

    # Score entry grids
    path('scores/<str:category_slug>/', views.score_entry, name='score-entry'),
    path('scores/<str:category_slug>/items/add/', views.score_item_add, name='score-item-add'),
    path('scores/cell/<int:item_id>/<int:enrollment_id>/', views.score_cell_save, name='score-cell-save'),

    # Attendance
    path('attendance/', views.attendance, name='attendance'),
    path('attendance/add-date/', views.attendance_add_date, name='attendance-add-date'),
    path('attendance/set/<int:enrollment_id>/<str:date_str>/<str:status>/', views.attendance_set, name='attendance-set'),

    # Midterm / Final
    path('exams/<str:exam_type_slug>/', views.exam_entry, name='exam-entry'),
    path('exams/save/<int:enrollment_id>/<str:exam_type_slug>/', views.exam_save, name='exam-save'),

    # Score Record / Final Result
    path('score-record/', views.score_record, name='score-record'),
    path('final-results/', views.final_result, name='final-result'),
    path('final-results/export.csv', views.final_result_csv, name='final-result-csv'),
    path('final-results/export.pdf', views.final_result_pdf, name='final-result-pdf'),

    # Report Card
    path('report-cards/<int:enrollment_id>/', views.report_card, name='report-card'),
    path('report-cards/<int:enrollment_id>/pdf/', views.report_card_pdf, name='report-card-pdf'),
    path('report-cards/<int:enrollment_id>/comment-options/', views.report_card_comment_options, name='report-card-comment-options'),
    path('report-cards/<int:enrollment_id>/remark/', views.report_card_save_remark, name='report-card-save-remark'),

    # Comment Bank
    path('comment-bank/', views.comment_bank_list, name='comment-bank'),
    path('comment-bank/add/', views.CommentBankCreateView.as_view(), name='comment-bank-create'),
    path('comment-bank/<int:pk>/edit/', views.CommentBankUpdateView.as_view(), name='comment-bank-update'),
    path('comment-bank/<int:pk>/delete/', views.comment_bank_delete, name='comment-bank-delete'),
]