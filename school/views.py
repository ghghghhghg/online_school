from django.utils import timezone

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth import login, logout, authenticate,update_session_auth_hash
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.decorators import login_required
from .models import Course, Lesson, Enrollment, LessonProgress, Test, Question, Answer, TestResult, TeacherProfile, \
    Review, FAQ, Comment, WhyUsBlock, StatBlock, Homework, HomeworkSubmission, Module
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.db.models import Count, Avg, Q
from django.contrib.auth.models import User
from django.contrib.auth.hashers import check_password
import uuid
from django.contrib.auth import authenticate


def index(request):
    courses = Course.objects.filter(is_published=True)
    teacher = TeacherProfile.objects.first()
    reviews = Review.objects.filter(is_published=True)
    faqs = FAQ.objects.all()
    why_us_blocks = WhyUsBlock.objects.all()
    stats = StatBlock.objects.all()
    return render(request, 'school/index.html', {
        'courses': courses,
        'teacher': teacher,
        'reviews': reviews,
        'faqs': faqs,
        'why_us_blocks': why_us_blocks,
        'stats': stats,
    })

def courses_list(request):
    courses = Course.objects.filter(is_published=True)
    return render(request, 'school/courses_list.html', {'courses': courses})

def register_view(request):
    if request.method == 'POST':
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password')
        password2 = request.POST.get('password2')

        errors = []
        if not first_name:
            errors.append('Введите имя')
        if not last_name:
            errors.append('Введите фамилию')
        if not email:
            errors.append('Введите email')
        elif User.objects.filter(email=email).exists():
            errors.append('Этот email уже зарегистрирован')
        if not password or len(password) < 8:
            errors.append('Пароль должен быть не короче 8 символов')
        if password != password2:
            errors.append('Пароли не совпадают')

        if not errors:
            username = f'user_{uuid.uuid4().hex[:12]}'
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
            )
            user = authenticate(request, username=email, password=password)
            login(request, user)
            return redirect('index')

        return render(request, 'school/register.html', {'errors': errors, 'form_data': request.POST})

    return render(request, 'school/register.html')


def login_view(request):
    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password')
        user = authenticate(request, username=email, password=password)
        if user:
            login(request, user)
            return redirect('index')
        return render(request, 'school/login.html', {
            'error': 'Неверный email или пароль',
            'email': email,
        })
    return render(request, 'school/login.html')

def logout_view(request):
    logout(request)
    return redirect('index')


def course_view(request, slug):
    course = get_object_or_404(Course, slug=slug)
    lessons = course.lessons.all()

    completed_ids = []
    enrollment = None
    if request.user.is_authenticated and not request.user.is_staff:
        enrollment = Enrollment.objects.filter(student=request.user, course=course).first()
        if enrollment and enrollment.status == Enrollment.STATUS_APPROVED:
            completed_ids = LessonProgress.objects.filter(
                student=request.user,
                lesson__in=lessons
            ).values_list('lesson_id', flat=True)

    return render(request, 'school/course.html', {
        'course': course,
        'lessons': lessons,
        'completed_ids': completed_ids,
        'enrollment': enrollment,
    })

@login_required
def course_lessons_view(request, slug):
    course = get_object_or_404(Course, slug=slug)
    lessons = course.lessons.all()

    if not request.user.is_staff:
        enrollment = Enrollment.objects.filter(student=request.user, course=course).first()
        if not enrollment or enrollment.status != Enrollment.STATUS_APPROVED:
            messages.warning(request, 'Доступ к урокам появится после одобрения заявки преподавателем')
            return redirect('course', slug=course.slug)

    completed_ids = LessonProgress.objects.filter(
        student=request.user,
        lesson__in=lessons
    ).values_list('lesson_id', flat=True) if not request.user.is_staff else []

    modules = course.modules.prefetch_related('lessons').all()
    lessons_without_module = lessons.filter(module__isnull=True)

    return render(request, 'school/course_lessons.html', {
        'course': course,
        'modules': modules,
        'lessons_without_module': lessons_without_module,
        'completed_ids': completed_ids,
    })

@login_required
def lesson_view(request, pk):
    lesson = get_object_or_404(Lesson, pk=pk)
    is_completed = LessonProgress.objects.filter(
        student=request.user, lesson=lesson
    ).exists()

    test_result = None
    if hasattr(lesson, 'test'):
        test_result = TestResult.objects.filter(
            student=request.user, test=lesson.test
        ).first()

    comments = lesson.comments.filter(parent=None).select_related('author').prefetch_related('replies__author')

    return render(request, 'school/lesson.html', {
        'lesson': lesson,
        'is_completed': is_completed,
        'test_result': test_result,
        'comments': comments,
    })


@login_required
def complete_lesson(request, pk):
    lesson = get_object_or_404(Lesson, pk=pk)
    if not request.user.is_staff:
        LessonProgress.objects.get_or_create(student=request.user, lesson=lesson)
    return redirect('lesson', pk=pk)

@staff_member_required
def teacher_dashboard(request):
    courses = Course.objects.all()
    return render(request, 'school/teacher/dashboard.html', {'courses': courses})


@staff_member_required
def teacher_course_dashboard(request, pk):
    course = get_object_or_404(Course, pk=pk)
    modules = course.modules.prefetch_related('lessons').all()
    lessons_without_module = course.lessons.filter(module__isnull=True)
    return render(request, 'school/teacher/course_dashboard.html', {
        'course': course,
        'modules': modules,
        'lessons_without_module': lessons_without_module,
    })


@staff_member_required
def teacher_add_course(request):
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        errors = []
        if not title:
            errors.append('Введите название курса')
        if not errors:
            course = Course.objects.create(
                title=title,
                description=request.POST.get('description', ''),
            )
            messages.success(request, 'Курс создан!')
            return redirect('teacher_course_dashboard', pk=course.pk)
        return render(request, 'school/teacher/add_course.html', {'errors': errors})
    return render(request, 'school/teacher/add_course.html')


@staff_member_required
def teacher_add_lesson(request, pk):
    course = get_object_or_404(Course, pk=pk)
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        order = request.POST.get('order', '').strip()
        module_id = request.POST.get('module') or None

        errors = []
        if not title:
            errors.append('Введите название урока')
        if not order or not order.isdigit():
            errors.append('Порядок должен быть числом')

        if not errors:
            lesson = Lesson.objects.create(
                course=course,
                module_id=module_id,
                title=title,
                description=request.POST.get('description', ''),
                video_url=request.POST.get('video_url', ''),
                order=order,
            )
            if request.FILES.get('video_file'):
                lesson.video_file = request.FILES.get('video_file')
                lesson.save()
            messages.success(request, 'Урок добавлен!')
            return redirect('teacher_course_dashboard', pk=course.pk)

        next_order = course.lessons.count() + 1
        return render(request, 'school/teacher/add_lesson.html', {
            'course': course,
            'next_order': next_order,
            'errors': errors,
            'form_data': request.POST,
        })

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
        lesson.video_url = request.POST.get('video_url', '')
        lesson.order = request.POST.get('order', lesson.order)
        lesson.module_id = request.POST.get('module') or None
        if request.FILES.get('video_file'):
            lesson.video_file = request.FILES.get('video_file')
        lesson.save()
        messages.success(request, 'Урок обновлён!')
        return redirect('teacher_course_dashboard', pk=lesson.course.pk)
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

    if request.user.is_staff:
        messages.info(request, 'Вы просматриваете тест как преподаватель — результат не будет сохранён')

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

        if not request.user.is_staff:
            TestResult.objects.create(
                student=request.user,
                test=test,
                score=score,
                passed=passed
            )
            if passed:
                LessonProgress.objects.get_or_create(
                    student=request.user, lesson=lesson
                )
            return redirect('test_result', pk=lesson.pk)
        else:
            messages.success(request, f'Предпросмотр: результат {score}% (не сохранён)')
            return redirect('lesson', pk=lesson.pk)

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
        text = request.POST.get('text', '').strip()
        correct = request.POST.get('correct')
        answers = [request.POST.get(f'answer_{i}', '').strip() for i in range(1, 5)]

        errors = []
        if not text:
            errors.append('Введите текст вопроса')
        if not correct:
            errors.append('Отметьте правильный ответ')
        if not all(answers):
            errors.append('Заполните все 4 варианта ответа')

        if not errors:
            question = Question.objects.create(
                test=test,
                text=text,
                order=test.questions.count() + 1,
            )
            for i, answer_text in enumerate(answers, start=1):
                Answer.objects.create(
                    question=question,
                    text=answer_text,
                    is_correct=(str(i) == correct)
                )
            messages.success(request, 'Вопрос добавлен!')
            return redirect('teacher_edit_test', pk=test.pk)

        return render(request, 'school/teacher/add_question.html', {
            'test': test,
            'errors': errors,
        })

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
    if request.user.is_staff:
        return redirect('teacher_dashboard')

    enrollments = Enrollment.objects.filter(
        student=request.user, status=Enrollment.STATUS_APPROVED
    ).select_related('course')
    test_results = TestResult.objects.filter(student=request.user).select_related('test')

    courses_progress = []
    for enrollment in enrollments:
        course = enrollment.course
        total = course.lessons.count()
        completed = LessonProgress.objects.filter(
            student=request.user, lesson__course=course
        ).count()
        percent = int((completed / total) * 100) if total > 0 else 0

        courses_progress.append({
            'course': course,
            'total': total,
            'completed': completed,
            'percent': percent,
        })

    pending_enrollments = Enrollment.objects.filter(
        student=request.user, status=Enrollment.STATUS_PENDING
    ).select_related('course')

    return render(request, 'school/profile.html', {
        'courses_progress': courses_progress,
        'test_results': test_results,
        'pending_enrollments': pending_enrollments,
    })

@login_required
def add_comment(request, pk):
    lesson = get_object_or_404(Lesson, pk=pk)
    if request.method == 'POST':
        text = request.POST.get('text')
        parent_id = request.POST.get('parent_id')
        parent = Comment.objects.filter(id=parent_id).first() if parent_id else None
        if text:
            Comment.objects.create(
                lesson=lesson,
                author=request.user,
                text=text,
                parent=parent,
            )
    return redirect('lesson', pk=lesson.pk)


@login_required
def delete_comment(request, pk):
    comment = get_object_or_404(Comment, pk=pk)
    lesson_pk = comment.lesson.pk
    if request.user == comment.author or request.user.is_staff:
        comment.delete()
    return redirect('lesson', pk=lesson_pk)

@staff_member_required
def teacher_analytics(request, pk):
    course = get_object_or_404(Course, pk=pk)
    total_lessons = course.lessons.count()

    enrollments = Enrollment.objects.filter(course=course).select_related('student')

    students_data = []
    for enrollment in enrollments:
        student = enrollment.student
        completed = LessonProgress.objects.filter(
            student=student, lesson__course=course
        ).count()
        percent = int((completed / total_lessons) * 100) if total_lessons > 0 else 0

        test_results = TestResult.objects.filter(
            student=student, test__lesson__course=course
        )
        avg_score = test_results.aggregate(avg=Avg('score'))['avg']

        hw_submissions = HomeworkSubmission.objects.filter(
            student=student, homework__lesson__course=course
        )
        hw_total = Homework.objects.filter(lesson__course=course).count()
        hw_done = hw_submissions.filter(status='checked').values('homework').distinct().count()
        hw_pending = hw_submissions.filter(status='pending').values('homework').distinct().count()

        students_data.append({
            'student': student,
            'completed': completed,
            'total': total_lessons,
            'percent': percent,
            'avg_score': round(avg_score) if avg_score else None,
            'enrolled_at': enrollment.enrolled_at,
            'hw_done': hw_done,
            'hw_total': hw_total,
            'hw_pending': hw_pending,
        })

    students_data.sort(key=lambda x: x['percent'], reverse=True)

    total_students = enrollments.count()
    avg_progress = int(sum(s['percent'] for s in students_data) / total_students) if total_students > 0 else 0

    lessons_stats = []
    for lesson in course.lessons.all():
        completed_count = LessonProgress.objects.filter(lesson=lesson).count()
        lessons_stats.append({
            'lesson': lesson,
            'completed_count': completed_count,
            'percent': int((completed_count / total_students) * 100) if total_students > 0 else 0,
        })

    # Статистика по домашкам
    homeworks = Homework.objects.filter(lesson__course=course).select_related('lesson')
    homework_stats = []
    for hw in homeworks:
        submissions = HomeworkSubmission.objects.filter(homework=hw)
        checked_count = submissions.filter(status='checked').values('student').distinct().count()
        pending_count = submissions.filter(status='pending').values('student').distinct().count()
        homework_stats.append({
            'homework': hw,
            'checked_count': checked_count,
            'pending_count': pending_count,
        })

    total_pending_hw = HomeworkSubmission.objects.filter(
        status='pending', homework__lesson__course=course
    ).count()

    return render(request, 'school/teacher/analytics.html', {
        'course': course,
        'students_data': students_data,
        'total_students': total_students,
        'avg_progress': avg_progress,
        'lessons_stats': lessons_stats,
        'homework_stats': homework_stats,
        'total_pending_hw': total_pending_hw,
    })

@login_required
def edit_student_profile(request):
    if request.method == 'POST':
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        email = request.POST.get('email', '').strip()
        new_password = request.POST.get('new_password', '').strip()
        new_password2 = request.POST.get('new_password2', '').strip()
        current_password = request.POST.get('current_password', '').strip()

        errors = []
        if not first_name:
            errors.append('Введите имя')
        if not last_name:
            errors.append('Введите фамилию')
        if not email:
            errors.append('Введите email')
        elif User.objects.filter(email=email).exclude(pk=request.user.pk).exists():
            errors.append('Этот email уже используется другим пользователем')

        password_changing = bool(new_password or new_password2)
        if password_changing:
            if not current_password:
                errors.append('Введите текущий пароль чтобы задать новый')
            elif not request.user.check_password(current_password):
                errors.append('Текущий пароль указан неверно')
            if len(new_password) < 8:
                errors.append('Новый пароль должен быть не короче 8 символов')
            if new_password != new_password2:
                errors.append('Новые пароли не совпадают')

        if not errors:
            request.user.first_name = first_name
            request.user.last_name = last_name
            request.user.email = email
            if password_changing:
                request.user.set_password(new_password)
            request.user.save()
            if password_changing:
                update_session_auth_hash(request, request.user)
            messages.success(request, 'Профиль обновлён!')
            return redirect('student_profile')

        return render(request, 'school/edit_profile.html', {'errors': errors})

    return render(request, 'school/edit_profile.html')

@staff_member_required
def teacher_edit_course(request, pk):
    course = get_object_or_404(Course, pk=pk)
    if request.method == 'POST':
        course.title = request.POST.get('title')
        course.description = request.POST.get('description')
        course.what_you_learn = request.POST.get('what_you_learn')
        course.for_whom = request.POST.get('for_whom')
        course.how_it_works = request.POST.get('how_it_works')
        course.is_published = request.POST.get('is_published') == 'on'
        course.save()
        messages.success(request, 'Курс обновлён!')
        return redirect('teacher_course_dashboard', pk=course.pk)
    return render(request, 'school/teacher/edit_course.html', {'course': course})


@login_required
def homework_view(request, pk):
    lesson = get_object_or_404(Lesson, pk=pk)
    homework = get_object_or_404(Homework, lesson=lesson)

    if request.user.is_staff:
        messages.info(request, 'Вы просматриваете задание как преподаватель')
        return render(request, 'school/homework.html', {
            'lesson': lesson,
            'homework': homework,
            'last_submission': None,
            'can_submit': False,
        })

    submissions = HomeworkSubmission.objects.filter(
        homework=homework, student=request.user
    )
    last_submission = submissions.first()

    already_passed = (
        last_submission
        and last_submission.status == HomeworkSubmission.STATUS_CHECKED
        and (
            last_submission.passed is True
            or (homework.grading_type == Homework.GRADING_COMMENT_ONLY)
        )
    )

    can_submit = homework.allow_resubmit and not already_passed
    if not submissions.exists():
        can_submit = True

    if request.method == 'POST' and can_submit:
        text = request.POST.get('text', '').strip()
        file = request.FILES.get('file')

        errors = []
        if homework.submission_type in [Homework.SUBMISSION_TEXT, Homework.SUBMISSION_BOTH] and not text:
            errors.append('Введите текст ответа')
        if homework.submission_type in [Homework.SUBMISSION_FILE, Homework.SUBMISSION_BOTH] and not file:
            errors.append('Прикрепите файл')

        if not errors:
            HomeworkSubmission.objects.create(
                homework=homework,
                student=request.user,
                text=text,
                file=file,
            )
            messages.success(request, 'Домашнее задание отправлено на проверку!')
            return redirect('homework', pk=lesson.pk)

        return render(request, 'school/homework.html', {
            'lesson': lesson,
            'homework': homework,
            'last_submission': last_submission,
            'can_submit': can_submit,
            'errors': errors,
        })

    return render(request, 'school/homework.html', {
        'lesson': lesson,
        'homework': homework,
        'last_submission': last_submission,
        'can_submit': can_submit,
    })


@staff_member_required
def teacher_create_homework(request, pk):
    lesson = get_object_or_404(Lesson, pk=pk)
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()

        errors = []
        if not title:
            errors.append('Введите название задания')
        if not description:
            errors.append('Введите текст задания')

        if not errors:
            Homework.objects.create(
                lesson=lesson,
                title=title,
                description=description,
                submission_type=request.POST.get('submission_type'),
                grading_type=request.POST.get('grading_type'),
                allow_resubmit=request.POST.get('allow_resubmit') == 'on',
            )
            messages.success(request, 'Домашнее задание создано!')
            return redirect('teacher_course_dashboard', pk=lesson.course.pk)

        return render(request, 'school/teacher/create_homework.html', {
            'lesson': lesson, 'errors': errors,
        })

    return render(request, 'school/teacher/create_homework.html', {'lesson': lesson})


@staff_member_required
def teacher_edit_homework(request, pk):
    homework = get_object_or_404(Homework, pk=pk)
    if request.method == 'POST':
        homework.title = request.POST.get('title', '').strip()
        homework.description = request.POST.get('description', '').strip()
        homework.submission_type = request.POST.get('submission_type')
        homework.grading_type = request.POST.get('grading_type')
        homework.allow_resubmit = request.POST.get('allow_resubmit') == 'on'
        homework.save()
        messages.success(request, 'Задание обновлено!')
        return redirect('teacher_course_dashboard', pk=homework.lesson.course.pk)
    return render(request, 'school/teacher/edit_homework.html', {'homework': homework})


@staff_member_required
def teacher_homework_submissions(request, pk):
    homework = get_object_or_404(Homework, pk=pk)
    submissions = homework.submissions.select_related('student').all()
    return render(request, 'school/teacher/homework_submissions.html', {
        'homework': homework,
        'submissions': submissions,
    })


@staff_member_required
def teacher_check_submission(request, pk):
    submission = get_object_or_404(HomeworkSubmission, pk=pk)
    homework = submission.homework

    if request.method == 'POST':
        if homework.grading_type == Homework.GRADING_SCORE:
            submission.score = request.POST.get('score')
        elif homework.grading_type == Homework.GRADING_PASS_FAIL:
            submission.passed = request.POST.get('passed') == 'yes'
        submission.teacher_comment = request.POST.get('comment', '')
        submission.status = HomeworkSubmission.STATUS_CHECKED
        submission.checked_at = timezone.now()
        submission.save()
        messages.success(request, 'Проверено!')
        return redirect('teacher_homework_submissions', pk=homework.pk)

    return redirect(request.META.get('HTTP_REFERER', 'teacher_all_homework'))

@staff_member_required
def teacher_all_homework(request):
    submissions = HomeworkSubmission.objects.select_related(
        'student', 'homework', 'homework__lesson', 'homework__lesson__course'
    ).all()

    course_id = request.GET.get('course')
    lesson_id = request.GET.get('lesson')
    status = request.GET.get('status')

    if course_id:
        submissions = submissions.filter(homework__lesson__course_id=course_id)
    if lesson_id:
        submissions = submissions.filter(homework__lesson_id=lesson_id)
    if status:
        submissions = submissions.filter(status=status)

    # Группируем по (ученик, домашка) — последняя попытка первая
    groups = {}
    for s in submissions:
        key = (s.student_id, s.homework_id)
        groups.setdefault(key, []).append(s)

    grouped_list = []
    for (student_id, homework_id), items in groups.items():
        items.sort(key=lambda x: x.submitted_at, reverse=True)
        grouped_list.append({
            'latest': items[0],
            'history': items[1:],
            'attempts_count': len(items),
        })

    # Сортируем группы: сначала непроверенные последние попытки, потом по дате
    grouped_list.sort(key=lambda g: (g['latest'].status == 'checked', -g['latest'].submitted_at.timestamp()))

    courses = Course.objects.all()
    lessons = Lesson.objects.filter(homework__isnull=False)
    if course_id:
        lessons = lessons.filter(course_id=course_id)

    pending_count = HomeworkSubmission.objects.filter(status='pending').count()

    return render(request, 'school/teacher/all_homework.html', {
        'grouped_list': grouped_list,
        'courses': courses,
        'lessons': lessons,
        'selected_course': course_id,
        'selected_lesson': lesson_id,
        'selected_status': status,
        'pending_count': pending_count,
    })

@staff_member_required
def teacher_add_module(request, pk):
    course = get_object_or_404(Course, pk=pk)
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        order = request.POST.get('order', '').strip()
        if title:
            Module.objects.create(
                course=course,
                title=title,
                order=order if order.isdigit() else course.modules.count() + 1,
            )
            messages.success(request, 'Раздел добавлен!')
        return redirect('teacher_course_dashboard', pk=course.pk)
    return redirect('teacher_course_dashboard', pk=course.pk)


@staff_member_required
def teacher_edit_module(request, pk):
    module = get_object_or_404(Module, pk=pk)
    if request.method == 'POST':
        module.title = request.POST.get('title', '').strip()
        module.order = request.POST.get('order', module.order)
        module.save()
        messages.success(request, 'Раздел обновлён!')
        return redirect('teacher_course_dashboard', pk=module.course.pk)
    return render(request, 'school/teacher/edit_module.html', {'module': module})

@staff_member_required
def teacher_delete_module(request, pk):
    module = get_object_or_404(Module, pk=pk)
    course_pk = module.course.pk
    if request.method == 'POST':
        module.delete()
        messages.success(request, 'Раздел удалён (уроки остались, но без раздела)')
    return redirect('teacher_course_dashboard', pk=course_pk)

@login_required
def apply_to_course(request, slug):
    course = get_object_or_404(Course, slug=slug)
    if request.user.is_staff:
        return redirect('course', slug=slug)

    Enrollment.objects.get_or_create(
        student=request.user, course=course,
        defaults={'status': Enrollment.STATUS_PENDING}
    )
    messages.success(request, 'Заявка отправлена! Ожидайте одобрения преподавателя.')
    return redirect('course', slug=slug)


@staff_member_required
def teacher_enrollments(request):
    status_filter = request.GET.get('status', 'pending')
    enrollments = Enrollment.objects.select_related('student', 'course').all()
    if status_filter:
        enrollments = enrollments.filter(status=status_filter)
    enrollments = enrollments.order_by('-enrolled_at')

    pending_count = Enrollment.objects.filter(status=Enrollment.STATUS_PENDING).count()

    return render(request, 'school/teacher/enrollments.html', {
        'enrollments': enrollments,
        'selected_status': status_filter,
        'pending_count': pending_count,
    })


@staff_member_required
def teacher_approve_enrollment(request, pk):
    enrollment = get_object_or_404(Enrollment, pk=pk)
    if request.method == 'POST':
        enrollment.status = Enrollment.STATUS_APPROVED
        enrollment.approved_at = timezone.now()
        enrollment.save()
        messages.success(request, f'Заявка {enrollment.student.first_name} одобрена!')
    return redirect('teacher_enrollments')


@staff_member_required
def teacher_reject_enrollment(request, pk):
    enrollment = get_object_or_404(Enrollment, pk=pk)
    if request.method == 'POST':
        enrollment.status = Enrollment.STATUS_REJECTED
        enrollment.save()
        messages.success(request, 'Заявка отклонена')
    return redirect('teacher_enrollments')