/* =====================================================================
   Кнопки «прослушать» у отдельных фраз.

   Обычный <audio controls> на каждую фразу не годится: их по три десятка
   на страницу, и полоса плеера рядом с каждой строкой забивает текст.
   Поэтому разметка даёт кнопку с data-audio, а звук играет один общий
   элемент Audio — заодно новое нажатие само глушит предыдущую фразу.

   Файла нет (в онлайн-версии или при переозвучке) — кнопка гаснет и
   больше не откликается, страница при этом не ломается.
   ===================================================================== */
(function () {
  'use strict';

  var player = new Audio();
  var active = null;      // кнопка, которая играет прямо сейчас

  function reset() {
    if (active) { active.classList.remove('ph-playing'); }
    active = null;
  }

  player.addEventListener('ended', reset);

  player.addEventListener('error', function () {
    if (active) { active.classList.add('ph-play-off'); active.disabled = true; }
    reset();
  });

  document.addEventListener('click', function (e) {
    var btn = e.target.closest && e.target.closest('[data-audio]');
    if (!btn) { return; }
    e.preventDefault();

    var wasActive = (btn === active);
    player.pause();
    reset();
    if (wasActive) { return; }        // второе нажатие по той же кнопке — стоп

    active = btn;
    btn.classList.add('ph-playing');
    player.src = btn.getAttribute('data-audio');

    var mine = btn;
    var p = player.play();
    // play() возвращает обещание, и при смене src оно отклоняется с AbortError
    // уже после того, как заиграла следующая фраза. Гасим состояние только
    // если кнопка с тех пор не сменилась — иначе сбросили бы чужую.
    if (p && p.catch) { p.catch(function () { if (active === mine) { reset(); } }); }
  });
})();
