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
]