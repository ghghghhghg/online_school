from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.decorators import login_required
from .models import Course, Lesson, Enrollment, LessonProgress


def index(request):
    """Главная — показываем первый курс"""
    course = Course.objects.first()
    return render(request, 'school/index.html', {'course': course})


def register_view(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('index')
    else:
        form = UserCreationForm()
    return render(request, 'school/register.html', {'form': form})


def login_view(request):
    if request.method == 'POST':
        form = AuthenticationForm(data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect('index')
    else:
        form = AuthenticationForm()
    return render(request, 'school/login.html', {'form': form})


def logout_view(request):
    logout(request)
    return redirect('index')


@login_required
def course_view(request, pk):
    course = get_object_or_404(Course, pk=pk)
    lessons = course.lessons.all()

    # Записываем ученика на курс автоматически
    Enrollment.objects.get_or_create(student=request.user, course=course)

    # Какие уроки уже пройдены
    completed_ids = LessonProgress.objects.filter(
        student=request.user,
        lesson__in=lessons
    ).values_list('lesson_id', flat=True)

    return render(request, 'school/course.html', {
        'course': course,
        'lessons': lessons,
        'completed_ids': completed_ids,
    })


@login_required
def lesson_view(request, pk):
    lesson = get_object_or_404(Lesson, pk=pk)
    is_completed = LessonProgress.objects.filter(
        student=request.user, lesson=lesson
    ).exists()

    return render(request, 'school/lesson.html', {
        'lesson': lesson,
        'is_completed': is_completed,
    })


@login_required
def complete_lesson(request, pk):
    lesson = get_object_or_404(Lesson, pk=pk)
    LessonProgress.objects.get_or_create(student=request.user, lesson=lesson)
    return redirect('lesson', pk=pk)