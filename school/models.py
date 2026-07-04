from django.db import models
from django.contrib.auth.models import User

from cloudinary.models import CloudinaryField

from django.utils.text import slugify


class Course(models.Model):
    title = models.CharField(max_length=200, verbose_name='Название')
    slug = models.SlugField(max_length=220, unique=True, blank=True, verbose_name='Адрес страницы')
    description = models.TextField(verbose_name='Описание')
    image = models.ImageField(upload_to='courses/', blank=True, verbose_name='Обложка')
    is_published = models.BooleanField(default=True, verbose_name='Опубликован')

    for_whom = models.TextField(blank=True, verbose_name='Кому подойдёт')
    what_you_learn = models.TextField(blank=True, verbose_name='Чему научитесь')
    how_it_works = models.TextField(blank=True, verbose_name='Как проходит обучение')

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Курс'
        verbose_name_plural = 'Курсы'
        ordering = ['-created_at']

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
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

class TeacherProfile(models.Model):
    name = models.CharField(max_length=200, verbose_name='Имя')
    bio = models.TextField(verbose_name='О себе')
    photo = models.ImageField(upload_to='teacher/', blank=True, verbose_name='Фото')

    class Meta:
        verbose_name = 'Профиль преподавателя'
        verbose_name_plural = 'Профиль преподавателя'

    def __str__(self):
        return self.name

class Review(models.Model):
    student_name = models.CharField(max_length=200, verbose_name='Имя ученика')
    text = models.TextField(verbose_name='Текст отзыва')
    rating = models.PositiveIntegerField(default=5, verbose_name='Оценка (1-5)')
    photo = models.ImageField(upload_to='reviews/', blank=True, verbose_name='Фото')
    order = models.PositiveIntegerField(default=0, verbose_name='Порядок')
    is_published = models.BooleanField(default=True, verbose_name='Опубликован')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Отзыв'
        verbose_name_plural = 'Отзывы'
        ordering = ['order', '-created_at']

    def __str__(self):
        return f'{self.student_name} — {self.rating}★'


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
    icon = models.CharField(max_length=10, default='✦', verbose_name='Иконка (эмодзи)')
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
    SUBMISSION_BOTH = 'both'
    SUBMISSION_CHOICES = [
        (SUBMISSION_TEXT, 'Только текст'),
        (SUBMISSION_FILE, 'Только файл'),
        (SUBMISSION_BOTH, 'Текст и файл'),
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