# -*- coding: utf-8 -*-
"""
Сборка сайта курса.

Одна папка на диске != один урок: у первых трёх уроков материалы и грамматика
лежат отдельными папками (а папка «05 Урок 2 (грамматика)» вообще вложена
в папку урока 2). Здесь эти половины сводятся в один урок, и нумерация
становится сквозной: подготовительные 1-2, затем уроки 1-30, затем бонус.

Запуск:  python build.py
Пишет:   lessons.json (манифест курса), index.html (список уроков)
         и блок навигации «назад / все уроки / вперёд» в каждой готовой странице.
"""

import io
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, 'site')

# Латинские слаги для адресов: по теме урока, чтобы ссылка читалась.
SLUGS = {
    1: 'begruessung',      2: 'vorstellung',       3: 'herkunft',
    4: 'wie-geht-es',      5: 'zahlen-0-10',       6: 'ja-nein-danke',
    7: 'der-die-das',      8: 'familie',           9: 'telefon-adresse',
    10: 'hobby',           11: 'wg',               12: 'supermarkt',
    13: 'max-tag',         14: 'kleidung',         15: 'buchhandlung',
    16: 'arzttermin',      17: 'garten',           18: 'weg-fragen',
    19: 'wetter',          20: 'einladung-kaffee', 21: 'wochenende-perfekt',
    22: 'beim-arzt',       23: 'verkehr',          24: 'restaurant',
    25: 'markt',           26: 'modalverben',      27: 'muelltrennung',
    28: 'smalltalk',       29: 'feste',            30: 'zukunft',
}
PREP_SLUGS = {1: 'laute', 2: 'grammatik-a1'}
BONUS_SLUG = 'nicos-weg'

# Страницы, которых нет в исходных папках курса: написаны нами в дополнение
# к материалам. В списке уроков идут сразу за подготовительными.
EXTRA = [
    {'n': 3, 'kind': 'guide', 'title': 'Как читать транскрипцию',
     'slug': 'prep-3-transkription', 'sources': []},
]


def scan_sources():
    """Все исходные папки курса, включая вложенную «05 (грамматика)»."""
    found = []
    for name in sorted(os.listdir(ROOT)):
        path = os.path.join(ROOT, name)
        if not os.path.isdir(path) or name == 'site':
            continue
        found.append((name, path))
        # папка 05 лежит внутри папки 06 — достаём её на тот же уровень
        for inner in sorted(os.listdir(path)):
            inner_path = os.path.join(path, inner)
            if os.path.isdir(inner_path) and re.match(r'^\d\d ', inner):
                found.append((inner, inner_path))
    return sorted(found, key=lambda x: x[0])


def media_of(path):
    files = os.listdir(path)
    return {
        'video': sorted(f for f in files if f.endswith('.mp4')),
        'audio': sorted(f for f in files if f.endswith('.mp3')),
        'pdf':   sorted(f for f in files if f.endswith('.pdf')),
        'zip':   sorted(f for f in files if f.endswith('.zip')),
        'html':  sorted(f for f in files if f.endswith('.html')),
    }


def build_manifest():
    lessons = {}   # номер урока -> запись
    preps = {}
    bonus = None

    for name, path in scan_sources():
        title = re.sub(r'_$', '', name)
        title = title.split(' ', 1)[1] if ' ' in title else title

        part = 'materials'
        if '(грамматика)' in title:
            part = 'grammar'
        elif '(материалы)' in title:
            part = 'materials'
        clean = re.sub(r'\s*\((грамматика|материалы)\)\s*$', '', title).strip()

        src = {'part': part, 'folder': os.path.relpath(path, ROOT), 'media': media_of(path)}

        m = re.match(r'^Подготовительный урок (\d+)\s*-\s*(.+)$', clean)
        if m:
            n = int(m.group(1))
            preps.setdefault(n, {'n': n, 'kind': 'prep', 'title': m.group(2).strip(),
                                 'slug': 'prep-%d-%s' % (n, PREP_SLUGS[n]), 'sources': []})
            preps[n]['sources'].append(src)
            continue

        m = re.match(r'^Урок (\d+)\s*-\s*(.+)$', clean)
        if m:
            n = int(m.group(1))
            lessons.setdefault(n, {'n': n, 'kind': 'lesson', 'title': m.group(2).strip(),
                                   'slug': '%02d-%s' % (n, SLUGS[n]), 'sources': []})
            lessons[n]['sources'].append(src)
            continue

        # Папка «36 Бонус - карточки Анки к сериалу Nicos Weg» на диске есть,
        # но владелец решил её не собирать, поэтому в список курса она не идёт.
        bonus = {'n': 0, 'kind': 'bonus', 'title': clean, 'slug': BONUS_SLUG, 'sources': [src]}

    items = ([preps[k] for k in sorted(preps)]
             + [dict(e, sources=[]) for e in EXTRA]
             + [lessons[k] for k in sorted(lessons)])

    for it in items:
        it['sources'].sort(key=lambda s: s['part'])          # grammar раньше materials
        it['ready'] = os.path.isfile(os.path.join(SITE, 'lessons', it['slug'], 'index.html'))
        it['has_video'] = any(s['media']['video'] for s in it['sources'])
        it['has_audio'] = any(s['media']['audio'] for s in it['sources'])
    return items


def label_of(it):
    if it['kind'] == 'lesson':
        return 'Урок %d. %s' % (it['n'], it['title'])
    if it['kind'] == 'prep':
        return 'Подготовительный урок %d. %s' % (it['n'], it['title'])
    if it['kind'] == 'guide':
        return 'Справочник. %s' % it['title']
    return it['title']


def nav_label(it):
    """Подпись для стрелки: короче, чем в списке, — строка навигации узкая."""
    if it['kind'] == 'prep':
        return 'Подготовительный урок %d' % it['n']
    if it['kind'] == 'guide':
        return it['title']
    if it['kind'] == 'lesson':
        return 'Урок %d. %s' % (it['n'], it['title'])
    return it['title']


def render_nav(items, i):
    """Блок «назад / все уроки / вперёд» для страницы items[i].

    Стрелка ведёт к ближайшему ГОТОВОМУ уроку в эту сторону: пока перенесены
    не все уроки, ссылка на ещё не собранную страницу вела бы в 404. Если
    готового соседа нет, показываем соседа по порядку неактивным — чтобы было
    видно, что там дальше.
    """
    def nearest(step):
        j = i + step
        while 0 <= j < len(items):
            if items[j]['ready']:
                return items[j]
            j += step
        return None

    def side(step, arrow):
        cls = 'nav-prev' if step < 0 else 'nav-next'
        target = nearest(step)
        if target:
            text = nav_label(target)
            marked = ('← ' + text) if step < 0 else (text + ' →')
            return '<a class="%s" href="../%s/index.html" title="%s">%s</a>' % (
                cls, target['slug'], label_of(target), marked)
        j = i + step
        if 0 <= j < len(items):
            text = nav_label(items[j])
            marked = ('← ' + text) if step < 0 else (text + ' →')
            return '<span class="%s nav-off" title="%s">%s</span>' % (cls, label_of(items[j]), marked)
        return '<span class="%s nav-off">%s</span>' % (cls, arrow)

    return ('<nav class="lesson-nav">\n%s\n'
            '<a class="nav-mid" href="../../index.html">Все уроки</a>\n%s\n</nav>'
            % (side(-1, '←'), side(1, '→')))


NAV_RE = re.compile(r'<nav class="lesson-nav">.*?</nav>', re.S)


def update_navs(items):
    """Переписывает блок навигации в каждой готовой странице."""
    touched = []
    for i, it in enumerate(items):
        if not it['ready']:
            continue
        path = os.path.join(SITE, 'lessons', it['slug'], 'index.html')
        with io.open(path, encoding='utf-8') as f:
            html = f.read()
        nav = render_nav(items, i)
        if NAV_RE.search(html):
            new_html = NAV_RE.sub(lambda _: nav, html, count=1)
        else:                                    # страница без навигации — ставим перед </article>
            new_html = html.replace('</article>', nav + '\n\n</article>', 1)
        if new_html != html:
            with io.open(path, 'w', encoding='utf-8') as f:
                f.write(new_html)
            touched.append(it['slug'])
    return touched


def anki_cards(path):
    """Сколько карточек в .apkg — читаем прямо из вложенной базы."""
    import sqlite3, tempfile, zipfile
    with zipfile.ZipFile(path) as z:
        raw = z.read('collection.anki2')
    tmp = os.path.join(tempfile.gettempdir(), '_apkg_count.anki2')
    with io.open(tmp, 'wb') as f:
        f.write(raw)
    con = sqlite3.connect(tmp)
    n = con.execute('select count(*) from cards').fetchone()[0]
    con.close()
    os.remove(tmp)
    return n


def render_index(items):
    def row(it):
        label = label_of(it)
        marks = []
        if it['has_video']:
            marks.append('видео')
        if it['has_audio']:
            marks.append('аудио')
        if len(it['sources']) > 1:
            marks.append('грамматика + материалы')
        meta = '<span class="meta">%s</span>' % ' · '.join(marks) if marks else ''

        if it['ready']:
            return ('<li class="done"><a href="lessons/%s/index.html">%s</a>'
                    '<span class="tag">готов</span>%s</li>' % (it['slug'], label, meta))
        return '<li>%s%s</li>' % (label, meta)

    preps = [i for i in items if i['kind'] == 'prep']
    guides = [i for i in items if i['kind'] == 'guide']
    lessons = [i for i in items if i['kind'] == 'lesson']
    ready = sum(1 for i in items if i['ready'])

    def block(title, group):
        if not group:
            return ''
        return '<h2>%s</h2>\n<ul class="toc">\n%s\n</ul>\n' % (
            title, '\n'.join(row(i) for i in group))

    def materials():
        """Файлы, которые качают, а не открывают: колода Anki."""
        apkg = os.path.join(SITE, 'data', 'anki', 'woerter-der-lektionen.apkg')
        if not os.path.isfile(apkg):
            return ''
        size = os.path.getsize(apkg) / 1024.0
        return ('<h2>Материалы</h2>\n<ul class="toc">\n'
                '<li class="done" data-local-only>'
                '<a href="data/anki/woerter-der-lektionen.apkg" download>'
                'Колода Anki: слова уроков вне первых 300</a>'
                '<span class="meta">%.0f КБ · %d карточек</span></li>\n</ul>\n'
                % (size, anki_cards(apkg)))

    return '''<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>Немецкий для жизни A1 — все уроки</title>
<link rel="stylesheet" href="shared/lesson.css">
<style>
.toc{list-style:none; padding:0; margin:20px 0}
.toc li{display:flex; align-items:baseline; gap:10px; flex-wrap:wrap;
        padding:11px 0; border-bottom:1px solid var(--line); color:var(--muted)}
.toc li.done{color:var(--ink)}
.toc a{font-weight:600}
.tag{font-size:11.5px; letter-spacing:.06em; text-transform:uppercase; color:#3f7d46}
.meta{margin-left:auto; font-size:13.5px; color:#a8aeb6}
@media (max-width:560px){ .meta{margin-left:0; flex-basis:100%%} }
</style>
</head>
<body>
<article class="lesson">
<header class="magnet-hero">
<h1>Немецкий для жизни A1</h1>
<p class="magnet-lede">Все уроки курса в одном месте. Перенесено %d из %d.</p>
</header>
<hr class="magnet-rule">
%s%s%s</article>
<script src="shared/offline-assets.js"></script>
</body>
</html>
''' % (ready, len(items),
       block('Подготовительные уроки', preps) + block('Справочники', guides),
       block('Уроки', lessons),
       materials())


if __name__ == '__main__':
    items = build_manifest()
    with open(os.path.join(SITE, 'lessons.json'), 'w', encoding='utf-8') as f:
        json.dump(items, f, ensure_ascii=False, indent=1)
    with open(os.path.join(SITE, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(render_index(items))
    touched = update_navs(items)

    print('позиций в курсе: %d (подготовительных %d, справочников %d, уроков %d)' % (
        len(items),
        sum(1 for i in items if i['kind'] == 'prep'),
        sum(1 for i in items if i['kind'] == 'guide'),
        sum(1 for i in items if i['kind'] == 'lesson')))
    for i in items:
        if len(i['sources']) > 1:
            print('  склеено:', i['slug'], '<-', ' + '.join(s['part'] for s in i['sources']))
    print('готовых страниц:', sum(1 for i in items if i['ready']))
    print('навигация обновлена в:', ', '.join(touched) if touched else '—')
