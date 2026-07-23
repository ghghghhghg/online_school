import json

from django.core.management.base import BaseCommand, CommandError

from school.models import (
    Course, Module, Lesson, Test, Question, Answer, Homework,
)


class Command(BaseCommand):
    help = (
        'Безопасно импортирует курс (с разделами, уроками, тестами, вопросами, '
        'ответами и домашками) из JSON-фикстуры. Никогда не перезаписывает '
        'существующие записи — если курс с таким slug уже есть, новые уроки '
        'добавляются к нему, а не создаётся дубликат курса.'
    )

    def add_arguments(self, parser):
        parser.add_argument('json_file', type=str, help='Путь к JSON-файлу')

    def handle(self, *args, **options):
        path = options['json_file']
        try:
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
        except FileNotFoundError:
            raise CommandError(f'Файл не найден: {path}')
        except json.JSONDecodeError as e:
            raise CommandError(f'Некорректный JSON: {e}')

        # Карты "pk из файла" -> "реальный объект в базе"
        course_map = {}
        module_map = {}
        lesson_map = {}
        test_map = {}
        question_map = {}

        stats = {
            'course_created': 0, 'course_reused': 0,
            'module': 0, 'lesson': 0, 'test': 0,
            'question': 0, 'answer': 0, 'homework': 0,
            'unknown_models': set(),
        }

        for item in data:
            model = item.get('model')
            old_pk = item.get('pk')
            fields = item.get('fields', {})

            if model == 'school.course':
                slug = fields.get('slug')
                existing = Course.objects.filter(slug=slug).first() if slug else None
                if existing:
                    course_map[old_pk] = existing
                    stats['course_reused'] += 1
                    self.stdout.write(self.style.WARNING(
                        f"Курс со slug '{slug}' уже существует — использую его, "
                        f"новый курс не создаю"
                    ))
                else:
                    course = Course.objects.create(
                        title=fields.get('title', ''),
                        slug=slug or '',
                        description=fields.get('description', ''),
                        is_published=fields.get('is_published', True),
                        card_tag=fields.get('card_tag', ''),
                        card_features=fields.get('card_features', ''),
                        for_whom=fields.get('for_whom', ''),
                        what_you_learn=fields.get('what_you_learn', ''),
                        how_it_works=fields.get('how_it_works', ''),
                        exam_type=fields.get('exam_type', ''),
                        subject=fields.get('subject', ''),
                    )
                    course_map[old_pk] = course
                    stats['course_created'] += 1

            elif model == 'school.module':
                course = course_map.get(fields.get('course'))
                if not course:
                    continue
                # Не дублируем раздел с тем же названием в этом курсе
                existing = Module.objects.filter(course=course, title=fields.get('title')).first()
                if existing:
                    module_map[old_pk] = existing
                    continue
                module = Module.objects.create(
                    course=course,
                    title=fields.get('title', ''),
                    order=fields.get('order', 0),
                )
                module_map[old_pk] = module
                stats['module'] += 1

            elif model == 'school.lesson':
                course = course_map.get(fields.get('course'))
                if not course:
                    continue
                module = module_map.get(fields.get('module')) if fields.get('module') else None
                existing = Lesson.objects.filter(course=course, title=fields.get('title')).first()
                if existing:
                    lesson_map[old_pk] = existing
                    continue
                lesson = Lesson.objects.create(
                    course=course,
                    module=module,
                    title=fields.get('title', ''),
                    description=fields.get('description', ''),
                    video_url=fields.get('video_url', ''),
                    order=fields.get('order', 0),
                )
                lesson_map[old_pk] = lesson
                stats['lesson'] += 1

            elif model == 'school.test':
                lesson = lesson_map.get(fields.get('lesson'))
                if not lesson:
                    continue
                if hasattr(lesson, 'test'):
                    test_map[old_pk] = lesson.test
                    continue
                test = Test.objects.create(
                    lesson=lesson,
                    title=fields.get('title', ''),
                    pass_score=fields.get('pass_score', 70),
                )
                test_map[old_pk] = test
                stats['test'] += 1

            elif model == 'school.question':
                test = test_map.get(fields.get('test'))
                if not test:
                    continue
                question = Question.objects.create(
                    test=test,
                    text=fields.get('text', ''),
                    order=fields.get('order', 0),
                    explanation=fields.get('explanation', ''),
                )
                question_map[old_pk] = question
                stats['question'] += 1

            elif model == 'school.answer':
                question = question_map.get(fields.get('question'))
                if not question:
                    continue
                Answer.objects.create(
                    question=question,
                    text=fields.get('text', ''),
                    is_correct=fields.get('is_correct', False),
                )
                stats['answer'] += 1

            elif model == 'school.homework':
                lesson = lesson_map.get(fields.get('lesson'))
                if not lesson:
                    continue
                if hasattr(lesson, 'homework'):
                    continue
                Homework.objects.create(
                    lesson=lesson,
                    title=fields.get('title', ''),
                    description=fields.get('description', ''),
                    submission_type=fields.get('submission_type', 'text'),
                    grading_type=fields.get('grading_type', 'pass_fail'),
                    allow_resubmit=fields.get('allow_resubmit', True),
                )
                stats['homework'] += 1

            else:
                stats['unknown_models'].add(model)

        self.stdout.write(self.style.SUCCESS(
            f"\nГотово!\n"
            f"  Курсов создано: {stats['course_created']} (переиспользовано существующих: {stats['course_reused']})\n"
            f"  Разделов: {stats['module']}\n"
            f"  Уроков: {stats['lesson']}\n"
            f"  Тестов: {stats['test']}\n"
            f"  Вопросов: {stats['question']}\n"
            f"  Ответов: {stats['answer']}\n"
            f"  Домашних заданий: {stats['homework']}"
        ))

        if stats['unknown_models']:
            self.stdout.write(self.style.WARNING(
                f"\nВнимание: в файле встретились модели, которые эта команда не умеет "
                f"импортировать (пропущены): {', '.join(stats['unknown_models'])}"
            ))