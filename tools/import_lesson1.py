# -*- coding: utf-8 -*-
"""
Сборка урока 1 из новой версии, опубликованной автором на erosheve.ru.

Исходник (снимок содержимого страницы) лежит в tools/source/. На платформе
xl.ru вся вёрстка набрана инлайновыми стилями — здесь они переводятся в наши
классы из shared/lesson.css, чтобы урок 1 и урок 2 были одним оформлением,
а правка стиля делалась в одном файле.

Выбрасывается только обвязка лид-магнита: подводка «это бесплатный урок»,
фото автора и финальный блок с кнопками покупки. Учебная часть — шпаргалка,
колода, диалоги, словарь, грамматика и девять упражнений — переносится как есть.

Запуск:  python tools/import_lesson1.py
"""

import io
import os
import re

TOOLS = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.dirname(TOOLS)
SRC = os.path.join(TOOLS, 'source', 'a1-urok-1-content.html')
OUT = os.path.join(SITE, 'lessons', '01-begruessung', 'index.html')

# style="…" -> class="…". Разметка машинная, поэтому строки совпадают точь-в-точь.
STYLE_TO_CLASS = [
    ('background:#fff3e6;color:#c2410c;padding:0.05em 0.32em;border-radius:4px;font-weight:600', 'hl'),
    ('color:#e0a11a;letter-spacing:2px', 'dot-on'),
    ('color:#dfe3e9;letter-spacing:2px', 'dot-off'),
    ('display:flex;flex-wrap:wrap;gap:6px 24px;padding:14px 0;border-bottom:1px solid #eef0f3', 'voc'),
    ('flex:0 0 210px;max-width:210px', 'voc-l'),
    ('flex:1 1 320px;min-width:0', 'voc-r'),
    ('font-weight:700;line-height:1.45', 'voc-word'),
    ('font-size:11px;letter-spacing:0.06em;margin-top:3px;color:#9aa3ad', 'voc-freq'),
    ('margin-left:5px', 'voc-rank'),
    ('font-size:12.5px;color:#8a9099;margin-top:2px;line-height:1.4', 'voc-forms'),
    ('font-weight:500', 'voc-ru'),
    ('margin-top:3px', 'voc-ex'),
    ('color:#949aa4;font-size:0.94em;line-height:1.5', 'voc-ex-ru'),
    ('font-size:13px;line-height:1.55;color:#9a7b45;margin-top:8px;border-left:2px solid #f2dfb8;padding-left:10px', 'voc-note'),
    ('color:#2f6fb0;font-weight:700', 'm'),
    ('color:#c0392b;font-weight:700', 'f'),
    ('color:#3f7d46;font-weight:700', 'n'),
    ('background:linear-gradient(180deg,#fffaf3 0%,#fff5e9 100%);border:1px solid #f6d9b0;border-left:5px solid #f59e0b;border-radius:8px;padding:16px 20px;margin:24px 0;', 'note'),
    ('font-size:12px;font-weight:700;letter-spacing:0.09em;text-transform:uppercase;color:#b45309;margin-bottom:8px;', 'note-title'),
    ('color:#4a3b2a;line-height:1.65;', 'note-body'),
    ('background:#f4f9f4;border:1px solid #cfe3cf;border-radius:8px;padding:16px 20px;margin:24px 0;', 'sample'),
    ('font-size:12px;font-weight:700;letter-spacing:0.09em;text-transform:uppercase;color:#3f7d46;margin-bottom:8px;', 'sample-title'),
    ('color:#2f4a33;line-height:1.7;font-style:italic;', 'sample-body'),
]

IPA_FONT = "font-family:'Charis SIL'"

# Медиа урока: имя файла на сайте -> имя в нашей папке media/
MEDIA = {
    'https://erosheve.ru/wp-content/uploads/l1-dialoge.mp3': 'media/dialoge.mp3',
    'https://erosheve.ru/wp-content/uploads/l1-formell-informell.mp3': 'media/formell-informell.mp3',
    'https://erosheve.ru/wp-content/uploads/l1-diktat.mp3': 'media/diktat.mp3',
    'https://erosheve.ru/wp-content/uploads/anki-decks/nem-a1/nem-slova-4500-free-preview-300.apkg':
        '../../shared/nem-slova-4500-free-preview-300.apkg',
}

PAGE = '''<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>Урок 1. Приветствия и прощания — Немецкий для жизни A1</title>
<link rel="stylesheet" href="../../shared/lesson.css">
</head>
<body>

<article class="lesson">

<header class="magnet-hero">
<h1>Урок 1. Приветствия и прощания</h1>
</header>

<hr class="magnet-rule">

%s

<nav class="lesson-nav">
<span class="nav-off">←</span>
<a class="nav-mid" href="../../index.html">Все уроки</a>
<span class="nav-off">→</span>
</nav>

</article>

<script src="../../shared/fillblanks.js"></script>
</body>
</html>
'''


def styles_to_classes(html):
    for style, cls in STYLE_TO_CLASS:
        html = html.replace(' style="%s"' % style, ' class="%s"' % cls)
    # транскрипция: длинный стек шрифтов, поэтому ищем по началу строки
    html = re.sub(r'\s*style="' + re.escape(IPA_FONT) + r'[^"]*"', ' class="voc-ipa"', html)
    html = html.replace(' data-vocab', '')
    return html


def cut_lead_magnet(html):
    """Убирает подводку лид-магнита и финальный блок с кнопками покупки."""
    # всё до первого h2 — это hero: заголовок, подводка, фото автора
    start = html.find('<h2>Прежде чем начать')
    if start < 0:
        raise SystemExit('не найден первый раздел урока')
    # финал: «Вы прошли первый урок из тридцати» и дальше CTA
    end = html.find('<div class="magnet-outro">')
    if end < 0:
        raise SystemExit('не найден финальный блок')
    return html[start:end].strip()


def cut_exam_section(html):
    """Убирает раздел «Где это встретится на экзамене» — по решению владельца сайта.

    Заодно снимает ссылку на него из предыдущего раздела, иначе она повисает.
    Упоминания экзамена внутри самих упражнений остаются: они часть заданий.
    """
    start = html.find('<h3>6. Где это встретится на экзамене</h3>')
    if start < 0:
        return html
    end = html.find('<h2>Упражнения', start)
    html = html[:start] + html[end:]
    return html.replace(' (см. следующий раздел)', '')


def rewrite_media(html):
    for remote, local in MEDIA.items():
        html = html.replace(remote, local)
    left = re.findall(r'(?:src|href)="(https?://[^"]+)"', html)
    external = [u for u in left if 'ankiweb.net' not in u]
    if external:
        print('ВНИМАНИЕ, остались внешние ссылки:')
        for u in sorted(set(external)):
            print('   ', u)
    return html


if __name__ == '__main__':
    src = io.open(SRC, encoding='utf-8').read()
    body = cut_lead_magnet(styles_to_classes(src))
    body = cut_exam_section(body)
    body = rewrite_media(body)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with io.open(OUT, 'w', encoding='utf-8') as f:
        f.write(PAGE % body)

    print('записано:', os.path.relpath(OUT, SITE))
    print('  словарных статей :', body.count('class="voc"'))
    print('  упражнений       :', body.count('class="fillblanks"'))
    print('  врезок           :', body.count('class="note"'), 'жёлтых,',
          body.count('class="sample"'), 'зелёных')
    print('  осталось инлайна :', len(re.findall(r'style="', body)))
