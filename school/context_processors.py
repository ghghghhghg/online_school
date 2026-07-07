from .models import HomeworkSubmission, Enrollment, CheckpointAttempt


def pending_homework_count(request):
    if request.user.is_authenticated and request.user.is_staff:
        count = HomeworkSubmission.objects.filter(status='pending').count()
        return {'pending_homework_count': count}
    return {}


def pending_homework_count(request):
    if request.user.is_authenticated and request.user.is_staff:
        hw_count = HomeworkSubmission.objects.filter(status='pending').count()
        enrollment_count = Enrollment.objects.filter(status='pending').count()
        checkpoint_count = sum(1 for a in CheckpointAttempt.objects.all() if a.has_pending)
        return {
            'pending_homework_count': hw_count,
            'pending_enrollment_count': enrollment_count,
            'pending_checkpoint_count': checkpoint_count,
        }
    return {}