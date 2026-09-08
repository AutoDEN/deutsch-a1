# -*- coding: utf-8 -*-
"""
Выкатка сайта на GitHub Pages.

Репозиторий — сама папка site/, поэтому то, что вы правите локально, и есть
то, что публикуется: отдельной «сборки для прода» нет. Из репозитория
исключены только видео (файлы по 130-150 МБ, у GitHub лимит 100 МБ) и колоды
Anki — вместо них онлайн показывается заглушка (shared/offline-assets.js).

Скрипт делает четыре шага: пересобирает манифест и навигацию, добавляет
изменения, коммитит, пушит. GitHub Pages пересобирает сайт сам, изменения
видны онлайн через 30-60 секунд.

Запуск:  python tools/deploy.py "правки урока 7"
         python tools/deploy.py            (сообщение коммита — дата и время)
"""

import datetime
import os
import subprocess
import sys

SITE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def say(text):
    """Свой вывод и вывод build.py должны идти по порядку, а не вперемешку:
    подпроцесс пишет в консоль сразу, а print без flush ждёт буфера."""
    print(text, flush=True)


def git(*args, **kw):
    """git в папке сайта. capture=True — вернуть вывод вместо печати."""
    cmd = ['git', '-C', SITE] + list(args)
    if kw.get('capture'):
        p = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
        return p.returncode, (p.stdout or '') + (p.stderr or '')
    return subprocess.call(cmd), ''


def main():
    if not os.path.isdir(os.path.join(SITE, '.git')):
        sys.exit('В папке сайта нет репозитория. Сначала git init и git remote add origin.')

    message = ' '.join(sys.argv[1:]).strip()
    if not message:
        message = datetime.datetime.now().strftime('Обновление сайта %d.%m.%Y %H:%M')

    say('[1/4] Пересборка')
    code = subprocess.call([sys.executable, os.path.join(SITE, 'build.py')])
    if code:
        sys.exit('build.py завершился с ошибкой — ничего не выкачено.')

    say('\n[2/4] Подготовка изменений')
    if git('add', '-A')[0]:
        sys.exit('git add не сработал.')

    _, staged = git('diff', '--cached', '--stat', capture=True)
    if not staged.strip():
        say('Изменений нет — выкатывать нечего.')
        return
    say(staged.rstrip())

    say('\n[3/4] Коммит: %s' % message)
    if git('commit', '-m', message)[0]:
        sys.exit('git commit не сработал.')

    say('\n[4/4] Отправка на GitHub')
    if git('push')[0]:
        sys.exit('git push не сработал. Проверьте подключение и вход в GitHub.')

    _, url = git('remote', 'get-url', 'origin', capture=True)
    say('\nГотово. Сайт обновится через 30-60 секунд.')
    say(site_url(url.strip()))


def site_url(remote):
    """https://user/repo.git или git@github.com:user/repo.git -> адрес Pages."""
    tail = remote.rstrip('/')
    if tail.endswith('.git'):
        tail = tail[:-4]
    parts = tail.replace(':', '/').split('/')
    if len(parts) < 2:
        return remote
    user, repo = parts[-2], parts[-1]
    return 'https://%s.github.io/%s/' % (user.lower(), repo)


if __name__ == '__main__':
    main()
