"""
Следующий шаг на экране урока (ТЗ 7).
Одна главная кнопка, остальное второстепенно.
"""
from dataclasses import dataclass

from django.urls import reverse


@dataclass(frozen=True)
class LessonStep:
    label: str
    url: str
    hint: str = ''


def choose_lesson_step(lesson, view_progress, test_result, homework,
                       homework_submission, next_lesson) -> LessonStep:
    """
    Порядок правил:
      видео не досмотрено      -> продолжить/смотреть урок
      есть тест, не сдан       -> пройти мини-проверку
      есть домашка, не сдана   -> сдать домашнюю работу
      всё сделано              -> следующая тема
    """
    watched = view_progress.is_watched if view_progress else False
    started = view_progress.is_started if view_progress else False

    has_video = bool(lesson.video_file or lesson.video_url)

    if has_video and not watched:
        return LessonStep(
            label='Продолжить урок' if started else 'Смотреть урок',
            url='#lesson-video',
            hint='Досмотрите видео, чтобы перейти к проверке',
        )

    has_test = hasattr(lesson, 'test')
    if has_test and not (test_result and test_result.passed):
        return LessonStep(
            label='Пройти мини-проверку',
            url=reverse('test', kwargs={'pk': lesson.pk}),
            hint='Короткая проверка по материалу урока',
        )

    if homework and not homework_submission:
        return LessonStep(
            label='Сдать домашнюю работу',
            url=reverse('homework', kwargs={'pk': lesson.pk}),
            hint='Задание к этому уроку',
        )

    if next_lesson:
        return LessonStep(
            label='Перейти к следующей теме',
            url=reverse('lesson', kwargs={'pk': next_lesson.pk}),
            hint=next_lesson.title,
        )

    return LessonStep(
        label='Вернуться к урокам',
        url=reverse('course_lessons', kwargs={'slug': lesson.course.slug}),
        hint='Все уроки курса пройдены',
    )