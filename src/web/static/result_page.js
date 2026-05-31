/**
 * Shared result UI helpers: score ring, rule labels, simple/streaming cards, dim tooltips.
 */
(function (global) {
    'use strict';

    function escapeHtml(text) {
        var div = document.createElement('div');
        div.textContent = text == null ? '' : String(text);
        return div.innerHTML;
    }

    function ruleHitLabel(rule) {
        var r = String(rule || '');
        if (r.indexOf('scam') !== -1) return '骗局关键词';
        if (r.indexOf('emotional') !== -1 || r.indexOf('anxiety') !== -1) return '情绪操纵词';
        if (r.indexOf('punctuation') !== -1) return '过度标点';
        if (r.indexOf('advertorial') !== -1 || r.indexOf('promo') !== -1) return '推广关键词';
        if (r.indexOf('ai_generated') !== -1) return 'AI 痕迹词';
        if (r.indexOf('combo') !== -1) return '组合信号';
        if (r.indexOf('platform_') === 0) return '平台特征';
        return '其他规则';
    }

    function scoreTier(score, opts) {
        opts = opts || {};
        var s = Number(score) || 0;
        var genre = opts.content_genre || '';
        var dims = opts.dimensions || {};
        if (genre === 'roundup' && (dims.scam_prob || 0) < 40 && s >= 32) {
            return { key: 'reference', label: '汇编参考', css: 'score-tier-normal' };
        }
        if (s >= 80) return { key: 'quality', label: '质量良好', css: 'score-tier-quality' };
        if (s >= 60) return { key: 'normal', label: '整体一般', css: 'score-tier-normal' };
        if (s >= 40) return { key: 'suspicious', label: '存在风险', css: 'score-tier-suspicious' };
        return { key: 'junk', label: '高风险', css: 'score-tier-junk' };
    }

    var READING_ACTIONS = {
        skip: { label: '建议跳过', emoji: '🚫', css: 'reading-action--skip', tone: 'skip' },
        skim: { label: '速查即可', emoji: '📋', css: 'reading-action--skim', tone: 'skim' },
        read: { label: '值得细读', emoji: '✓', css: 'reading-action--read', tone: 'read_carefully' },
        verify: { label: '谨慎核实', emoji: '⚠', css: 'reading-action--verify', tone: 'skim' },
    };

    function buildReadingAction(data, verdict, tier) {
        var rec = (verdict && verdict.tone) || '';
        var key = 'skim';
        if (rec === 'skip') key = 'skip';
        else if (rec === 'read_carefully') key = 'read';
        else if (rec === 'skim') key = 'skim';
        else if (tier.key === 'junk') key = 'skip';
        else if (tier.key === 'quality') key = 'read';
        else if (data.content_genre === 'roundup') key = 'skim';
        else if (tier.key === 'suspicious' || tier.key === 'junk') key = 'verify';
        var dims = data.dimensions || {};
        if ((dims.scam_prob || 0) >= 60) key = 'skip';
        var action = Object.assign({ key: key }, READING_ACTIONS[key]);
        return action;
    }

    function alignDisplayTier(tier, action, genre) {
        if (action.key === 'skip') {
            return { key: 'junk', label: '建议跳过', css: 'score-tier-junk' };
        }
        if (action.key === 'read') {
            return tier.key === 'quality' ? tier : { key: 'quality', label: '质量良好', css: 'score-tier-quality' };
        }
        if (action.key === 'verify') {
            return { key: 'suspicious', label: '谨慎阅读', css: 'score-tier-suspicious' };
        }
        if (action.key === 'skim' && genre === 'roundup') {
            return { key: 'reference', label: '汇编参考', css: 'score-tier-normal' };
        }
        if (action.key === 'skim' && tier.key === 'junk') {
            return { key: 'suspicious', label: '可参考', css: 'score-tier-suspicious' };
        }
        return tier;
    }

    function scoreRingStroke(score) {
        var s = Number(score) || 0;
        if (s > 70) return '#10b981';
        if (s > 40) return '#f59e0b';
        return '#ef4444';
    }

    function scoreColorClass(score) {
        var s = Number(score) || 0;
        if (s > 70) return 'score-high';
        if (s > 40) return 'score-mid';
        return 'score-low';
    }

    function renderScoreRing(score, size, animate) {
        var s = Math.round(Number(score) || 0);
        var sz = size === 'md' ? 96 : 128;
        var textClass = size === 'md' ? 'text-2xl' : 'text-4xl';
        var offset = 282.7 - (282.7 * s / 100);
        var stroke = scoreRingStroke(s);
        var animCls = animate !== false ? ' score-ring-circle' : '';
        var colorCls = scoreColorClass(s);
        var html = '<div class="score-ring-wrap inline-flex items-center justify-center relative" style="width:' + sz + 'px;height:' + sz + 'px;">';
        html += '<svg width="' + sz + '" height="' + sz + '" viewBox="0 0 100 100" aria-hidden="true">';
        html += '<circle cx="50" cy="50" r="45" fill="none" stroke="#334155" stroke-width="6"/>';
        html += '<circle cx="50" cy="50" r="45" fill="none" stroke="' + stroke + '" stroke-width="6" stroke-linecap="round"';
        html += ' stroke-dasharray="282.7" stroke-dashoffset="' + offset + '" class="' + animCls.trim() + '"/>';
        html += '</svg>';
        html += '<span class="absolute font-bold score-value-animate ' + textClass + ' ' + colorCls + '" aria-label="综合评分 ' + s + ' 分">' + s + '</span>';
        html += '</div>';
        return html;
    }

    function dedupeRuleLabels(matchedRules) {
        var seen = {};
        var order = [];
        (matchedRules || []).forEach(function (rule) {
            var label = ruleHitLabel(rule);
            if (!seen[label]) {
                seen[label] = true;
                order.push(label);
            }
        });
        return order;
    }

    function resolveReadingVerdict(data) {
        if (data && data.reading_action) {
            var act = data.reading_action;
            var rv = data.reading_verdict || {};
            return {
                headline: act.label,
                detail: rv.detail || (data.summary || ''),
                tone: act.tone || act.key || 'skim',
                action: act,
            };
        }
        if (data && data.reading_verdict) {
            var rv2 = data.reading_verdict;
            var css = rv2.css || '';
            var tone = rv2.recommendation || 'skim';
            if (css.indexOf('focus-verdict--') !== -1) {
                tone = css.replace('focus-verdict--', '');
            }
            return {
                headline: rv2.headline || '',
                detail: rv2.detail || '',
                tone: tone,
            };
        }
        var fg = data && data.focus_guide;
        if (fg) {
            return {
                headline: fg.verdict_headline || '',
                detail: fg.verdict_detail || fg.tldr || '',
                tone: fg.recommendation || 'skim',
            };
        }
        var tier = scoreTier(data && data.overall_score != null ? data.overall_score : 50, {
            content_genre: data && data.content_genre,
            dimensions: data && data.dimensions,
        });
        return {
            headline: tier.label,
            detail: (data && data.summary) || '',
            tone: 'skim',
        };
    }

    function renderVerdictBlock(verdict, compact) {
        var action = verdict.action;
        var tone = verdict.tone || 'skim';
        var headline = verdict.headline || '综合评分';
        var detail = verdict.detail || '';
        var html = '<div class="verdict-hero' + (compact ? ' result-simple-verdict' : '') + '">';
        if (action) {
            html += '<div class="verdict-hero-main">';
            html += '<div class="verdict-hero-copy">';
            html += '<p class="verdict-hero-eyebrow">阅读裁决</p>';
            html += '<h2 class="verdict-hero-action ' + escapeHtml(action.css) + '">';
            html += '<span class="verdict-hero-emoji" aria-hidden="true">' + escapeHtml(action.emoji) + '</span>';
            html += '<span class="verdict-hero-action-label">' + escapeHtml(action.label) + '</span></h2>';
            if (detail) {
                html += '<p class="verdict-hero-detail">' + escapeHtml(detail) + '</p>';
            }
            html += '</div></div>';
        } else {
            html += '<div class="focus-verdict focus-verdict--' + escapeHtml(tone) + '">';
            html += '<p class="focus-verdict-label">阅读结论</p>';
            html += '<h2 class="focus-verdict-headline">' + escapeHtml(headline) + '</h2>';
            if (detail) {
                html += '<p class="focus-verdict-detail">' + escapeHtml(detail) + '</p>';
            }
            html += '</div>';
        }
        html += '</div>';
        return html;
    }

    function renderScoringProgress(activeStage) {
        var stages = [
            { key: 'rules', label: '规则检测' },
            { key: 'llm', label: 'LLM 分析' },
            { key: 'final', label: '生成结果' },
        ];
        var html = '<div class="scoring-progress mt-4"><div class="scoring-progress-stages">';
        stages.forEach(function (st) {
            var cls = 'stage';
            if (st.key === activeStage) cls += ' active';
            else if (
                (activeStage === 'llm' && st.key === 'rules') ||
                (activeStage === 'final' && (st.key === 'rules' || st.key === 'llm'))
            ) {
                cls += ' done';
            }
            html += '<span class="' + cls + '">' + st.label + '</span>';
        });
        html += '</div></div>';
        return html;
    }

    function renderRulesPreview(container, data) {
        var score = data.overall_score != null ? data.overall_score : 50;
        var tier = scoreTier(score);
        var labels = dedupeRuleLabels(data.matched_rules);

        var html = '<div class="result-stream-card bg-surface rounded-xl p-6 border border-navy-700 fade-in">';
        html += '<div class="flex flex-wrap items-center gap-2 mb-4">';
        html += '<span class="px-2 py-0.5 rounded-full text-xs bg-amber-900/50 text-amber-300 border border-amber-700/50">规则预览</span>';
        html += '<span class="score-tier-badge ' + tier.css + '">' + escapeHtml(tier.label) + '</span>';
        html += '</div>';
        html += '<div class="flex flex-col sm:flex-row items-center justify-center gap-4 sm:gap-6">';
        html += renderScoreRing(score, 'md', true);
        html += '<div class="text-center sm:text-left text-sm text-gray-400 max-w-md">';
        html += '<p>规则引擎预检分数，完整 AI 分析进行中…</p>';
        if (labels.length) {
            html += '<div class="flex flex-wrap justify-center sm:justify-start gap-1.5 mt-3">';
            labels.forEach(function (label) {
                html += '<span class="judgment-rule-chip">' + escapeHtml(label) + '</span>';
            });
            html += '</div>';
        }
        html += '</div></div>';
        html += renderScoringProgress('llm');
        html += '</div>';
        container.innerHTML = html;
    }

    function renderSimpleFinalResult(container, data, options) {
        options = options || {};
        var score = data.overall_score != null ? data.overall_score : 0;
        var rawTier = scoreTier(score, {
            content_genre: data.content_genre,
            dimensions: data.dimensions,
        });
        var verdict = resolveReadingVerdict(data);
        if (!verdict.action) {
            verdict.action = buildReadingAction(data, verdict, rawTier);
        }
        var tier = alignDisplayTier(
            data.score_tier || rawTier,
            verdict.action,
            data.content_genre || ''
        );
        var showExpand = options.showExpand !== false;

        var html = '<div class="result-simple result-stream-card bg-surface rounded-xl p-6 border border-navy-700 fade-in">';
        html += renderVerdictBlock(verdict, true);
        html += '<div class="result-simple-score mt-5 flex flex-col items-center gap-2">';
        html += '<span class="score-tier-badge ' + tier.css + '">' + escapeHtml(tier.label) + '</span>';
        html += renderScoreRing(score, 'md', true);
        html += '<p class="text-xs text-gray-500">参考分</p>';
        html += '</div>';
        if (data.labels && data.labels.length) {
            html += '<div class="flex flex-wrap justify-center gap-2 mt-4">';
            data.labels.forEach(function (label) {
                html += '<span class="result-label-chip result-label-chip--warn">' + escapeHtml(label) + '</span>';
            });
            html += '</div>';
        }
        if (showExpand) {
            html += '<button type="button" class="btn-secondary mt-6" onclick="ResultPage.expandFromSimpleMode()">展开详细分析</button>';
        }
        html += '</div>';
        container.innerHTML = html;
    }

    function expandFromSimpleMode() {
        if (!document.body.classList.contains('simple-mode')) return;
        if (typeof global.toggleSimpleMode === 'function') {
            global.toggleSimpleMode();
            return;
        }
        document.body.classList.remove('simple-mode');
        try {
            localStorage.setItem('simple_mode', 'false');
        } catch (e) { /* ignore */ }
        ['simple-mode-btn', 'simple-mode-btn-mobile'].forEach(function (id) {
            var btn = document.getElementById(id);
            if (btn) btn.classList.remove('active');
        });
    }

    function copyToClipboard(text) {
        var value = text == null ? '' : String(text);
        return new Promise(function (resolve, reject) {
            if (global.navigator && global.navigator.clipboard && global.navigator.clipboard.writeText) {
                global.navigator.clipboard.writeText(value).then(resolve).catch(function () {
                    fallbackCopy(value) ? resolve() : reject(new Error('copy failed'));
                });
                return;
            }
            fallbackCopy(value) ? resolve() : reject(new Error('copy failed'));
        });
    }

    function fallbackCopy(text) {
        var ta = document.createElement('textarea');
        ta.value = text;
        ta.setAttribute('readonly', '');
        ta.style.position = 'fixed';
        ta.style.left = '-9999px';
        document.body.appendChild(ta);
        ta.select();
        try {
            return document.execCommand('copy');
        } finally {
            document.body.removeChild(ta);
        }
    }

    var dimHelpDocBound = false;
    var activeDimLinkKey = null;
    var activeParaIndex = null;

    function parseDimKeys(raw) {
        if (!raw) return [];
        try {
            var parsed = JSON.parse(raw);
            return Array.isArray(parsed) ? parsed : [];
        } catch (e) {
            return [];
        }
    }

    function clearDimensionHighlights() {
        document.querySelectorAll('.focus-para--dim-linked').forEach(function (el) {
            el.classList.remove('focus-para--dim-linked');
        });
        document.querySelectorAll('.focus-para--dim-source').forEach(function (el) {
            el.classList.remove('focus-para--dim-source');
        });
        document.querySelectorAll('.dimension-row--active').forEach(function (el) {
            el.classList.remove('dimension-row--active');
        });
        document.querySelectorAll('.judgment-rule-chip--active').forEach(function (el) {
            el.classList.remove('judgment-rule-chip--active');
        });
        activeDimLinkKey = null;
        activeParaIndex = null;
    }

    function highlightDimensionRows(dimKeys) {
        if (!dimKeys || !dimKeys.length) return;
        dimKeys.forEach(function (key) {
            document.querySelectorAll('.dimension-row[data-dim-key="' + key + '"]').forEach(function (row) {
                row.classList.add('dimension-row--active');
            });
        });
    }

    function highlightParagraphs(indices, sourceIndex) {
        indices.forEach(function (idx) {
            var para = document.getElementById('focus-para-' + idx);
            if (!para) return;
            para.classList.add('focus-para--dim-linked');
            if (sourceIndex != null && idx === sourceIndex) {
                para.classList.add('focus-para--dim-source');
            }
        });
    }

    function scrollToDimensionSection() {
        var section = document.querySelector('.dimension-all-details') ||
            document.querySelector('.detail-section');
        if (section && typeof section.scrollIntoView === 'function') {
            section.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }
    }

    function applyDimensionLink(options) {
        options = options || {};
        var dimKeys = options.dimKeys || [];
        var indices = options.paragraphIndices || [];
        var sourceEl = options.sourceEl || null;
        var sourceIndex = options.sourceIndex != null ? options.sourceIndex : null;
        var scrollDimSection = options.scrollDimSection !== false;

        if (!indices.length && !dimKeys.length) return;

        var toggleKey = dimKeys.length === 1 ? dimKeys[0] : null;
        if (toggleKey && activeDimLinkKey === toggleKey && sourceIndex == null) {
            clearDimensionHighlights();
            return;
        }

        clearDimensionHighlights();
        activeDimLinkKey = toggleKey;
        activeParaIndex = sourceIndex;

        if (sourceEl) {
            if (sourceEl.classList.contains('judgment-rule-chip')) {
                sourceEl.classList.add('judgment-rule-chip--active');
            } else if (sourceEl.classList.contains('dimension-row')) {
                sourceEl.classList.add('dimension-row--active');
            }
        }

        highlightDimensionRows(dimKeys);
        // Always scroll to source panel when any dimension is clicked
        if (dimKeys.length && typeof global.scrollToFocusSource === 'function') {
            global.scrollToFocusSource();
        }
        if (indices.length) {
            highlightParagraphs(indices, sourceIndex);
            if (sourceIndex == null && typeof global.scrollToFocusPara === 'function') {
                global.scrollToFocusPara(indices[0]);
            }
        }
        if (scrollDimSection && dimKeys.length) {
            scrollToDimensionSection();
        }
    }

    function parseParagraphIndices(raw) {
        if (!raw) return [];
        return String(raw)
            .split(',')
            .map(function (s) { return parseInt(s.trim(), 10); })
            .filter(function (n) { return !isNaN(n); });
    }

    function linkDimensionToSource(rowEl) {
        if (!rowEl) return;
        console.log('[stagger] linkDimensionToSource', rowEl.dataset.dimKey);
        applyDimensionLink({
            dimKeys: [rowEl.getAttribute('data-dim-key')].filter(Boolean),
            paragraphIndices: parseParagraphIndices(rowEl.getAttribute('data-paragraph-indices')),
            sourceEl: rowEl,
            scrollDimSection: false,
        });
    }

    function linkParagraphToDimensions(paraEl) {
        if (!paraEl) return;
        var index = parseInt(paraEl.getAttribute('data-para-index'), 10);
        if (isNaN(index)) return;

        if (activeParaIndex === index) {
            clearDimensionHighlights();
            return;
        }

        var dimKeys = parseDimKeys(paraEl.getAttribute('data-dim-keys'));
        var indices = [index];
        dimKeys.forEach(function (key) {
            document.querySelectorAll('.dimension-row[data-dim-key="' + key + '"]').forEach(function (row) {
                parseParagraphIndices(row.getAttribute('data-paragraph-indices')).forEach(function (idx) {
                    if (indices.indexOf(idx) === -1) indices.push(idx);
                });
            });
        });

        applyDimensionLink({
            dimKeys: dimKeys,
            paragraphIndices: indices,
            sourceEl: paraEl,
            sourceIndex: index,
            scrollDimSection: true,
        });
    }

    function linkRuleSignalToSource(chipEl) {
        if (!chipEl) return;
        applyDimensionLink({
            dimKeys: parseDimKeys(chipEl.getAttribute('data-dim-keys')),
            paragraphIndices: parseParagraphIndices(chipEl.getAttribute('data-paragraph-indices')),
            sourceEl: chipEl,
            scrollDimSection: false,
        });
    }

    function initDimensionLinks(root) {
        var scope = root && root.querySelectorAll ? root : document;
        scope.querySelectorAll('.dimension-row--linkable').forEach(function (row) {
            if (row.dataset.dimLinkBound === '1') return;
            row.dataset.dimLinkBound = '1';
        });
        scope.querySelectorAll('.focus-para--has-dim-link').forEach(function (para) {
            if (para.dataset.paraDimBound === '1') return;
            para.dataset.paraDimBound = '1';
        });
        scope.querySelectorAll('.judgment-rule-chip--linkable').forEach(function (chip) {
            if (chip.dataset.ruleLinkBound === '1') return;
            chip.dataset.ruleLinkBound = '1';
        });
    }

    function initDimHelpToggles(root) {
        var scope = root && root.querySelectorAll ? root : document;
        scope.querySelectorAll('.dim-help').forEach(function (el) {
            if (el.dataset.dimHelpBound === '1') return;
            el.dataset.dimHelpBound = '1';
            el.addEventListener('click', function (e) {
                e.stopPropagation();
                var wasOpen = el.classList.contains('dim-help-open');
                scope.querySelectorAll('.dim-help.dim-help-open').forEach(function (other) {
                    other.classList.remove('dim-help-open');
                });
                if (!wasOpen) el.classList.add('dim-help-open');
            });
        });
        if (!dimHelpDocBound) {
            dimHelpDocBound = true;
            document.addEventListener('click', function () {
                document.querySelectorAll('.dim-help.dim-help-open').forEach(function (el) {
                    el.classList.remove('dim-help-open');
                });
            });
        }
    }

    global.ResultPage = {
        escapeHtml: escapeHtml,
        ruleHitLabel: ruleHitLabel,
        scoreTier: scoreTier,
        renderScoreRing: renderScoreRing,
        renderRulesPreview: renderRulesPreview,
        renderSimpleFinalResult: renderSimpleFinalResult,
        renderScoringProgress: renderScoringProgress,
        copyToClipboard: copyToClipboard,
        expandFromSimpleMode: expandFromSimpleMode,
        initDimHelpToggles: initDimHelpToggles,
        initDimensionLinks: initDimensionLinks,
        linkDimensionToSource: linkDimensionToSource,
        linkParagraphToDimensions: linkParagraphToDimensions,
        linkRuleSignalToSource: linkRuleSignalToSource,
        clearDimensionHighlights: clearDimensionHighlights,
        dedupeRuleLabels: dedupeRuleLabels,
    };

    document.addEventListener('DOMContentLoaded', function () {
        initDimHelpToggles(document);
        initDimensionLinks(document);
    });
})(window);
