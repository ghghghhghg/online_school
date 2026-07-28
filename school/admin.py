from django.contrib import admin
from .models import Course, Lesson, Enrollment, LessonProgress, Review, FAQ, Comment, WhyUsBlock, StatBlock, Homework, \
    HomeworkSubmission, Module, Checkpoint, CheckpointTask, CheckpointAttempt, ExamMock, ExamTask, ExamAttempt, \
    CheckpointAnswer, Notification, FearBlock, ParentBlock, SiteSettings, ReviewPhoto, Timecode, CourseTeacherDisplay, \
    TeacherProfile, CourseBenefit, CourseAudience, CourseStep, Question, Test

from .models import (
    ErrorCorrectionAttempt, ErrorRecord, PlanItem, ScoreConversionTable,
    StudentProfile, StudentSubjectGoal, StudyPlan, StudySession, Subject,
)

class QuestionInline(admin.TabularInline):
    """Вопросы теста с весом в первичных баллах."""
    model = Question
    extra = 1
    fields = ['order', 'text', 'points', 'explanation']


class StudentSubjectGoalInline(admin.TabularInline):
    model = StudentSubjectGoal
    extra = 1
    autocomplete_fields = ['subject']


class ErrorCorrectionAttemptInline(admin.TabularInline):
    model = ErrorCorrectionAttempt
    extra = 0
    readonly_fields = ['attempted_at']
    fields = ['attempted_at', 'is_correct', 'is_similar_task', 'session_key']


class PlanItemInline(admin.TabularInline):
    model = PlanItem
    extra = 1
    fields = ['order', 'item_type', 'title', 'due_at', 'estimated_minutes',
              'required', 'status', 'priority']

class CourseBenefitInline(admin.TabularInline):
    model = CourseBenefit
    extra = 1


class CourseAudienceInline(admin.TabularInline):
    model = CourseAudience
    extra = 1


class CourseStepInline(admin.TabularInline):
    model = CourseStep
    extra = 1

class CheckpointTaskInline(admin.TabularInline):
    model = CheckpointTask
    extra = 1
    fields = ['order', 'title', 'task_type', 'points', 'correct_answers',
              'submission_type']

class CourseTeacherDisplayInline(admin.TabularInline):
    model = CourseTeacherDisplay
    extra = 1

class TimecodeInline(admin.TabularInline):
    model = Timecode
    extra = 1


class LessonInline(admin.TabularInline):
    """Уроки прямо внутри страницы курса"""
    model = Lesson
    extra = 1
    fields = ['order', 'title', 'description', 'video_url']


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = ['title', 'course', 'module', 'order']
    inlines = [TimecodeInline]


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ['student', 'course', 'status', 'enrolled_at']
    list_filter = ['status', 'course']
    list_editable = ['status']


@admin.register(LessonProgress)
class LessonProgressAdmin(admin.ModelAdmin):
    list_display = ['student', 'lesson', 'completed_at']

class ReviewPhotoInline(admin.TabularInline):
    model = ReviewPhoto
    extra = 1
    max_num = 4

@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ['student_name', 'city', 'subject', 'exam_type', 'score_before', 'score_after', 'is_published']
    list_editable = ['is_published', 'subject', 'exam_type']
    inlines = [ReviewPhotoInline]
    autocomplete_fields = ['subject_ref']


@admin.register(FAQ)
class FAQAdmin(admin.ModelAdmin):
    list_display = ['question', 'order']
    list_editable = ['order']

@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ['author', 'lesson', 'text', 'created_at']
    list_filter = ['lesson']

@admin.register(WhyUsBlock)
class WhyUsBlockAdmin(admin.ModelAdmin):
    list_display = ['title', 'icon', 'order']
    list_editable = ['icon', 'order']


@admin.register(StatBlock)
class StatBlockAdmin(admin.ModelAdmin):
    list_display = ['icon', 'number', 'label', 'order']
    list_editable = ['order']

@admin.register(Homework)
class HomeworkAdmin(admin.ModelAdmin):
    list_display = ['title', 'lesson', 'submission_type', 'grading_type']


@admin.register(HomeworkSubmission)
class HomeworkSubmissionAdmin(admin.ModelAdmin):
    list_display = ['student', 'homework', 'status', 'submitted_at']
    list_filter = ['status', 'homework']

@admin.register(Module)
class ModuleAdmin(admin.ModelAdmin):
    list_display = ['title', 'course', 'order']
    list_editable = ['order']

@admin.register(Checkpoint)
class CheckpointAdmin(admin.ModelAdmin):
    list_display = ['title', 'course', 'after_module']
    inlines = [CheckpointTaskInline]


@admin.register(CheckpointAttempt)
class CheckpointAttemptAdmin(admin.ModelAdmin):
    list_display = ['student', 'checkpoint', 'submitted_at']

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['user', 'text', 'is_read', 'created_at']
    list_filter = ['is_read']

class ExamTaskInline(admin.TabularInline):
    model = ExamTask
    extra = 1
    fields = ['order', 'title', 'task_type', 'points', 'correct_answers',
              'submission_type']

@admin.register(ExamMock)
class ExamMockAdmin(admin.ModelAdmin):
    list_display = ['title', 'course', 'duration_minutes', 'order']
    list_editable = ['order']
    inlines = [ExamTaskInline]

@admin.register(ExamAttempt)
class ExamAttemptAdmin(admin.ModelAdmin):
    list_display = ['student', 'exam', 'started_at', 'submitted_at']


@admin.register(FearBlock)
class FearBlockAdmin(admin.ModelAdmin):
    list_display = ['question', 'order']
    list_editable = ['order']


@admin.register(ParentBlock)
class ParentBlockAdmin(admin.ModelAdmin):
    list_display = ['title', 'icon', 'order']
    list_editable = ['icon', 'order']


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        # Разрешаем создать только одну запись
        return not SiteSettings.objects.exists()


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ['title', 'exam_type', 'subject', 'nav_short_name', 'slug', 'is_published', 'created_at']
    list_editable = ['is_published', 'exam_type', 'subject', 'nav_short_name']
    prepopulated_fields = {'slug': ('title',)}
    inlines = [LessonInline, CourseTeacherDisplayInline, CourseBenefitInline, CourseAudienceInline, CourseStepInline]
    search_fields = ['title', 'subject']
    autocomplete_fields = ['subject_ref']

@admin.register(TeacherProfile)
class TeacherProfileAdmin(admin.ModelAdmin):
    list_display = ['name', 'subject', 'exam_type']
    list_editable = ['subject', 'exam_type']
    autocomplete_fields = ['subject_ref']

@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'is_active', 'order']
    list_editable = ['is_active', 'order']
    search_fields = ['name', 'code']
    prepopulated_fields = {'code': ('name',)}


@admin.register(ScoreConversionTable)
class ScoreConversionTableAdmin(admin.ModelAdmin):
    list_display = ['subject', 'exam_type', 'exam_year', 'version',
                    'is_active', 'valid_from', 'points_count']
    list_filter = ['exam_type', 'exam_year', 'is_active', 'subject']
    autocomplete_fields = ['subject']
    fieldsets = [
        (None, {
            'fields': ['subject', 'exam_type', 'exam_year', 'version'],
        }),
        ('Действие', {
            'fields': ['is_active', 'valid_from', 'source'],
            'description': 'Активной может быть только одна шкала '
                           'на пару «предмет + год». Пустая таблица активной быть не может.',
        }),
        ('Таблица перевода', {
            'fields': ['table'],
            'description': 'Формат: {"0": 0, "1": 3, "2": 5, ...} — '
                           'ключ это первичный балл, значение — тестовый. '
                           'Шкала не должна убывать.',
        }),
    ]

    @admin.display(description='Строк в шкале')
    def points_count(self, obj):
        return len(obj.table or {})


@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'exam_year', 'available_days_per_week',
                    'daily_minutes', 'onboarding_completed', 'diagnostic_completed']
    list_filter = ['exam_year', 'onboarding_completed', 'diagnostic_completed']
    search_fields = ['user__first_name', 'user__last_name', 'user__email']
    autocomplete_fields = ['user']
    inlines = [StudentSubjectGoalInline]


@admin.register(ErrorRecord)
class ErrorRecordAdmin(admin.ModelAdmin):
    list_display = ['student', 'lesson', 'error_type', 'status',
                    'repeated_count', 'last_detected_at']
    list_filter = ['status', 'error_type', 'subject']
    search_fields = ['student__first_name', 'student__last_name']
    readonly_fields = ['first_detected_at', 'last_detected_at', 'reinforced_at',
                       'repeated_count']
    inlines = [ErrorCorrectionAttemptInline]

    def has_add_permission(self, request):
        """Ошибки создаются системой при прохождении, не вручную."""
        return False


@admin.register(StudySession)
class StudySessionAdmin(admin.ModelAdmin):
    list_display = ['student', 'course', 'activity_type', 'start_at',
                    'active_minutes', 'ended_at']
    list_filter = ['activity_type', 'start_at']
    search_fields = ['student__first_name', 'student__last_name']
    readonly_fields = ['start_at', 'last_activity_at', 'ended_at',
                       'active_seconds', 'client_session_id']

    @admin.display(description='Активных минут')
    def active_minutes(self, obj):
        return obj.active_seconds // 60

    def has_add_permission(self, request):
        return False


@admin.register(StudyPlan)
class StudyPlanAdmin(admin.ModelAdmin):
    list_display = ['student', 'subject', 'start_date', 'end_date',
                    'status', 'source', 'items_count']
    list_filter = ['status', 'source', 'subject']
    search_fields = ['student__first_name', 'student__last_name']
    autocomplete_fields = ['student', 'subject']
    inlines = [PlanItemInline]

    @admin.display(description='Задач')
    def items_count(self, obj):
        return obj.items.count()

@admin.register(Test)
class TestAdmin(admin.ModelAdmin):
    list_display = ['title', 'lesson', 'pass_score']
    inlines = [QuestionInline]