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

class Lesson(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE,
                               related_name='lessons', verbose_name='Курс')
    title = models.CharField(max_length=200, verbose_name='Название')
    description = models.TextField(blank=True, verbose_name='Описание')
    video_file = CloudinaryField(resource_type='video',
                                 blank=True, null=True)
    video_url = models.URLField(blank=True, verbose_name='Ссылка на видео (VK/YouTube)')
    order = models.PositiveIntegerField(default=0, verbose_name='Порядок')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Урок'
        verbose_name_plural = 'Уроки'
        ordering = ['order']

    def __str__(self):
        return f'{self.order}. {self.title}'


class Enrollment(models.Model):
    """Ученик записан на курс"""
    student = models.ForeignKey(User, on_delete=models.CASCADE,
                                related_name='enrollments', verbose_name='Ученик')
    course = models.ForeignKey(Course, on_delete=models.CASCADE,
                               related_name='enrollments', verbose_name='Курс')
    enrolled_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Запись на курс'
        verbose_name_plural = 'Записи на курсы'
        unique_together = ('student', 'course')  # нельзя записаться дважды

    def __str__(self):
        return f'{self.student.username} → {self.course.title}'


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