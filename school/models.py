from django.db import models
from django.contrib.auth.models import User


class Course(models.Model):
    """Курс — один, но пусть будет модель для гибкости"""
    title = models.CharField(max_length=200, verbose_name='Название')
    description = models.TextField(verbose_name='Описание')
    image = models.ImageField(upload_to='courses/', blank=True, verbose_name='Обложка')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Курс'
        verbose_name_plural = 'Курсы'

    def __str__(self):
        return self.title


class Lesson(models.Model):
    """Урок внутри курса"""
    course = models.ForeignKey(Course, on_delete=models.CASCADE,
                               related_name='lessons', verbose_name='Курс')
    title = models.CharField(max_length=200, verbose_name='Название')
    description = models.TextField(blank=True, verbose_name='Описание')
    video_url = models.URLField(verbose_name='Ссылка на YouTube')
    order = models.PositiveIntegerField(default=0, verbose_name='Порядок')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Урок'
        verbose_name_plural = 'Уроки'
        ordering = ['order']  # уроки всегда в правильном порядке

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