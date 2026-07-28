from django.db import migrations
from django.utils.text import slugify

# Транслитерация для code: slugify не умеет кириллицу
TRANSLIT = str.maketrans({
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'e',
    'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
    'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
    'ф': 'f', 'х': 'h', 'ц': 'c', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch', 'ъ': '',
    'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
})


def make_code(name, taken):
    base = slugify(name.lower().translate(TRANSLIT)) or 'subject'
    code, n = base, 1
    while code in taken:
        n += 1
        code = f'{base}-{n}'
    taken.add(code)
    return code


def create_subjects(apps, schema_editor):
    Subject = apps.get_model('school', 'Subject')
    Course = apps.get_model('school', 'Course')
    Review = apps.get_model('school', 'Review')
    TeacherProfile = apps.get_model('school', 'TeacherProfile')

    # Собираем уникальные названия из трёх источников
    names = set()
    for model in (Course, Review, TeacherProfile):
        for value in model.objects.exclude(subject='').values_list('subject', flat=True):
            if value and value.strip():
                names.add(value.strip())

    taken = set(Subject.objects.values_list('code', flat=True))
    by_name = {s.name: s for s in Subject.objects.all()}

    for order, name in enumerate(sorted(names), start=1):
        if name in by_name:
            continue
        by_name[name] = Subject.objects.create(
            code=make_code(name, taken), name=name, order=order,
        )

    # Проставляем ссылки, не трогая записи, где subject_ref уже задан
    for model in (Course, Review, TeacherProfile):
        for obj in model.objects.filter(subject_ref__isnull=True).exclude(subject=''):
            subject = by_name.get((obj.subject or '').strip())
            if subject:
                obj.subject_ref = subject
                obj.save(update_fields=['subject_ref'])


def unlink_subjects(apps, schema_editor):
    """Обратная миграция: снимаем ссылки, сами Subject оставляем."""
    for name in ('Course', 'Review', 'TeacherProfile'):
        model = apps.get_model('school', name)
        model.objects.update(subject_ref=None)


class Migration(migrations.Migration):

    dependencies = [
        ('school', '0043_conversion_table_blank'),
    ]

    operations = [
        migrations.RunPython(create_subjects, unlink_subjects),
    ]