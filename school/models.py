from django.db import models
from django.contrib.auth.models import User

from django.utils import timezone

from cloudinary.models import CloudinaryField

from django.utils.text import slugify


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

    for_whom = models.TextField(blank=True, verbose_name='Кому подойдёт')
    what_you_learn = models.TextField(blank=True, verbose_name='Чему научитесь')
    how_it_works = models.TextField(blank=True, verbose_name='Как проходит обучение')

    exam_type = models.CharField(max_length=10, choices=EXAM_CHOICES,
                                 blank=True, verbose_name='Тип экзамена')
    subject = models.CharField(max_length=100, blank=True, verbose_name='Предмет')

    created_at = models.DateTimeField(auto_now_add=True)

    teacher = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                related_name='courses', verbose_name='Преподаватель')

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


class Question(models.Model):
    test = models.ForeignKey(Test, on_delete=models.CASCADE,
                             related_name='questions', verbose_name='Тест')
    text = models.TextField(verbose_name='Вопрос')
    order = models.PositiveIntegerField(default=0, verbose_name='Порядок')
    explanation = models.TextField(blank=True, verbose_name='Объяснение (показывается при ошибке)')

    class Meta:
        verbose_name = 'Вопрос'
        verbose_name_plural = 'Вопросы'
        ordering = ['order']

    def __str__(self):
        return f'{self.order}. {self.text[:50]}'


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


class TestResult(models.Model):
    student = models.ForeignKey(User, on_delete=models.CASCADE,
                                related_name='test_results', verbose_name='Ученик')
    test = models.ForeignKey(Test, on_delete=models.CASCADE,
                             related_name='results', verbose_name='Тест')
    score = models.PositiveIntegerField(verbose_name='Результат (%)')
    passed = models.BooleanField(verbose_name='Сдан')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Результат теста'
        verbose_name_plural = 'Результаты тестов'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.student.username} — {self.test} — {self.score}%'

class TestAnswerLog(models.Model):
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


class HomeworkSubmission(models.Model):
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

    class Meta:
        verbose_name = 'Задание контрольной точки'
        verbose_name_plural = 'Задания контрольной точки'
        ordering = ['order']

    def __str__(self):
        return f'{self.checkpoint.title} — {self.title}'

class CheckpointAttempt(models.Model):
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


class CheckpointAnswer(models.Model):
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

    class Meta:
        verbose_name = 'Задание пробника'
        verbose_name_plural = 'Задания пробника'
        ordering = ['order']

    def __str__(self):
        return f'{self.exam.title} — {self.title}'


class ExamAttempt(models.Model):
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


class ExamAnswer(models.Model):
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
    def display_photo(self):
        return self.photo_override if self.photo_override else self.teacher.photo