(function() {
  'use strict';

  // Локальная версия сайта полная, онлайн-версия на GitHub Pages — нет:
  // пять видео по 127–153 МБ не проходят лимит GitHub в 100 МБ на файл,
  // а колоды Anki владелец решил онлайн не выкладывать. Разметка при этом
  // одна на обе версии — иначе каждая пересборка расходилась бы с продом.
  // Разницу прячет этот скрипт.

  var NOTE_VIDEO = 'Видео доступно только в локальной версии сайта: файл ' +
                   'около 140 МБ, GitHub такие не принимает.';
  var NOTE_DECK  = 'Колода Anki доступна только в локальной версии сайта.';

  // Плашка встаёт на место того, что заменяет, поэтому и тег берёт от него:
  // внутри <ul class="toc"> это должен остаться <li>, а не абзац.
  function replaceWithNote(el, text) {
      if (!el.parentNode) return;
      const tag = el.tagName === 'LI' ? 'li' : 'p';
      const note = document.createElement(tag);
      note.className = 'asset-missing';
      note.textContent = text;
      el.parentNode.replaceChild(note, el);
  }

  // Видео. Событие error на <source> не всплывает, поэтому вешаем его на
  // каждый источник отдельно. Работает и на file://, и по http: локально
  // файл на месте, обработчик просто не срабатывает.
  function watchVideo(video) {
      const sources = video.querySelectorAll('source');
      let failed = 0;
      Array.prototype.forEach.call(sources, function(source) {
          source.addEventListener('error', function() {
              failed++;
              if (failed >= sources.length) replaceWithNote(video, NOTE_VIDEO);
          });
      });
  }

  // Колоды. Проверяем не запросом к серверу, а по имени хоста: fetch на
  // file:// блокируется CORS и давал бы ложное срабатывание локально.
  function isProduction() {
      return /(^|\.)github\.io$/.test(location.hostname);
  }

  function run() {
      Array.prototype.forEach.call(document.querySelectorAll('video'), watchVideo);

      if (!isProduction()) return;
      Array.prototype.forEach.call(
          document.querySelectorAll('[data-local-only]'),
          function(el) { replaceWithNote(el, NOTE_DECK); });
  }

  if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', run);
  } else {
      run();
  }
})();
