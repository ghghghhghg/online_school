"""
Сборка данных экрана результата теста (ТЗ 10).
Главная кнопка выбирается здесь, а не в шаблоне.
"""
from dataclasses import dataclass, field
from decimal import Decimal

from django.urls import reverse

from .analytics import activity_score


# Порог, ниже которого результат считается недостаточным
WEAK_RESULT_THRESHOLD = 60
# Сколько ошибок считается существенным количеством
SIGNIFICANT_ERRORS = 1


@dataclass
class NextStep:
    label: str
    url: str
    reason: str


@dataclass
class TestResultData:
    result: object
    score: int
    earned_points: Decimal | None
    max_points: Decimal | None
    correct_count: int
    wrong_count: int
    total_count: int
    passed: bool
    previous_score: int | None = None
    score_delta: int | None = None
    attempt_number: int = 1
    next_step: NextStep | None = None
    wrong_logs: list = field(default_factory=list)

    @property
    def has_points(self) -> bool:
        return self.max_points is not None and self.max_points > 0

    @property
    def is_weak(self) -> bool:
        return self.score < WEAK_RESULT_THRESHOLD

    @property
    def improved(self) -> bool:
        return self.score_delta is not None and self.score_delta > 0


def choose_next_step(result, lesson, wrong_count: int, passed: bool, score: int,
                     next_lesson=None) -> NextStep:
    """
    Логика главной кнопки (ТЗ 10):
      существенные ошибки  -> разобрать ошибки
      результат слабый     -> пройти закрепление
      ошибок нет           -> следующая тема
    """
    if wrong_count >= SIGNIFICANT_ERRORS:
        return NextStep(
            label='Разобрать ошибки',
            url=reverse('error_notebook'),
            reason=f'В работе есть ошибки — разберите их, пока материал свежий',
        )

    if score < WEAK_RESULT_THRESHOLD:
        return NextStep(
            label='Пройти закрепление',
            url=reverse('test', kwargs={'pk': lesson.pk}),
            reason='Результат ниже проходного — стоит закрепить материал',
        )

    if next_lesson:
        return NextStep(
            label='Перейти к следующей теме',
            url=reverse('lesson', kwargs={'pk': next_lesson.pk}),
            reason='Тема усвоена, можно двигаться дальше',
        )

    return NextStep(
        label='Вернуться к урокам',
        url=reverse('course_lessons', kwargs={'slug': lesson.course.slug}),
        reason='Тема усвоена',
    )


def build_test_result(student, lesson, result, answer_logs, previous_result=None,
                      next_lesson=None, attempt_number=1) -> TestResultData:
    """Собирает всё, что показывает экран результата."""
    logs = list(answer_logs)
    wrong_logs = [log for log in logs if not log.is_correct]

    previous_score = previous_result.score if previous_result else None
    delta = (result.score - previous_score) if previous_score is not None else None

    return TestResultData(
        result=result,
        score=result.score,
        earned_points=result.earned_points,
        max_points=result.max_points,
        correct_count=len(logs) - len(wrong_logs),
        wrong_count=len(wrong_logs),
        total_count=len(logs),
        passed=result.passed,
        previous_score=previous_score,
        score_delta=delta,
        attempt_number=attempt_number,
        next_step=choose_next_step(
            result, lesson, len(wrong_logs), result.passed, result.score, next_lesson
        ),
        wrong_logs=wrong_logs,
    )