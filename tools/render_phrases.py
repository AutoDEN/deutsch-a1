# -*- coding: utf-8 -*-
"""
Сборка блоков с озвученными фразами из phrases.json урока.

Две разные вёрстки на одних данных:

* layout "columns" — «Выучить наизусть»: слева немецкая фраза с кнопкой звука
  и транскрипцией, справа перевод, под переводом закрытый разбор произношения.
  Немецкий идёт первым не случайно: так строку можно пройти как проверку себя,
  а не как чтение готового перевода. Транскрипция здесь фразовая, а не
  словарная: в живой речи слова склеиваются, и учить их по одному бесполезно;
* layout "sample" — образец к устному заданию: одна кнопка на сценку целиком
  и текст обеих ролей. Разбора тут нет — задание на речь, а не на чтение
  транскрипции;
* layout "qa" — «вопрос — ответ» в контрольных: по-русски сказано, о чём
  спросить, немецкий вопрос и образец ответа закрыты и озвучены по отдельности.
  Так список проходится в обе стороны: сначала спрашиваешь сам, потом отвечаешь
  на запись вопроса.

Разметка вставляется в index.html между маркерами <!-- <id>:start -->
и <!-- <id>:end -->, где <id> — идентификатор группы из phrases.json.
Имена mp3 считаются функцией tracks() из tools/tts_phrases.py — той же, что
их записывает, поэтому порядок такой: сначала озвучка, потом сборка.

Запуск:  python tools/render_phrases.py [слаг ...]
"""

import io
import json
import os
import re
import sys

TOOLS = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.dirname(TOOLS)

sys.path.insert(0, TOOLS)
from tts_phrases import tracks                    # noqa: E402  (нужен путь выше)

AUDIO_REL = 'media/phrases'

# Вступление к таблице одно на все уроки, поэтому лежит здесь, а не в тридцати
# копиях по файлам. Урок может задать своё поле "intro" вместо этого или
# "intro_add" — абзацы, которые допишутся следом (так сделано в уроке 3,
# где половина фраз это заготовки с пропуском).
DEFAULT_INTRO = [
    'Это те фразы, которые в разговоре не собирают по словам, а достают из памяти '
    'целиком. Слева немецкая фраза с кнопкой звука и транскрипцией, справа перевод. '
    'Под переводом спрятан разбор — что здесь звучит не так, как пишется: он '
    'открывается щелчком, чтобы сначала можно было проверить себя, а не читать '
    'готовое объяснение.',
    'Порядок работы простой: нажмите кнопку, прослушайте, повторите вслух — и так, пока '
    'фраза не пойдёт без запинки. Читается транскрипция не с ходу, зато без «примерно '
    'как по-русски»: все её знаки разобраны в справочнике '
    '<a href="../prep-3-transkription/index.html">«Как читать транскрипцию»</a>.',
    'Проверять себя удобно листом бумаги, как в словаре урока. Закройте правую '
    'половину — останется немецкий, и видно, помните ли Вы смысл. Потом сдвиньте лист '
    'влево, чтобы закрыть немецкий: теперь по русскому надо вспомнить саму фразу '
    'целиком. Вторая сторона и есть та, ради которой фразы учат наизусть.',
]


def intro_of(group):
    base = group.get('intro') or (DEFAULT_INTRO if group['layout'] == 'columns' else [])
    return list(base) + list(group.get('intro_add', []))


def files_of(group, item):
    """Пути к mp3 — те же имена, что пишет tts_phrases.py."""
    return ['%s/%s' % (AUDIO_REL, name) for name, _ in tracks(group, item)]


def attr(value):
    """Текст реплики уходит в aria-label, а там могут встретиться кавычки."""
    return value.replace('&', '&amp;').replace('"', '&quot;').replace('<', '&lt;')


def play_button(src, label):
    return ('<button class="ph-play" type="button" data-audio="%s" '
            'aria-label="%s"></button>' % (src, attr(label)))


def row(src, label, body):
    return ('<div class="ph-line">\n%s\n<div class="ph-body">\n%s\n</div>\n</div>'
            % (play_button(src, label), '\n'.join(body)))


TIP = ('<details class="ph-tip">\n<summary>разбор произношения</summary>\n'
       '<div>%s</div>\n</details>')


def render_columns(group):
    """Фразы наизусть: немецкий слева, перевод справа, разбор под переводом.

    Одна фраза — один блок .ph-item, внутри сетка в две колонки: реплика
    ложится в левую ячейку, её перевод в правую. Реплик у фразы бывает
    несколько (обмен репликами в уроке 1) — сетка сама ставит каждую напротив
    своего перевода, чего таблица с кнопками звука не удерживала.
    Разбор закрыт: сначала проверить себя по звуку, потом читать объяснение.
    """
    out = []
    for item in group['items']:
        cells = []
        for line, src in zip(item['lines'], files_of(group, item)):
            body = ['<div class="ph-de">%s</div>' % line['de'],
                    '<div class="ph-ipa">[%s]</div>' % line['ipa']]
            cells.append(row(src, 'Прослушать: ' + line['de'], body))
            cells.append('<div class="ph-ru">%s</div>' % line.get('ru', ''))
        if item.get('tip'):
            cells.append(TIP % item['tip'])
        out.append('<div class="ph-item">\n%s\n</div>' % '\n'.join(cells))
    return '<div class="ph-list">\n%s\n</div>' % '\n'.join(out)


def render_sample(group):
    """Образец к устному заданию: кнопка на сценку, под ней обе роли."""
    out = []
    for item in group['items']:
        src = files_of(group, item)[0]
        body = ['<div class="ph-sit-label">%s</div>' % item['label']]
        dash = '— ' if len(item['lines']) > 1 else ''
        body += ['<div class="ph-de">%s%s</div>' % (dash, l['de']) for l in item['lines']]
        out.append('<div class="ph-sit">\n%s\n</div>'
                   % row(src, 'Прослушать: ' + item['label'], body))
    return ('<div class="sample">\n<div class="sample-title">%s</div>\n'
            '<div class="sample-body">\n%s\n</div>\n</div>'
            % (group.get('title', 'Образец для самопроверки'), '\n'.join(out)))


QA_STEP = '<details class="qa-step">\n<summary>%s</summary>\n%s\n</details>'


def render_qa(group):
    """Вопрос — ответ: задание по-русски, немецкий закрыт.

    Здесь тренируется не узнавание, а речь в обе стороны, поэтому вопрос
    и ответ озвучены по отдельности, а не сценкой: список проходится дважды.
    Сверху вниз — спрашиваешь сам и сверяешься с записью вопроса; второй раз —
    включаешь запись вопроса и отвечаешь на неё вслух, и только потом
    открываешь образец ответа. Разбора произношения тут нет: задание на речь,
    а не на чтение транскрипции.
    """
    out = []
    for item in group['items']:
        steps = []
        for n, (line, src) in enumerate(zip(item['lines'], files_of(group, item))):
            body = ['<div class="ph-de">%s</div>' % line['de']]
            if line.get('ru'):
                body.append('<div class="qa-ru">%s</div>' % line['ru'])
            steps.append(QA_STEP % ('вопрос по-немецки' if n == 0 else 'образец ответа',
                                    row(src, 'Прослушать: ' + line['de'], body)))
        out.append('<div class="qa-item">\n<div class="qa-task">%s</div>\n%s\n</div>'
                   % (item['task'], '\n'.join(steps)))
    return '<div class="qa-list">\n%s\n</div>' % '\n'.join(out)


LAYOUTS = {'columns': render_columns, 'sample': render_sample, 'qa': render_qa}


def build(slug):
    lesson = os.path.join(SITE, 'lessons', slug)
    data = json.load(io.open(os.path.join(lesson, 'phrases.json'), encoding='utf-8'))
    path = os.path.join(lesson, 'index.html')
    html = io.open(path, encoding='utf-8').read()

    files_total, missing = 0, []
    for group in data['groups']:
        block = ''.join('<p>%s</p>\n' % p for p in intro_of(group))
        block += LAYOUTS[group['layout']](group)
        marked = '<!-- %s:start -->\n%s\n<!-- %s:end -->' % (group['id'], block, group['id'])
        html, n = re.subn(r'<!-- %s:start -->.*?<!-- %s:end -->' % (group['id'], group['id']),
                          lambda _: marked, html, count=1, flags=re.S)
        if not n:
            raise SystemExit('в %s нет маркеров <!-- %s:start --> / <!-- %s:end -->'
                             % (slug, group['id'], group['id']))
        for item in group['items']:
            files = files_of(group, item)
            files_total += len(files)
            missing += [f for f in files
                        if not os.path.exists(os.path.join(lesson, f.replace('/', os.sep)))]

    io.open(path, 'w', encoding='utf-8').write(html)
    print('%s: групп %d, записей %d' % (slug, len(data['groups']), files_total))
    for f in missing:
        print('   нет озвучки:', f, '— запустите tools/tts_phrases.py')


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    slugs = sys.argv[1:] or [d for d in sorted(os.listdir(os.path.join(SITE, 'lessons')))
                             if os.path.isfile(os.path.join(SITE, 'lessons', d, 'phrases.json'))]
    for s in slugs:
        build(s)
    return 0


if __name__ == '__main__':
    sys.exit(main())
