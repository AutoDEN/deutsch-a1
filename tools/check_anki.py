# -*- coding: utf-8 -*-
"""
Проверка готовой колоды .apkg — тем же набором правил, что применяет сам Anki.

Anki при импорте и при «Инструменты → Проверить базу данных» делает несколько
проверок, и часть из них молча ЧИНИТ или УДАЛЯЕТ данные. Самая опасная —
заметки с пустым первым полем: они удаляются без вопросов. Поэтому колоду
имеет смысл проверить до того, как она попадёт в Anki.

Что проверяется:

  формат      в архиве есть collection.anki2 и media; база открывается
  col         одна строка, ver = 11, во всех json-полях валидный JSON
  тип заметки поля пронумерованы 0..n-1, sortf в диапазоне, req ссылается
              на существующие поля, шаблоны есть
  заметки     mid существует; число полей совпадает с типом заметки;
              ПЕРВОЕ ПОЛЕ НЕ ПУСТОЕ; guid уникален; csum совпадает с первым
              полем; sfld совпадает с полем сортировки
  карточки    nid существует; did существует; ord < числа шаблонов;
              у новых карточек due = позиция и не больше conf.nextPos
  шаблон      все поля, на которые ссылается шаблон, есть в типе заметки

Запуск:  python tools/check_anki.py [путь к .apkg]
"""

import hashlib
import io
import json
import os
import re
import sqlite3
import sys
import tempfile
import zipfile

TOOLS = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.dirname(TOOLS)
DEFAULT = os.path.join(SITE, 'data', 'anki', 'woerter-der-lektionen.apkg')


def field_checksum(text):
    plain = re.sub(r'<[^>]+>', '', text).replace('&nbsp;', ' ').replace('&amp;', '&').strip()
    return int(hashlib.sha1(plain.encode('utf-8')).hexdigest()[:8], 16)


def strip_tags(s):
    return ' '.join(re.sub(r'<[^>]+>', '', s).split())


def check(path):
    problems, notes_ok = [], 0
    warnings = []

    def bad(fmt, *args):
        """Ошибка: Anki либо не откроет колоду, либо молча испортит данные."""
        problems.append(fmt % args if args else fmt)

    def warn(fmt, *args):
        """Замечание: Anki это переживёт и починит сам, но лучше сделать правильно."""
        warnings.append(fmt % args if args else fmt)

    # ---- архив
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        if 'collection.anki2' not in names:
            bad('в архиве нет collection.anki2')
            return problems, warnings, 0
        if 'media' not in names:
            bad('в архиве нет файла media (Anki ждёт его даже пустым)')
        tmp = os.path.join(tempfile.gettempdir(), '_check.anki2')
        with io.open(tmp, 'wb') as f:
            f.write(z.read('collection.anki2'))

    con = sqlite3.connect(tmp)
    con.text_factory = str

    # ---- col
    rows = con.execute('select id, ver, conf, models, decks, dconf from col').fetchall()
    if len(rows) != 1:
        bad('в таблице col %d строк, должна быть одна', len(rows))
        return problems, warnings, 0
    _, ver, conf_s, models_s, decks_s, dconf_s = rows[0]
    if ver != 11:
        bad('версия схемы %s, Anki ждёт 11', ver)
    try:
        conf = json.loads(conf_s)
        models = json.loads(models_s)
        decks = json.loads(decks_s)
        json.loads(dconf_s)
    except ValueError as e:
        bad('невалидный JSON в col: %s', e)
        return problems, warnings, 0

    # ---- тип заметки
    for mid, m in models.items():
        names = [f['name'] for f in m['flds']]
        ords = [f['ord'] for f in m['flds']]
        if ords != list(range(len(names))):
            bad('%s: поля пронумерованы %s, ожидалось 0..%d', m['name'], ords, len(names) - 1)
        if not 0 <= m['sortf'] < len(names):
            bad('%s: sortf = %s, а полей %d', m['name'], m['sortf'], len(names))
        if not m['tmpls']:
            bad('%s: нет ни одного шаблона карточки', m['name'])
        for r in m.get('req', []):
            for o in r[2]:
                if o >= len(names):
                    bad('%s: req ссылается на поле №%d, которого нет', m['name'], o)
        # поля, на которые ссылается шаблон, должны существовать
        for t in m['tmpls']:
            used = set(re.findall(r'\{\{[#^/]?([a-zA-Z_][\w-]*)\}\}', t['qfmt'] + t['afmt']))
            for name in used - {'FrontSide', 'Tags', 'Type', 'Deck', 'Subdeck', 'Card'}:
                if name not in names:
                    bad('%s / %s: шаблон обращается к полю «%s», которого нет в типе заметки',
                        m['name'], t['name'], name)

    # ---- заметки
    guids = {}
    for nid, guid, mid, tags, flds, sfld, csum in con.execute(
            'select id, guid, mid, tags, flds, sfld, csum from notes'):
        m = models.get(str(mid))
        if m is None:
            bad('заметка %s ссылается на несуществующий тип %s', nid, mid)
            continue
        values = flds.split('\x1f')
        if len(values) != len(m['flds']):
            bad('заметка %s: полей %d, а в типе заметки %d', nid, len(values), len(m['flds']))
            continue
        if not strip_tags(values[0]):
            bad('заметка %s: ПУСТОЕ ПЕРВОЕ ПОЛЕ — Anki удалит её при проверке базы', nid)
            continue
        if guid in guids:
            bad('заметка %s: guid совпадает с заметкой %s', nid, guids[guid])
        guids[guid] = nid
        if csum != field_checksum(values[0]):
            # Anki пересчитывает csum при проверке базы, поэтому это не ошибка.
            # В колоде курса csum вообще нули — и она отлично работает.
            warn('заметка %s: csum не соответствует первому полю', nid)
        want_sfld = strip_tags(values[m['sortf']])
        if str(sfld) != want_sfld:
            bad('заметка %s: sfld «%s», а поле сортировки «%s»', nid, sfld, want_sfld)
        if tags != tags.strip() and not (tags.startswith(' ') and tags.endswith(' ')):
            bad('заметка %s: теги должны быть окружены пробелами: %r', nid, tags)
        notes_ok += 1

    # ---- карточки
    note_ids = {r[0]: r[1] for r in con.execute('select id, mid from notes')}
    next_pos = conf.get('nextPos', 0)
    for cid, nid, did, ordi, due, typ in con.execute(
            'select id, nid, did, ord, due, type from cards'):
        if nid not in note_ids:
            bad('карточка %s: заметки %s не существует', cid, nid)
            continue
        if str(did) not in decks:
            bad('карточка %s: колоды %s не существует', cid, did)
        m = models[str(note_ids[nid])]
        if ordi >= len(m['tmpls']):
            bad('карточка %s: шаблон №%d, а их %d', cid, ordi, len(m['tmpls']))
        if typ == 0 and due >= next_pos:
            # при импорте Anki всё равно раздаёт позиции заново
            warn('карточка %s: позиция %s не меньше conf.nextPos (%s)', cid, due, next_pos)

    # ---- колода назначения у типа заметки
    for m in models.values():
        if m.get('did') and str(m['did']) not in decks:
            bad('%s: колода по умолчанию %s не существует', m['name'], m['did'])

    con.close()
    os.remove(tmp)
    return problems, warnings, notes_ok


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT
    problems, warnings, notes_ok = check(path)

    print('колода: %s (%.0f КБ)' % (os.path.relpath(path, SITE), os.path.getsize(path) / 1024.0))
    print('заметок без замечаний: %d' % notes_ok)
    print()
    def dump(title, rows):
        if not rows:
            return
        print('%s (%d):' % (title, len(rows)))
        for r in rows[:15]:
            print('   ' + r)
        if len(rows) > 15:
            print('   … и ещё %d того же вида' % (len(rows) - 15))
        print()

    dump('ОШИБКИ — Anki сломается или потеряет данные', problems)
    dump('замечания — Anki починит сам', warnings)
    if problems:
        return 1
    print('ошибок нет: колода готова к импорту'
          + (' (замечания некритичны)' if warnings else ''))
    return 0


if __name__ == '__main__':
    sys.exit(main())
