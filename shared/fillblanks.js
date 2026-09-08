(function() {
  'use strict';

  // --- Data Storage ---
  if (!window.fillBlanksData) window.fillBlanksData = {};
  if (!window.fillBlanksCorrect) window.fillBlanksCorrect = {};

  // Обратная связь = цвет слова + цвет линии. Фон не трогаем:
  // страница не должна «мигать» цветными плашками.
  var LINE = {
    neutral:   '',          // вернуть цвета из CSS
    correct:   '#3f7d46',
    incorrect: '#b4232a',
    shown:     '#2f6fb0'
  };

  // Порядок вариантов в выпадающем списке тасуется, иначе правильный всегда
  // стоял бы первым. Seed — сами варианты, поэтому порядок один и тот же при
  // каждой загрузке страницы (студент не должен видеть «прыгающий» список).
  function shuffleStable(options) {
      let seed = 0;
      const key = options.join('|');
      for (let i = 0; i < key.length; i++) seed = (seed * 31 + key.charCodeAt(i)) >>> 0;
      const rand = function() {
          seed = (seed * 1103515245 + 12345) >>> 0;
          return seed / 4294967296;
      };
      const out = options.slice();
      for (let i = out.length - 1; i > 0; i--) {
          const j = Math.floor(rand() * (i + 1));
          [out[i], out[j]] = [out[j], out[i]];
      }
      return out;
  }

  function escapeAttr(s) {
      return s.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function createFillBlanksQuiz(content, quizId) {
      // Два вида пропуска: ((ответ::подсказка)) — вписать руками;
      // {{верный|вариант|вариант::подсказка}} — выбрать из списка (telc, richtig/falsch).
      const pattern = /\(\(([^:)]+)(?:::(.*?))?\)\)|\{\{([^{}]+?)\}\}/g;
      let match;
      let blanksCount = 0;
      let html = content;
      const answersAndHints = [];

      while ((match = pattern.exec(content)) !== null) {
          const isChoice = match[3] !== undefined;
          let answer, hint, options = null;

          if (isChoice) {
              const parts = match[3].split('::');
              options = parts[0].split('|').map(s => s.trim()).filter(Boolean);
              hint = parts[1] ? parts[1].trim() : '';
              answer = options[0];               // верный вариант пишем первым
          } else {
              answer = match[1].trim();
              hint = match[2] ? match[2].trim() : '';
          }
          answersAndHints.push({ answer, hint });

          const blankId = `${quizId}-${blanksCount}`;
          const hintId = `${blankId}-hint`;
          let replacement = `<span class="fill-blank">`;

          if (isChoice) {
              replacement += `<select class="fill-choice" required data-blank-id="${blankId}" aria-label="Выбор ${blanksCount + 1}">`;
              replacement += `<option value="">— выберите —</option>`;
              shuffleStable(options).forEach(function(opt) {
                  replacement += `<option value="${escapeAttr(opt)}">${opt}</option>`;
              });
              replacement += `</select>`;
          } else {
          // Ширина поля — ступенькой по длине ответа: в пропуск может идти
          // несколько слов сразу (диктант). Ступеньки грубые, чтобы поле не
          // подсказывало точное число букв. Ширина задана сразу и не меняется.
          const w = answer.length <= 10 ? 120
                  : answer.length <= 16 ? 190
                  : answer.length <= 24 ? 260
                  : answer.length <= 34 ? 340 : 430;
          replacement += `<input type="text" style="width:${w}px" data-blank-id="${blankId}" aria-label="Пропуск ${blanksCount + 1}">`;
          }

          if (hint) {
              // Иконка и подсказка — в одной обёртке: поп-ап привязан ровно к знаку вопроса,
              // а не к полю ввода.
              replacement += `<span class="hint-wrap">`;
              replacement +=   `<span class="hint-icon" tabindex="0" role="button" aria-describedby="${hintId}"
                                   onmouseover="window.showHint('${hintId}')"
                                   onmouseout="window.hideHint('${hintId}')"
                                   onfocus="window.showHint('${hintId}')"
                                   onblur="window.hideHint('${hintId}')">?</span>`;
              replacement +=   `<span class="hint-text" id="${hintId}" role="tooltip">${hint}</span>`;
              replacement += `</span>`;
          }
          replacement += `</span>`;
          html = html.replace(match[0], replacement);
          blanksCount++;
      }

      const quizElement = document.createElement('div');
      quizElement.className = 'fill-blanks-quiz';
      quizElement.id = quizId;

      quizElement.innerHTML = `
          <div class="fill-blanks-content">${html}</div>
          <div class="fill-blanks-actions">
              <button class="check-answers-btn" onclick="window.checkFillBlanks('${quizId}')">Проверить</button>
              <button class="reset-btn" onclick="window.resetFillBlanks('${quizId}')">Сбросить</button>
              <button class="show-answers-btn" onclick="window.showFillBlanksAnswers('${quizId}')">Показать ответы</button>
          </div>
          <div class="fill-blanks-result" id="${quizId}-result" aria-live="polite"></div>
      `;

      window.fillBlanksData[quizId] = answersAndHints;
      return quizElement;
  }

  function processFillBlanksElements() {
      const elements = document.querySelectorAll('div.fillblanks');
      elements.forEach(function(element, index) {
          try {
              if (element.closest('.fill-blanks-quiz')) return;
              const quizId = 'quiz-' + Date.now() + '-' + index;
              const quizElement = createFillBlanksQuiz(element.innerHTML, quizId);
              if (element.parentNode) element.parentNode.replaceChild(quizElement, element);
          } catch (error) {
              console.error("Error processing fillblanks element:", error, element);
          }
      });
  }

  // --- Подсказки: класс, а не display, чтобы всплывало плавно и ничего не двигало ---
  window.showHint = function(hintId) {
      const hint = document.getElementById(hintId);
      if (!hint) return;
      hint.classList.add('visible');
      // если подсказка вылезает за правый/левый край — подвинуть её, но не текст
      hint.style.transform = '';
      const rect = hint.getBoundingClientRect();
      const pad = 12;
      let shift = 0;
      if (rect.right > window.innerWidth - pad) shift = window.innerWidth - pad - rect.right;
      if (rect.left + shift < pad) shift = pad - rect.left;
      if (shift) hint.style.transform = 'translateX(calc(-50% + ' + Math.round(shift) + 'px))';
  };

  window.hideHint = function(hintId) {
      const hint = document.getElementById(hintId);
      if (hint) hint.classList.remove('visible');
  };

  function paint(input, color) {
      // слово и линия под ним; фон и толщина линии — никогда
      input.style.color = color;
      input.style.borderBottomColor = color;
  }

  window.checkFillBlanks = function(quizId) {
      const quizData = window.fillBlanksData[quizId];
      if (!quizData) return;

      let correct = 0;
      window.fillBlanksCorrect[quizId] = [];

      for (let i = 0; i < quizData.length; i++) {
          const input = document.querySelector(`[data-blank-id="${quizId}-${i}"]`);
          if (!input) continue;

          const isCorrect = input.value.trim().toLowerCase() === quizData[i].answer.trim().toLowerCase();
          window.fillBlanksCorrect[quizId][i] = isCorrect;
          paint(input, isCorrect ? LINE.correct : LINE.incorrect);
          if (isCorrect) correct++;
      }

      const resultElement = document.getElementById(`${quizId}-result`);
      if (resultElement) {
           resultElement.textContent = `Правильных ответов: ${correct} из ${quizData.length}`;
           resultElement.className = 'fill-blanks-result visible ' + (correct === quizData.length ? 'correct' : 'incorrect');
      }
  };

  window.resetFillBlanks = function(quizId) {
      const quizData = window.fillBlanksData[quizId];
      if (!quizData) return;

      for (let i = 0; i < quizData.length; i++) {
          const input = document.querySelector(`[data-blank-id="${quizId}-${i}"]`);
          if (!input) continue;
          input.value = '';
          paint(input, LINE.neutral);
      }

      const resultElement = document.getElementById(`${quizId}-result`);
      if (resultElement) {
          resultElement.className = 'fill-blanks-result';
          resultElement.textContent = '';
      }
      window.fillBlanksCorrect[quizId] = [];
  };

  window.showFillBlanksAnswers = function(quizId) {
      const quizData = window.fillBlanksData[quizId];
      if (!quizData) return;

      const correctAnswers = window.fillBlanksCorrect ? (window.fillBlanksCorrect[quizId] || []) : [];

      for (let i = 0; i < quizData.length; i++) {
          const input = document.querySelector(`[data-blank-id="${quizId}-${i}"]`);
          if (!input) continue;
          if (correctAnswers[i] === true) continue;
          input.value = quizData[i].answer;
          paint(input, LINE.shown);
      }
  };

  function initializeFillBlanks() {
      processFillBlanksElements();

      const targetNode = document.querySelector('section') || document.body;
      if (!targetNode) return;

      const observer = new MutationObserver(function(mutationsList) {
          let processed = false;
          for (const mutation of mutationsList) {
              if (mutation.type !== 'childList' || !mutation.addedNodes.length) continue;
              let needsProcessing = false;
              mutation.addedNodes.forEach(node => {
                  if (node.nodeType === Node.ELEMENT_NODE &&
                      (node.matches('div.fillblanks') || node.querySelector('div.fillblanks'))) {
                      needsProcessing = true;
                  }
              });
              if (needsProcessing && !processed) {
                  setTimeout(processFillBlanksElements, 50);
                  processed = true;
              }
          }
      });
      observer.observe(targetNode, { childList: true, subtree: true });
  }

  if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', initializeFillBlanks);
  } else {
      initializeFillBlanks();
  }

})();
