/**
 * Focus guide UI: copy anchor, scroll to paragraph, reading-route dock magnify.
 */
(function (global) {
    'use strict';

    function fallbackCopy(text, cb) {
        var ta = document.createElement('textarea');
        ta.value = text;
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        try {
            document.execCommand('copy');
            cb();
        } catch (e) { /* ignore */ }
        document.body.removeChild(ta);
    }

    global.copyFocusAnchor = function (btn) {
        var text = btn.getAttribute('data-anchor');
        if (!text) return;
        var label = btn.getAttribute('aria-label') || btn.title || '复制定位词';
        var done = function () {
            if (btn.querySelector('.focus-icon-btn__svg')) {
                btn.classList.add('focus-icon-btn--copied');
                btn.setAttribute('aria-label', '已复制');
                btn.title = '已复制';
            } else {
                var orig = btn.textContent;
                btn.textContent = '已复制';
                btn._origText = orig;
            }
            btn.disabled = true;
            setTimeout(function () {
                btn.classList.remove('focus-icon-btn--copied');
                btn.setAttribute('aria-label', label);
                btn.title = label;
                if (btn._origText) {
                    btn.textContent = btn._origText;
                    delete btn._origText;
                }
                btn.disabled = false;
            }, 1600);
        };
        if (global.navigator.clipboard && global.navigator.clipboard.writeText) {
            global.navigator.clipboard.writeText(text).then(done).catch(function () {
                fallbackCopy(text, done);
            });
        } else {
            fallbackCopy(text, done);
        }
    };

    global.scrollToFocusSource = function () {
        var panel = document.getElementById('focus-source-panel');
        if (panel) {
            panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
            panel.classList.add('focus-source-panel--flash');
            setTimeout(function () {
                panel.classList.remove('focus-source-panel--flash');
            }, 1800);
            return;
        }
        var urlEl = document.querySelector('[data-result-source-url]');
        var url = urlEl && urlEl.getAttribute('data-result-source-url');
        if (url) {
            global.open(url, '_blank', 'noopener,noreferrer');
        }
    };

    global.scrollToFocusPara = function (index) {
        var el = document.getElementById('focus-para-' + index);
        if (!el) return;
        var body = el.closest('[data-focus-source-body]');
        if (body && body.classList.contains('focus-source-body--hide-junk')) {
            var isJunk =
                el.classList.contains('focus-para--skip') ||
                el.classList.contains('focus-para--neutral');
            if (isJunk) {
                var panel = body.closest('.focus-source-panel');
                var toggle = panel && panel.querySelector('[data-focus-junk-toggle]');
                if (toggle) {
                    toggle.checked = false;
                    applyJunkFold(body, false, panel);
                }
            }
        }
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
        el.classList.add('focus-para--flash');
        setTimeout(function () {
            el.classList.remove('focus-para--flash');
        }, 1800);
    };

    function countJunkParagraphs(body) {
        return body.querySelectorAll('.focus-para--skip, .focus-para--neutral').length;
    }

    function applyJunkFold(body, hide, panel) {
        body.classList.toggle('focus-source-body--hide-junk', hide);
        var note = panel && panel.querySelector('[data-focus-fold-note]');
        var hint = panel && panel.querySelector('[data-focus-source-hint]');
        if (note) {
            if (hide) {
                var n = countJunkParagraphs(body);
                note.textContent = n > 0 ? '已折叠 ' + n + ' 段低价值内容，仅显示必看与警惕' : '';
                note.hidden = n === 0;
            } else {
                note.textContent = '';
                note.hidden = true;
            }
        }
        if (hint) {
            hint.hidden = hide;
        }
    }

    function initJunkFoldToggle(panel) {
        var input = panel.querySelector('[data-focus-junk-toggle]');
        var body = panel.querySelector('[data-focus-source-body]');
        if (!input || !body || input.dataset.junkToggleReady === '1') return;
        input.dataset.junkToggleReady = '1';

        input.addEventListener('change', function () {
            applyJunkFold(body, input.checked, panel);
            try {
                sessionStorage.setItem('focus-hide-junk', input.checked ? '1' : '0');
            } catch (e) { /* ignore */ }
        });

        try {
            if (sessionStorage.getItem('focus-hide-junk') === '1') {
                input.checked = true;
                applyJunkFold(body, true, panel);
            }
        } catch (e) { /* ignore */ }
    }

    function bootFocusSourcePanels(root) {
        var scope = root && root.querySelectorAll ? root : document;
        scope.querySelectorAll('.focus-source-panel').forEach(initJunkFoldToggle);
    }

    function dockScale(distance, influence, maxScale) {
        if (distance >= influence) return 1;
        var t = distance / influence;
        return 1 + (maxScale - 1) * Math.cos(t * Math.PI / 2);
    }

    function initReadingMapMagnify(track) {
        if (track.dataset.magnifyReady === '1') return;
        track.dataset.magnifyReady = '1';

        var stage = track.closest('.reading-map-stage');
        if (!stage) return;

        var blocks = Array.prototype.slice.call(track.querySelectorAll('.reading-map-block'));
        if (!blocks.length) return;

        if (global.matchMedia && global.matchMedia('(prefers-reduced-motion: reduce)').matches) {
            track.classList.add('reading-map-track--static');
            return;
        }

        var maxScaleY = 2.15;
        var maxScaleX = 1.28;
        var centers = [];
        var resizeTimer = null;

        function measureCenters() {
            blocks.forEach(function (block) {
                block.style.transform = '';
                block.style.zIndex = '';
            });
            centers = blocks.map(function (block) {
                var rect = block.getBoundingClientRect();
                return {
                    el: block,
                    x: rect.left + rect.width / 2,
                };
            });
        }

        measureCenters();

        global.addEventListener('resize', function () {
            clearTimeout(resizeTimer);
            resizeTimer = setTimeout(measureCenters, 120);
        });

        var rafId = null;
        var pointerX = null;

        function applyScales() {
            if (pointerX === null) return;
            var trackWidth = track.getBoundingClientRect().width;
            var influence = Math.max(56, Math.min(110, trackWidth / Math.max(blocks.length, 1) * 2.4));

            centers.forEach(function (item) {
                var dist = Math.abs(pointerX - item.x);
                var factorY = dockScale(dist, influence, maxScaleY);
                var factorX = dockScale(dist, influence, maxScaleX);
                item.el.style.transform =
                    'scale(' + factorX.toFixed(3) + ', ' + factorY.toFixed(3) + ')';
                item.el.style.zIndex = factorY > 1.06 ? String(Math.round(factorY * 10)) : '';
            });
        }

        function scheduleUpdate(clientX) {
            pointerX = clientX;
            if (rafId !== null) return;
            rafId = global.requestAnimationFrame(function () {
                rafId = null;
                applyScales();
            });
        }

        function resetScales() {
            pointerX = null;
            if (rafId !== null) {
                global.cancelAnimationFrame(rafId);
                rafId = null;
            }
            blocks.forEach(function (block) {
                block.style.transform = '';
                block.style.zIndex = '';
            });
        }

        stage.addEventListener('mousemove', function (e) {
            scheduleUpdate(e.clientX);
        });
        stage.addEventListener('mouseleave', resetScales);

        stage.addEventListener(
            'touchmove',
            function (e) {
                if (!e.touches || !e.touches.length) return;
                scheduleUpdate(e.touches[0].clientX);
            },
            { passive: true }
        );
        stage.addEventListener('touchend', resetScales);
        stage.addEventListener('touchcancel', resetScales);
    }

    function bootReadingMapMagnify(root) {
        var scope = root && root.querySelectorAll ? root : document;
        scope.querySelectorAll('.reading-map-track--magnify').forEach(initReadingMapMagnify);
    }

    global.bootReadingMapMagnify = bootReadingMapMagnify;
    global.bootFocusGuideUI = bootAll;

    function bootAll(root) {
        bootReadingMapMagnify(root);
        bootFocusSourcePanels(root);
        if (global.ResultPage && global.ResultPage.initDimensionLinks) {
            global.ResultPage.initDimensionLinks(root);
        }
        if (global.ResultPage && global.ResultPage.initDimHelpToggles) {
            global.ResultPage.initDimHelpToggles(root);
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () {
            bootAll(document);
        });
    } else {
        bootAll(document);
    }

    document.body.addEventListener('htmx:afterSwap', function (evt) {
        bootAll(evt.detail && evt.detail.target ? evt.detail.target : document);
    });
    document.body.addEventListener('htmx:load', function (evt) {
        bootAll(evt.detail && evt.detail.elt ? evt.detail.elt : document);
    });
})(window);
