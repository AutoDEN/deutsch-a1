# -*- coding: utf-8 -*-
"""
Озвучка отдельных фраз урока.

Зачем отдельно от tts.py: тот склеивает сценарий в одну дорожку (диктант,
диалог целиком), а здесь нужна кнопка «прослушать» у каждой фразы наизусть —
значит, каждая фраза это свой файл. Голоса те же, из VOICES в tools/tts.py,
темп обычный: фразы должны звучать так же, как диалоги урока, иначе ученик
привыкает к речи, которой в жизни не бывает.

Два режима, они задаются в phrases.json на уровне группы:

* обычный — файл на реплику; так сделаны фразы наизусть;
* "join": true — все реплики одним файлом, с паузой между ними; так сделаны
  сценки к устному заданию: сценка это цельный кусок речи, и резать её
  по предложениям незачем.

Имя файла = группа + номер фразы + хвост из хеша произносимого текста. Хеш нужен, чтобы
правка текста давала новый файл, а не тихо оставляла старую запись. Файлы,
на которые больше никто не ссылается, скрипт удаляет сам.

Скрипт докачивает: уже записанные фразы пропускаются.

Запуск:  python tools/tts_phrases.py [слаг ...]
Пишет:   lessons/<слаг>/media/phrases/*.mp3
"""

import asyncio
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

import edge_tts

TOOLS = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.dirname(TOOLS)

sys.path.insert(0, TOOLS)
from tts import VOICES                            # noqa: E402  (нужен путь выше)

PAUSE = 0.6                                       # смена роли в сценке, секунды
BATCH = 4                                         # столько запросов одновременно
FFMPEG = 'ffmpeg'

# Синтез оставляет по секунде тишины с краёв и растягивает паузу после
# восклицательного знака до секунды с лишним — из-за этого речь кажется
# медленной, хотя темп у неё обычный. Сверено с авторским dialoge.mp3:
# там между «Hallo Lena!» и «Danke, gut» треть секунды, а не секунда.
# Поэтому: тишину с краёв срезаем до 50 мс, внутренние паузы подрезаем
# до PAUSE_MAX — на слух получается тот же темп, что в диалогах урока.
PAUSE_MAX = 0.35

TRIM = ('silenceremove=start_periods=1:start_silence=0.05:start_threshold=-45dB:'
        'stop_periods=-1:stop_duration=%s:stop_threshold=-45dB:detection=peak,'
        'areverse,'
        'silenceremove=start_periods=1:start_silence=0.05:start_threshold=-45dB:detection=peak,'
        'areverse' % PAUSE_MAX)


def digest(parts):
    return hashlib.sha1('|'.join(parts).encode('utf-8')).hexdigest()[:6]


def voice_of(line):
    return line.get('voice', 'erzaehler')


def spoken(line):
    """Что произносим. Обычно это сама фраза, но у фраз-заготовок с многоточием
    («Ich komme aus…») в поле speak лежит тот же текст, договорённый до конца
    с городом для примера: многоточие вслух не произнесёшь."""
    return line.get('speak', line['de'])


def tracks(group, item):
    """Как реплики фразы раскладываются по файлам: [(имя файла, реплики)].

    Общая для озвучки и для вёрстки: render_phrases.py считает имена этой же
    функцией, поэтому разъехаться они не могут."""
    lines = item['lines']
    if group.get('join'):
        tail = digest(['%s~%s' % (voice_of(l), spoken(l)) for l in lines])
        return [('%s-%s-%s.mp3' % (group['id'], item['id'], tail), lines)]
    return [('%s-%s-%d-%s.mp3' % (group['id'], item['id'], i,
                                  digest([voice_of(l), spoken(l)])), [l])
            for i, l in enumerate(lines, 1)]


def plan(slug):
    """Читает phrases.json урока и возвращает (папка, [(путь, реплики)])."""
    lesson = os.path.join(SITE, 'lessons', slug)
    data = json.load(io.open(os.path.join(lesson, 'phrases.json'), encoding='utf-8'))
    out_dir = os.path.join(lesson, 'media', 'phrases')

    items = []
    for group in data['groups']:
        for item in group['items']:
            for name, lines in tracks(group, item):
                items.append((os.path.join(out_dir, name), lines))
    return out_dir, items


def encode(src, dst):
    """Приводит к формату остальных наших аудио и срезает тишину с краёв."""
    subprocess.run([FFMPEG, '-y', '-loglevel', 'error', '-i', src, '-af', TRIM,
                    '-c:a', 'libmp3lame', '-b:a', '64k', '-ar', '24000', '-ac', '1', dst],
                   check=True)


def silence(seconds, path):
    subprocess.run([FFMPEG, '-y', '-loglevel', 'error', '-f', 'lavfi',
                    '-i', 'anullsrc=r=24000:cl=mono', '-t', str(seconds),
                    '-c:a', 'libmp3lame', '-b:a', '64k', '-ac', '1', path], check=True)


def concat(parts, out):
    with tempfile.NamedTemporaryFile('w', suffix='.txt', delete=False, encoding='utf-8') as f:
        for p in parts:
            f.write("file '%s'\n" % p.replace('\\', '/'))
        listfile = f.name
    # с перекодированием: при -c copy ffmpeg врёт в таймкодах, и плеер
    # показывает не ту длительность
    subprocess.run([FFMPEG, '-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0',
                    '-i', listfile, '-c:a', 'libmp3lame', '-b:a', '64k',
                    '-ar', '24000', '-ac', '1', out], check=True)
    os.unlink(listfile)


async def make(path, lines):
    """Одна реплика — просто запись; несколько — склейка с паузой между ними."""
    tmp = tempfile.mkdtemp(prefix='ph-')
    try:
        parts = []
        for i, line in enumerate(lines):
            raw = os.path.join(tmp, '%02d.raw.mp3' % i)
            cut = os.path.join(tmp, '%02d.mp3' % i)
            await edge_tts.Communicate(spoken(line), VOICES.get(voice_of(line),
                                                                 voice_of(line))).save(raw)
            encode(raw, cut)
            parts.append(cut)
            if i + 1 < len(lines):
                sil = os.path.join(tmp, '%02d.pause.mp3' % i)
                silence(PAUSE, sil)
                parts.append(sil)
        if len(parts) == 1:
            shutil.move(parts[0], path)
        else:
            concat(parts, path)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


async def run(todo):
    done = 0
    for i in range(0, len(todo), BATCH):
        chunk = todo[i:i + BATCH]
        await asyncio.gather(*(make(p, lines) for p, lines in chunk))
        done += len(chunk)
        print('   %d / %d' % (done, len(todo)), flush=True)
        await asyncio.sleep(0.3)          # не частим запросами


def build(slug):
    out_dir, items = plan(slug)
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)

    todo = [(p, lines) for p, lines in items
            if not (os.path.exists(p) and os.path.getsize(p) > 500)]
    print('%s: записей %d · уже озвучено %d · озвучить %d'
          % (slug, len(items), len(items) - len(todo), len(todo)))
    if todo:
        started = time.time()
        asyncio.run(run(todo))
        print('   готово за %.0f с' % (time.time() - started))

    # чистка: файлы старых редакций текста больше никому не нужны
    keep = set(os.path.basename(p) for p, _ in items)
    for f in sorted(os.listdir(out_dir)):
        if f.endswith('.mp3') and f not in keep:
            os.remove(os.path.join(out_dir, f))
            print('   удалён устаревший файл:', f)

    total = sum(os.path.getsize(os.path.join(out_dir, f))
                for f in os.listdir(out_dir) if f.endswith('.mp3'))
    print('   файлов %d · %.0f КБ' % (len(keep), total / 1024))


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
