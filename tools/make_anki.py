# -*- coding: utf-8 -*-
"""
Вторая колода Anki: слова уроков, которых нет в первых 300.

Курс даёт колоду на 300 самых частотных слов. В словарях наших уроков таких
слов меньше трети — остальные тематические, и учить их тоже надо. Этот скрипт
собирает всё, чего в колоде курса нет, в отдельную колоду .apkg с ТЕМ ЖЕ типом
заметки: те же поля, тот же шаблон карточки, тот же CSS.

Номер в частотном списке ставится только там, где его дал автор курса. Так
у нескольких слов урока 1 номер есть, просто он за пределами первых 300
(danke — 773, tschüss — 3632), и жёлтый бейдж на карточке появится. У остальных
слов номера нет вообще, бейдж не показывается: выдумывать его нельзя.

Данные берутся из готовых страниц уроков, а не из vocab.json: у урока 1
своего json нет (он импортирован с сайта автора), а разметка словаря у всех
уроков одинаковая.

Формат .apkg — zip с collection.anki2 (SQLite схемы 11) и файлом media.
Схема таблиц и тип заметки копируются из исходной колоды курса.

Запуск:  python tools/make_anki.py
Пишет:   site/data/anki/woerter-der-lektionen.apkg
"""

import hashlib
import io
import json
import os
import random
import re
import sqlite3
import sys
import time
import zipfile

TOOLS = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.dirname(TOOLS)
SOURCE_APKG = os.path.join(os.path.dirname(SITE), 'nem-slova-4500-free-preview-300.apkg')
OUT_DIR = os.path.join(SITE, 'data', 'anki')
OUT = os.path.join(OUT_DIR, 'woerter-der-lektionen.apkg')

DECK_NAME = 'Немецкий для жизни A1 · слова уроков'
MODEL_NAME = 'Нем-слова · уроки курса'

FIELDS = ['rank', 'german', 'gender', 'ipa', 'pos_display', 'german_example',
          'russian_example', 'russian', 'german_rektion', 'verb_forms', 'audio']

# Порядок полей в НАШЕЙ колоде: german первым.
#
# В колоде курса первым полем идёт rank, и это нам не подходит: у большинства
# наших слов номера нет. А Anki считает первое поле обязательным — «Check
# Database» молча удаляет заметки с пустым первым полем, то есть колода
# развалилась бы при первой же проверке базы. Поэтому меняем местами два первых
# поля: german непустой всегда.
#
# На вид карточки это не влияет: шаблон обращается к полям по имени, а не по
# номеру. Меняется только порядок строк в редакторе заметки.
ORDER = ['german', 'rank', 'gender', 'ipa', 'pos_display', 'german_example',
         'russian_example', 'russian', 'german_rektion', 'verb_forms', 'audio']

GENDERS = ('der', 'die', 'das')


# ------------------------------------------------------------------ разбор

def strip_tags(s):
    return ' '.join(re.sub(r'<[^>]+>', '', s).split())


def read_lessons():
    """Слова со всех страниц уроков: только те, у которых нет номера в списке."""
    words = []
    lessons = os.path.join(SITE, 'lessons')
    for slug in sorted(os.listdir(lessons)):
        path = os.path.join(lessons, slug, 'index.html')
        if not os.path.isfile(path):
            continue
        html = io.open(path, encoding='utf-8').read()
        # режем по началу карточки, а не по закрывающим тегам: у урока 1
        # вёрстка пришла с сайта автора и переносы строк там расставлены иначе
        for block in html.split('<div class="voc">')[1:]:
            block = block.split('<!-- vocab:end -->')[0]
            def field(cls):
                m = re.search(r'<div class="%s[^"]*">(.*?)</div>' % cls, block, re.S)
                return strip_tags(m.group(1)) if m else ''

            head = re.search(r'<div class="voc-word">(.*?)</div>', block, re.S)
            if not head:
                continue
            ipa = re.search(r'<span class="voc-ipa">\[(.*?)\]</span>', head.group(1), re.S)
            plain = strip_tags(re.sub(r'<span class="voc-ipa">.*?</span>', '',
                                      head.group(1), flags=re.S))
            # В колоду курса входят первые 300 слов. Всё, что за их пределами,
            # идёт к нам — включая слова урока 1 с авторскими номерами вроде
            # danke #773: номер есть, но карточки в колоде нет.
            rank = re.search(r'<span class="voc-rank">(\d+)</span>', block)
            rank = int(rank.group(1)) if rank else None
            if rank is not None and rank <= 300:
                continue

            gender = ''
            lemma = plain
            m = re.match(r'^(der|die|das)\s+(.+)$', plain)
            if m:
                gender, lemma = m.group(1), m.group(2)

            words.append({
                'slug': slug,
                'rank': rank,
                'lemma': lemma,
                'gender': gender,
                'ipa': ipa.group(1) if ipa else '',
                'forms': field('voc-forms'),
                'ru': field('voc-ru'),
                'ex': field('voc-ex'),
                'ex_ru': field('voc-ex-ru'),
                'note': field('voc-note'),
            })
    return words


def plural_of(forms, lemma):
    """Множественное число в стиле исходной колоды: «Tag, -e», «Lehrer, -».

    Если множественное отличается только окончанием, пишем окончание;
    если форма не совпадает (умлаут: Ausflug -> Ausflüge) — пишем целиком.
    «без мн. ч.» даёт пустую строку.
    """
    m = re.match(r'^мн\.\s+(?:der|die|das)\s+(\S+)', forms)
    if not m:
        return ''
    pl = m.group(1)
    if pl == lemma:
        return '-'
    if pl.startswith(lemma):
        return '-' + pl[len(lemma):]
    return pl


def pos_of(w):
    """Часть речи — по данным записи, без догадок.

    Существительное выдаёт артикль, глагол — три формы через «·»,
    прилагательное — степень сравнения «am …sten». Всё прочее оставляем
    пустым: на карточке подпись просто не появится.
    """
    if w['gender']:
        return 'noun'
    if ' · ' in w['forms'] and re.search(r'\b(hat|ist)\b', w['forms']):
        return 'verb'
    if re.search(r',\s*am\s+\S+sten', w['forms']):
        return 'adjective'
    return ''


def german_field(w):
    """Заголовок карточки в формате исходной колоды."""
    if w['gender']:
        art = '<span class="art">%s</span> %s' % (w['gender'], w['lemma'])
        pl = plural_of(w['forms'], w['lemma'])
        return '%s, %s' % (art, pl) if pl else art
    return w['lemma']


def verb_forms_field(w, pos):
    """Три формы глагола, как в исходной колоде: «machen - machte - hat gemacht»."""
    if pos == 'verb':
        parts = [p.strip() for p in w['forms'].split('·')]
        if len(parts) == 2:
            return '%s - %s - %s' % (w['lemma'], parts[0], parts[1])
        return w['forms']
    if pos == 'adjective':
        return w['forms']            # «bunter, am buntesten» — тоже формы слова
    return ''


def lesson_tag(slug):
    m = re.match(r'^(\d\d)-', slug)
    if m:
        return 'урок-%s' % m.group(1)
    return 'подготовительный'


# ---------------------------------------------------------------- сборка

def source_model():
    """Тип заметки из колоды курса: поля, шаблон и CSS берём как есть."""
    with zipfile.ZipFile(SOURCE_APKG) as z:
        raw = z.read('collection.anki2')
    tmp = os.path.join(OUT_DIR, '_source.anki2')
    with io.open(tmp, 'wb') as f:
        f.write(raw)
    con = sqlite3.connect(tmp)
    models = json.loads(con.execute('select models from col').fetchone()[0])
    schema = [r[0] for r in con.execute("select sql from sqlite_master where sql is not null")]
    con.close()
    os.remove(tmp)
    model = list(models.values())[0]
    assert [f['name'] for f in model['flds']] == FIELDS, 'поля исходной колоды изменились'
    return model, schema


def field_checksum(text):
    """Контрольная сумма первого поля — тем же способом, что считает Anki.

    По ней Anki ищет дубликаты. Если у всех заметок она одинаковая (а так
    и выходит, когда первое поле пустое), поиск дубликатов не работает.
    """
    plain = re.sub(r'<[^>]+>', '', text).replace('&nbsp;', ' ').replace('&amp;', '&').strip()
    return int(hashlib.sha1(plain.encode('utf-8')).hexdigest()[:8], 16)


def guid():
    """Anki хранит guid как base91 от случайного числа; хватает случайной строки."""
    alphabet = ('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
                '!#$%&()*+,-./:;<=>?@[]^_`{|}~')
    return ''.join(random.choice(alphabet) for _ in range(10))


AUDIO_DIR = os.path.join(OUT_DIR, 'audio')


def audio_for(w, media):
    """Ссылка на озвучку слова — если файл записан.

    Имя файла считает tts_words.py по слову и уроку, поэтому здесь достаточно
    повторить тот же расчёт. Если файла нет, поле остаётся пустым, и на
    карточке просто не будет кнопки воспроизведения.
    """
    key = ('%s|%s|%s' % (w['slug'], w['gender'], w['lemma'])).encode('utf-8')
    name = 'lekt-%s.mp3' % hashlib.sha1(key).hexdigest()[:8]
    if not os.path.isfile(os.path.join(AUDIO_DIR, name)):
        return ''
    media[str(len(media))] = name
    return '[sound:%s]' % name


def build(words):
    if not os.path.isdir(OUT_DIR):
        os.makedirs(OUT_DIR)
    model, schema = source_model()

    now = int(time.time())
    now_ms = now * 1000
    model_id = 1900450100          # свой id: чтобы не перезаписать тип заметки курса
    deck_id = 1900450101

    model = json.loads(json.dumps(model))       # копия
    model['id'] = model_id
    model['name'] = MODEL_NAME
    # переставляем поля в порядке ORDER: german первым (см. комментарий к ORDER)
    by_name = {f['name']: f for f in model['flds']}
    model['flds'] = []
    for i, name in enumerate(ORDER):
        fld = by_name[name]
        fld['ord'] = i
        model['flds'].append(fld)
    model['sortf'] = 0                          # сортировка по первому полю, german
    # req: какие поля нужны, чтобы карточка вообще создалась. Местами меняются
    # только два первых поля, оба и так в списке, поэтому набор номеров прежний.
    model['req'] = [[0, 'any', sorted(ORDER.index(n) for n in
                                      ('german', 'rank', 'gender', 'pos_display',
                                       'german_example', 'audio'))]]
    model['mod'] = now
    model['did'] = deck_id
    for t in model['tmpls']:
        t['did'] = None

    decks = {
        '1': {'id': 1, 'name': 'Default', 'mod': now, 'usn': -1, 'lrnToday': [0, 0],
              'revToday': [0, 0], 'newToday': [0, 0], 'timeToday': [0, 0], 'collapsed': True,
              'browserCollapsed': True, 'desc': '', 'dyn': 0, 'conf': 1, 'extendNew': 0,
              'extendRev': 0},
        str(deck_id): {'id': deck_id, 'name': DECK_NAME, 'mod': now, 'usn': -1,
                       'lrnToday': [0, 0], 'revToday': [0, 0], 'newToday': [0, 0],
                       'timeToday': [0, 0], 'collapsed': False, 'browserCollapsed': False,
                       'desc': 'Слова из уроков курса «Немецкий для жизни A1», '
                               'которых нет в колоде первых 300 слов.',
                       'dyn': 0, 'conf': 1, 'extendNew': 0, 'extendRev': 0},
    }
    dconf = {'1': {'id': 1, 'name': 'Default', 'mod': 0, 'usn': 0, 'maxTaken': 60,
                   'autoplay': True, 'timer': 0, 'replayq': True,
                   'new': {'bury': False, 'delays': [1.0, 10.0], 'initialFactor': 2500,
                           'ints': [1, 4, 0], 'order': 1, 'perDay': 20},
                   'rev': {'bury': False, 'ease4': 1.3, 'ivlFct': 1.0, 'maxIvl': 36500,
                           'perDay': 200, 'hardFactor': 1.2},
                   'lapse': {'delays': [10.0], 'leechAction': 1, 'leechFails': 8,
                             'minInt': 1, 'mult': 0.0},
                   'dyn': False, 'newMix': 0, 'newPerDayMinimum': 0, 'interdayLearningMix': 0,
                   'reviewOrder': 0, 'newSortOrder': 0, 'newGatherPriority': 0,
                   'buryInterdayLearning': False}}
    conf = {'activeDecks': [1], 'curDeck': 1, 'newSpread': 0, 'collapseTime': 1200,
            'timeLim': 0, 'estTimes': True, 'dueCounts': True, 'curModel': str(model_id),
            'nextPos': len(words) + 1, 'sortType': 'noteFld', 'sortBackwards': False,
            'addToCur': True, 'dayLearnFirst': False, 'schedVer': 2}

    db_path = os.path.join(OUT_DIR, '_build.anki2')
    if os.path.exists(db_path):
        os.remove(db_path)
    con = sqlite3.connect(db_path)
    for sql in schema:
        con.execute(sql)
    con.execute('insert into col values (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (1, now - 86400, now_ms, now_ms, 11, 0, 0, 0,
                 json.dumps(conf), json.dumps({str(model_id): model}),
                 json.dumps(decks), json.dumps(dconf), '{}'))

    media = {}          # имя внутри архива -> имя файла, как его увидит Anki
    nid = now_ms
    for pos_i, w in enumerate(words):
        pos = pos_of(w)
        sound = audio_for(w, media)
        flds = {
            # номер ставим только тот, что дал автор курса; выдумывать нельзя
            'rank': str(w['rank']) if w['rank'] else '',
            'german': german_field(w),
            'gender': w['gender'],
            'ipa': w['ipa'],
            'pos_display': pos,
            'german_example': w['ex'],
            'russian_example': w['ex_ru'],
            'russian': w['ru'],
            'german_rektion': '',
            'verb_forms': verb_forms_field(w, pos),
            'audio': sound,               # [sound:...] или пусто, если файла нет
        }
        row = '\x1f'.join(flds[f] for f in ORDER)
        tags = ' %s вне-первых-300 ' % lesson_tag(w['slug'])
        con.execute('insert into notes values (?,?,?,?,?,?,?,?,?,?,?)',
                    (nid, guid(), model_id, now, -1, tags, row,
                     strip_tags(flds['german']),          # sfld: по нему сортировка и поиск
                     field_checksum(flds['german']), 0, ''))
        con.execute('insert into cards values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (nid + 1, nid, deck_id, 0, now, -1, 0, 0, pos_i + 1,
                     0, 0, 0, 0, 0, 0, 0, 0, ''))
        nid += 2

    con.commit()
    con.close()

    if os.path.exists(OUT):
        os.remove(OUT)
    # .apkg кладёт медиа под номерами, а настоящие имена держит в файле media
    with zipfile.ZipFile(OUT, 'w', zipfile.ZIP_DEFLATED) as z:
        z.write(db_path, 'collection.anki2')
        z.writestr('media', json.dumps(media, ensure_ascii=False))
        for num, name in media.items():
            z.write(os.path.join(AUDIO_DIR, name), num)
    os.remove(db_path)


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    words = read_lessons()
    words.sort(key=lambda w: (w['rank'] or 10 ** 6, w['lemma']))
    build(words)

    by_pos = {}
    for w in words:
        by_pos[pos_of(w) or 'прочее'] = by_pos.get(pos_of(w) or 'прочее', 0) + 1
    print('слов вне первых 300: %d' % len(words))
    print('по частям речи: %s' % ', '.join('%s %d' % kv for kv in sorted(by_pos.items())))
    print('колода: %s (%.0f КБ)' % (os.path.relpath(OUT, SITE), os.path.getsize(OUT) / 1024.0))


if __name__ == '__main__':
    main()
