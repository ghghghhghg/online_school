from django.contrib import admin
from .models import Course, Lesson, Enrollment, LessonProgress, Review, FAQ


class LessonInline(admin.TabularInline):
    """Уроки прямо внутри страницы курса"""
    model = Lesson
    extra = 1  # одно пустое поле для нового урока
    fields = ['order', 'title', 'description', 'video_url']


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ['title', 'created_at']
    inlines = [LessonInline]  # уроки редактируются прямо здесь


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = ['order', 'title', 'course']
    list_filter = ['course']
    ordering = ['course', 'order']


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ['student', 'course', 'enrolled_at']
    list_filter = ['course']


@admin.register(LessonProgress)
class LessonProgressAdmin(admin.ModelAdmin):
    list_display = ['student', 'lesson', 'completed_at']

@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ['student_name', 'rating', 'is_published', 'order']
    list_editable = ['is_published', 'order']


@admin.register(FAQ)
class FAQAdmin(admin.ModelAdmin):
    list_display = ['question', 'order']
    list_editable = ['order']