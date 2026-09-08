# -*- coding: utf-8 -*-
"""
Проверка транскрипции во всех словарях уроков.

Слова из первых 300 сверяются с колодой Anki посимвольно — там транскрипция
авторская, и спорить с ней не о чем. Остальные слова (их больше двух третей)
проверяются по правилам чтения из подготовительного урока 1: каждое правило —
это связка «в написании есть X, значит в транскрипции обязан быть Y».

Проверка намеренно грубая и придирчивая: она не доказывает, что транскрипция
верна, но ловит опечатки, забытые знаки долготы, пропущенные умлауты и
неоглушённые конечные согласные — то есть ровно те ошибки, которые легко
допустить, набирая транскрипцию руками.

Запуск:  python tools/check_ipa.py
"""

import io
import json
import os
import re
import sys

TOOLS = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.dirname(TOOLS)
DECK = os.path.join(SITE, 'data', 'frequency-300.json')

# U+0067 «g» и U+0261 «ɡ» — один звук, в колоде встречаются оба написания
NORM = lambda s: s.replace(u'g', u'ɡ')

# Гласные ядра: по ним считаем слоги
NUCLEI = u'iɪyʏeɛøœaɑuʊoɔəɐ'

# Знаки, которые вообще допустимы в нашей транскрипции
ALLOWED = set(u'abdefhijklmnoprstuvxyzæðøœɐɑɒɔəɛɜɡɪɱŋɲʁʃʊʌʏʒʔθçβɟʎʝ'
              u'̯̩̥͡ːˈˌ ')

# Известные и осознанные исключения: слово → почему правило к нему неприменимо
EXCEPTIONS = {
    'bisschen': 'здесь не sch, а s + суффикс -chen: biss|chen [ˈbɪsçən]',
    'Angebot': 'ng на стыке морфем: an|gebot, поэтому [nɡ], а не [ŋ]',
    'recyceln': 'английское заимствование, y читается как [aɪ̯]',
    'Spezialität': 'в -tion-подобном -tät нет [t͡si̯oːn], там [tɛːt]',
}


def load_deck():
    deck = {}
    for d in json.load(io.open(DECK, encoding='utf-8')):
        lemma = re.sub(r'^(der|die|das)\s+', '', d['german_plain']).split(',')[0].strip()
        deck.setdefault(lemma.lower(), []).append(d)
    return deck


def read_vocab():
    """Все слова сайта: слаг урока, лемма, род, номер в списке, транскрипция.

    Урок 1 пришёл с сайта автора и словаря в json не имеет, поэтому читаем
    готовые страницы: разметка словаря у всех уроков одинаковая.
    """
    out = []
    lessons = os.path.join(SITE, 'lessons')
    for slug in sorted(os.listdir(lessons)):
        path = os.path.join(lessons, slug, 'index.html')
        if not os.path.isfile(path):
            continue
        html = io.open(path, encoding='utf-8').read()
        for m in re.finditer(r'<div class="voc-word">(.*?)</div>\s*'
                             r'(?:<div class="voc-freq[^"]*">(.*?)</div>)?', html, re.S):
            word, freq = m.group(1), m.group(2) or ''
            ipa = re.search(r'<span class="voc-ipa">\[(.*?)\]</span>', word, re.S)
            plain = re.sub(r'<span class="voc-ipa">.*?</span>', '', word, flags=re.S)
            plain = ' '.join(re.sub(r'<[^>]+>', '', plain).split())
            rank = re.search(r'<span class="voc-rank">(\d+)</span>', freq)
            out.append({
                'slug': slug,
                'lemma': re.sub(r'^(der|die|das|sich)\s+', '', plain),
                'rank': int(rank.group(1)) if rank else None,
                'ipa': ipa.group(1) if ipa else None,
            })
    return out


def count_syllables(ipa):
    """Слоги в транскрипции: гласные ядра минус неслоговые части дифтонгов."""
    n = 0
    for i, ch in enumerate(ipa):
        if ch in NUCLEI:
            if ipa[i + 1:i + 2] == u'̯':      # ɪ̯ ʊ̯ ɐ̯ — вторая часть дифтонга
                continue
            n += 1
    return n + len(re.findall(u'[nlm]̩', ipa))   # слоговые согласные


def rules(word, ipa):
    """Нарушенные правила чтения. Каждое сверяется с подготовительным уроком 1."""
    w = word.lower()
    bad = []

    def need(cond, signs, why):
        if cond and not any(s in ipa for s in signs):
            bad.append(u'%s → ожидается %s' % (why, u' или '.join(signs)))

    # дифтонги
    need(re.search(r'ei|ai', w), [u'aɪ̯'], 'ei/ai')
    need(re.search(r'eu|äu', w), [u'ɔɪ̯'], 'eu/äu')
    need(re.search(r'au', w) and 'äu' not in w, [u'aʊ̯'], 'au')

    # буквосочетания
    #  -chen — суффикс, s и ch там читаются раздельно: bisschen [ˈbɪsçən]
    need('sch' in w and not re.search(r'schen$', w), [u'ʃ'], 'sch')
    need(re.search(r'^(st|sp)', w), [u'ʃ'], 'st-/sp- в начале слова')
    need('z' in w, [u't͡s'], 'z')
    need('qu' in w, [u'kv'], 'qu')
    #  аффрикаты пишем единообразно, с дугой сверху: t͡s, p͡f, t͡ʃ
    need('pf' in w, [u'p͡f'], 'pf (аффриката пишется с дугой: p͡f)')
    need('tsch' in w, [u't͡ʃ'], 'tsch (аффриката пишется с дугой: t͡ʃ)')
    need('w' in w, [u'v'], 'w')
    need(u'ü' in w, [u'yː', u'ʏ'], 'ü')
    need(u'ö' in w, [u'øː', u'œ'], 'ö')
    need(re.search(r'ung(en)?$', w), [u'ʊŋ'], '-ung')
    need(re.search(r'lich$', w), [u'lɪç'], '-lich')
    need(re.search(r'tion$', w), [u't͡si̯oːn'], '-tion')
    need(re.search(r'(?<!e)ig$', w), [u'ɪç'], '-ig')
    #  chs читается [ks] (wachsen), поэтому ach-Laut там не ищем
    need(re.search(r'[aou]ch', w) and 'chs' not in w, [u'x'], 'ach-Laut (a/o/u + ch)')
    need(re.search(r'[iöüäe]ch', w) and 'chs' not in w, [u'ç'], 'ich-Laut')
    need(re.search(r'ng$', w), [u'ŋ'], 'конечное -ng')

    # долгота гласного — то, что на слух различает Staat и Stadt
    #  «ie» ищем только там, где это действительно диграф: в Feier и schneien
    #  подряд стоят ei + e, а не ie
    need(re.search(r'(?<![aeiouäöü])ie', w), [u'iː', u'i̯', u'i'],
         'ie (долгий [iː]; [i̯] в -ion, краткий [i] в безударном слоге)')
    need(re.search(r'aa', w), [u'aː'], 'aa')
    need(re.search(r'ee', w), [u'eː', u'e'], 'ee')
    need(re.search(r'oo', w), [u'oː'], 'oo')
    #  h удлиняет только одиночную гласную; после дифтонга (Weihnachten) он
    #  просто не читается, а сам дифтонг знака долготы не получает
    need(re.search(r'(?<![aeiouäöü])[aeiouäöü]h(?![aeiouäöü])', w), [u'ː'],
         'гласная + h — долгая')
    #  односложное слово с удвоенной согласной или ck/tz — гласная краткая
    #  (ß сюда не входит: после него гласная как раз долгая — Spaß [ʃpaːs])
    if (count_syllables(ipa) == 1 and u'ː' in ipa
            and re.search(r'(bb|dd|ff|gg|ll|mm|nn|pp|rr|ss|tt|ck|tz)', w)
            and not re.search(r'(aa|ee|oo|ie|[aeiouäöü]h)', w)):
        bad.append(u'удвоенная согласная — гласная должна быть краткой, без [ː]')

    # оглушение в конце слова
    if re.search(r'b$', w) and not ipa.endswith('p'):
        bad.append(u'конечное -b → ожидается [p]')
    if re.search(r'd$', w) and not ipa.endswith('t'):
        bad.append(u'конечное -d → ожидается [t]')
    #  -ng и -ung сюда не относятся: там звук [ŋ], а не [ɡ]
    if re.search(r'(?<!n)g$', w) and not re.search(u'(k|ç)$', ipa):
        bad.append(u'конечное -g → ожидается [k] (или [ç] в -ig)')

    # -er и -en в конце
    if re.search(r'er$', w) and u'ɐ' not in ipa:
        bad.append(u'конечное -er → ожидается [ɐ]')
    if re.search(r'e[nl]$', w) and not re.search(u'(n̩|ən|m̩|l̩|əl|lən)$', ipa):
        bad.append(u'конечное -en/-el → ожидается [n̩] / [ən] / [l̩]')

    # h после гласной не звучит, а удлиняет её
    if re.search(r'[aeiouäöü]h(?![aeiouäöü])', w):
        tail = ipa[1:] if ipa[:1] in u'ˈˌ' else ipa
        if re.search(u'[' + NUCLEI + u']ː?h', tail):
            bad.append(u'h после гласной не произносится, а удлиняет её')

    # ударение: ровно одно основное, если слогов больше одного
    if ipa.count(u'ˈ') != 1 and count_syllables(ipa) > 1:
        bad.append(u'ударений: %d (ожидается ровно одно основное)' % ipa.count(u'ˈ'))

    return bad


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    deck = load_deck()
    words = read_vocab()
    no_ipa, deck_diff, rule_hits, syl_hits, char_hits, skipped = [], [], [], [], [], []
    from_deck = 0

    for w in words:
        if not w['ipa']:
            no_ipa.append(w)
            continue
        for ch in w['ipa']:
            if ch not in ALLOWED:
                char_hits.append((w, 'U+%04X %s' % (ord(ch), ch)))

        cards = deck.get(w['lemma'].lower(), [])
        if cards:
            from_deck += 1
            if NORM(w['ipa']) not in {NORM(c['ipa']) for c in cards}:
                deck_diff.append((w, sorted({c['ipa'] for c in cards})))
            continue                      # авторскую транскрипцию правилами не судим
        if w['lemma'].isupper():
            skipped.append((w, 'аббревиатура, читается по буквам'))
            continue
        if w['lemma'] in EXCEPTIONS:
            skipped.append((w, EXCEPTIONS[w['lemma']]))
            continue

        problems = rules(w['lemma'], w['ipa'])
        if problems:
            rule_hits.append((w, problems))

        n_word = len(re.findall(r'[aeiouäöüyV]',
                                re.sub(r'(ei|ai|eu|äu|au|ie)', 'V', w['lemma'].lower())))
        n_ipa = count_syllables(w['ipa'])
        if abs(n_word - n_ipa) > 1:
            syl_hits.append((w, n_word, n_ipa))

    print(u'слов в словарях: %d · сверено с колодой: %d · проверено правилами: %d · пропущено: %d'
          % (len(words), from_deck, len(words) - from_deck - len(no_ipa) - len(skipped), len(skipped)))
    print()

    def dump(title, rows, fmt):
        print(u'%s: %d' % (title, len(rows)))
        for r in rows:
            print(u'   ' + fmt(r))
        print()

    dump(u'без транскрипции', no_ipa, lambda w: u'%s / %s' % (w['slug'], w['lemma']))
    dump(u'расходится с колодой', deck_diff,
         lambda r: u'%s / %s: [%s], в колоде %s' % (r[0]['slug'], r[0]['lemma'], r[0]['ipa'], r[1]))
    dump(u'недопустимые знаки', char_hits,
         lambda r: u'%s / %s: %s в [%s]' % (r[0]['slug'], r[0]['lemma'], r[1], r[0]['ipa']))
    dump(u'нарушены правила чтения', rule_hits,
         lambda r: u'%s / %-18s [%s]  %s' % (r[0]['slug'], r[0]['lemma'], r[0]['ipa'], u'; '.join(r[1])))
    dump(u'расходится число слогов', syl_hits,
         lambda r: u'%s / %-18s [%s]  в слове ~%d, в транскрипции ~%d'
                   % (r[0]['slug'], r[0]['lemma'], r[0]['ipa'], r[1], r[2]))
    dump(u'сознательно пропущены', skipped,
         lambda r: u'%s / %-18s %s' % (r[0]['slug'], r[0]['lemma'], r[1]))

    total = len(no_ipa) + len(deck_diff) + len(char_hits) + len(rule_hits) + len(syl_hits)
    print(u'всего замечаний:', total)
    return 1 if total else 0


if __name__ == '__main__':
    sys.exit(main())
