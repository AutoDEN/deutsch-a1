# -*- coding: utf-8 -*-
"""
Проверка контрольной работы: не появилось ли в ней слово, которого не было
в уроках, за которые она отвечает.

Главная договорённость с владельцем — ничего не выдумывать (README §4.1).
Для урока это проверяется глазами при сборке, а контрольная сводит пять уроков
сразу, и там легко написать «правильную» немецкую фразу со словом, которого
студент ещё не видел. Скрипт берёт все немецкие слова со страницы контрольной
и сверяет их со словарём охваченных уроков.

Что считается известным: всё, что есть на страницах уроков с первого по тот,
за которым стоит контрольная (диалоги, словарь, фразы наизусть, упражнения
вместе с ответами), плюс реплики из их phrases.json. Курс накопительный:
во второй контрольной «Ich heiße» законно, хотя разбиралось оно в уроке 2.
Кириллица не смотрится вовсе: задания и подсказки на русском.

Отдельно разрешены служебные слова самой контрольной (Teil, Aufgabe, richtig,
falsch и т.п.) — это язык бланка, а не материал урока; список ниже, SERVICE.

Запуск:  python tools/check_test.py [слаг ...]     (без аргументов — все)
Вывод:   пусто = чисто. Иначе список слов и где они встретились.
"""

import io
import json
import os
import re
import sys

TOOLS = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.dirname(TOOLS)
sys.path.insert(0, SITE)
from build import TESTS, SLUGS                      # noqa: E402  (нужен путь выше)

# Язык самого бланка: названия частей, «верно/неверно», роли в расшифровке.
# Материалом урока они не являются и в словарь не обязаны попадать.
SERVICE = {
    'teil', 'aufgabe', 'wiederholung', 'hören', 'lesen', 'schreiben', 'sprechen',
    'richtig', 'falsch', 'kellnerin', 'erzählt',
}

SCRIPTS = re.compile(r'<(script|style)\b.*?</\1>', re.S | re.I)
TAGS = re.compile(r'<[^>]+>')
WORD = re.compile(r"[A-Za-zÄÖÜäöüß][A-Za-zÄÖÜäöüß\-’']*")


def text_of(html):
    html = SCRIPTS.sub(' ', html)
    html = TAGS.sub(' ', html)
    return html.replace('&#39;', "'").replace('&amp;', '&').replace('&nbsp;', ' ')


def words(text):
    out = set()
    for w in WORD.findall(text):
        for part in w.split('-'):                   # Kopf-schmerzen, AnnenMayKantereit
            if part:
                out.add(part.lower())
    return out


def lesson_words(slug):
    """Всё немецкое, что студент видел на странице урока и слышал в его фразах."""
    folder = os.path.join(SITE, 'lessons', slug)
    known = set()

    page = os.path.join(folder, 'index.html')
    if os.path.isfile(page):
        known |= words(text_of(io.open(page, encoding='utf-8').read()))

    phrases = os.path.join(folder, 'phrases.json')
    if os.path.isfile(phrases):
        data = json.load(io.open(phrases, encoding='utf-8'))
        for group in data['groups']:
            for item in group['items']:
                for line in item['lines']:
                    known |= words(line.get('de', ''))
                    known |= words(line.get('speak', ''))
    return known


def covered(test):
    """Слаги всех уроков, пройденных к этой контрольной.

    Тема контрольной — последние пять уроков, но язык у курса накопительный:
    ко второй контрольной студент знает и «Ich heiße», и «Wie lange», хотя
    разбирались они раньше. Поэтому словарь берётся с первого урока по тот,
    за которым контрольная стоит, — иначе скрипт ругался бы на давно
    выученные слова и его перестали бы читать.
    """
    return ['%02d-%s' % (n, SLUGS[n]) for n in range(1, test['after'] + 1)]


def check(test):
    folder = os.path.join(SITE, 'lessons', test['slug'])
    page = os.path.join(folder, 'index.html')
    if not os.path.isfile(page):
        print('%s: страницы нет, пропускаю' % test['slug'])
        return 0

    known = set(SERVICE)
    for slug in covered(test):
        known |= lesson_words(slug)

    html = io.open(page, encoding='utf-8').read()
    unknown = sorted(w for w in words(text_of(html)) if w not in known)

    # то же самое для озвучки: в mp3 слова не видно, а слушать её студенту
    for name in ('tts', 'phrases.json'):
        path = os.path.join(folder, name)
        if name == 'phrases.json' and os.path.isfile(path):
            data = json.load(io.open(path, encoding='utf-8'))
            said = set()
            for group in data['groups']:
                for item in group['items']:
                    for line in item['lines']:
                        said |= words(line.get('speak') or line.get('de', ''))
            unknown += sorted(w for w in said if w not in known and w not in unknown)
        elif name == 'tts' and os.path.isdir(path):
            said = set()
            for f in sorted(os.listdir(path)):
                if f.endswith('.json'):
                    data = json.load(io.open(os.path.join(path, f), encoding='utf-8'))
                    for line in data['lines']:
                        said |= words(line['text'])
            unknown += sorted(w for w in said if w not in known and w not in unknown)

    print('%s (тема: уроки %d–%d, словарь: уроки 1–%d): известных слов %d' % (
        test['slug'], test['after'] - 4, test['after'], test['after'], len(known)))
    if unknown:
        print('  ВНЕ КУРСА %d: %s' % (len(unknown), ', '.join(sorted(set(unknown)))))
    else:
        print('  чисто: ни одного слова вне пройденных уроков')
    return len(set(unknown))


if __name__ == '__main__':
    want = sys.argv[1:]
    tests = [t for t in TESTS if not want or t['slug'] in want]
    if not tests:
        raise SystemExit('нет такой контрольной: %s' % ', '.join(want))
    bad = sum(check(t) for t in tests)
    if bad:
        raise SystemExit(1)
