from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('course/<int:pk>/', views.course_view, name='course'),
    path('lesson/<int:pk>/', views.lesson_view, name='lesson'),
    path('lesson/<int:pk>/complete/', views.complete_lesson, name='complete_lesson'),
    path('profile/', views.student_profile, name='student_profile'),

    # Восстановление пароля
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
    path('teacher/course/edit/', views.teacher_edit_course, name='teacher_edit_course'),
    path('teacher/profile/', views.teacher_edit_profile, name='teacher_edit_profile'),
    path('teacher/lesson/add/', views.teacher_add_lesson, name='teacher_add_lesson'),
    path('teacher/lesson/<int:pk>/edit/', views.teacher_edit_lesson, name='teacher_edit_lesson'),
    path('teacher/lesson/<int:pk>/delete/', views.teacher_delete_lesson, name='teacher_delete_lesson'),

    path('lesson/<int:pk>/test/', views.test_view, name='test'),
    path('lesson/<int:pk>/test/result/', views.test_result_view, name='test_result'),
    path('teacher/lesson/<int:pk>/test/create/', views.teacher_create_test, name='teacher_create_test'),
    path('teacher/test/<int:pk>/edit/', views.teacher_edit_test, name='teacher_edit_test'),
    path('teacher/test/<int:pk>/question/add/', views.teacher_add_question, name='teacher_add_question'),
    path('teacher/question/<int:pk>/delete/', views.teacher_delete_question, name='teacher_delete_question'),
    path('lesson/<int:pk>/comment/', views.add_comment, name='add_comment'),
    path('comment/<int:pk>/delete/', views.delete_comment, name='delete_comment'),
    path('teacher/analytics/', views.teacher_analytics, name='teacher_analytics'),
    path('profile/edit/', views.edit_student_profile, name='edit_student_profile'),
]