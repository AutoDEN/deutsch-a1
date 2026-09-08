# -*- coding: utf-8 -*-
"""
Сборка блока «Словарь урока» из vocab.json урока.

Словарь урока набран из того же частотного списка, что и колода Anki
(data/frequency-300.json, выгружена из вашего .apkg): номер рядом со словом —
это его место в списке, и оно совпадает с номером карточки. Слова за пределами
первых 300 помечаются отдельно: точного номера для них у нас нет, а выдумывать
его нельзя.

Транскрипция и формы для слов из первых 300 берутся из колоды и сверяются
с тем, что записано в vocab.json, — расхождения печатаются при сборке.

Разметка вставляется в index.html урока между маркерами
<!-- vocab:start --> и <!-- vocab:end -->.

Запуск:  python tools/render_vocab.py [слаг урока ...]
"""

import io
import json
import os
import re
import sys

TOOLS = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.dirname(TOOLS)
DECK = os.path.join(SITE, 'data', 'frequency-300.json')

GENDER_CLASS = {'der': 'm', 'die': 'f', 'das': 'n'}
DECK_SIZE = 300


def load_deck():
    """lemma -> список карточек. У слова может быть несколько: natürlich стоит
    в колоде и прилагательным (73), и наречием (74)."""
    deck = {}
    for d in json.load(io.open(DECK, encoding='utf-8')):
        lemma = re.sub(r'^(der|die|das)\s+', '', d['german_plain']).split(',')[0].strip()
        deck.setdefault(lemma.lower(), []).append(d)
    return deck


def dots(rank):
    """Пять точек — первые 300 слов языка; дальше шкала гаснет."""
    if rank is None:
        return None
    filled = 5 if rank <= DECK_SIZE else 4 if rank <= 800 else 3 if rank <= 2000 else 2
    out = '<span class="dot-on">%s</span>' % ('●' * filled)
    if filled < 5:
        out += '<span class="dot-off">%s</span>' % ('●' * (5 - filled))
    return out


def render_entry(w, deck):
    head = w['lemma']
    if w.get('gender'):
        cls = GENDER_CLASS[w['gender']]
        head = '<span class="%s">%s</span> %s' % (cls, w['gender'], w['lemma'])

    left = ['<div class="voc-word">%s <span class="voc-ipa">[%s]</span></div>' % (head, w['ipa'])]

    rank = w.get('rank')
    if rank:
        left.append('<div class="voc-freq">%s <span class="voc-rank">%d</span></div>'
                    % (dots(rank), rank))
    elif w.get('service'):
        # предлоги, артикли, местоимения: частотность у них ни о чём не говорит
        left.append('<div class="voc-freq voc-freq-out">служеб.</div>')
    else:
        left.append('<div class="voc-freq voc-freq-out">вне первых 300</div>')

    if w.get('forms'):
        left.append('<div class="voc-forms">%s</div>' % w['forms'])

    right = ['<div class="voc-ru">%s</div>' % w['ru'],
             '<div class="voc-ex">%s</div>' % w['ex'],
             '<div class="voc-ex-ru">%s</div>' % w['ex_ru']]
    if w.get('note'):
        right.append('<div class="voc-note">%s</div>' % w['note'])

    return ('<div class="voc">\n<div class="voc-l">\n%s\n</div>\n'
            '<div class="voc-r">\n%s\n</div>\n</div>'
            % ('\n'.join(left), '\n'.join(right)))


def same_ipa(a, b):
    """Сравнение транскрипций.

    U+0067 «g» и U+0261 «ɡ» — один и тот же звук: первый берут из обычной
    раскладки, второй из МФА. В колоде встречаются оба (37 против 3), на
    страницах везде знак МФА, и ругаться на это расхождение незачем.
    """
    return a.replace('g', 'ɡ') == b.replace('g', 'ɡ')


def check_against_deck(words, deck):
    """Сверяет транскрипцию, номер и род с колодой — чтобы данные не разъезжались."""
    problems = []
    for w in words:
        key = w['lemma'].replace('sich ', '').lower()
        cards = deck.get(key)
        if not cards:
            if w.get('rank'):
                problems.append('%s: указан номер %s, но слова нет в колоде' % (w['lemma'], w['rank']))
            continue
        if not w.get('rank'):
            if w.get('homonym'):
                continue          # в колоде другое слово с тем же написанием
            ranks = ', '.join(str(c['rank']) for c in cards)
            problems.append('%s: помечено как вне списка, но в колоде есть под номером %s'
                            % (w['lemma'], ranks))
            continue
        # у слова может быть несколько карточек — берём ту, на которую ссылается номер
        card = next((c for c in cards if c['rank'] == w['rank']), None)
        if card is None:
            ranks = ', '.join(str(c['rank']) for c in cards)
            problems.append('%s: номер %s, а в колоде %s' % (w['lemma'], w['rank'], ranks))
            continue
        if same_ipa(w['ipa'], card['ipa']):
            pass
        else:
            problems.append('%s: транскрипция [%s], в колоде [%s]' % (w['lemma'], w['ipa'], card['ipa']))
        if card['gender'] and w.get('gender') != card['gender']:
            problems.append('%s: род %s, в колоде %s' % (w['lemma'], w.get('gender'), card['gender']))
    return problems


def check_duplicates(slug, words):
    """Ищет слова, уже разобранные в других уроках.

    Курс держится на правиле «ни одно слово не разбирается дважды», а вручную
    за двумя сотнями слов не уследишь. Пассивный список урока 1 («заучивать
    не нужно») тоже считается занятым — эти слова там уже названы.
    """
    passive = {'buchhandlung', 'garten', 'wetter', 'spaziergang', 'nachfrage',
               'gruß', 'müde', 'wunderbar', 'recht'}
    taken = {}
    for other in sorted(os.listdir(os.path.join(SITE, 'lessons'))):
        if other == slug:
            continue
        path = os.path.join(SITE, 'lessons', other, 'index.html')
        if not os.path.isfile(path):
            continue
        html = io.open(path, encoding='utf-8').read()
        for m in re.finditer(r'<div class="voc-word">(.*?)</div>', html, re.S):
            t = re.sub(r'<span class="voc-ipa">.*?</span>', '', m.group(1), flags=re.S)
            t = re.sub(r'<[^>]+>', '', t).strip()
            taken.setdefault(re.sub(r'^(der|die|das|sich)\s+', '', t).lower(), other)

    problems = []
    for w in words:
        key = re.sub(r'^(der|die|das|sich)\s+', '', w['lemma']).lower()
        if key in taken:
            problems.append('%s: уже разобрано в уроке %s' % (w['lemma'], taken[key]))
        elif key in passive:
            problems.append('%s: уже названо в пассивном списке урока 1' % w['lemma'])
    return problems


INTRO = '''<p>Слева — слово, как оно живёт в языке: артикль, транскрипция, частотность и формы. Справа — перевод и пример из диалогов урока. Закройте правую половину листом бумаги и пройдите список сверху вниз: это и есть первая проверка себя.</p>

<p>Артикль выделен цветом: <span class="m">der</span> — мужской род, <span class="f">die</span> — женский, <span class="n">das</span> — средний. Те же три цвета стоят у слов в колоде Anki, так что цвет запоминается вместе со словом.</p>

<p>Под словом — его место в частотном списке, по которому собрана ваша колода: число рядом с точками и есть номер карточки. Слова, которые в первые 300 не входят, помечены отдельно — сказать их всё равно придётся.</p>'''


def build(slug):
    lesson_dir = os.path.join(SITE, 'lessons', slug)
    words = json.load(io.open(os.path.join(lesson_dir, 'vocab.json'), encoding='utf-8'))
    deck = load_deck()

    problems = check_against_deck(words, deck) + check_duplicates(slug, words)
    block = '<!-- vocab:start -->\n%s\n\n%s\n<!-- vocab:end -->' % (
        INTRO, '\n\n'.join(render_entry(w, deck) for w in words))

    path = os.path.join(lesson_dir, 'index.html')
    html = io.open(path, encoding='utf-8').read()
    new_html, n = re.subn(r'<!-- vocab:start -->.*?<!-- vocab:end -->',
                          lambda _: block, html, count=1, flags=re.S)
    if not n:
        raise SystemExit('в %s нет маркеров <!-- vocab:start --> / <!-- vocab:end -->' % slug)
    io.open(path, 'w', encoding='utf-8').write(new_html)

    in_deck = sum(1 for w in words if w.get('rank'))
    print('%s: %d слов (%d из первых 300, %d вне списка)'
          % (slug, len(words), in_deck, len(words) - in_deck))
    for p in problems:
        print('   расхождение с колодой:', p)
    return problems


if __name__ == '__main__':
    # в отчёте печатаются знаки МФА, которых нет в cp1251 — иначе tool падает
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    slugs = sys.argv[1:] or [d for d in sorted(os.listdir(os.path.join(SITE, 'lessons')))
                             if os.path.isfile(os.path.join(SITE, 'lessons', d, 'vocab.json'))]
    for s in slugs:
        build(s)
