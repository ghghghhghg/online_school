from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('profile/', views.student_profile, name='student_profile'),
    path('profile/edit/', views.edit_student_profile, name='edit_student_profile'),

    path('courses/', views.courses_list, name='courses_list'),
    path('course/<slug:slug>/', views.course_view, name='course'),
    path('course/<slug:slug>/lessons/', views.course_lessons_view, name='course_lessons'),

    path('teacher/course/<int:pk>/module/add/', views.teacher_add_module, name='teacher_add_module'),
    path('teacher/module/<int:pk>/edit/', views.teacher_edit_module, name='teacher_edit_module'),
    path('teacher/module/<int:pk>/delete/', views.teacher_delete_module, name='teacher_delete_module'),

    path('course/<slug:slug>/apply/', views.apply_to_course, name='apply_to_course'),
    path('teacher/enrollments/', views.teacher_enrollments, name='teacher_enrollments'),
    path('teacher/enrollment/<int:pk>/approve/', views.teacher_approve_enrollment, name='teacher_approve_enrollment'),
    path('teacher/enrollment/<int:pk>/reject/', views.teacher_reject_enrollment, name='teacher_reject_enrollment'),

    # Контрольные точки — ученик
    path('checkpoint/<int:pk>/', views.checkpoint_view, name='checkpoint'),
    path('checkpoint-result/<int:pk>/', views.checkpoint_result_view, name='checkpoint_result'),

    path('teacher/course/<int:pk>/checkpoint/add/', views.teacher_add_checkpoint, name='teacher_add_checkpoint'),
    path('teacher/checkpoint/<int:pk>/edit/', views.teacher_edit_checkpoint, name='teacher_edit_checkpoint'),
    path('teacher/checkpoint/<int:pk>/delete/', views.teacher_delete_checkpoint, name='teacher_delete_checkpoint'),
    path('teacher/checkpoint/<int:pk>/task/add/', views.teacher_add_checkpoint_task,
         name='teacher_add_checkpoint_task'),
    path('teacher/checkpoint-task/<int:pk>/delete/', views.teacher_delete_checkpoint_task,
         name='teacher_delete_checkpoint_task'),
    path('teacher/checkpoints/', views.teacher_all_checkpoints, name='teacher_all_checkpoints'),
    path('teacher/checkpoint-attempt/<int:pk>/check/', views.teacher_check_checkpoint_attempt,
         name='teacher_check_checkpoint_attempt'),

    path('lesson/<int:pk>/', views.lesson_view, name='lesson'),
    path('lesson/<int:pk>/complete/', views.complete_lesson, name='complete_lesson'),
    path('lesson/<int:pk>/comment/', views.add_comment, name='add_comment'),
    # Домашние задания — ученик
    path('lesson/<int:pk>/homework/', views.homework_view, name='homework'),
    path('teacher/homework/', views.teacher_all_homework, name='teacher_all_homework'),
    path('comment/<int:pk>/delete/', views.delete_comment, name='delete_comment'),

    path('lesson/<int:pk>/test/', views.test_view, name='test'),
    path('lesson/<int:pk>/test/result/', views.test_result_view, name='test_result'),

    path('password-reset/',
         auth_views.PasswordResetView.as_view(
             template_name='school/password_reset.html',
             email_template_name='school/password_reset_email.html',
             subject_template_name='school/password_reset_subject.txt',
         ),
         name='password_reset'),
    path('password-reset/done/',
         auth_views.PasswordResetDoneView.as_view(
             template_name='school/password_reset_done.html'),
         name='password_reset_done'),
    path('reset/<uidb64>/<token>/',
         auth_views.PasswordResetConfirmView.as_view(
             template_name='school/password_reset_confirm.html'),
         name='password_reset_confirm'),
    path('reset/done/',
         auth_views.PasswordResetCompleteView.as_view(
             template_name='school/password_reset_complete.html'),
         name='password_reset_complete'),

    # Панель преподавателя
    path('teacher/', views.teacher_dashboard, name='teacher_dashboard'),
    path('teacher/profile/', views.teacher_edit_profile, name='teacher_edit_profile'),
    path('teacher/course/add/', views.teacher_add_course, name='teacher_add_course'),
    path('teacher/course/<int:pk>/', views.teacher_course_dashboard, name='teacher_course_dashboard'),
    path('teacher/course/<int:pk>/edit/', views.teacher_edit_course, name='teacher_edit_course'),
    path('teacher/course/<int:pk>/analytics/', views.teacher_analytics, name='teacher_analytics'),
    path('teacher/course/<int:pk>/lesson/add/', views.teacher_add_lesson, name='teacher_add_lesson'),
    path('teacher/lesson/<int:pk>/edit/', views.teacher_edit_lesson, name='teacher_edit_lesson'),
    path('teacher/lesson/<int:pk>/delete/', views.teacher_delete_lesson, name='teacher_delete_lesson'),

    # Домашние задания — преподаватель
    path('teacher/lesson/<int:pk>/homework/create/', views.teacher_create_homework, name='teacher_create_homework'),
    path('teacher/homework/<int:pk>/edit/', views.teacher_edit_homework, name='teacher_edit_homework'),
    path('teacher/homework/<int:pk>/submissions/', views.teacher_homework_submissions, name='teacher_homework_submissions'),
    path('teacher/submission/<int:pk>/check/', views.teacher_check_submission, name='teacher_check_submission'),
    path('teacher/homework/<int:pk>/delete/', views.teacher_delete_homework, name='teacher_delete_homework'),

    path('teacher/lesson/<int:pk>/test/create/', views.teacher_create_test, name='teacher_create_test'),
    path('teacher/test/<int:pk>/edit/', views.teacher_edit_test, name='teacher_edit_test'),
    path('teacher/test/<int:pk>/question/add/', views.teacher_add_question, name='teacher_add_question'),
    path('teacher/question/<int:pk>/delete/', views.teacher_delete_question, name='teacher_delete_question'),

    path('notifications/read/<int:pk>/', views.mark_notification_read, name='mark_notification_read'),
    path('notifications/', views.all_notifications, name='all_notifications'),
    path('notifications/clear/', views.clear_notifications, name='clear_notifications'),
    path('notifications/<int:pk>/delete/', views.delete_notification, name='delete_notification'),

    # Пробники — ученик
    path('exam/<int:pk>/start/', views.exam_start_view, name='exam_start'),
    path('exam-attempt/<int:pk>/', views.exam_attempt_view, name='exam_attempt'),
    path('exam-result/<int:pk>/', views.exam_result_view, name='exam_result'),

    # Пробники — преподаватель
    path('teacher/course/<int:pk>/exam/add/', views.teacher_add_exam, name='teacher_add_exam'),
    path('teacher/exam/<int:pk>/edit/', views.teacher_edit_exam, name='teacher_edit_exam'),
    path('teacher/exam/<int:pk>/delete/', views.teacher_delete_exam, name='teacher_delete_exam'),
    path('teacher/exam/<int:pk>/task/add/', views.teacher_add_exam_task, name='teacher_add_exam_task'),
    path('teacher/exam-task/<int:pk>/delete/', views.teacher_delete_exam_task, name='teacher_delete_exam_task'),
    path('teacher/exams/', views.teacher_all_exams, name='teacher_all_exams'),
    path('teacher/exam-attempt/<int:pk>/check/', views.teacher_check_exam_attempt, name='teacher_check_exam_attempt'),

    path('my-analytics/', views.student_analytics, name='student_analytics'),

    path('my-errors/', views.error_notebook, name='error_notebook'),

    path('course/<int:course_pk>/continue/', views.continue_learning, name='continue_learning'),

    path('reviews/', views.all_reviews_view, name='all_reviews'),

    path('my-courses/', views.student_courses, name='student_courses'),

    path('confirm-email/<uidb64>/<token>/', views.confirm_email_view, name='confirm_email'),
]