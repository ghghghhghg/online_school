from django.contrib import admin
from .models import Course, Lesson, Enrollment, LessonProgress, Review, FAQ, Comment, WhyUsBlock, StatBlock, Homework, \
    HomeworkSubmission, Module, Checkpoint, CheckpointTask, CheckpointAttempt, ExamMock, ExamTask, ExamAttempt, \
    CheckpointAnswer, Notification, FearBlock, ParentBlock, SiteSettings, ReviewPhoto, Timecode, CourseTeacherDisplay


class CheckpointTaskInline(admin.TabularInline):
    model = CheckpointTask
    extra = 1

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
    list_display = ['student_name', 'city', 'score_before', 'score_after', 'is_published']
    list_editable = ['is_published']
    inlines = [ReviewPhotoInline]


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
    list_display = ['title', 'exam_type', 'subject', 'slug', 'is_published', 'created_at']
    list_editable = ['is_published', 'exam_type', 'subject']
    prepopulated_fields = {'slug': ('title',)}
    inlines = [LessonInline, CourseTeacherDisplayInline]