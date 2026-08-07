from cloudinary.models import CloudinaryField
from django.http import JsonResponse
from django.utils import timezone

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth import login, logout, authenticate,update_session_auth_hash
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.decorators import login_required
from .models import Course, Lesson, Enrollment, LessonProgress, Test, Question, Answer, TestResult, TeacherProfile, \
    Review, FAQ, Comment, WhyUsBlock, StatBlock, Homework, HomeworkSubmission, Module, Checkpoint, CheckpointTask, \
    CheckpointAttempt, CheckpointAnswer, Notification, ExamMock, ExamAttempt, ExamTask, ExamAnswer, FearBlock, \
    ParentBlock, SiteSettings, TestAnswerLog, Timecode, CourseTeacherDisplay
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.db.models import Count, Avg, Q
from django.db import models, transaction, IntegrityError
from django.contrib.auth.models import User
from django.contrib.auth.hashers import check_password
import uuid
from django.contrib.auth import authenticate

from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes
from django.core.mail import send_mail
from django.urls import reverse

from .services.scoring import (
    record_answer_points, record_checkpoint_attempt, record_exam_attempt,
    record_homework_submission, record_test_attempt, register_errors,
    resolve_errors_on_success,
)

def index(request):
    courses = Course.objects.filter(is_published=True)

    exam_filter = request.GET.get('exam', 'ege')
    subject_filter = request.GET.get('subject', '')

    if exam_filter:
        courses = courses.filter(exam_type=exam_filter)
    if subject_filter:
        courses = courses.filter(subject=subject_filter)

    subjects = Course.objects.filter(is_published=True).exclude(subject='') \
        .order_by('subject').values_list('subject', flat=True).distinct()

    hero_teacher = TeacherProfile.objects.filter(subject='Русский язык').first() or TeacherProfile.objects.first()

    teacher_exam_filter = request.GET.get('teacher_exam', 'ege')
    teacher_subject_filter = request.GET.get('teacher_subject', 'Русский язык')

    teachers = TeacherProfile.objects.filter(exam_type=teacher_exam_filter)
    if teacher_subject_filter:
        teachers = teachers.filter(subject=teacher_subject_filter)

    teacher_subjects = TeacherProfile.objects.filter(exam_type=teacher_exam_filter) \
        .exclude(subject='').order_by('subject').values_list('subject', flat=True).distinct()

    reviews = Review.objects.filter(is_published=True).prefetch_related('photos')[:10]
    faqs = FAQ.objects.all()
    stats = StatBlock.objects.all()
    fears = FearBlock.objects.all()
    parent_blocks = ParentBlock.objects.all()
    site_settings = SiteSettings.objects.first()
    features = WhyUsBlock.objects.all()

    return render(request, 'school/index.html', {
        'courses': courses,
        'subjects': subjects,
        'exam_filter': exam_filter,
        'subject_filter': subject_filter,
        'teachers': teachers,
        'teacher_subjects': teacher_subjects,
        'teacher_subject_filter': teacher_subject_filter,
        'teacher_exam_filter': teacher_exam_filter,
        'reviews': reviews,
        'faqs': faqs,
        'stats': stats,
        'fears': fears,
        'parent_blocks': parent_blocks,
        'site_settings': site_settings,
        'hero_teacher': hero_teacher,
        'features': features,
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
                is_active=False,  # неактивен до подтверждения почты
            )

            # Письмо со ссылкой подтверждения
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            confirm_url = request.build_absolute_uri(
                reverse('confirm_email', kwargs={'uidb64': uid, 'token': token})
            )
            send_mail(
                'Подтверждение регистрации — Онлайн-школа',
                f'Здравствуйте, {first_name}!\n\n'
                f'Для завершения регистрации перейдите по ссылке:\n{confirm_url}\n\n'
                f'Если вы не регистрировались — просто проигнорируйте это письмо.',
                None,
                [email],
                fail_silently=False,
            )

            return render(request, 'school/confirm_email_sent.html', {'email': email})

        return render(request, 'school/register.html', {'errors': errors, 'form_data': request.POST})

    return render(request, 'school/register.html')


def confirm_email_view(request, uidb64, token):
    try:
        uid = urlsafe_base64_decode(uidb64).decode()
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user and default_token_generator.check_token(user, token):
        user.is_active = True
        user.save()
        login(request, user, backend='school.auth_backends.EmailBackend')

        send_mail(
            'Добро пожаловать в онлайн-школу!',
            f'Здравствуйте, {user.first_name}!\n\n'
            f'Ваша регистрация успешно завершена — добро пожаловать!\n\n'
            f'Что дальше:\n'
            f'— Выберите курс на главной странице: https://abs-school.ru\n'
            f'— Подайте заявку на курс, и преподаватель откроет вам доступ\n'
            f'— Следите за уведомлениями в личном кабинете\n\n'
            f'Если возникнут вопросы — задавайте их прямо под уроками, преподаватель отвечает лично.\n\n'
            f'Удачи в подготовке!',
            None,
            [user.email],
            fail_silently=True,
        )

        messages.success(request, 'Почта подтверждена! Добро пожаловать!')
        return redirect('index')

    return render(request, 'school/confirm_email_invalid.html')

def login_view(request):
    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password')
        user = authenticate(request, username=email, password=password)
        if user:
            login(request, user)
            return redirect('index')

        # Проверим — может аккаунт есть, но не подтверждён
        existing = User.objects.filter(email=email, is_active=False).first()
        if existing and existing.check_password(password):
            error = 'Аккаунт не подтверждён — проверьте почту, мы отправляли ссылку для подтверждения'
        else:
            error = 'Неверный email или пароль'

        return render(request, 'school/login.html', {
            'error': error,
            'email': email,
        })
    return render(request, 'school/login.html')

def logout_view(request):
    logout(request)
    return redirect('index')


def course_view(request, slug):
    course = get_object_or_404(Course, slug=slug)
    lessons = course.lessons.all()

    teacher_displays = course.teacher_displays.select_related('teacher').all()

    completed_ids = []
    enrollment = None
    if request.user.is_authenticated and not request.user.is_staff:
        enrollment = Enrollment.objects.filter(student=request.user, course=course).first()
        if enrollment and enrollment.status == Enrollment.STATUS_APPROVED:
            completed_ids = LessonProgress.objects.filter(
                student=request.user,
                lesson__in=lessons
            ).values_list('lesson_id', flat=True)

    benefits = course.benefits.all()
    audience = course.audience_items.all()
    steps = course.steps.all()

    modules = course.modules.prefetch_related('lessons').all()
    lessons_without_module = lessons.filter(module__isnull=True)

    why_cards = WhyUsBlock.objects.all()

    course_reviews = Review.objects.filter(is_published=True).prefetch_related('photos')
    if course.exam_type:
        course_reviews = course_reviews.filter(exam_type=course.exam_type)
    if course.subject:
        course_reviews = course_reviews.filter(subject=course.subject)

    faqs = FAQ.objects.all()

    return render(request, 'school/course.html', {
        'course': course,
        'lessons': lessons,
        'completed_ids': completed_ids,
        'enrollment': enrollment,
        'teacher_displays': teacher_displays,
        'benefits': benefits,
        'audience': audience,
        'steps': steps,
        'modules': modules,
        'lessons_without_module': lessons_without_module,
        'why_cards': why_cards,
        'course_reviews': course_reviews,
        'faqs': faqs,
        'stats': StatBlock.objects.all(),
    })

def is_checkpoint_passed(checkpoint, user):
    attempt = CheckpointAttempt.objects.filter(
        checkpoint=checkpoint, student=user
    ).order_by('-submitted_at').first()
    if not attempt:
        return False
    return attempt.all_passed

@login_required
def course_lessons_view(request, slug):
    course = get_object_or_404(Course, slug=slug)
    lessons = course.lessons.all()

    completed_ids = []
    checkpoints_passed = {}
    if not request.user.is_staff:
        Enrollment.objects.get_or_create(student=request.user, course=course)
        completed_ids = LessonProgress.objects.filter(
            student=request.user,
            lesson__in=lessons
        ).values_list('lesson_id', flat=True)

    modules = course.modules.prefetch_related('lessons').all()
    lessons_without_module = lessons.filter(module__isnull=True)
    checkpoints = course.checkpoints.prefetch_related('tasks').all()
    checkpoints_before_start = checkpoints.filter(after_module__isnull=True)
    exams = course.exams.all()

    exam_attempts = {}
    if not request.user.is_staff:
        for cp in checkpoints:
            checkpoints_passed[cp.id] = is_checkpoint_passed(cp, request.user)
        for exam in exams:
            last = ExamAttempt.objects.filter(exam=exam, student=request.user).order_by('-started_at').first()
            exam_attempts[exam.id] = last

    return render(request, 'school/course_lessons.html', {
        'course': course,
        'modules': modules,
        'lessons_without_module': lessons_without_module,
        'checkpoints': checkpoints,
        'checkpoints_before_start': checkpoints_before_start,
        'checkpoints_passed': checkpoints_passed,
        'exams': exams,
        'exam_attempts': exam_attempts,
        'completed_ids': completed_ids,
    })

@login_required
def lesson_view(request, pk):
    lesson = get_object_or_404(
        Lesson.objects.select_related('course', 'module'), pk=pk
    )

    from .models import LessonViewProgress
    from .services.lesson_flow import choose_lesson_step

    view_progress = None
    if not request.user.is_staff:
        view_progress, created = LessonViewProgress.objects.get_or_create(
            student=request.user, lesson=lesson
        )
        if not created:
            LessonViewProgress.objects.filter(pk=view_progress.pk).update(
                returns_count=view_progress.returns_count + 1
            )

    is_completed = LessonProgress.objects.filter(
        student=request.user, lesson=lesson
    ).exists()

    test_result = None
    if hasattr(lesson, 'test'):
        test_result = TestResult.objects.filter(
            student=request.user, test=lesson.test
        ).order_by('-created_at').first()

    homework = Homework.objects.filter(lesson=lesson).first()
    homework_submission = None
    if homework:
        homework_submission = HomeworkSubmission.objects.filter(
            homework=homework, student=request.user
        ).first()

    completed_ids = LessonProgress.objects.filter(
        student=request.user, lesson__course=lesson.course
    ).values_list('lesson_id', flat=True)
    next_lesson = (
        lesson.course.lessons
        .exclude(id__in=completed_ids).exclude(pk=lesson.pk)
        .order_by('module__order', 'order').first()
    )

    step = choose_lesson_step(
        lesson, view_progress, test_result, homework, homework_submission, next_lesson
    )

    comments = (
        lesson.comments.filter(parent=None)
        .select_related('author').prefetch_related('replies__author')
    )

    return render(request, 'school/lesson.html', {
        'lesson': lesson,
        'is_completed': is_completed,
        'test_result': test_result,
        'homework': homework,
        'homework_submission': homework_submission,
        'comments': comments,
        'timecodes': lesson.timecodes.all(),
        'view_progress': view_progress,
        'step': step,
        'next_lesson': next_lesson,
    })


@login_required
def lesson_video_progress(request, pk):
    """AJAX: сохранение позиции и процента просмотра."""
    from django.http import JsonResponse
    from django.utils import timezone as tz
    from .models import LessonViewProgress

    if request.method != 'POST' or request.user.is_staff:
        return JsonResponse({'ok': False}, status=400)

    lesson = get_object_or_404(Lesson, pk=pk)
    progress, _ = LessonViewProgress.objects.get_or_create(
        student=request.user, lesson=lesson
    )

    try:
        position = int(float(request.POST.get('position', 0)))
        percent = min(100, max(0, int(float(request.POST.get('percent', 0)))))
    except (TypeError, ValueError):
        return JsonResponse({'ok': False}, status=400)

    progress.position_seconds = position
    progress.watched_percent = max(progress.watched_percent, percent)
    if progress.is_watched and not progress.completed_at:
        progress.completed_at = tz.now()
    progress.save(update_fields=[
        'position_seconds', 'watched_percent', 'completed_at',
    ])

    return JsonResponse({'ok': True, 'watched': progress.is_watched})


@login_required
def lesson_mark_watched(request, pk):
    """Ручная отметка — когда видео недоступно или уже изучено."""
    from django.utils import timezone as tz
    from .models import LessonViewProgress

    lesson = get_object_or_404(Lesson, pk=pk)
    if request.method == 'POST' and not request.user.is_staff:
        progress, _ = LessonViewProgress.objects.get_or_create(
            student=request.user, lesson=lesson
        )
        progress.marked_manually = True
        progress.completed_at = progress.completed_at or tz.now()
        progress.save(update_fields=['marked_manually', 'completed_at'])
    return redirect('lesson', pk=pk)


@login_required
def complete_lesson(request, pk):
    lesson = get_object_or_404(Lesson, pk=pk)
    if not request.user.is_staff:
        LessonProgress.objects.get_or_create(student=request.user, lesson=lesson)
    return redirect('lesson', pk=pk)

@staff_member_required
def teacher_dashboard(request):
    if request.user.is_superuser:
        courses = Course.objects.all()
    else:
        courses = Course.objects.filter(teacher=request.user)
    return render(request, 'school/teacher/dashboard.html', {'courses': courses})

@staff_member_required
def teacher_course_dashboard(request, pk):
    course = get_object_or_404(Course, pk=pk)
    if not request.user.is_superuser and course.teacher != request.user:
        messages.error(request, 'У вас нет доступа к этому курсу')
        return redirect('teacher_dashboard')
    modules = course.modules.prefetch_related('lessons').all()
    lessons_without_module = course.lessons.filter(module__isnull=True)
    checkpoints = course.checkpoints.all()
    checkpoints_before_start = checkpoints.filter(after_module__isnull=True)
    exams = course.exams.all()
    return render(request, 'school/teacher/course_dashboard.html', {
        'course': course,
        'modules': modules,
        'lessons_without_module': lessons_without_module,
        'checkpoints': checkpoints,
        'checkpoints_before_start': checkpoints_before_start,
        'exams': exams,
    })


@staff_member_required
def teacher_add_course(request):
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        if title:
            course = Course.objects.create(
                title=title,
                description=request.POST.get('description', ''),
                teacher=request.user,
            )
            messages.success(request, 'Курс создан!')
            return redirect('teacher_course_dashboard', pk=course.pk)
        return render(request, 'school/teacher/add_course.html', {'errors': ['Введите название']})
    return render(request, 'school/teacher/add_course.html')


@staff_member_required
def teacher_add_lesson(request, pk):
    course = get_object_or_404(Course, pk=pk)
    if not request.user.is_superuser and course.teacher != request.user:
        messages.error(request, 'У вас нет доступа к этому курсу')
        return redirect('teacher_dashboard')
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
            if request.FILES.get('conspect'):
                lesson.conspect = request.FILES.get('conspect')
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
        if request.FILES.get('conspect'):
            lesson.conspect = request.FILES.get('conspect')
        lesson.save()
        messages.success(request, 'Урок обновлён!')
        return redirect('teacher_course_dashboard', pk=lesson.course.pk)
    return render(request, 'school/teacher/edit_lesson.html', {
        'lesson': lesson,
        'timecodes': lesson.timecodes.all(),
    })

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
        answers_log = []

        for question in questions:
            answer_id = request.POST.get(f'question_{question.id}')
            chosen = Answer.objects.filter(id=answer_id, question=question).first() if answer_id else None
            is_correct = bool(chosen and chosen.is_correct)
            if is_correct:
                correct += 1
            answers_log.append((question, chosen, is_correct))

        score = int((correct / total) * 100) if total > 0 else 0
        passed = score >= test.pass_score

        if not request.user.is_staff:
            key = request.POST.get('idempotency_key') or ''
            if key and TestResult.objects.filter(idempotency_key=key).exists():
                # Повторная отправка той же формы — попытка уже сохранена (ТЗ 4.8)
                return redirect('test_result', pk=lesson.pk)

            try:
                with transaction.atomic():
                    result = TestResult.objects.create(
                        student=request.user,
                        test=test,
                        score=score,
                        passed=passed,
                        idempotency_key=key or None,
                    )
                    for question, chosen, is_correct in answers_log:
                        log = TestAnswerLog.objects.create(
                            result=result,
                            question=question,
                            chosen_answer=chosen,
                            is_correct=is_correct,
                        )
                        record_answer_points(log, question, is_correct)

                    record_test_attempt(result, answers_log)
                    register_errors(request.user, result, answers_log)
                    resolve_errors_on_success(
                        request.user, answers_log,
                        session_key=request.session.session_key or '',
                    )

                    if passed:
                        LessonProgress.objects.get_or_create(
                            student=request.user, lesson=lesson
                        )
            except IntegrityError:
                # Два запроса пришли одновременно — второй проиграл гонку
                # на unique-ключе. Данные уже записаны первым, это не ошибка.
                pass

            return redirect('test_result', pk=lesson.pk)
        else:
            messages.success(request, f'Предпросмотр: результат {score}% (не сохранён)')
            return redirect('lesson', pk=lesson.pk)

    return render(request, 'school/test.html', {
        'lesson': lesson,
        'test': test,
        'questions': questions,
        'idempotency_key': uuid.uuid4().hex,
    })


@login_required
def test_result_view(request, pk):
    lesson = get_object_or_404(Lesson, pk=pk)
    test = get_object_or_404(Test, lesson=lesson)

    from .services.test_result import build_test_result

    results = TestResult.objects.filter(
        student=request.user, test=test
    ).order_by('-created_at')

    result = results.first()
    if not result:
        return redirect('test', pk=lesson.pk)

    previous_result = results[1] if results.count() > 1 else None

    answer_logs = (
        result.answer_logs
        .select_related('question', 'chosen_answer')
        .prefetch_related('question__answers')
    )

    completed_ids = LessonProgress.objects.filter(
        student=request.user, lesson__course=lesson.course
    ).values_list('lesson_id', flat=True)

    next_lesson = (
        lesson.course.lessons
        .exclude(id__in=completed_ids)
        .exclude(pk=lesson.pk)
        .order_by('module__order', 'order')
        .first()
    )

    data = build_test_result(
        student=request.user,
        lesson=lesson,
        result=result,
        answer_logs=answer_logs,
        previous_result=previous_result,
        next_lesson=next_lesson,
        attempt_number=results.count(),
    )

    return render(request, 'school/test_result.html', {
        'lesson': lesson,
        'test': test,
        'data': data,
        'result': result,          # для обратной совместимости
        'answer_logs': answer_logs,
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
                explanation=request.POST.get('explanation', ''),
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
    profile, created = TeacherProfile.objects.get_or_create(
        user=request.user,
        defaults={'name': request.user.first_name or request.user.username}
    )
    if request.method == 'POST':
        profile.name = request.POST.get('name')
        profile.subject = request.POST.get('subject', '')
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

    from .services.dashboard import build_dashboard

    dashboard = build_dashboard(request.user)

    pending_enrollments = Enrollment.objects.filter(
        student=request.user, status=Enrollment.STATUS_PENDING
    ).select_related('course')

    return render(request, 'school/home.html', {
        'dashboard': dashboard,
        'day_state': dashboard.day_state,
        'courses_progress': dashboard.courses,
        'weak_topics': dashboard.weak_topics,
        'pending_enrollments': pending_enrollments,
    })


@login_required
def student_courses(request):
    if request.user.is_staff:
        return redirect('teacher_dashboard')

    enrollments = Enrollment.objects.filter(
        student=request.user, status=Enrollment.STATUS_APPROVED
    ).select_related('course')

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

    return render(request, 'school/courses.html', {
        'courses_progress': courses_progress,
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
            comment = Comment.objects.create(
                lesson=lesson,
                author=request.user,
                text=text,
                parent=parent,
            )

            if not request.user.is_staff:
                # Уведомляем всех преподавателей о новом вопросе
                for teacher in User.objects.filter(is_staff=True):
                    Notification.objects.create(
                        user=teacher,
                        text=f'Новый вопрос к уроку «{lesson.title}» от {request.user.first_name} {request.user.last_name}',
                        link=f'/lesson/{lesson.pk}/',
                    )
            else:
                # Преподаватель ответил — уведомляем автора родительского комментария (если не сам себе)
                if parent and parent.author != request.user:
                    Notification.objects.create(
                        user=parent.author,
                        text=f'Ответ на ваш вопрос к уроку «{lesson.title}»',
                        link=f'/lesson/{lesson.pk}/',
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
    if not request.user.is_superuser and course.teacher != request.user:
        messages.error(request, 'У вас нет доступа к этому курсу')
        return redirect('teacher_dashboard')
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
        course.is_published = request.POST.get('is_published') == 'on'
        course.card_tag = request.POST.get('card_tag', '')
        course.card_features = request.POST.get('card_features', '')
        course.save()
        messages.success(request, 'Курс обновлён!')
        return redirect('teacher_course_dashboard', pk=course.pk)

    return render(request, 'school/teacher/edit_course.html', {
        'course': course,
        'teacher_displays': course.teacher_displays.select_related('teacher'),
        'all_teachers': TeacherProfile.objects.all(),
    })

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
        if homework.submission_type == Homework.SUBMISSION_TEXT and not text:
            errors.append('Введите текст ответа')
        elif homework.submission_type == Homework.SUBMISSION_FILE and not file:
            errors.append('Прикрепите файл')
        elif homework.submission_type == Homework.SUBMISSION_EITHER and not text and not file:
            errors.append('Введите текст ответа или прикрепите файл')

        key = request.POST.get('idempotency_key') or ''
        if key and HomeworkSubmission.objects.filter(idempotency_key=key).exists():
            # Повторная отправка той же формы — работа уже сдана (ТЗ 4.8)
            return redirect('homework', pk=lesson.pk)

        if not errors:
            try:
                HomeworkSubmission.objects.create(
                    homework=homework,
                    student=request.user,
                    text=text,
                    file=file,
                    attempt_number=submissions.count() + 1,
                    idempotency_key=key or None,
                )
                messages.success(request, 'Домашнее задание отправлено на проверку!')
            except IntegrityError:
                # Одновременные запросы: второй проиграл гонку на unique-ключе,
                # работа уже сохранена первым.
                pass
            return redirect('homework', pk=lesson.pk)

        return render(request, 'school/homework.html', {
            'lesson': lesson,
            'homework': homework,
            'last_submission': last_submission,
            'can_submit': can_submit,
            'errors': errors,
            'idempotency_key': uuid.uuid4().hex,
        })

    return render(request, 'school/homework.html', {
        'lesson': lesson,
        'homework': homework,
        'last_submission': last_submission,
        'can_submit': can_submit,
        'idempotency_key': uuid.uuid4().hex,
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
def teacher_delete_homework(request, pk):
    homework = get_object_or_404(Homework, pk=pk)
    lesson_pk = homework.lesson.pk
    course_pk = homework.lesson.course.pk
    if request.method == 'POST':
        homework.delete()
        messages.success(request, 'Домашнее задание удалено')
    return redirect('teacher_course_dashboard', pk=course_pk)

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
        record_homework_submission(submission)

        Notification.objects.create(
            user=submission.student,
            text=f'Проверена домашка «{homework.title}»',
            link=f'/lesson/{homework.lesson.pk}/homework/',
        )

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
    if not request.user.is_superuser and course.teacher != request.user:
        messages.error(request, 'У вас нет доступа к этому курсу')
        return redirect('teacher_dashboard')
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

        Notification.objects.create(
            user=enrollment.student,
            text=f'Заявка на курс «{enrollment.course.title}» одобрена!',
            link=f'/course/{enrollment.course.slug}/lessons/',
        )

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


@login_required
def checkpoint_view(request, pk):
    checkpoint = get_object_or_404(Checkpoint, pk=pk)
    tasks = checkpoint.tasks.all()

    if request.user.is_staff:
        messages.info(request, 'Вы просматриваете контрольную точку как преподаватель')
        return render(request, 'school/checkpoint.html', {
            'checkpoint': checkpoint,
            'tasks': tasks,
            'last_attempt': None,
        })

    last_attempt = CheckpointAttempt.objects.filter(
        checkpoint=checkpoint, student=request.user
    ).prefetch_related('answers__task').first()

    if request.method == 'POST':
        attempt = CheckpointAttempt.objects.create(checkpoint=checkpoint, student=request.user)

        for task in tasks:
            if task.task_type == CheckpointTask.TYPE_AUTO:
                answer_text = request.POST.get(f'answer_{task.id}', '').strip()
                correct_variants = [
                    line.strip().lower()
                    for line in task.correct_answers.splitlines() if line.strip()
                ]
                passed = answer_text.strip().lower() in correct_variants
                CheckpointAnswer.objects.create(
                    attempt=attempt,
                    task=task,
                    answer_text=answer_text,
                    status=CheckpointAnswer.STATUS_CHECKED,
                    passed=passed,
                    checked_at=timezone.now(),
                )
            else:
                CheckpointAnswer.objects.create(
                    attempt=attempt,
                    task=task,
                    answer_text=request.POST.get(f'answer_text_{task.id}', ''),
                    file=request.FILES.get(f'file_{task.id}'),
                )
            record_checkpoint_attempt(attempt)

        messages.success(request, 'Ответы отправлены!')
        return redirect('checkpoint_result', pk=attempt.pk)

    return render(request, 'school/checkpoint.html', {
        'checkpoint': checkpoint,
        'tasks': tasks,
        'last_attempt': last_attempt,
    })


@login_required
def checkpoint_result_view(request, pk):
    attempt = get_object_or_404(CheckpointAttempt, pk=pk)
    if attempt.student != request.user and not request.user.is_staff:
        return redirect('index')

    answers = attempt.answers.select_related('task').all()
    return render(request, 'school/checkpoint_result.html', {
        'attempt': attempt,
        'answers': answers,
    })

@staff_member_required
def teacher_add_checkpoint(request, pk):
    course = get_object_or_404(Course, pk=pk)
    if not request.user.is_superuser and course.teacher != request.user:
        messages.error(request, 'У вас нет доступа к этому курсу')
        return redirect('teacher_dashboard')
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        after_module_id = request.POST.get('after_module') or None

        if title:
            checkpoint = Checkpoint.objects.create(
                course=course,
                after_module_id=after_module_id,
                title=title,
            )
            messages.success(request, 'Контрольная точка создана! Теперь добавьте задания.')
            return redirect('teacher_edit_checkpoint', pk=checkpoint.pk)

        messages.warning(request, 'Введите название')
        return render(request, 'school/teacher/add_checkpoint.html', {'course': course})

    return render(request, 'school/teacher/add_checkpoint.html', {'course': course})

@staff_member_required
def teacher_edit_checkpoint(request, pk):
    checkpoint = get_object_or_404(Checkpoint, pk=pk)
    if request.method == 'POST':
        checkpoint.title = request.POST.get('title', '').strip()
        checkpoint.after_module_id = request.POST.get('after_module') or None
        checkpoint.save()
        messages.success(request, 'Контрольная точка обновлена!')
        return redirect('teacher_course_dashboard', pk=checkpoint.course.pk)
    tasks = checkpoint.tasks.all()
    return render(request, 'school/teacher/edit_checkpoint.html', {
        'checkpoint': checkpoint,
        'tasks': tasks,
    })

@staff_member_required
def teacher_add_checkpoint_task(request, pk):
    checkpoint = get_object_or_404(Checkpoint, pk=pk)
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()

        errors = []
        if not title:
            errors.append('Введите название задания')
        if not description:
            errors.append('Введите текст задания')

        if not errors:
            CheckpointTask.objects.create(
                checkpoint=checkpoint,
                title=title,
                description=description,
                task_type=request.POST.get('task_type'),
                correct_answers=request.POST.get('correct_answers', ''),
                submission_type=request.POST.get('submission_type', Homework.SUBMISSION_TEXT),
                order=checkpoint.tasks.count() + 1,
            )
            messages.success(request, 'Задание добавлено!')
            return redirect('teacher_edit_checkpoint', pk=checkpoint.pk)

        messages.warning(request, ' '.join(errors))
    return redirect('teacher_edit_checkpoint', pk=checkpoint.pk)


@staff_member_required
def teacher_delete_checkpoint(request, pk):
    checkpoint = get_object_or_404(Checkpoint, pk=pk)
    course_pk = checkpoint.course.pk
    if request.method == 'POST':
        checkpoint.delete()
        messages.success(request, 'Контрольная точка удалена')
    return redirect('teacher_course_dashboard', pk=course_pk)

@staff_member_required
def teacher_checkpoint_attempts(request, pk):
    checkpoint = get_object_or_404(Checkpoint, pk=pk)
    attempts = checkpoint.attempts.select_related('student').prefetch_related('answers__task').all()
    return render(request, 'school/teacher/checkpoint_attempts.html', {
        'checkpoint': checkpoint,
        'attempts': attempts,
    })


@staff_member_required
def teacher_check_checkpoint_attempt(request, pk):
    attempt = get_object_or_404(CheckpointAttempt, pk=pk)
    answers = attempt.answers.select_related('task').all()

    if request.method == 'POST':
        for answer in answers:
            if answer.task.task_type == CheckpointTask.TYPE_MANUAL:
                passed_value = request.POST.get(f'passed_{answer.id}')
                comment_value = request.POST.get(f'comment_{answer.id}', '')
                if passed_value is not None:
                    answer.passed = passed_value == 'yes'
                    answer.teacher_comment = comment_value
                    answer.status = CheckpointAnswer.STATUS_CHECKED
                    answer.checked_at = timezone.now()
                    answer.save()
                    record_checkpoint_attempt(attempt)

        Notification.objects.create(
            user=attempt.student,
            text=f'Проверена контрольная точка «{attempt.checkpoint.title}»',
            link=f'/checkpoint-result/{attempt.pk}/',
        )


        messages.success(request, 'Проверено!')
        return redirect(request.META.get('HTTP_REFERER', 'teacher_all_checkpoints'))

    return render(request, 'school/teacher/check_checkpoint_attempt.html', {
        'attempt': attempt,
        'answers': answers,
    })

@staff_member_required
def teacher_delete_checkpoint_task(request, pk):
    task = get_object_or_404(CheckpointTask, pk=pk)
    checkpoint_pk = task.checkpoint.pk
    if request.method == 'POST':
        task.delete()
        messages.success(request, 'Задание удалено')
    return redirect('teacher_edit_checkpoint', pk=checkpoint_pk)

@staff_member_required
def teacher_all_checkpoints(request):
    attempts = CheckpointAttempt.objects.select_related(
        'student', 'checkpoint', 'checkpoint__course'
    ).prefetch_related('answers__task').all()

    course_id = request.GET.get('course')
    checkpoint_id = request.GET.get('checkpoint')
    status = request.GET.get('status')

    if course_id:
        attempts = attempts.filter(checkpoint__course_id=course_id)
    if checkpoint_id:
        attempts = attempts.filter(checkpoint_id=checkpoint_id)

    # Группируем по (ученик, точка) — последняя попытка первая
    groups = {}
    for a in attempts:
        key = (a.student_id, a.checkpoint_id)
        groups.setdefault(key, []).append(a)

    grouped_list = []
    for (student_id, checkpoint_id_), items in groups.items():
        items.sort(key=lambda x: x.submitted_at, reverse=True)
        latest = items[0]

        if status == 'pending' and not latest.has_pending:
            continue
        if status == 'checked' and latest.has_pending:
            continue

        grouped_list.append({
            'latest': latest,
            'history': items[1:],
            'attempts_count': len(items),
        })

    grouped_list.sort(key=lambda g: (not g['latest'].has_pending, -g['latest'].submitted_at.timestamp()))

    courses = Course.objects.all()
    checkpoints = Checkpoint.objects.all()
    if course_id:
        checkpoints = checkpoints.filter(course_id=course_id)

    pending_count = sum(1 for g in grouped_list if g['latest'].has_pending)

    return render(request, 'school/teacher/all_checkpoints.html', {
        'grouped_list': grouped_list,
        'courses': courses,
        'checkpoints': checkpoints,
        'selected_course': course_id,
        'selected_checkpoint': checkpoint_id,
        'selected_status': status,
        'pending_count': pending_count,
    })

@login_required
def mark_notification_read(request, pk):
    notification = get_object_or_404(Notification, pk=pk, user=request.user)
    notification.is_read = True
    notification.save()
    if notification.link:
        return redirect(notification.link)
    return redirect('student_profile')


@login_required
def all_notifications(request):
    notifications = Notification.objects.filter(user=request.user)
    return render(request, 'school/notifications.html', {'notifications': notifications})


@login_required
def clear_notifications(request):
    if request.method == 'POST':
        Notification.objects.filter(user=request.user).delete()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'status': 'ok'})
        messages.success(request, 'Уведомления очищены')
    return redirect('all_notifications')


@login_required
def delete_notification(request, pk):
    notification = get_object_or_404(Notification, pk=pk, user=request.user)
    if request.method == 'POST':
        notification.delete()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'status': 'ok'})
    return redirect('all_notifications')


@login_required
def exam_start_view(request, pk):
    exam = get_object_or_404(ExamMock, pk=pk)

    if request.user.is_staff:
        messages.info(request, 'Вы просматриваете пробник как преподаватель')
        return redirect('teacher_course_dashboard', pk=exam.course.pk)

    # Есть ли уже незавершённая попытка — продолжаем её вместо создания новой
    existing = ExamAttempt.objects.filter(
        exam=exam, student=request.user, submitted_at__isnull=True
    ).first()

    if existing:
        if timezone.now() >= existing.deadline:
            _finalize_exam_attempt(existing, auto=True)
            return redirect('exam_result', pk=existing.pk)
        return redirect('exam_attempt', pk=existing.pk)

    attempt = ExamAttempt.objects.create(exam=exam, student=request.user)
    return redirect('exam_attempt', pk=attempt.pk)


@login_required
def exam_attempt_view(request, pk):
    attempt = get_object_or_404(ExamAttempt, pk=pk)
    if attempt.student != request.user:
        return redirect('index')

    if attempt.is_finished:
        return redirect('exam_result', pk=attempt.pk)

    if timezone.now() >= attempt.deadline:
        _finalize_exam_attempt(attempt, auto=True)
        return redirect('exam_result', pk=attempt.pk)

    tasks = attempt.exam.tasks.all()
    remaining_seconds = int((attempt.deadline - timezone.now()).total_seconds())

    if request.method == 'POST':
        _save_exam_answers(attempt, tasks, request)
        attempt.submitted_at = timezone.now()
        attempt.save()
        record_exam_attempt(attempt)
        messages.success(request, 'Пробник завершён!')
        return redirect('exam_result', pk=attempt.pk)

    return render(request, 'school/exam_attempt.html', {
        'attempt': attempt,
        'tasks': tasks,
        'remaining_seconds': remaining_seconds,
    })


def _save_exam_answers(attempt, tasks, request):
    for task in tasks:
        if task.task_type == ExamTask.TYPE_AUTO:
            answer_text = request.POST.get(f'answer_{task.id}', '').strip()
            correct_variants = [
                line.strip().lower()
                for line in task.correct_answers.splitlines() if line.strip()
            ]
            passed = answer_text.strip().lower() in correct_variants
            ExamAnswer.objects.create(
                attempt=attempt,
                task=task,
                answer_text=answer_text,
                status=ExamAnswer.STATUS_CHECKED,
                passed=passed,
                checked_at=timezone.now(),
            )
        else:
            ExamAnswer.objects.create(
                attempt=attempt,
                task=task,
                answer_text=request.POST.get(f'answer_text_{task.id}', ''),
                file=request.FILES.get(f'file_{task.id}'),
            )


def _finalize_exam_attempt(attempt, auto=False):
    # Автозавершение без ответов на оставшиеся задания (если что-то не успели отправить)
    tasks = attempt.exam.tasks.all()
    answered_task_ids = set(attempt.answers.values_list('task_id', flat=True))
    for task in tasks:
        if task.id not in answered_task_ids:
            if task.task_type == ExamTask.TYPE_AUTO:
                ExamAnswer.objects.create(
                    attempt=attempt, task=task, answer_text='',
                    status=ExamAnswer.STATUS_CHECKED, passed=False,
                    checked_at=timezone.now(),
                )
            else:
                ExamAnswer.objects.create(attempt=attempt, task=task, answer_text='')
    attempt.submitted_at = timezone.now()
    attempt.auto_submitted = auto
    attempt.save()
    record_exam_attempt(attempt)


@login_required
def exam_result_view(request, pk):
    attempt = get_object_or_404(ExamAttempt, pk=pk)
    if attempt.student != request.user and not request.user.is_staff:
        return redirect('index')

    answers = attempt.answers.select_related('task').all()
    return render(request, 'school/exam_result.html', {
        'attempt': attempt,
        'answers': answers,
    })


@staff_member_required
def teacher_add_exam(request, pk):
    course = get_object_or_404(Course, pk=pk)
    if not request.user.is_superuser and course.teacher != request.user:
        messages.error(request, 'У вас нет доступа к этому курсу')
        return redirect('teacher_dashboard')
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        duration = request.POST.get('duration_minutes', '').strip()

        errors = []
        if not title:
            errors.append('Введите название')
        if not duration or not duration.isdigit():
            errors.append('Укажите время в минутах числом')

        if not errors:
            exam = ExamMock.objects.create(
                course=course,
                title=title,
                description=request.POST.get('description', ''),
                duration_minutes=duration,
                order=course.exams.count() + 1,
            )
            messages.success(request, 'Пробник создан! Теперь добавьте задания.')
            return redirect('teacher_edit_exam', pk=exam.pk)

        messages.warning(request, ' '.join(errors))
        return render(request, 'school/teacher/add_exam.html', {'course': course})

    return render(request, 'school/teacher/add_exam.html', {'course': course})


@staff_member_required
def teacher_edit_exam(request, pk):
    exam = get_object_or_404(ExamMock, pk=pk)
    if request.method == 'POST':
        exam.title = request.POST.get('title', '').strip()
        exam.description = request.POST.get('description', '')
        duration = request.POST.get('duration_minutes', '').strip()
        exam.duration_minutes = duration if duration.isdigit() else exam.duration_minutes
        exam.save()
        messages.success(request, 'Пробник обновлён!')
        return redirect('teacher_course_dashboard', pk=exam.course.pk)
    tasks = exam.tasks.all()
    return render(request, 'school/teacher/edit_exam.html', {
        'exam': exam,
        'tasks': tasks,
    })


@staff_member_required
def teacher_delete_exam(request, pk):
    exam = get_object_or_404(ExamMock, pk=pk)
    course_pk = exam.course.pk
    if request.method == 'POST':
        exam.delete()
        messages.success(request, 'Пробник удалён')
    return redirect('teacher_course_dashboard', pk=course_pk)


@staff_member_required
def teacher_add_exam_task(request, pk):
    exam = get_object_or_404(ExamMock, pk=pk)
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()

        errors = []
        if not title:
            errors.append('Введите название задания')
        if not description:
            errors.append('Введите текст задания')

        if not errors:
            ExamTask.objects.create(
                exam=exam,
                title=title,
                description=description,
                task_type=request.POST.get('task_type'),
                correct_answers=request.POST.get('correct_answers', ''),
                submission_type=request.POST.get('submission_type', Homework.SUBMISSION_TEXT),
                order=exam.tasks.count() + 1,
            )
            messages.success(request, 'Задание добавлено!')
            return redirect('teacher_edit_exam', pk=exam.pk)

        messages.warning(request, ' '.join(errors))
    return redirect('teacher_edit_exam', pk=exam.pk)


@staff_member_required
def teacher_delete_exam_task(request, pk):
    task = get_object_or_404(ExamTask, pk=pk)
    exam_pk = task.exam.pk
    if request.method == 'POST':
        task.delete()
        messages.success(request, 'Задание удалено')
    return redirect('teacher_edit_exam', pk=exam_pk)


@staff_member_required
def teacher_all_exams(request):
    attempts = ExamAttempt.objects.filter(submitted_at__isnull=False).select_related(
        'student', 'exam', 'exam__course'
    ).prefetch_related('answers__task').all()

    course_id = request.GET.get('course')
    exam_id = request.GET.get('exam')
    status = request.GET.get('status')

    if course_id:
        attempts = attempts.filter(exam__course_id=course_id)
    if exam_id:
        attempts = attempts.filter(exam_id=exam_id)

    groups = {}
    for a in attempts:
        key = (a.student_id, a.exam_id)
        groups.setdefault(key, []).append(a)

    grouped_list = []
    for (student_id, exam_id_), items in groups.items():
        items.sort(key=lambda x: x.submitted_at, reverse=True)
        latest = items[0]

        if status == 'pending' and not latest.has_pending:
            continue
        if status == 'checked' and latest.has_pending:
            continue

        grouped_list.append({
            'latest': latest,
            'history': items[1:],
            'attempts_count': len(items),
        })

    grouped_list.sort(key=lambda g: (not g['latest'].has_pending, -g['latest'].submitted_at.timestamp()))

    courses = Course.objects.all()
    exams = ExamMock.objects.all()
    if course_id:
        exams = exams.filter(course_id=course_id)

    pending_count = sum(1 for g in grouped_list if g['latest'].has_pending)

    return render(request, 'school/teacher/all_exams.html', {
        'grouped_list': grouped_list,
        'courses': courses,
        'exams': exams,
        'selected_course': course_id,
        'selected_exam': exam_id,
        'selected_status': status,
        'pending_count': pending_count,
    })


@staff_member_required
def teacher_check_exam_attempt(request, pk):
    attempt = get_object_or_404(ExamAttempt, pk=pk)
    answers = attempt.answers.select_related('task').all()

    if request.method == 'POST':
        for answer in answers:
            if answer.task.task_type == ExamTask.TYPE_MANUAL:
                passed_value = request.POST.get(f'passed_{answer.id}')
                comment_value = request.POST.get(f'comment_{answer.id}', '')
                if passed_value is not None:
                    answer.passed = passed_value == 'yes'
                    answer.teacher_comment = comment_value
                    answer.status = ExamAnswer.STATUS_CHECKED
                    answer.checked_at = timezone.now()
                    answer.save()
                    record_exam_attempt(attempt)

        Notification.objects.create(
            user=attempt.student,
            text=f'Проверен пробник «{attempt.exam.title}»',
            link=f'/exam-result/{attempt.pk}/',
        )

        messages.success(request, 'Проверено!')
        return redirect(request.META.get('HTTP_REFERER', 'teacher_all_exams'))

    return render(request, 'school/teacher/check_exam_attempt.html', {
        'attempt': attempt,
        'answers': answers,
    })

@login_required
def student_analytics(request):
    if request.user.is_staff:
        return redirect('teacher_dashboard')

    from .services.analytics_page import build_analytics

    return render(request, 'school/student_analytics.html', {
        'data': build_analytics(request.user),
    })

@login_required
def continue_learning(request, course_pk):
    if request.user.is_staff:
        return redirect('teacher_dashboard')

    course = get_object_or_404(Course, pk=course_pk)

    enrollment = Enrollment.objects.filter(
        student=request.user, course=course, status=Enrollment.STATUS_APPROVED
    ).first()
    if not enrollment:
        return redirect('course', slug=course.slug)

    completed_ids = LessonProgress.objects.filter(
        student=request.user, lesson__course=course
    ).values_list('lesson_id', flat=True)

    # Первый непройденный урок: сначала по модулям (в порядке модулей и уроков), потом без модуля
    next_lesson = None
    for module in course.modules.prefetch_related('lessons').all():
        for lesson in module.lessons.all():
            if lesson.id not in completed_ids:
                next_lesson = lesson
                break
        if next_lesson:
            break

    if not next_lesson:
        for lesson in course.lessons.filter(module__isnull=True):
            if lesson.id not in completed_ids:
                next_lesson = lesson
                break

    if next_lesson:
        return redirect('lesson', pk=next_lesson.pk)

    # Всё пройдено — на список уроков
    messages.success(request, '🎉 Все уроки курса пройдены!')
    return redirect('course_lessons', slug=course.slug)


@login_required
def error_notebook(request):
    if request.user.is_staff:
        return redirect('teacher_dashboard')

    from .services import analytics_repository as repo
    from .models import ErrorStatus

    status_filter = request.GET.get('status', '')
    group_by = request.GET.get('group', 'lesson')

    groups = repo.get_error_records(
        request.user,
        status=status_filter or None,
        group_by=group_by,
    )
    stats = repo.get_error_stats(request.user)

    return render(request, 'school/error_notebook.html', {
        'groups': groups,
        'stats': stats,
        'status_filter': status_filter,
        'group_by': group_by,
        'status_choices': ErrorStatus.choices,
    })


@login_required
def error_detail(request, pk):
    """Разбор одной ошибки: объяснение, верный ответ, похожее задание."""
    from .services import analytics_repository as repo

    record = repo.get_error_record_for_student(request.user, pk)
    if not record:
        return redirect('error_notebook')

    correct_answer = None
    if record.question:
        correct_answer = next(
            (a for a in record.question.answers.all() if a.is_correct), None
        )

    attempts = list(record.correction_attempts.all())
    correct_attempts = [a for a in attempts if a.is_correct]
    sessions = {a.session_key for a in correct_attempts if a.session_key}

    return render(request, 'school/error_detail.html', {
        'record': record,
        'correct_answer': correct_answer,
        'attempts': attempts,
        'progress': {
            'explanation_viewed': bool(record.explanation_viewed_at),
            'correct_count': len(correct_attempts),
            'session_count': len(sessions),
            'can_reinforce': record.can_be_reinforced(),
        },
    })


@login_required
def error_mark_explained(request, pk):
    """Отметка «объяснение изучено» — первое из трёх условий закрепления."""
    from django.utils import timezone as tz
    from .models import ErrorRecord, ErrorStatus

    record = get_object_or_404(ErrorRecord, pk=pk, student=request.user)
    if request.method == 'POST' and not record.explanation_viewed_at:
        record.explanation_viewed_at = tz.now()
        if record.status == ErrorStatus.NOT_ANALYZED:
            record.status = ErrorStatus.IN_PROGRESS
        record.save(update_fields=['explanation_viewed_at', 'status'])
        record.try_reinforce()
        messages.success(request, 'Отмечено. Теперь решите похожее задание.')
    return redirect('error_detail', pk=pk)

def all_reviews_view(request):
    reviews = Review.objects.filter(is_published=True).prefetch_related('photos')
    return render(request, 'school/all_reviews.html', {'reviews': reviews})

@staff_member_required
def teacher_add_timecode(request, pk):
    lesson = get_object_or_404(Lesson, pk=pk)
    if request.method == 'POST':
        minutes = int(request.POST.get('minutes', 0) or 0)
        seconds = int(request.POST.get('seconds', 0) or 0)
        label = request.POST.get('label', '').strip()
        if label:
            Timecode.objects.create(
                lesson=lesson,
                time_seconds=minutes * 60 + seconds,
                label=label,
                order=lesson.timecodes.count() + 1,
            )
            messages.success(request, 'Таймкод добавлен!')
    return redirect('teacher_edit_lesson', pk=lesson.pk)


@staff_member_required
def teacher_delete_timecode(request, pk):
    timecode = get_object_or_404(Timecode, pk=pk)
    lesson_pk = timecode.lesson.pk
    if request.method == 'POST':
        timecode.delete()
        messages.success(request, 'Таймкод удалён')
    return redirect('teacher_edit_lesson', pk=lesson_pk)

@staff_member_required
def teacher_add_course_teacher(request, pk):
    course = get_object_or_404(Course, pk=pk)
    if request.method == 'POST':
        teacher_id = request.POST.get('teacher_id')
        teacher_profile = get_object_or_404(TeacherProfile, pk=teacher_id)
        display, created = CourseTeacherDisplay.objects.get_or_create(
            course=course, teacher=teacher_profile,
            defaults={'order': course.teacher_displays.count() + 1}
        )
        display.name_override = request.POST.get('name_override', '')
        display.bio_override = request.POST.get('bio_override', '')
        if request.FILES.get('photo_override'):
            display.photo_override = request.FILES.get('photo_override')
        display.save()
        messages.success(request, 'Преподаватель добавлен на страницу курса!')
    return redirect('teacher_edit_course', pk=pk)


@staff_member_required
def teacher_delete_course_teacher(request, pk):
    display = get_object_or_404(CourseTeacherDisplay, pk=pk)
    course_pk = display.course.pk
    if request.method == 'POST':
        display.delete()
        messages.success(request, 'Преподаватель удалён со страницы курса')
    return redirect('teacher_edit_course', pk=course_pk)


@login_required
def study_plan_view(request):
    if request.user.is_staff:
        return redirect('teacher_dashboard')

    from datetime import timedelta
    from django.utils import timezone as tz
    from .models import PlanItem, PlanStatus, StudyPlan

    mode = request.GET.get('mode', 'today')
    today = tz.localdate()

    plans = StudyPlan.objects.filter(student=request.user, status='active')
    items = (
        PlanItem.objects
        .filter(plan__in=plans)
        .exclude(status__in=PlanStatus.cancelled())
        .select_related('plan', 'plan__subject')
        .order_by('due_at', 'priority', 'order')
    )

    # Просроченные помечаем на лету
    PlanItem.objects.filter(
        plan__in=plans, status=PlanStatus.PLANNED, due_at__lt=tz.now()
    ).update(status=PlanStatus.OVERDUE)

    if mode == 'week':
        end = today + timedelta(days=6)
        visible = items.filter(due_at__date__gte=today, due_at__date__lte=end)
    elif mode == 'all':
        visible = items
    else:
        visible = items.filter(due_at__date__lte=today)

    overdue = items.filter(status=PlanStatus.OVERDUE)
    today_items = items.filter(due_at__date=today)
    done_today = today_items.filter(status__in=PlanStatus.completed()).count()

    by_day = {}
    for item in visible:
        by_day.setdefault(item.due_at.date(), []).append(item)

    days = [
        {
            'date': day,
            'items': day_items,
            'minutes': sum(i.estimated_minutes for i in day_items),
            'is_today': day == today,
        }
        for day, day_items in sorted(by_day.items())
    ]

    return render(request, 'school/plan.html', {
        'mode': mode,
        'days': days,
        'today': today,
        'overdue_count': overdue.count(),
        'today_total': today_items.count(),
        'today_done': done_today,
        'has_plan': plans.exists(),
    })


@login_required
def plan_generate(request):
    """Создать или пересобрать план по всем курсам ученика."""
    from .services.analytics_repository import get_enrolled_courses
    from .services.planner import build_plan_for_student

    if request.method == 'POST' and not request.user.is_staff:
        created = 0
        for course in get_enrolled_courses(request.user):
            if build_plan_for_student(request.user, course):
                created += 1
        if created:
            messages.success(request, 'План составлен')
        else:
            messages.info(request, 'Пока нечего планировать — все задачи выполнены')
    return redirect('study_plan')


@login_required
def plan_item_complete(request, pk):
    """Отметить задачу выполненной."""
    from .models import PlanItem

    item = get_object_or_404(PlanItem, pk=pk, plan__student=request.user)
    if request.method == 'POST':
        item.mark_completed()
        messages.success(request, 'Задача выполнена')
    return redirect('study_plan')


@login_required
def plan_item_skip(request, pk):
    from .models import PlanItem, PlanStatus

    item = get_object_or_404(PlanItem, pk=pk, plan__student=request.user)
    if request.method == 'POST':
        item.status = PlanStatus.SKIPPED
        item.save(update_fields=['status'])
    return redirect('study_plan')

@login_required
def study_heartbeat(request):
    """
    Пульс активности от клиента. Вызывается раз в минуту,
    только когда вкладка видима (ТЗ 15.11).
    """
    from django.http import JsonResponse
    from django.utils import timezone as tz

    from .models import StudySession
    from .services.study_time import seconds_to_add

    if request.method != 'POST' or request.user.is_staff:
        return JsonResponse({'ok': False}, status=400)

    client_id = (request.POST.get('session_id') or '')[:64]
    if not client_id:
        return JsonResponse({'ok': False}, status=400)

    now = tz.now()
    activity_type = (request.POST.get('activity') or '')[:30]
    course_id = request.POST.get('course_id') or None

    session, created = StudySession.objects.get_or_create(
        student=request.user,
        client_session_id=client_id,
        defaults={
            'activity_type': activity_type,
            'course_id': course_id if str(course_id).isdigit() else None,
        },
    )

    if not created:
        delta = seconds_to_add(session.last_activity_at, now)
        StudySession.objects.filter(pk=session.pk).update(
            active_seconds=session.active_seconds + delta,
            last_activity_at=now,
            activity_type=activity_type or session.activity_type,
        )
        session.active_seconds += delta

    return JsonResponse({'ok': True, 'seconds': session.active_seconds})

@login_required
def practice_home(request):
    if request.user.is_staff:
        return redirect('teacher_dashboard')

    from .models import ErrorRecord, ErrorStatus, PracticeSession, Question
    from .services.analytics_repository import get_enrolled_courses
    from .services.practice import MODE_DESCRIPTIONS

    courses = list(get_enrolled_courses(request.user))

    selected_course_id = request.GET.get('course')
    selected_course = None
    if selected_course_id:
        selected_course = next(
            (c for c in courses if str(c.pk) == selected_course_id), None
        )
    if not selected_course and courses:
        selected_course = courses[0]

    lessons = selected_course.lessons.all() if selected_course else []

    unresolved_errors = 0
    if selected_course:
        unresolved_errors = (
            ErrorRecord.objects
            .filter(student=request.user, lesson__course=selected_course)
            .exclude(status=ErrorStatus.REINFORCED)
            .count()
        )
        bank_size = Question.objects.filter(
            is_in_bank=True
        ).filter(
            models.Q(lesson__course=selected_course) |
            models.Q(test__lesson__course=selected_course)
        ).count()
    else:
        bank_size = 0

    recent = (
        PracticeSession.objects
        .filter(student=request.user, finished_at__isnull=False)
        .select_related('lesson', 'course')[:5]
    )
    unfinished = (
        PracticeSession.objects
        .filter(student=request.user, finished_at__isnull=True)
        .first()
    )

    return render(request, 'school/practice_home.html', {
        'modes': MODE_DESCRIPTIONS,
        'courses': courses,
        'selected_course': selected_course,
        'lessons': lessons,
        'unresolved_errors': unresolved_errors,
        'bank_size': bank_size,
        'recent_sessions': recent,
        'unfinished': unfinished,
    })


@login_required
def practice_start(request):
    """Создание сессии по выбранному режиму."""
    from .models import Course, Lesson
    from .services.practice import DEFAULT_TASK_COUNT, create_session

    if request.method != 'POST':
        return redirect('practice_home')

    mode = request.POST.get('mode', 'mixed')
    lesson_id = request.POST.get('lesson') or None
    course_id = request.POST.get('course') or None
    try:
        count = int(request.POST.get('count', DEFAULT_TASK_COUNT))
    except (TypeError, ValueError):
        count = DEFAULT_TASK_COUNT

    lesson = Lesson.objects.filter(pk=lesson_id).first() if lesson_id else None
    course = Course.objects.filter(pk=course_id).first() if course_id else None
    if lesson and not course:
        course = lesson.course

    session = create_session(
        request.user, mode, course=course, lesson=lesson, count=count
    )
    if not session:
        messages.info(
            request,
            'По этому режиму пока нет заданий. Попробуйте другой режим или '
            'обратитесь к преподавателю.',
        )
        return redirect('practice_home')

    return redirect('practice_session', pk=session.pk)


@login_required
def practice_session_view(request, pk):
    """Экран текущего задания."""
    from .models import PracticeSession

    session = get_object_or_404(PracticeSession, pk=pk, student=request.user)
    if session.is_finished:
        return redirect('practice_result', pk=session.pk)

    current = session.next_answer()
    if not current:
        from .services.practice import finish_session
        finish_session(session)
        return redirect('practice_result', pk=session.pk)

    total = session.total_count
    progress_percent = int(current.order / total * 100) if total else 0

    return render(request, 'school/practice_task.html', {
        'session': session,
        'answer': current,
        'question': current.question,
        'answers': current.question.answers.all(),
        'position': current.order,
        'total': total,
        'progress_percent': progress_percent,
    })


@login_required
def practice_submit(request, pk):
    """Проверка ответа с показом разбора."""
    from .models import PracticeAnswer, PracticeSession
    from .services.practice import skip_answer, submit_answer

    session = get_object_or_404(PracticeSession, pk=pk, student=request.user)
    if request.method != 'POST' or session.is_finished:
        return redirect('practice_session', pk=pk)

    answer_id = request.POST.get('answer_id')
    practice_answer = get_object_or_404(
        PracticeAnswer, pk=answer_id, session=session
    )

    if request.POST.get('action') == 'skip':
        skip_answer(practice_answer)
        return redirect('practice_session', pk=pk)

    if request.POST.get('mark_review'):
        practice_answer.marked_for_review = True

    question = practice_answer.question
    if question.answer_type == 'text':
        payload = request.POST.get('text_answer', '')
    elif question.answer_type == 'multiple':
        payload = request.POST.getlist('choice')
    else:
        payload = request.POST.get('choice', '')

    try:
        time_spent = int(request.POST.get('time_spent', 0))
    except (TypeError, ValueError):
        time_spent = 0

    is_correct, earned, maximum = submit_answer(practice_answer, payload, time_spent)

    return render(request, 'school/practice_feedback.html', {
        'session': session,
        'answer': practice_answer,
        'question': question,
        'answers': question.answers.all(),
        'is_correct': is_correct,
        'earned': earned,
        'maximum': maximum,
        'has_next': session.next_answer() is not None,
    })


@login_required
def practice_result(request, pk):
    """Итог сессии."""
    from .models import PracticeSession
    from .services.practice import finish_session

    session = get_object_or_404(
        PracticeSession.objects.prefetch_related('answers__question'),
        pk=pk, student=request.user,
    )
    if not session.is_finished:
        finish_session(session)
        session.refresh_from_db()

    answers = list(session.answers.select_related('question').all())
    wrong = [a for a in answers if not a.is_correct and not a.skipped]
    skipped = [a for a in answers if a.skipped]

    percent = 0
    if session.max_points and session.max_points > 0:
        percent = int(float(session.earned_points) / float(session.max_points) * 100)

    return render(request, 'school/practice_result.html', {
        'session': session,
        'answers': answers,
        'wrong': wrong,
        'skipped': skipped,
        'correct_count': len(answers) - len(wrong) - len(skipped),
        'percent': percent,
    })


@login_required
def practice_mark_error_type(request, pk):
    """Ученик уточняет тип своей ошибки (ТЗ 9)."""
    from .models import ErrorRecord, PracticeAnswer

    practice_answer = get_object_or_404(
        PracticeAnswer, pk=pk, session__student=request.user
    )
    if request.method == 'POST':
        error_type = request.POST.get('error_type', '')
        practice_answer.error_type = error_type
        practice_answer.save(update_fields=['error_type'])
        ErrorRecord.objects.filter(
            student=request.user, question=practice_answer.question
        ).update(error_type=error_type)
    return redirect('practice_result', pk=practice_answer.session_id)

@login_required
def onboarding_goal(request):
    if request.user.is_staff:
        return redirect('teacher_dashboard')

    from datetime import date
    from .models import StudentProfile, StudentSubjectGoal
    from .services.analytics_repository import get_enrolled_courses

    courses = list(get_enrolled_courses(request.user))
    profile, _ = StudentProfile.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        for course in courses:
            if not course.subject_ref:
                continue
            score = request.POST.get(f'target_{course.pk}')
            year = request.POST.get(f'year_{course.pk}')
            exam_date = request.POST.get(f'date_{course.pk}') or None
            if not score:
                continue
            StudentSubjectGoal.objects.update_or_create(
                student=profile, subject=course.subject_ref,
                exam_year=int(year) if year else date.today().year + 1,
                defaults={
                    'target_test_score': int(score),
                    'exam_date': exam_date,
                    'is_active': True,
                },
            )

        profile.available_days_per_week = int(request.POST.get('days', 5))
        profile.daily_minutes = int(request.POST.get('minutes', 60))
        profile.onboarding_completed = True
        profile.save()

        messages.success(request, 'Цель настроена! Прогноз будет учитывать её.')
        return redirect('student_profile')

    existing_goals = {
        g.subject_id: g for g in profile.goals.filter(is_active=True)
    }

    return render(request, 'school/onboarding_goal.html', {
        'courses': courses,
        'existing_goals': existing_goals,
        'profile': profile,
        'current_year': date.today().year,
    })

@login_required
def mocks_list(request):
    if request.user.is_staff:
        return redirect('teacher_dashboard')

    from .services.analytics_repository import get_mocks_overview
    return render(request, 'school/mocks_list.html', {
        'overview': get_mocks_overview(request.user),
    })