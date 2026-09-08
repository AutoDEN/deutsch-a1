# -*- coding: utf-8 -*-
"""
Озвучка материалов урока нейроголосами Microsoft Edge (edge-tts).

Зачем: у курса озвучены диалоги, но нет записей для заданий на слух — диктанта
и «formell oder informell». Их можно собрать из текста самого урока.

Сценарий — JSON: список реплик {voice, text, pause}. ВНИМАНИЕ: pause задаётся
в СЕКУНДАХ (0.7 — семьсот миллисекунд), а не в миллисекундах: 700 здесь
означает почти двенадцать минут тишины после каждой реплики.
Каждая реплика синтезируется
отдельно, паузы вставляются тишиной через ffmpeg, результат склеивается в один mp3.
Разные голоса на персонажей дают ту же «озвучку по ролям», что у автора.

    python tools/tts.py script.json out.mp3

Голоса персонажей курса заданы в VOICES: Lena, Clara, Max, Herr Müller
и нейтральный рассказчик для диктантов.
"""

import asyncio
import io
import json
import os
import subprocess
import sys
import tempfile

import edge_tts

VOICES = {
    'lena':      'de-DE-AmalaNeural',        # студентка
    'clara':     'de-DE-KatjaNeural',        # работает в книжном
    'max':       'de-DE-KillianNeural',      # ровесник Лены
    'mueller':   'de-DE-ConradNeural',       # пожилой сосед
    'erzaehler': 'de-DE-SeraphinaMultilingualNeural',   # рассказчик: диктанты, тексты
}

FFMPEG = 'ffmpeg'


async def synth(text, voice, rate, path):
    kw = {'voice': voice}
    if rate:
        kw['rate'] = rate
    await edge_tts.Communicate(text, **kw).save(path)


def silence(seconds, path):
    subprocess.run([FFMPEG, '-y', '-loglevel', 'error', '-f', 'lavfi',
                    '-i', 'anullsrc=r=24000:cl=mono', '-t', str(seconds),
                    '-q:a', '9', path], check=True)


def concat(parts, out):
    with tempfile.NamedTemporaryFile('w', suffix='.txt', delete=False, encoding='utf-8') as f:
        for p in parts:
            f.write("file '%s'\n" % p.replace('\\', '/'))
        listfile = f.name
    # склейка с перекодированием: у синтеза и у тишины разные параметры, и при
    # -c copy ffmpeg выдаёт кашу в таймкодах — плеер потом врёт с длительностью
    subprocess.run([FFMPEG, '-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0',
                    '-i', listfile, '-c:a', 'libmp3lame', '-b:a', '96k',
                    '-ar', '24000', '-ac', '1', out], check=True)
    os.unlink(listfile)


def build(script_path, out_path):
    script = json.load(io.open(script_path, encoding='utf-8'))
    lines = script['lines']
    rate = script.get('rate', '')          # напр. "-5%" для диктанта

    tmp = tempfile.mkdtemp(prefix='tts-')
    parts = []
    for i, line in enumerate(lines):
        voice = VOICES.get(line.get('voice', 'erzaehler'), line.get('voice'))
        chunk = os.path.join(tmp, '%03d.mp3' % i)
        asyncio.run(synth(line['text'], voice, line.get('rate', rate), chunk))
        parts.append(chunk)
        pause = line.get('pause', script.get('pause', 0))
        if pause:
            sil = os.path.join(tmp, '%03d-p.mp3' % i)
            silence(pause, sil)
            parts.append(sil)

    os.makedirs(os.path.dirname(out_path) or '.', exist_ok=True)
    concat(parts, out_path)
    for p in parts:
        os.unlink(p)
    os.rmdir(tmp)

    size = os.path.getsize(out_path)
    print('готово: %s (%d реплик, %.0f КБ)' % (out_path, len(lines), size / 1024))


if __name__ == '__main__':
    if len(sys.argv) != 3:
        raise SystemExit('использование: python tools/tts.py script.json out.mp3')
    build(sys.argv[1], sys.argv[2])
