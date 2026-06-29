from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.decorators import login_required
from .models import Course, Lesson, Enrollment, LessonProgress
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages


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

@staff_member_required
def teacher_dashboard(request):
    course = Course.objects.first()
    lessons = course.lessons.all() if course else []
    return render(request, 'school/teacher/dashboard.html', {
        'course': course,
        'lessons': lessons,
    })


@staff_member_required
def teacher_edit_course(request):
    course = Course.objects.first()
    if request.method == 'POST':
        course.title = request.POST.get('title')
        course.description = request.POST.get('description')
        course.save()
        messages.success(request, 'Курс обновлён!')
        return redirect('teacher_dashboard')
    return render(request, 'school/teacher/edit_course.html', {'course': course})


@staff_member_required
def teacher_add_lesson(request):
    course = Course.objects.first()
    if request.method == 'POST':
        Lesson.objects.create(
            course=course,
            title=request.POST.get('title'),
            description=request.POST.get('description'),
            video_url=request.POST.get('video_url'),
            order=request.POST.get('order', 0),
        )
        messages.success(request, 'Урок добавлен!')
        return redirect('teacher_dashboard')
    next_order = course.lessons.count() + 1
    return render(request, 'school/teacher/add_lesson.html', {
        'course': course,
        'next_order': next_order,
    })


@staff_member_required
def teacher_edit_lesson(request, pk):
    lesson = get_object_or_404(Lesson, pk=pk)
    if request.method == 'POST':
        lesson.title = request.POST.get('title')
        lesson.description = request.POST.get('description')
        lesson.video_url = request.POST.get('video_url')
        lesson.order = request.POST.get('order', lesson.order)
        lesson.save()
        messages.success(request, 'Урок обновлён!')
        return redirect('teacher_dashboard')
    return render(request, 'school/teacher/edit_lesson.html', {'lesson': lesson})


@staff_member_required
def teacher_delete_lesson(request, pk):
    lesson = get_object_or_404(Lesson, pk=pk)
    if request.method == 'POST':
        lesson.delete()
        messages.success(request, 'Урок удалён!')
    return redirect('teacher_dashboard')