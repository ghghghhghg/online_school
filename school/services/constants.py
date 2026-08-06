"""
Константы расчётного слоя ABS SCHOOL.
Меняются здесь, а не в формулах (ТЗ 24.17-24.19).
"""

# Веса типов активности (ТЗ 15.5)
ACTIVITY_WEIGHTS = {
    'mini_check': 0.8,
    'practice': 1.0,
    'homework': 1.1,
    'checkpoint': 1.2,
    'mock_exam': 1.3,
    # Повторы по ошибкам ученик проходит внутри практики (режим «по ошибкам»)
    # и они учитываются как PracticeSession. Отдельного источника нет.
    'error_retry': 0.9,
}
DEFAULT_ACTIVITY_WEIGHT = 1.0

# Затухание веса по времени
MASTERY_HALF_LIFE_DAYS = 45
MASTERY_WINDOW_DAYS = 90
MASTERY_MAX_ATTEMPTS = 30

# Объём доказательств: одно крупное задание не должно подавить остальные
EVIDENCE_WEIGHT_CAP = 3.0

# Достоверность
CONFIDENCE_TARGET_ATTEMPTS = 20

# Сглаживание прогноза (ТЗ 15.13)
PREDICTION_PRIOR_PROBABILITY = 0.5
PREDICTION_PRIOR_STRENGTH = 6.0

# Пороги активного учебного дня (ТЗ 15.12)
ACTIVE_DAY_MIN_SECONDS = 15 * 60
ACTIVE_DAY_MIN_TASKS = 5
SESSION_IDLE_TIMEOUT_SECONDS = 5 * 60

# Планировщик (ТЗ 18)
PLANNER_DEFAULT_DAILY_MINUTES = 60
PLANNER_MAX_DAYS_AHEAD = 180
PLANNER_HORIZON_DAYS = 14
MINUTES_LESSON = 20
MINUTES_TEST = 10
MINUTES_HOMEWORK = 30
MINUTES_ERROR_WORK = 15
MINUTES_MOCK_DEFAULT = 210