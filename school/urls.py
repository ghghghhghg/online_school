from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('course/<int:pk>/', views.course_view, name='course'),
    path('lesson/<int:pk>/', views.lesson_view, name='lesson'),
    path('lesson/<int:pk>/complete/', views.complete_lesson, name='complete_lesson'),

# Панель преподавателя
    path('teacher/', views.teacher_dashboard, name='teacher_dashboard'),
    path('teacher/course/edit/', views.teacher_edit_course, name='teacher_edit_course'),
    path('teacher/lesson/add/', views.teacher_add_lesson, name='teacher_add_lesson'),
    path('teacher/lesson/<int:pk>/edit/', views.teacher_edit_lesson, name='teacher_edit_lesson'),
    path('teacher/lesson/<int:pk>/delete/', views.teacher_delete_lesson, name='teacher_delete_lesson'),

# Тесты
    path('lesson/<int:pk>/test/', views.test_view, name='test'),
    path('lesson/<int:pk>/test/result/', views.test_result_view, name='test_result'),

    # Тесты в панели преподавателя
    path('teacher/lesson/<int:pk>/test/create/', views.teacher_create_test, name='teacher_create_test'),
    path('teacher/test/<int:pk>/edit/', views.teacher_edit_test, name='teacher_edit_test'),
    path('teacher/test/<int:pk>/question/add/', views.teacher_add_question, name='teacher_add_question'),
    path('teacher/question/<int:pk>/delete/', views.teacher_delete_question, name='teacher_delete_question'),
    path('teacher/profile/', views.teacher_edit_profile, name='teacher_edit_profile'),
]