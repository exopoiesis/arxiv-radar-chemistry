/* Chemistry arxiv-radar — theme toggle + abstract popup. Vanilla JS. */
(function () {
  'use strict';

  // === theme ===
  function applyTheme(t) {
    document.documentElement.setAttribute('data-theme', t);
    var btn = document.getElementById('theme-toggle');
    if (btn) {
      var isDark = t === 'dark';
      btn.querySelector('.ico').textContent = isDark ? '☼' : '☾';
      btn.querySelector('.label').textContent = isDark ? 'light' : 'dark';
      btn.setAttribute('aria-label', 'Switch to ' + (isDark ? 'light' : 'dark') + ' theme');
    }
  }
  function currentTheme() {
    return document.documentElement.getAttribute('data-theme') || 'light';
  }
  function initThemeToggle() {
    var btn = document.getElementById('theme-toggle');
    if (!btn) return;
    applyTheme(currentTheme());
    btn.addEventListener('click', function () {
      var next = currentTheme() === 'dark' ? 'light' : 'dark';
      try { localStorage.setItem('theme', next); } catch (e) {}
      applyTheme(next);
    });
  }

  // === abstract popup ===
  // Cache fetched fragments so popping the same paper twice is free.
  var cache = {};
  var overlay = null;

  function ensureOverlay() {
    if (overlay) return overlay;
    overlay = document.createElement('div');
    overlay.className = 'abstract-overlay';
    overlay.innerHTML =
      '<div class="abstract-modal" role="dialog" aria-modal="true">' +
        '<button type="button" class="abstract-close" aria-label="Close">×</button>' +
        '<div class="abstract-content"></div>' +
      '</div>';
    document.body.appendChild(overlay);

    overlay.addEventListener('click', function (e) {
      if (e.target === overlay) closePopup();
    });
    overlay.querySelector('.abstract-close').addEventListener('click', closePopup);
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && overlay.classList.contains('is-open')) closePopup();
    });
    return overlay;
  }

  function openPopup(href) {
    var ov = ensureOverlay();
    var content = ov.querySelector('.abstract-content');
    ov.classList.add('is-open');
    document.body.style.overflow = 'hidden';

    if (cache[href]) {
      content.innerHTML = cache[href];
      return;
    }
    content.innerHTML = '<p class="abstract-loading">Loading abstract…</p>';
    fetch(href, { credentials: 'same-origin' })
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.text();
      })
      .then(function (html) {
        cache[href] = html;
        // Only inject if still on the same paper (user didn't close+open another)
        if (ov.classList.contains('is-open')) content.innerHTML = html;
      })
      .catch(function (err) {
        content.innerHTML = '<p class="abstract-error">Could not load abstract: ' + err.message + '</p>';
      });
  }

  function closePopup() {
    if (!overlay) return;
    overlay.classList.remove('is-open');
    document.body.style.overflow = '';
  }

  function initPopupLinks() {
    document.body.addEventListener('click', function (e) {
      var link = e.target.closest('a.abstract-popup');
      if (!link) return;
      // Allow modifier-clicks (Ctrl/Cmd, middle-click, shift) to open in new tab.
      if (e.ctrlKey || e.metaKey || e.shiftKey || e.button !== 0) return;
      e.preventDefault();
      openPopup(link.getAttribute('href'));
    });
  }

  // === init ===
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () {
      initThemeToggle();
      initPopupLinks();
    });
  } else {
    initThemeToggle();
    initPopupLinks();
  }
})();
