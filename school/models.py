from django.core.exceptions import ValidationError
from django.db import models
from django.contrib.auth.models import User

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone as dj_timezone

from django.utils import timezone

from cloudinary.models import CloudinaryField

from django.utils.text import slugify

from django.core.validators import MinValueValidator, MaxValueValidator


class AnalyticsDataQuality(models.TextChoices):
    """
    Точность первичных баллов попытки.

    EXACT         — записаны в момент прохождения (с шага 3.2.5);
    RECONSTRUCTED — восстановлены из логов ответов и Question.points — достоверны;
    ESTIMATED     — пересчитаны из процента, приблизительны;
    LEGACY        — восстановить невозможно, в расчётах не участвуют.
    """
    EXACT = 'exact', 'Точные данные'
    RECONSTRUCTED = 'reconstructed', 'Восстановленные данные'
    ESTIMATED = 'estimated', 'Приблизительные данные'
    LEGACY = 'legacy', 'Недостаточно данных'


class PrimaryScoreMixin(models.Model):
    """
    Первичные баллы попытки/ответа.

    Оба поля nullable: старые записи до backfill остаются пустыми,
    аналитика такие записи пропускает (ТЗ-уточнение 5в).
    """
    earned_points = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0)],
        verbose_name='Полученные первичные баллы',
    )
    max_points = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0)],
        verbose_name='Максимальные первичные баллы',
    )

    class Meta:
        abstract = True


class AnalyticsQualityMixin(models.Model):
    """Качество данных. Только для моделей попыток, не для отдельных ответов."""
    analytics_data_quality = models.CharField(
        max_length=15,
        choices=AnalyticsDataQuality.choices,
        default=AnalyticsDataQuality.LEGACY,
        db_index=True,
        verbose_name='Качество аналитических данных',
    )

    class Meta:
        abstract = True

class Subject(models.Model):
    """
    Нормализованный предмет.

    Вводится параллельно строковому Course.subject: legacy-поле продолжает
    работать, переключение чтения — на этапе 4 (ТЗ-уточнение 8).
    """
    code = models.SlugField(max_length=50, unique=True, verbose_name='Код')
    name = models.CharField(max_length=100, unique=True, verbose_name='Название')
    is_active = models.BooleanField(default=True, verbose_name='Активен')
    order = models.PositiveSmallIntegerField(default=0, verbose_name='Порядок')

    class Meta:
        verbose_name = 'Предмет'
        verbose_name_plural = 'Предметы'
        ordering = ['order', 'name']

    def __str__(self):
        return self.name


class Course(models.Model):
    EXAM_EGE = 'ege'
    EXAM_OGE = 'oge'
    EXAM_CHOICES = [
        (EXAM_EGE, 'ЕГЭ'),
        (EXAM_OGE, 'ОГЭ'),
    ]
    title = models.CharField(max_length=200, verbose_name='Название')
    slug = models.SlugField(max_length=220, unique=True, blank=True, verbose_name='Адрес страницы')
    description = models.TextField(verbose_name='Описание')
    image = models.ImageField(upload_to='courses/', blank=True, verbose_name='Обложка')
    is_published = models.BooleanField(default=True, verbose_name='Опубликован')

    teacher = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='courses', verbose_name='Преподаватель')

    card_tag = models.CharField(max_length=50, blank=True, verbose_name='Тег на карточке (например «9 класс»)')
    card_features = models.TextField(blank=True, verbose_name='Пункты на карточке (по одному на строку)')

    exam_type = models.CharField(max_length=10, choices=EXAM_CHOICES,
                                 blank=True, verbose_name='Тип экзамена')
    subject = models.CharField(max_length=100, blank=True, verbose_name='Предмет')
    subject_ref = models.ForeignKey(
        'Subject', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='courses',
        verbose_name='Предмет (нормализованный)',
    )

    created_at = models.DateTimeField(auto_now_add=True)

    teacher = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='courses', verbose_name='Преподаватель')
    nav_short_name = models.CharField(max_length=50, blank=True,
                                      verbose_name='Короткое название для меню (например «Профильная», «Базовая»)')

    class Meta:
        verbose_name = 'Курс'
        verbose_name_plural = 'Курсы'
        ordering = ['-created_at']

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if self.subject:
            self.subject = self.subject.strip()
        if not self.slug:
            base_slug = slugify(self.title) or 'course'
            slug = base_slug
            n = 1
            while Course.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                n += 1
                slug = f'{base_slug}-{n}'
            self.slug = slug
        super().save(*args, **kwargs)

class CourseBenefit(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE,
                               related_name='benefits', verbose_name='Курс')
    icon = models.CharField(max_length=30, default='check-circle', verbose_name='Иконка')
    title = models.CharField(max_length=200, blank=True, verbose_name='Заголовок')
    text = models.CharField(max_length=300, verbose_name='Описание')
    order = models.PositiveIntegerField(default=0, verbose_name='Порядок')

    class Meta:
        verbose_name = 'Пункт «Что получит ученик»'
        verbose_name_plural = 'Пункты «Что получит ученик»'
        ordering = ['order']

    def __str__(self):
        return self.title or self.text


class CourseAudience(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE,
                               related_name='audience_items', verbose_name='Курс')
    icon = models.CharField(max_length=30, default='target', verbose_name='Иконка')
    title = models.CharField(max_length=200, blank=True, verbose_name='Заголовок')
    text = models.CharField(max_length=300, verbose_name='Описание')
    order = models.PositiveIntegerField(default=0, verbose_name='Порядок')

    class Meta:
        verbose_name = 'Пункт «Кому подойдёт»'
        verbose_name_plural = 'Пункты «Кому подойдёт»'
        ordering = ['order']

    def __str__(self):
        return self.title or self.text


class CourseStep(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE,
                               related_name='steps', verbose_name='Курс')
    icon = models.CharField(max_length=30, default='play-circle', verbose_name='Иконка')
    title = models.CharField(max_length=200, blank=True, verbose_name='Заголовок')
    text = models.CharField(max_length=300, verbose_name='Описание')
    order = models.PositiveIntegerField(default=0, verbose_name='Порядок')

    class Meta:
        verbose_name = 'Шаг «Как проходит обучение»'
        verbose_name_plural = 'Шаги «Как проходит обучение»'
        ordering = ['order']

    def __str__(self):
        return self.title or self.text

class Module(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE,
                               related_name='modules', verbose_name='Курс')
    title = models.CharField(max_length=200, verbose_name='Название раздела')
    order = models.PositiveIntegerField(default=0, verbose_name='Порядок')

    class Meta:
        verbose_name = 'Раздел курса'
        verbose_name_plural = 'Разделы курса'
        ordering = ['order']

    def __str__(self):
        return f'{self.order}. {self.title}'

class Lesson(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE,
                               related_name='lessons', verbose_name='Курс')
    module = models.ForeignKey(Module, on_delete=models.SET_NULL,
                               null=True, blank=True,
                               related_name='lessons', verbose_name='Раздел')
    title = models.CharField(max_length=200, verbose_name='Название')
    description = models.TextField(blank=True, verbose_name='Описание')
    video_file = CloudinaryField(resource_type='video', blank=True, null=True)
    video_url = models.URLField(blank=True, verbose_name='Ссылка на видео (VK/YouTube)')
    conspect = CloudinaryField(resource_type='raw', blank=True, null=True, verbose_name='Конспект (PDF)')
    order = models.PositiveIntegerField(default=0, verbose_name='Порядок')
    created_at = models.DateTimeField(auto_now_add=True)
    learning_goal = models.TextField(
        blank=True, verbose_name='Учебная цель',
        help_text='Что ученик будет уметь после урока. Одно-два предложения.',
    )
    duration_minutes = models.PositiveSmallIntegerField(
        default=0, verbose_name='Длительность, мин',
        help_text='0 — не показывать',
    )

    class Meta:
        verbose_name = 'Урок'
        verbose_name_plural = 'Уроки'
        ordering = ['order']

    def __str__(self):
        return f'{self.order}. {self.title}'


class Enrollment(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_REJECTED = 'rejected'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'На рассмотрении'),
        (STATUS_APPROVED, 'Одобрено'),
        (STATUS_REJECTED, 'Отклонено'),
    ]

    student = models.ForeignKey(User, on_delete=models.CASCADE,
                                related_name='enrollments', verbose_name='Ученик')
    course = models.ForeignKey(Course, on_delete=models.CASCADE,
                               related_name='enrollments', verbose_name='Курс')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES,
                              default=STATUS_PENDING, verbose_name='Статус')
    enrolled_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Запись на курс'
        verbose_name_plural = 'Записи на курсы'
        unique_together = ('student', 'course')

    def __str__(self):
        return f'{self.student.username} → {self.course.title} ({self.status})'


class LessonProgress(models.Model):
    """Какие уроки ученик уже прошёл"""
    student = models.ForeignKey(User, on_delete=models.CASCADE,
                                related_name='progress', verbose_name='Ученик')
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE,
                               related_name='progress', verbose_name='Урок')
    completed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Прогресс'
        verbose_name_plural = 'Прогресс'
        unique_together = ('student', 'lesson')  # нельзя пройти дважды

    def __str__(self):
        return f'{self.student.username} ✓ {self.lesson.title}'

class Test(models.Model):
    lesson = models.OneToOneField(Lesson, on_delete=models.CASCADE,
                                  related_name='test', verbose_name='Урок')
    title = models.CharField(max_length=200, verbose_name='Название теста')
    pass_score = models.PositiveIntegerField(default=70,
                                             verbose_name='Проходной балл (%)')

    class Meta:
        verbose_name = 'Тест'
        verbose_name_plural = 'Тесты'

    def __str__(self):
        return f'Тест: {self.lesson.title}'

class AnswerType(models.TextChoices):
    SINGLE = 'single', 'Один вариант'
    MULTIPLE = 'multiple', 'Несколько вариантов'
    TEXT = 'text', 'Короткий ответ'

class Question(models.Model):
    # --- Банк заданий (задание может существовать вне теста) ---
    test = models.ForeignKey(
        Test, on_delete=models.CASCADE, related_name='questions',
        null=True, blank=True, verbose_name='Тест',
    )
    lesson = models.ForeignKey(
        Lesson, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='bank_questions', verbose_name='Тема',
    )
    exam_task_number = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name='Номер задания ЕГЭ',
    )
    answer_type = models.CharField(
        max_length=10, choices=AnswerType.choices,
        default=AnswerType.SINGLE, verbose_name='Тип ответа',
    )
    correct_text = models.CharField(
        max_length=300, blank=True,
        verbose_name='Правильный ответ (для короткого ответа)',
        help_text='Несколько допустимых вариантов — через точку с запятой',
    )
    is_in_bank = models.BooleanField(
        default=False, db_index=True, verbose_name='В банке заданий',
    )
    text = models.TextField(verbose_name='Вопрос')
    order = models.PositiveIntegerField(default=0, verbose_name='Порядок')
    explanation = models.TextField(blank=True, verbose_name='Объяснение (показывается при ошибке)')
    points = models.PositiveSmallIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
        verbose_name='Максимальный первичный балл',
    )

    @property
    def effective_lesson(self):
        """Тема задания: своя или через тест."""
        if self.lesson_id:
            return self.lesson
        return self.test.lesson if self.test_id else None

    def check_answer(self, payload) -> tuple[bool, float]:
        """
        Проверка ответа. Возвращает (верно_полностью, набранные_баллы).
        Для множественного выбора баллы частичные (ТЗ 9).
        """
        from decimal import Decimal

        points = Decimal(str(self.points or 1))

        if self.answer_type == AnswerType.TEXT:
            given = _normalize_answer(payload if isinstance(payload, str) else '')
            variants = [
                _normalize_answer(v) for v in (self.correct_text or '').split(';')
            ]
            correct = bool(given) and given in variants
            return correct, float(points if correct else 0)

        chosen_ids = set()
        if isinstance(payload, (list, tuple, set)):
            chosen_ids = {int(x) for x in payload if str(x).isdigit()}
        elif str(payload).isdigit():
            chosen_ids = {int(payload)}

        answers = list(self.answers.all())
        correct_ids = {a.id for a in answers if a.is_correct}
        if not correct_ids:
            return False, 0.0

        if self.answer_type == AnswerType.SINGLE:
            correct = chosen_ids == correct_ids
            return correct, float(points if correct else 0)

        hits = len(chosen_ids & correct_ids)
        misses = len(chosen_ids - correct_ids)
        ratio = max(0.0, (hits - misses) / len(correct_ids))
        earned = float(points) * ratio
        return ratio >= 1.0, round(earned, 2)

    class Meta:
        verbose_name = 'Вопрос'
        verbose_name_plural = 'Вопросы'
        ordering = ['order']

    def __str__(self):
        return f'{self.order}. {self.text[:50]}'

def _normalize_answer(value: str) -> str:
    """Нормализация короткого ответа: регистр, пробелы, ё."""
    return (
        (value or '')
        .strip().lower()
        .replace('ё', 'е')
        .replace(' ', '')
        .replace(',', '')
    )

class Answer(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE,
                                 related_name='answers', verbose_name='Вопрос')
    text = models.CharField(max_length=300, verbose_name='Ответ')
    is_correct = models.BooleanField(default=False, verbose_name='Правильный')

    class Meta:
        verbose_name = 'Ответ'
        verbose_name_plural = 'Ответы'

    def __str__(self):
        return f'{"✓" if self.is_correct else "✗"} {self.text}'


class TestResult(PrimaryScoreMixin, AnalyticsQualityMixin, models.Model):
    student = models.ForeignKey(User, on_delete=models.CASCADE,
                                related_name='test_results', verbose_name='Ученик')
    test = models.ForeignKey(Test, on_delete=models.CASCADE,
                             related_name='results', verbose_name='Тест')
    score = models.PositiveIntegerField(verbose_name='Результат (%)')
    passed = models.BooleanField(verbose_name='Сдан')
    created_at = models.DateTimeField(auto_now_add=True)
    idempotency_key = models.CharField(
        max_length=64, null=True, blank=True, unique=True, db_index=True,
        verbose_name='Ключ идемпотентности',
    )

    class Meta:
        verbose_name = 'Результат теста'
        verbose_name_plural = 'Результаты тестов'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.student.username} — {self.test} — {self.score}%'

class TestAnswerLog(PrimaryScoreMixin, models.Model):
    result = models.ForeignKey(TestResult, on_delete=models.CASCADE,
                               related_name='answer_logs', verbose_name='Результат')
    question = models.ForeignKey(Question, on_delete=models.CASCADE, verbose_name='Вопрос')
    chosen_answer = models.ForeignKey(Answer, on_delete=models.CASCADE,
                                      null=True, blank=True, verbose_name='Выбранный ответ')
    is_correct = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'Ответ в тесте'
        verbose_name_plural = 'Ответы в тестах'

class TeacherProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE,
                                related_name='teacher_profile', verbose_name='Аккаунт')
    name = models.CharField(max_length=200, verbose_name='Короткая фраза или имя')
    subject = models.CharField(max_length=100, blank=True, verbose_name='Предмет')
    subject_ref = models.ForeignKey(
        'Subject', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='teachers',
        verbose_name='Предмет (нормализованный)',
    )
    exam_type = models.CharField(max_length=10, choices=Course.EXAM_CHOICES,
                                 blank=True, verbose_name='Тип экзамена')
    bio = models.TextField(verbose_name='О себе')
    photo = models.ImageField(upload_to='teacher/', blank=True, verbose_name='Фото')

    class Meta:
        verbose_name = 'Профиль преподавателя'
        verbose_name_plural = 'Профили преподавателей'

    def __str__(self):
        return self.name

class Review(models.Model):
    student_name = models.CharField(max_length=100, verbose_name='Имя ученика')
    city = models.CharField(max_length=100, blank=True, verbose_name='Город')
    subject = models.CharField(max_length=100, blank=True, verbose_name='Предмет')
    subject_ref = models.ForeignKey(
        'Subject', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='reviews',
        verbose_name='Предмет (нормализованный)',
    )
    exam_type = models.CharField(max_length=10, choices=Course.EXAM_CHOICES,
                                 blank=True, verbose_name='Тип экзамена')
    text = models.TextField(verbose_name='Текст отзыва')
    score_before = models.CharField(max_length=10, blank=True, verbose_name='Балл «было»')
    score_after = models.CharField(max_length=10, blank=True, verbose_name='Балл «стало»')
    is_published = models.BooleanField(default=True, verbose_name='Опубликован')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Отзыв'
        verbose_name_plural = 'Отзывы'
        ordering = ['-created_at']

    def __str__(self):
        return self.student_name


class ReviewPhoto(models.Model):
    review = models.ForeignKey(Review, on_delete=models.CASCADE,
                               related_name='photos', verbose_name='Отзыв')
    image = models.ImageField(upload_to='reviews/', verbose_name='Фото')
    order = models.PositiveIntegerField(default=0, verbose_name='Порядок')

    class Meta:
        verbose_name = 'Фото к отзыву'
        verbose_name_plural = 'Фото к отзыву'
        ordering = ['order']


class FAQ(models.Model):
    question = models.CharField(max_length=300, verbose_name='Вопрос')
    answer = models.TextField(verbose_name='Ответ')
    order = models.PositiveIntegerField(default=0, verbose_name='Порядок')

    class Meta:
        verbose_name = 'Вопрос-ответ'
        verbose_name_plural = 'FAQ'
        ordering = ['order']

    def __str__(self):
        return self.question

class Comment(models.Model):
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE,
                               related_name='comments', verbose_name='Урок')
    author = models.ForeignKey(User, on_delete=models.CASCADE,
                               related_name='comments', verbose_name='Автор')
    text = models.TextField(verbose_name='Текст')
    parent = models.ForeignKey('self', on_delete=models.CASCADE,
                               null=True, blank=True,
                               related_name='replies', verbose_name='Ответ на')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Комментарий'
        verbose_name_plural = 'Комментарии'
        ordering = ['created_at']

    def __str__(self):
        return f'{self.author.username}: {self.text[:50]}'

class WhyUsBlock(models.Model):
    icon = models.CharField(max_length=30, default='✦', verbose_name='Иконка (эмодзи)')
    title = models.CharField(max_length=100, verbose_name='Заголовок')
    text = models.TextField(verbose_name='Текст')
    order = models.PositiveIntegerField(default=0, verbose_name='Порядок')

    class Meta:
        verbose_name = 'Блок "Почему мы"'
        verbose_name_plural = 'Блоки "Почему мы"'
        ordering = ['order']

    def __str__(self):
        return self.title


class StatBlock(models.Model):
    icon = models.CharField(max_length=30, default='⭐', verbose_name='Эмодзи')
    number = models.CharField(max_length=20, verbose_name='Число')
    label = models.CharField(max_length=100, verbose_name='Подпись')
    order = models.PositiveIntegerField(default=0, verbose_name='Порядок')

    class Meta:
        verbose_name = 'Цифра-достижение'
        verbose_name_plural = 'Цифры-достижения'
        ordering = ['order']

    def __str__(self):
        return f'{self.number} — {self.label}'

class Homework(models.Model):
    SUBMISSION_TEXT = 'text'
    SUBMISSION_FILE = 'file'
    SUBMISSION_EITHER = 'either'
    SUBMISSION_CHOICES = [
        (SUBMISSION_TEXT, 'Только текст'),
        (SUBMISSION_FILE, 'Только файл'),
        (SUBMISSION_EITHER, 'Текст или файл (на выбор)'),
    ]

    GRADING_SCORE = 'score'
    GRADING_PASS_FAIL = 'pass_fail'
    GRADING_COMMENT_ONLY = 'comment_only'
    GRADING_CHOICES = [
        (GRADING_SCORE, 'Баллы (0-100)'),
        (GRADING_PASS_FAIL, 'Зачёт / незачёт'),
        (GRADING_COMMENT_ONLY, 'Только комментарий'),
    ]

    lesson = models.OneToOneField(Lesson, on_delete=models.CASCADE,
                                  related_name='homework', verbose_name='Урок')
    title = models.CharField(max_length=200, verbose_name='Название задания')
    description = models.TextField(verbose_name='Текст задания')
    submission_type = models.CharField(max_length=10, choices=SUBMISSION_CHOICES,
                                       default=SUBMISSION_TEXT, verbose_name='Формат сдачи')
    grading_type = models.CharField(max_length=15, choices=GRADING_CHOICES,
                                    default=GRADING_PASS_FAIL, verbose_name='Формат оценки')
    allow_resubmit = models.BooleanField(default=True, verbose_name='Разрешить пересдачу')

    class Meta:
        verbose_name = 'Домашнее задание'
        verbose_name_plural = 'Домашние задания'

    def __str__(self):
        return f'ДЗ: {self.lesson.title}'


class HomeworkSubmission(PrimaryScoreMixin, AnalyticsQualityMixin,  models.Model):
    STATUS_PENDING = 'pending'
    STATUS_CHECKED = 'checked'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'На проверке'),
        (STATUS_CHECKED, 'Проверено'),
    ]

    homework = models.ForeignKey(Homework, on_delete=models.CASCADE,
                                 related_name='submissions', verbose_name='Задание')
    student = models.ForeignKey(User, on_delete=models.CASCADE,
                                related_name='homework_submissions', verbose_name='Ученик')
    text = models.TextField(blank=True, verbose_name='Текст ответа')
    file = CloudinaryField('raw', resource_type='raw', blank=True, null=True)

    status = models.CharField(max_length=10, choices=STATUS_CHOICES,
                              default=STATUS_PENDING, verbose_name='Статус')
    score = models.PositiveIntegerField(null=True, blank=True, verbose_name='Баллы')
    passed = models.BooleanField(null=True, blank=True, verbose_name='Зачёт')
    teacher_comment = models.TextField(blank=True, verbose_name='Комментарий преподавателя')

    submitted_at = models.DateTimeField(auto_now_add=True)
    checked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Сдача домашнего задания'
        verbose_name_plural = 'Сдачи домашних заданий'
        ordering = ['-submitted_at']

    def __str__(self):
        return f'{self.student.username} — {self.homework.title}'

class Checkpoint(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE,
                               related_name='checkpoints', verbose_name='Курс')
    after_module = models.ForeignKey(Module, on_delete=models.SET_NULL,
                                     null=True, blank=True, related_name='+',
                                     verbose_name='После раздела (пусто = в начале курса)')
    title = models.CharField(max_length=200, verbose_name='Название')
    order = models.PositiveIntegerField(default=0, verbose_name='Порядок среди точек в этом месте')

    class Meta:
        verbose_name = 'Контрольная точка'
        verbose_name_plural = 'Контрольные точки'
        ordering = ['order']

    def __str__(self):
        return f'Точка: {self.title}'


class CheckpointTask(models.Model):
    TYPE_AUTO = 'auto'
    TYPE_MANUAL = 'manual'
    TYPE_CHOICES = [
        (TYPE_AUTO, 'Автопроверка текста'),
        (TYPE_MANUAL, 'Проверка преподавателем'),
    ]

    checkpoint = models.ForeignKey(Checkpoint, on_delete=models.CASCADE,
                                   related_name='tasks', verbose_name='Точка')
    title = models.CharField(max_length=200, verbose_name='Название задания')
    description = models.TextField(verbose_name='Задание')
    task_type = models.CharField(max_length=10, choices=TYPE_CHOICES,
                                 default=TYPE_MANUAL, verbose_name='Тип проверки')
    correct_answers = models.TextField(blank=True, verbose_name='Правильные ответы (по одному на строку)')
    submission_type = models.CharField(max_length=10, choices=Homework.SUBMISSION_CHOICES,
                                       default=Homework.SUBMISSION_TEXT, verbose_name='Формат сдачи')
    order = models.PositiveIntegerField(default=0, verbose_name='Порядок')
    points = models.PositiveSmallIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
        verbose_name='Максимальный первичный балл',
    )

    class Meta:
        verbose_name = 'Задание контрольной точки'
        verbose_name_plural = 'Задания контрольной точки'
        ordering = ['order']

    def __str__(self):
        return f'{self.checkpoint.title} — {self.title}'

class CheckpointAttempt(PrimaryScoreMixin, AnalyticsQualityMixin, models.Model):
    checkpoint = models.ForeignKey(Checkpoint, on_delete=models.CASCADE,
                                   related_name='attempts', verbose_name='Точка')
    student = models.ForeignKey(User, on_delete=models.CASCADE,
                                related_name='checkpoint_attempts', verbose_name='Ученик')
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Попытка контрольной точки'
        verbose_name_plural = 'Попытки контрольных точек'
        ordering = ['-submitted_at']

    def __str__(self):
        return f'{self.student.username} — {self.checkpoint.title}'

    @property
    def all_passed(self):
        answers = self.answers.select_related('task')
        if not answers:
            return False
        for a in answers:
            if a.task.task_type == CheckpointTask.TYPE_MANUAL and a.status != 'checked':
                return False
            if not a.passed:
                return False
        return True

    @property
    def has_pending(self):
        return self.answers.filter(task__task_type=CheckpointTask.TYPE_MANUAL, status='pending').exists()


class CheckpointAnswer(PrimaryScoreMixin, models.Model):
    STATUS_PENDING = 'pending'
    STATUS_CHECKED = 'checked'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'На проверке'),
        (STATUS_CHECKED, 'Проверено'),
    ]

    attempt = models.ForeignKey(CheckpointAttempt, on_delete=models.CASCADE,
                                related_name='answers', verbose_name='Попытка')
    task = models.ForeignKey(CheckpointTask, on_delete=models.CASCADE,
                             related_name='answers', verbose_name='Задание')
    answer_text = models.TextField(blank=True, verbose_name='Ответ')
    file = CloudinaryField(resource_type='raw', blank=True, null=True, verbose_name='Файл')

    status = models.CharField(max_length=10, choices=STATUS_CHOICES,
                              default=STATUS_PENDING, verbose_name='Статус')
    passed = models.BooleanField(null=True, blank=True, verbose_name='Зачтено')
    teacher_comment = models.TextField(blank=True, verbose_name='Комментарий')
    checked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Ответ на задание точки'
        verbose_name_plural = 'Ответы на задания точки'

    def __str__(self):
        return f'{self.attempt} — {self.task.title}'

class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE,
                             related_name='notifications', verbose_name='Получатель')
    text = models.CharField(max_length=300, verbose_name='Текст')
    link = models.CharField(max_length=300, blank=True, verbose_name='Ссылка')
    is_read = models.BooleanField(default=False, verbose_name='Прочитано')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Уведомление'
        verbose_name_plural = 'Уведомления'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user.username}: {self.text[:50]}'

class ExamMock(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE,
                               related_name='exams', verbose_name='Курс')
    title = models.CharField(max_length=200, verbose_name='Название')
    description = models.TextField(blank=True, verbose_name='Описание')
    duration_minutes = models.PositiveIntegerField(default=60, verbose_name='Время на выполнение (минут)')
    order = models.PositiveIntegerField(default=0, verbose_name='Порядок')

    class Meta:
        verbose_name = 'Пробник ЕГЭ'
        verbose_name_plural = 'Пробники ЕГЭ'
        ordering = ['order']

    def __str__(self):
        return self.title


class ExamTask(models.Model):
    TYPE_AUTO = 'auto'
    TYPE_MANUAL = 'manual'
    TYPE_CHOICES = [
        (TYPE_AUTO, 'Автопроверка текста'),
        (TYPE_MANUAL, 'Проверка преподавателем'),
    ]

    exam = models.ForeignKey(ExamMock, on_delete=models.CASCADE,
                             related_name='tasks', verbose_name='Пробник')
    title = models.CharField(max_length=200, verbose_name='Название задания')
    description = models.TextField(verbose_name='Задание')
    task_type = models.CharField(max_length=10, choices=TYPE_CHOICES,
                                 default=TYPE_MANUAL, verbose_name='Тип проверки')
    correct_answers = models.TextField(blank=True, verbose_name='Правильные ответы (по одному на строку)')
    submission_type = models.CharField(max_length=10, choices=Homework.SUBMISSION_CHOICES,
                                       default=Homework.SUBMISSION_TEXT, verbose_name='Формат сдачи')
    order = models.PositiveIntegerField(default=0, verbose_name='Порядок')
    points = models.PositiveSmallIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
        verbose_name='Максимальный первичный балл',
    )

    class Meta:
        verbose_name = 'Задание пробника'
        verbose_name_plural = 'Задания пробника'
        ordering = ['order']

    def __str__(self):
        return f'{self.exam.title} — {self.title}'


class ExamAttempt(PrimaryScoreMixin, AnalyticsQualityMixin, models.Model):
    exam = models.ForeignKey(ExamMock, on_delete=models.CASCADE,
                             related_name='attempts', verbose_name='Пробник')
    student = models.ForeignKey(User, on_delete=models.CASCADE,
                                related_name='exam_attempts', verbose_name='Ученик')
    started_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    auto_submitted = models.BooleanField(default=False, verbose_name='Отправлено автоматически по таймеру')

    class Meta:
        verbose_name = 'Попытка пробника'
        verbose_name_plural = 'Попытки пробника'
        ordering = ['-started_at']

    def __str__(self):
        return f'{self.student.username} — {self.exam.title}'

    @property
    def deadline(self):
        return self.started_at + timezone.timedelta(minutes=self.exam.duration_minutes)

    @property
    def is_finished(self):
        return self.submitted_at is not None

    @property
    def all_passed(self):
        answers = self.answers.select_related('task')
        if not answers:
            return False
        for a in answers:
            if a.task.task_type == ExamTask.TYPE_MANUAL and a.status != 'checked':
                return False
            if not a.passed:
                return False
        return True

    @property
    def has_pending(self):
        return self.answers.filter(task__task_type=ExamTask.TYPE_MANUAL, status='pending').exists()

    @property
    def auto_score_percent(self):
        auto_answers = self.answers.filter(task__task_type=ExamTask.TYPE_AUTO)
        total = auto_answers.count()
        if total == 0:
            return None
        correct = auto_answers.filter(passed=True).count()
        return int((correct / total) * 100)


class ExamAnswer(PrimaryScoreMixin, models.Model):
    STATUS_PENDING = 'pending'
    STATUS_CHECKED = 'checked'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'На проверке'),
        (STATUS_CHECKED, 'Проверено'),
    ]

    attempt = models.ForeignKey(ExamAttempt, on_delete=models.CASCADE,
                                related_name='answers', verbose_name='Попытка')
    task = models.ForeignKey(ExamTask, on_delete=models.CASCADE,
                             related_name='answers', verbose_name='Задание')
    answer_text = models.TextField(blank=True, verbose_name='Ответ')
    file = CloudinaryField(resource_type='raw', blank=True, null=True, verbose_name='Файл')

    status = models.CharField(max_length=10, choices=STATUS_CHOICES,
                              default=STATUS_PENDING, verbose_name='Статус')
    passed = models.BooleanField(null=True, blank=True, verbose_name='Зачтено')
    teacher_comment = models.TextField(blank=True, verbose_name='Комментарий')
    checked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Ответ на задание пробника'
        verbose_name_plural = 'Ответы на задания пробника'

    def __str__(self):
        return f'{self.attempt} — {self.task.title}'

class FearBlock(models.Model):
    question = models.CharField(max_length=200, verbose_name='Страх (вопрос в кавычках)')
    answer = models.TextField(verbose_name='Ответ (можно с <b>жирным</b>)')
    order = models.PositiveIntegerField(default=0, verbose_name='Порядок')

    class Meta:
        verbose_name = 'Блок «Страхи»'
        verbose_name_plural = 'Блоки «Страхи»'
        ordering = ['order']

    def __str__(self):
        return self.question


class ParentBlock(models.Model):
    icon = models.CharField(max_length=30, default='✓', verbose_name='Эмодзи')
    title = models.CharField(max_length=150, verbose_name='Заголовок')
    text = models.TextField(verbose_name='Текст')
    order = models.PositiveIntegerField(default=0, verbose_name='Порядок')

    class Meta:
        verbose_name = 'Блок «Родителям»'
        verbose_name_plural = 'Блоки «Родителям»'
        ordering = ['order']

    def __str__(self):
        return self.title


class SiteSettings(models.Model):
    """Единственная запись — общие настройки главной страницы"""
    hero_eyebrow = models.CharField(max_length=200, default='егэ и огэ по русскому — без паники',
                                    verbose_name='Надпись над заголовком (рукописная)')
    hero_title = models.CharField(max_length=300, default='сдай русский на максимум с личным преподавателем',
                                  verbose_name='Главный заголовок')
    hero_subtitle = models.TextField(default='', blank=True, verbose_name='Подзаголовок')
    grade_number = models.CharField(max_length=10, default='100', verbose_name='Число в кружке на фото')
    grade_label = models.CharField(max_length=20, default='ЕГЭ', verbose_name='Подпись в кружке')
    platform_screenshot = models.ImageField(upload_to='site/', blank=True,
                                            verbose_name='Скриншот личного кабинета')

    class Meta:
        verbose_name = 'Настройки главной'
        verbose_name_plural = 'Настройки главной'

    def __str__(self):
        return 'Настройки главной страницы'

class Timecode(models.Model):
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE,
                               related_name='timecodes', verbose_name='Урок')
    time_seconds = models.PositiveIntegerField(verbose_name='Время (в секундах)')
    label = models.CharField(max_length=200, verbose_name='Подпись')
    order = models.PositiveIntegerField(default=0, verbose_name='Порядок')

    class Meta:
        verbose_name = 'Таймкод'
        verbose_name_plural = 'Таймкоды'
        ordering = ['time_seconds']

    def __str__(self):
        return f'{self.time_seconds}с — {self.label}'

    @property
    def formatted_time(self):
        minutes = self.time_seconds // 60
        seconds = self.time_seconds % 60
        return f'{minutes}:{seconds:02d}'

class CourseTeacherDisplay(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE,
                               related_name='teacher_displays', verbose_name='Курс')
    teacher = models.ForeignKey(TeacherProfile, on_delete=models.CASCADE,
                                related_name='course_displays', verbose_name='Преподаватель')
    name_override = models.CharField(max_length=200, blank=True,
                                     verbose_name='Другая короткая фраза/имя для этого курса')
    bio_override = models.TextField(blank=True,
                                    verbose_name='Другой текст/описание для этого курса')
    photo_override = models.ImageField(upload_to='course_teacher/', blank=True,
                                       verbose_name='Другое фото для этого курса')
    order = models.PositiveIntegerField(default=0, verbose_name='Порядок')

    class Meta:
        verbose_name = 'Преподаватель на странице курса'
        verbose_name_plural = 'Преподаватели на странице курса'
        ordering = ['order']
        unique_together = ('course', 'teacher')

    def __str__(self):
        return f'{self.course.title} — {self.teacher.name}'

    @property
    def display_name(self):
        return self.name_override or self.teacher.name

    @property
    def display_bio(self):
        return self.bio_override or self.teacher.bio

    @property
    def display_photo(self):
        return self.photo_override if self.photo_override else self.teacher.photo


class StudentProfile(models.Model):
    """
    Общие настройки ученика. Роль по-прежнему определяется через is_staff —
    новое поле роли не вводится (ТЗ-уточнение 7).
    Целевые баллы живут в StudentSubjectGoal: предметов может быть несколько.
    """
    user = models.OneToOneField(
        User, on_delete=models.CASCADE,
        related_name='student_profile', verbose_name='Пользователь',
    )
    exam_year = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name='Год экзамена',
    )
    timezone = models.CharField(
        max_length=50, default='Europe/Moscow', verbose_name='Часовой пояс',
    )
    available_days_per_week = models.PositiveSmallIntegerField(
        default=5, validators=[MinValueValidator(1), MaxValueValidator(7)],
        verbose_name='Доступных дней в неделю',
    )
    daily_minutes = models.PositiveSmallIntegerField(
        default=60, validators=[MinValueValidator(5)],
        verbose_name='Минут в день',
    )
    onboarding_completed = models.BooleanField(default=False, verbose_name='Онбординг пройден')
    diagnostic_completed = models.BooleanField(default=False, verbose_name='Диагностика пройдена')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Профиль ученика'
        verbose_name_plural = 'Профили учеников'

    def __str__(self):
        return f'{self.user.first_name} {self.user.last_name}'.strip() or self.user.username


class StudentSubjectGoal(models.Model):
    """Цель ученика по одному предмету. У ученика может быть несколько."""
    student = models.ForeignKey(
        StudentProfile, on_delete=models.CASCADE,
        related_name='goals', verbose_name='Ученик',
    )
    subject = models.ForeignKey(
        Subject, on_delete=models.PROTECT,
        related_name='student_goals', verbose_name='Предмет',
    )
    target_test_score = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(100)],
        verbose_name='Целевой тестовый балл',
    )
    exam_year = models.PositiveSmallIntegerField(verbose_name='Год экзамена')
    exam_date = models.DateField(null=True, blank=True, verbose_name='Дата экзамена')
    weekly_minutes = models.PositiveSmallIntegerField(
        default=300, verbose_name='Минут в неделю на предмет',
    )
    is_active = models.BooleanField(default=True, verbose_name='Активна')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Цель по предмету'
        verbose_name_plural = 'Цели по предметам'
        ordering = ['subject__order', 'subject__name']
        constraints = [
            models.UniqueConstraint(
                fields=['student', 'subject', 'exam_year'],
                name='unique_goal_per_subject_year',
            ),
        ]
        indexes = [models.Index(fields=['student', 'is_active'])]

    def __str__(self):
        return f'{self.student} — {self.subject}: {self.target_test_score}'


class ScoreConversionTable(models.Model):
    """
    Шкала перевода первичных баллов в тестовые.
    Хранится в конфигурации, не в сервисах и не в UI (ТЗ 13, 24.18).
    """
    subject = models.ForeignKey(
        Subject, on_delete=models.PROTECT,
        related_name='conversion_tables', verbose_name='Предмет',
    )
    exam_type = models.CharField(
        max_length=10, choices=Course.EXAM_CHOICES, verbose_name='Тип экзамена',
    )
    exam_year = models.PositiveSmallIntegerField(verbose_name='Год экзамена')
    version = models.PositiveSmallIntegerField(default=1, verbose_name='Версия')
    is_active = models.BooleanField(default=False, verbose_name='Активна')
    valid_from = models.DateField(verbose_name='Действует с')
    source = models.CharField(
        max_length=300, blank=True, verbose_name='Источник / комментарий',
    )
    table = models.JSONField(
        default=dict, blank=True, verbose_name='Таблица перевода',
        help_text='Ключ — первичный балл, значение — тестовый: {"0": 0, "1": 3, ...}',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Шкала перевода баллов'
        verbose_name_plural = 'Шкалы перевода баллов'
        ordering = ['-exam_year', 'subject__name', '-version']
        constraints = [
            models.UniqueConstraint(
                fields=['subject', 'exam_type', 'exam_year', 'version'],
                name='unique_conversion_version',
            ),
            models.UniqueConstraint(
                fields=['subject', 'exam_type', 'exam_year'],
                condition=models.Q(is_active=True),
                name='single_active_conversion_table',
            ),
        ]
        indexes = [models.Index(fields=['subject', 'exam_year', 'is_active'])]

    def __str__(self):
        state = 'активна' if self.is_active else 'неактивна'
        return f'{self.subject} {self.get_exam_type_display()} {self.exam_year} v{self.version} ({state})'

    def clean(self):
        """Валидация структуры таблицы (ТЗ-уточнение 6)."""
        errors = {}

        if not isinstance(self.table, dict):
            raise ValidationError({'table': 'Таблица должна быть объектом «балл: балл».'})

        if self.is_active and not self.table:
            errors['is_active'] = 'Пустая таблица не может быть активной.'

        parsed = {}
        for raw_key, raw_value in self.table.items():
            try:
                key = int(raw_key)
            except (TypeError, ValueError):
                errors['table'] = f'Первичный балл «{raw_key}» не является целым числом.'
                break
            if key < 0:
                errors['table'] = f'Первичный балл не может быть отрицательным: {key}.'
                break
            if key in parsed:
                errors['table'] = f'Дублирующийся первичный балл: {key}.'
                break
            try:
                value = int(raw_value)
            except (TypeError, ValueError):
                errors['table'] = f'Тестовый балл для {key} не является целым числом.'
                break
            if not 0 <= value <= 100:
                errors['table'] = f'Тестовый балл для {key} вне диапазона 0–100: {value}.'
                break
            parsed[key] = value

        if 'table' not in errors and parsed:
            previous = None
            for key in sorted(parsed):
                if previous is not None and parsed[key] < previous:
                    errors['table'] = (
                        f'Шкала убывает: при первичном балле {key} '
                        f'тестовый балл {parsed[key]} меньше предыдущего {previous}.'
                    )
                    break
                previous = parsed[key]

        if errors:
            raise ValidationError(errors)

    def as_mapping(self) -> dict:
        """Нормализованная таблица для передачи в convert_to_test_score()."""
        return {int(k): int(v) for k, v in self.table.items()}

    @classmethod
    def get_active(cls, subject, exam_type: str, exam_year: int):
        """Выбор шкалы по предмету, типу и году. Без хардкода в сервисах."""
        return cls.objects.filter(
            subject=subject, exam_type=exam_type,
            exam_year=exam_year, is_active=True,
        ).first()


class ErrorStatus(models.TextChoices):
    NOT_ANALYZED = 'not_analyzed', 'Не разобрано'
    IN_PROGRESS = 'in_progress', 'В работе'
    CORRECTED_ONCE = 'corrected_once', 'Исправлено один раз'
    REINFORCED = 'reinforced', 'Закреплено'
    REGRESSED = 'regressed', 'Вернулось в ошибки'


class ErrorType(models.TextChoices):
    THEORY = 'theory', 'Не знаю теорию'
    MISREAD = 'misread', 'Неверно понял условие'
    CALCULATION = 'calculation', 'Ошибка в вычислениях'
    CARELESS = 'careless', 'Невнимательность'
    STRATEGY = 'strategy', 'Неправильная стратегия'
    FORMATTING = 'formatting', 'Ошибка оформления'
    RANDOM = 'random', 'Случайный ответ'
    UNCLASSIFIED = 'unclassified', 'Не классифицирована'


class ErrorRecord(models.Model):
    """
    Одна ошибка ученика по конкретному заданию.
    Живёт дольше одной попытки: накапливает историю исправлений (ТЗ-уточнение 9).
    """
    student = models.ForeignKey(
        User, on_delete=models.CASCADE,
        related_name='error_records', verbose_name='Ученик',
    )
    subject = models.ForeignKey(
        Subject, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='error_records', verbose_name='Предмет',
    )
    lesson = models.ForeignKey(
        Lesson, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='error_records', verbose_name='Урок',
    )

    # Откуда пришла ошибка: тест, пробник, контрольная точка
    source_content_type = models.ForeignKey(
        ContentType, on_delete=models.CASCADE, null=True, blank=True,
        related_name='+', verbose_name='Тип источника',
    )
    source_object_id = models.PositiveIntegerField(null=True, blank=True)
    source_object = GenericForeignKey('source_content_type', 'source_object_id')

    # Само задание
    question = models.ForeignKey(
        Question, on_delete=models.CASCADE, null=True, blank=True,
        related_name='error_records', verbose_name='Вопрос теста',
    )

    error_type = models.CharField(
        max_length=20, choices=ErrorType.choices,
        default=ErrorType.UNCLASSIFIED, verbose_name='Тип ошибки',
    )
    status = models.CharField(
        max_length=20, choices=ErrorStatus.choices,
        default=ErrorStatus.NOT_ANALYZED, db_index=True, verbose_name='Статус',
    )
    repeated_count = models.PositiveSmallIntegerField(
        default=1, verbose_name='Сколько раз повторилась',
    )
    explanation_viewed_at = models.DateTimeField(
        null=True, blank=True, verbose_name='Объяснение изучено',
    )
    first_detected_at = models.DateTimeField(auto_now_add=True)
    last_detected_at = models.DateTimeField(auto_now=True)
    reinforced_at = models.DateTimeField(
        null=True, blank=True, verbose_name='Закреплено',
    )

    class Meta:
        verbose_name = 'Ошибка ученика'
        verbose_name_plural = 'Ошибки учеников'
        ordering = ['-last_detected_at']
        indexes = [
            models.Index(fields=['student', 'status']),
            models.Index(fields=['student', 'question']),
            models.Index(fields=['student', 'subject']),
        ]

    def __str__(self):
        return f'{self.student.username} — {self.get_status_display()}'

    def can_be_reinforced(self) -> bool:
        """
        Три условия закрепления (ТЗ 11):
          1) объяснение изучено;
          2) верно решено похожее задание;
          3) верно решено ещё одно — в другой учебной сессии.
        """
        if not self.explanation_viewed_at:
            return False
        correct = list(
            self.correction_attempts.filter(is_correct=True).order_by('attempted_at')
        )
        if len(correct) < 2:
            return False
        if not any(a.is_similar_task for a in correct):
            return False
        sessions = {a.session_key for a in correct if a.session_key}
        return len(sessions) >= 2

    def try_reinforce(self) -> bool:
        """Переводит в «Закреплено», только если выполнены все условия."""
        if not self.can_be_reinforced():
            return False
        self.status = ErrorStatus.REINFORCED
        self.reinforced_at = dj_timezone.now()
        self.save(update_fields=['status', 'reinforced_at'])
        return True

    def register_repeat(self):
        """Ошибка повторилась после закрепления."""
        self.repeated_count += 1
        if self.status == ErrorStatus.REINFORCED:
            self.status = ErrorStatus.REGRESSED
            self.reinforced_at = None
        self.save(update_fields=['repeated_count', 'status', 'reinforced_at'])


class ErrorCorrectionAttempt(models.Model):
    """Одна попытка исправления ошибки."""
    error_record = models.ForeignKey(
        ErrorRecord, on_delete=models.CASCADE,
        related_name='correction_attempts', verbose_name='Ошибка',
    )
    attempted_at = models.DateTimeField(auto_now_add=True)
    is_correct = models.BooleanField(default=False, verbose_name='Решено верно')
    is_similar_task = models.BooleanField(
        default=True, verbose_name='Аналогичное задание',
    )
    session_key = models.CharField(
        max_length=64, blank=True, db_index=True,
        verbose_name='Ключ учебной сессии',
    )

    class Meta:
        verbose_name = 'Попытка исправления ошибки'
        verbose_name_plural = 'Попытки исправления ошибок'
        ordering = ['attempted_at']

    def __str__(self):
        return f'{self.error_record_id}: {"верно" if self.is_correct else "неверно"}'


class StudySession(models.Model):
    """
    Активное учебное время. Одна строка на сессию вкладки, не на секунду.
    Агрегация — через heartbeat, идемпотентно (ТЗ-уточнение 10).
    """
    student = models.ForeignKey(
        User, on_delete=models.CASCADE,
        related_name='study_sessions', verbose_name='Ученик',
    )
    course = models.ForeignKey(
        Course, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='study_sessions', verbose_name='Курс',
    )
    activity_type = models.CharField(
        max_length=30, blank=True, verbose_name='Тип активности',
    )
    object_id = models.PositiveIntegerField(
        null=True, blank=True, verbose_name='ID объекта',
    )
    client_session_id = models.CharField(
        max_length=64, verbose_name='ID сессии клиента',
    )
    start_at = models.DateTimeField(auto_now_add=True)
    last_activity_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    active_seconds = models.PositiveIntegerField(
        default=0, verbose_name='Активных секунд',
    )

    class Meta:
        verbose_name = 'Учебная сессия'
        verbose_name_plural = 'Учебные сессии'
        ordering = ['-start_at']
        constraints = [
            models.UniqueConstraint(
                fields=['student', 'client_session_id'],
                name='unique_client_session_per_student',
            ),
        ]
        indexes = [
            models.Index(fields=['student', 'start_at']),
            models.Index(fields=['student', 'ended_at']),
        ]

    def __str__(self):
        return f'{self.student.username}: {self.active_seconds // 60} мин'

    @property
    def is_stale(self) -> bool:
        """Простой дольше таймаута — время больше не капает."""
        from school.services.constants import SESSION_IDLE_TIMEOUT_SECONDS
        idle = (dj_timezone.now() - self.last_activity_at).total_seconds()
        return idle > SESSION_IDLE_TIMEOUT_SECONDS

class PlanStatus(models.TextChoices):
    PLANNED = 'planned', 'Запланировано'
    IN_PROGRESS = 'in_progress', 'В процессе'
    DONE_ON_TIME = 'done_on_time', 'Выполнено вовремя'
    DONE_LATE = 'done_late', 'Выполнено с опозданием'
    OVERDUE = 'overdue', 'Просрочено'
    CANCELLED_BY_TEACHER = 'cancelled_by_teacher', 'Отменено преподавателем'
    CANCELLED_BY_SYSTEM = 'cancelled_by_system', 'Отменено системой'
    SKIPPED = 'skipped', 'Пропущено учеником'

    @classmethod
    def cancelled(cls):
        """Не ухудшают plan_adherence (ТЗ 15.10)."""
        return [cls.CANCELLED_BY_TEACHER, cls.CANCELLED_BY_SYSTEM]

    @classmethod
    def completed(cls):
        return [cls.DONE_ON_TIME, cls.DONE_LATE]


class StudyPlan(models.Model):
    student = models.ForeignKey(
        User, on_delete=models.CASCADE,
        related_name='study_plans', verbose_name='Ученик',
    )
    subject = models.ForeignKey(
        Subject, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='study_plans', verbose_name='Предмет',
    )
    start_date = models.DateField(verbose_name='Начало')
    end_date = models.DateField(verbose_name='Окончание')
    status = models.CharField(
        max_length=20,
        choices=[('active', 'Активен'), ('archived', 'В архиве')],
        default='active', verbose_name='Статус',
    )
    source = models.CharField(
        max_length=20,
        choices=[('system', 'Система'), ('teacher', 'Преподаватель'), ('student', 'Ученик')],
        default='system', verbose_name='Источник',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Учебный план'
        verbose_name_plural = 'Учебные планы'
        ordering = ['-start_date']
        indexes = [models.Index(fields=['student', 'status'])]

    def __str__(self):
        return f'{self.student.username}: {self.start_date} — {self.end_date}'


class PlanItem(models.Model):
    plan = models.ForeignKey(
        StudyPlan, on_delete=models.CASCADE,
        related_name='items', verbose_name='План',
    )
    item_type = models.CharField(
        max_length=30,
        choices=[
            ('lesson', 'Урок'), ('mini_check', 'Мини-проверка'),
            ('practice', 'Практика'), ('homework', 'Домашняя работа'),
            ('mock_exam', 'Пробник'), ('review', 'Повторение'),
            ('error_work', 'Работа над ошибками'),
        ],
        verbose_name='Тип задачи',
    )
    content_type = models.ForeignKey(
        ContentType, on_delete=models.CASCADE, null=True, blank=True,
        related_name='+', verbose_name='Тип объекта',
    )
    object_id = models.PositiveIntegerField(null=True, blank=True)
    target_object = GenericForeignKey('content_type', 'object_id')

    title = models.CharField(max_length=300, verbose_name='Название')
    due_at = models.DateTimeField(verbose_name='Срок')
    estimated_minutes = models.PositiveSmallIntegerField(
        default=30, verbose_name='Оценка времени, мин',
    )
    required = models.BooleanField(default=True, verbose_name='Обязательная')
    status = models.CharField(
        max_length=25, choices=PlanStatus.choices,
        default=PlanStatus.PLANNED, db_index=True, verbose_name='Статус',
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.CharField(
        max_length=300, blank=True, verbose_name='Причина отмены',
    )
    order = models.PositiveSmallIntegerField(default=0)
    priority = models.PositiveSmallIntegerField(
        default=5, verbose_name='Приоритет (1 — высший)',
    )

    class Meta:
        verbose_name = 'Задача плана'
        verbose_name_plural = 'Задачи плана'
        ordering = ['due_at', 'priority', 'order']
        indexes = [
            models.Index(fields=['status', 'due_at']),
            models.Index(fields=['plan', 'status']),
        ]

    def __str__(self):
        return self.title

    def mark_completed(self, when=None):
        """Различает выполнение вовремя и с опозданием."""
        when = when or dj_timezone.now()
        self.completed_at = when
        self.status = (
            PlanStatus.DONE_ON_TIME if when <= self.due_at else PlanStatus.DONE_LATE
        )
        self.save(update_fields=['completed_at', 'status'])
        

class LessonViewProgress(models.Model):
    """
    Прогресс просмотра урока (ТЗ 7).

    Отдельно от LessonProgress: тот фиксирует «урок засчитан»,
    этот — сколько реально просмотрено и где остановились.
    """
    WATCHED_THRESHOLD_PERCENT = 85

    student = models.ForeignKey(
        User, on_delete=models.CASCADE,
        related_name='lesson_views', verbose_name='Ученик',
    )
    lesson = models.ForeignKey(
        Lesson, on_delete=models.CASCADE,
        related_name='view_progress', verbose_name='Урок',
    )
    position_seconds = models.PositiveIntegerField(
        default=0, verbose_name='Последняя позиция, сек',
    )
    watched_percent = models.PositiveSmallIntegerField(
        default=0, validators=[MaxValueValidator(100)],
        verbose_name='Просмотрено, %',
    )
    marked_manually = models.BooleanField(
        default=False, verbose_name='Отмечен вручную',
    )
    returns_count = models.PositiveSmallIntegerField(
        default=0, verbose_name='Возвращений к уроку',
    )
    first_opened_at = models.DateTimeField(auto_now_add=True)
    last_opened_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Просмотр урока'
        verbose_name_plural = 'Просмотры уроков'
        constraints = [
            models.UniqueConstraint(
                fields=['student', 'lesson'], name='unique_lesson_view',
            ),
        ]
        indexes = [models.Index(fields=['student', 'lesson'])]

    def __str__(self):
        return f'{self.student.username} — {self.lesson.title}: {self.watched_percent}%'

    @property
    def is_watched(self) -> bool:
        """Просмотрено по порогу или отмечено вручную (ТЗ 7)."""
        return (
            self.marked_manually
            or self.watched_percent >= self.WATCHED_THRESHOLD_PERCENT
        )

    @property
    def is_started(self) -> bool:
        return self.watched_percent > 0 and not self.is_watched


class PracticeMode(models.TextChoices):
    TOPIC = 'topic', 'По теме'
    EXAM_NUMBER = 'exam_number', 'По номеру задания'
    WEAK = 'weak', 'По слабым местам'
    ERRORS = 'errors', 'По ошибкам'
    MIXED = 'mixed', 'Смешанная'
    RECOMMENDED = 'recommended', 'Рекомендованная'
    REVIEW = 'review', 'Повторение'


class PracticeSession(PrimaryScoreMixin, AnalyticsQualityMixin, models.Model):
    """Одна сессия практики (ТЗ 9)."""
    student = models.ForeignKey(
        User, on_delete=models.CASCADE,
        related_name='practice_sessions', verbose_name='Ученик',
    )
    course = models.ForeignKey(
        Course, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='practice_sessions', verbose_name='Курс',
    )
    lesson = models.ForeignKey(
        Lesson, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='practice_sessions', verbose_name='Тема',
    )
    mode = models.CharField(
        max_length=20, choices=PracticeMode.choices,
        default=PracticeMode.MIXED, verbose_name='Режим',
    )
    exam_task_number = models.PositiveSmallIntegerField(null=True, blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Сессия практики'
        verbose_name_plural = 'Сессии практики'
        ordering = ['-started_at']
        indexes = [models.Index(fields=['student', 'started_at'])]

    def __str__(self):
        return f'{self.student.username} — {self.get_mode_display()}'

    @property
    def is_finished(self) -> bool:
        return self.finished_at is not None

    @property
    def session_key(self) -> str:
        """Ключ учебной сессии для механики закрепления ошибок."""
        return f'practice-{self.pk}'

    def next_answer(self):
        """Первое неотвеченное задание сессии."""
        return self.answers.filter(answered_at__isnull=True).order_by('order').first()

    @property
    def answered_count(self) -> int:
        return self.answers.filter(answered_at__isnull=False).count()

    @property
    def total_count(self) -> int:
        return self.answers.count()


class PracticeAnswer(PrimaryScoreMixin, models.Model):
    """Ответ на одно задание в сессии практики."""
    session = models.ForeignKey(
        PracticeSession, on_delete=models.CASCADE,
        related_name='answers', verbose_name='Сессия',
    )
    question = models.ForeignKey(
        Question, on_delete=models.CASCADE,
        related_name='practice_answers', verbose_name='Задание',
    )
    order = models.PositiveSmallIntegerField(default=0)
    student_answer = models.TextField(blank=True, verbose_name='Ответ ученика')
    is_correct = models.BooleanField(default=False)
    skipped = models.BooleanField(default=False, verbose_name='Пропущено')
    marked_for_review = models.BooleanField(
        default=False, verbose_name='Отмечено для повторения',
    )
    error_type = models.CharField(
        max_length=20, choices=ErrorType.choices, blank=True,
        verbose_name='Тип ошибки',
    )
    answered_at = models.DateTimeField(null=True, blank=True)
    time_spent_seconds = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = 'Ответ в практике'
        verbose_name_plural = 'Ответы в практике'
        ordering = ['order']
        indexes = [models.Index(fields=['session', 'order'])]