from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.decorators import login_required
from .models import Course, Lesson, Enrollment, LessonProgress, Test, Question, Answer, TestResult, TeacherProfile, \
    Review, FAQ
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages


def index(request):
    course = Course.objects.first()
    teacher = TeacherProfile.objects.first()
    reviews = Review.objects.filter(is_published=True)
    faqs = FAQ.objects.all()
    return render(request, 'school/index.html', {
        'course': course,
        'teacher': teacher,
        'reviews': reviews,
        'faqs': faqs,
    })

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

    # Последний результат теста если есть
    test_result = None
    if hasattr(lesson, 'test'):
        test_result = TestResult.objects.filter(
            student=request.user, test=lesson.test
        ).first()

    return render(request, 'school/lesson.html', {
        'lesson': lesson,
        'is_completed': is_completed,
        'test_result': test_result,
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
        course.what_you_learn = request.POST.get('what_you_learn')
        course.for_whom = request.POST.get('for_whom')
        course.how_it_works = request.POST.get('how_it_works')
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


@login_required
def test_view(request, pk):
    lesson = get_object_or_404(Lesson, pk=pk)
    test = get_object_or_404(Test, lesson=lesson)
    questions = test.questions.prefetch_related('answers').all()

    if request.method == 'POST':
        total = questions.count()
        correct = 0

        for question in questions:
            answer_id = request.POST.get(f'question_{question.id}')
            if answer_id:
                answer = Answer.objects.filter(id=answer_id, is_correct=True).first()
                if answer:
                    correct += 1

        score = int((correct / total) * 100) if total > 0 else 0
        passed = score >= test.pass_score

        # Сохраняем результат
        TestResult.objects.create(
            student=request.user,
            test=test,
            score=score,
            passed=passed
        )

        # Если тест сдан — автоматически отмечаем урок пройденным
        if passed:
            LessonProgress.objects.get_or_create(
                student=request.user, lesson=lesson
            )

        return redirect('test_result', pk=lesson.pk)

    return render(request, 'school/test.html', {
        'lesson': lesson,
        'test': test,
        'questions': questions,
    })

@login_required
def test_result_view(request, pk):
    lesson = get_object_or_404(Lesson, pk=pk)
    test = get_object_or_404(Test, lesson=lesson)
    result = TestResult.objects.filter(
        student=request.user, test=test
    ).first()
    return render(request, 'school/test_result.html', {
        'lesson': lesson,
        'test': test,
        'result': result,
    })


@staff_member_required
def teacher_create_test(request, pk):
    lesson = get_object_or_404(Lesson, pk=pk)
    if request.method == 'POST':
        Test.objects.create(
            lesson=lesson,
            title=request.POST.get('title'),
            pass_score=request.POST.get('pass_score', 70),
        )
        messages.success(request, 'Тест создан!')
        return redirect('teacher_dashboard')
    return render(request, 'school/teacher/create_test.html', {'lesson': lesson})


@staff_member_required
def teacher_edit_test(request, pk):
    test = get_object_or_404(Test, pk=pk)
    questions = test.questions.prefetch_related('answers').all()

    if request.method == 'POST':
        test.title = request.POST.get('title')
        test.pass_score = request.POST.get('pass_score', 70)
        test.save()
        messages.success(request, 'Тест обновлён!')
        return redirect('teacher_edit_test', pk=pk)

    return render(request, 'school/teacher/edit_test.html', {
        'test': test,
        'questions': questions,
    })


@staff_member_required
def teacher_add_question(request, pk):
    test = get_object_or_404(Test, pk=pk)

    if request.method == 'POST':
        question = Question.objects.create(
            test=test,
            text=request.POST.get('text'),
            order=test.questions.count() + 1,
        )
        # Сохраняем 4 варианта ответа
        correct = request.POST.get('correct')
        for i in range(1, 5):
            text = request.POST.get(f'answer_{i}')
            if text:
                Answer.objects.create(
                    question=question,
                    text=text,
                    is_correct=(str(i) == correct)
                )
        messages.success(request, 'Вопрос добавлен!')
        return redirect('teacher_edit_test', pk=test.pk)

    return render(request, 'school/teacher/add_question.html', {'test': test})


@staff_member_required
def teacher_delete_question(request, pk):
    question = get_object_or_404(Question, pk=pk)
    test_pk = question.test.pk
    if request.method == 'POST':
        question.delete()
        messages.success(request, 'Вопрос удалён!')
    return redirect('teacher_edit_test', pk=test_pk)

@staff_member_required
def teacher_edit_profile(request):
    profile, created = (TeacherProfile.objects.get_or_create(id=1))
    if request.method == 'POST':
        profile.name = request.POST.get('name')
        profile.bio = request.POST.get('bio')
        if request.FILES.get('photo'):
            profile.photo = request.FILES.get('photo')
        profile.save()
        messages.success(request, 'Профиль обновлён!')
        return redirect('teacher_dashboard')
    return render(request, 'school/teacher/edit_profile.html', {'profile': profile})


@login_required
def student_profile(request):
    enrollments = Enrollment.objects.filter(student=request.user).select_related('course')
    progress = LessonProgress.objects.filter(student=request.user).select_related('lesson')
    test_results = TestResult.objects.filter(student=request.user).select_related('test')

    course = Course.objects.first()
    total_lessons = course.lessons.count() if course else 0
    completed_count = progress.count()
    percent = int((completed_count / total_lessons) * 100) if total_lessons > 0 else 0

    return render(request, 'school/profile.html', {
        'enrollments': enrollments,
        'progress': progress,
        'test_results': test_results,
        'total_lessons': total_lessons,
        'completed_count': completed_count,
        'percent': percent,
    })