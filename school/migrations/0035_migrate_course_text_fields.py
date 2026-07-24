from django.db import migrations


def migrate_text_to_items(apps, schema_editor):
    Course = apps.get_model('school', 'Course')
    CourseBenefit = apps.get_model('school', 'CourseBenefit')
    CourseAudience = apps.get_model('school', 'CourseAudience')
    CourseStep = apps.get_model('school', 'CourseStep')

    for course in Course.objects.all():
        for i, line in enumerate((course.what_you_learn or '').splitlines()):
            if line.strip():
                CourseBenefit.objects.create(course=course, text=line.strip(), order=i + 1)

        for i, line in enumerate((course.for_whom or '').splitlines()):
            if line.strip():
                CourseAudience.objects.create(course=course, text=line.strip(), order=i + 1)

        for i, line in enumerate((course.how_it_works or '').splitlines()):
            if line.strip():
                CourseStep.objects.create(course=course, text=line.strip(), order=i + 1)


def reverse_migration(apps, schema_editor):
    pass  # обратный перенос не требуется


class Migration(migrations.Migration):

    dependencies = [
        ('school', '0034_courseaudience_coursebenefit_coursestep'),  # замени на реальный номер предыдущей миграции
    ]

    operations = [
        migrations.RunPython(migrate_text_to_items, reverse_migration),
    ]