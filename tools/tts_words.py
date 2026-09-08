# -*- coding: utf-8 -*-
"""
Озвучка слов для второй колоды Anki: по одному mp3 на слово.

В колоде курса к каждому слову приложен opus-файл примерно на две секунды —
это само слово с артиклем, без примера. Здесь то же самое: «der Wochenmarkt»,
«werfen», «bunt». Голос — тот же рассказчик, что читает диктанты, темп чуть
замедлен, чтобы слышны были окончания.

Имя файла считается из слова и урока, а не из его номера в списке: если словарь
изменится, уже записанные файлы останутся на своих местах.

Скрипт докачивает: уже записанные файлы пропускаются, поэтому его можно
прерывать и запускать снова.

Запуск:  python tools/tts_words.py [--limit N]
Пишет:   site/data/anki/audio/lekt-XXXXXXXX.mp3
"""

import asyncio
import hashlib
import os
import subprocess
import sys
import time

import edge_tts

TOOLS = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.dirname(TOOLS)
AUDIO_DIR = os.path.join(SITE, 'data', 'anki', 'audio')

VOICE = 'de-DE-SeraphinaMultilingualNeural'      # тот же голос, что в диктантах
RATE = '-10%'
BATCH = 4                                        # столько запросов одновременно
FFMPEG = 'ffmpeg'

sys.path.insert(0, TOOLS)
import make_anki                                  # noqa: E402  (нужен путь выше)


def audio_name(w):
    """Стабильное имя файла: от слова и урока, а не от места в списке."""
    key = ('%s|%s|%s' % (w['slug'], w['gender'], w['lemma'])).encode('utf-8')
    return 'lekt-%s.mp3' % hashlib.sha1(key).hexdigest()[:8]


def spoken(w):
    """Что произносим: существительное — с артиклем, остальное — как есть."""
    if w['gender']:
        return '%s %s' % (w['gender'], w['lemma'])
    return w['lemma']


async def synth(text, path):
    tmp = path + '.part'
    comm = edge_tts.Communicate(text, VOICE, rate=RATE)
    await comm.save(tmp)
    # приводим к тому же формату, что и остальные наши аудио
    subprocess.run([FFMPEG, '-y', '-loglevel', 'error', '-i', tmp,
                    '-c:a', 'libmp3lame', '-b:a', '64k', '-ar', '24000', '-ac', '1', path],
                   check=True)
    os.remove(tmp)


async def run(todo):
    done = 0
    for i in range(0, len(todo), BATCH):
        chunk = todo[i:i + BATCH]
        await asyncio.gather(*(synth(t, p) for t, p in chunk))
        done += len(chunk)
        print('   %d / %d' % (done, len(todo)), flush=True)
        await asyncio.sleep(0.3)          # не частим запросами


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    if not os.path.isdir(AUDIO_DIR):
        os.makedirs(AUDIO_DIR)

    words = make_anki.read_lessons()
    limit = None
    if '--limit' in sys.argv:
        limit = int(sys.argv[sys.argv.index('--limit') + 1])

    todo = []
    for w in words:
        path = os.path.join(AUDIO_DIR, audio_name(w))
        if os.path.exists(path) and os.path.getsize(path) > 500:
            continue
        todo.append((spoken(w), path))
    if limit:
        todo = todo[:limit]

    print('слов всего: %d · уже озвучено: %d · озвучить: %d'
          % (len(words), len(words) - len(todo), len(todo)))
    if not todo:
        return 0

    started = time.time()
    asyncio.run(run(todo))
    total = sum(os.path.getsize(os.path.join(AUDIO_DIR, f))
                for f in os.listdir(AUDIO_DIR) if f.endswith('.mp3'))
    print('готово за %.0f с · файлов %d · всего %.1f МБ'
          % (time.time() - started,
             len([f for f in os.listdir(AUDIO_DIR) if f.endswith('.mp3')]),
             total / 1e6))
    return 0


if __name__ == '__main__':
    sys.exit(main())
