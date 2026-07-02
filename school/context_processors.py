from .models import HomeworkSubmission


def pending_homework_count(request):
    if request.user.is_authenticated and request.user.is_staff:
        count = HomeworkSubmission.objects.filter(status='pending').count()
        return {'pending_homework_count': count}
    return {}