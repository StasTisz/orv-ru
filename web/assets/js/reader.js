(function () {
    const THEMES = {
        dark: { bg: '#14151b', primary: '#1f2129', nav: '#18191f', text: '#b6bccc', heading: '#c6cee2', icon: '#c6cee2' },
        light: { bg: '#ffffff', primary: '#f0f0f0', nav: '#d0d0d0', text: '#000000', heading: '#333333', icon: '#333333' },
        sepia: { bg: '#cab793', primary: '#f5deb3', nav: '#ac9b7c', text: '#000000', heading: '#000000', icon: '#2d2416' },
        pastel: { bg: '#f9f5f6', primary: '#f0e6ef', nav: '#e3c2d9', text: '#4a3b4c', heading: '#635066', icon: '#4a3b4c' },
        midnight: { bg: '#000000', primary: '#000000', nav: '#0e0e18', text: '#c0c8d0', heading: '#a8b0b8', icon: '#d0d8e0' },
        forest: { bg: '#e8f5e9', primary: '#c8e6c9', nav: '#a5d6a7', text: '#2e7d32', heading: '#388e3c', icon: '#1b5e20' },
        paper: { bg: '#f8f5f0', primary: '#f5f0e8', nav: '#e8e0d8', text: '#333333', heading: '#444444', icon: '#333333' },
        lavender: { bg: '#f3efff', primary: '#ede7f6', nav: '#ded5e8', text: '#4527a0', heading: '#512da8', icon: '#4527a0' },
        'dark-sepia': { bg: '#2a241e', primary: '#322c26', nav: '#2e2822', text: '#d2c8bc', heading: '#c0b6aa', icon: '#d2c8bc' },
        'dark-pastel': { bg: '#1e1b1e', primary: '#28252a', nav: '#252227', text: '#d1c2d3', heading: '#b9a9bc', icon: '#d1c2d3' },
        'dark-forest': { bg: '#121813', primary: '#1a221b', nav: '#171f18', text: '#b8d2b9', heading: '#a6c0a7', icon: '#b8d2b9' },
        'dark-paper': { bg: '#1c1b1a', primary: '#242322', nav: '#222120', text: '#d4d3d2', heading: '#c2c1c0', icon: '#d4d3d2' },
        'dark-lavender': { bg: '#1c1920', primary: '#24202a', nav: '#221e26', text: '#d2c9e0', heading: '#c0b7d0', icon: '#d2c9e0' },
    };

    const RICH_TEXT_MAP = [
        ['orv_system', 'set-rich-system-msg', 'systemMsgStyle'],
        ['orv_window', 'set-rich-system-window', 'systemWindowStyle'],
        ['orv_constellation', 'set-rich-const', 'constSpeechStyle'],
        ['orv_outergod', 'set-rich-outer', 'outerSpeechStyle'],
        ['orv_quote', 'set-rich-quote', 'quoteStyle'],
        ['orv_notice', 'set-rich-notice', 'noticeStyle'],
        ['orv_box', 'set-rich-box', 'genericBoxStyle'],
    ];

    function setRichClass(className, themeClass) {
        const nodes = document.getElementsByClassName(className);
        Array.from(nodes).forEach((el) => {
            el.classList.remove('theme1', 'theme2', 'theme3', 'theme4', 'theme5', 'theme6');
            el.classList.add(themeClass);
        });
    }

    function escapeHtml(str) {
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
    }

    function debounce(fn, waitMs) {
        let timer = null;
        return function (...args) {
            clearTimeout(timer);
            timer = setTimeout(() => fn.apply(this, args), waitMs);
        };
    }

    document.addEventListener('DOMContentLoaded', () => {
        const scriptEl = document.getElementById('reader-app');
        if (!scriptEl) return;

        const slug = scriptEl.dataset.slug;
        const chapterNumber = parseInt(scriptEl.dataset.number, 10);
        const titlesUrl = scriptEl.dataset.titles;

        const form = document.getElementById('settings-form');

        function loadSettings() {
            const state = window.OrvStorage.getReaderState();
            const s = state.settings;
            if (!s) return;
            if (s.theme) document.getElementById('set-theme').value = s.theme;
            if (s.font) document.getElementById('set-font').value = s.font;
            if (s.fontSize) document.getElementById('set-font-size').value = s.fontSize;
            if (s.fontWeight) document.getElementById('set-font-weight').value = s.fontWeight;
            if (s.lineHeight) document.getElementById('set-line-height').value = s.lineHeight;
            if (s.richTextToggle !== undefined) {
                document.getElementById('set-rich-text-toggle').checked = s.richTextToggle;
            }
            RICH_TEXT_MAP.forEach(([_cls, elId, key]) => {
                if (s[key]) document.getElementById(elId).value = s[key];
            });
        }

        function applySettings() {
            const root = document.documentElement;
            const themeKey = document.getElementById('set-theme').value;
            const font = document.getElementById('set-font').value;
            let rawFontSize = Number(document.getElementById('set-font-size').value) || 51;
            let rawLineHeight = Number(document.getElementById('set-line-height').value) || 49;
            const fontWeight = document.getElementById('set-font-weight').value;
            const richEnabled = document.getElementById('set-rich-text-toggle').checked;

            rawFontSize = Math.min(100, Math.max(30, rawFontSize));
            rawLineHeight = Math.min(100, Math.max(1, rawLineHeight));

            const palette = THEMES[themeKey] || THEMES.dark;
            root.style.setProperty('--body-background', palette.bg);
            root.style.setProperty('--primary', palette.primary);
            root.style.setProperty('--nav', palette.nav);
            root.style.setProperty('--text-primary', palette.text);
            root.style.setProperty('--text-secondary', palette.heading);
            root.style.setProperty('--icon-color', palette.icon);
            root.style.setProperty('--default-font', font);
            root.style.setProperty('--line-space', `${rawLineHeight / 30.625}rem`);

            document.body.className = themeKey;
            document.body.style.fontSize = `${rawFontSize / 3}px`;
            document.body.style.fontWeight = fontWeight;

            const savedSettings = {
                theme: themeKey,
                font,
                fontSize: String(rawFontSize),
                fontWeight,
                lineHeight: String(rawLineHeight),
                richTextToggle: richEnabled,
            };

            RICH_TEXT_MAP.forEach(([className, selectId, stateKey]) => {
                const selectEl = document.getElementById(selectId);
                selectEl.disabled = !richEnabled;
                savedSettings[stateKey] = selectEl.value;
                setRichClass(className, richEnabled ? selectEl.value : 'theme1');
            });

            const state = window.OrvStorage.getReaderState();
            state.settings = savedSettings;
            window.OrvStorage.saveReaderState(state);
        }

        loadSettings();
        applySettings();

        form.addEventListener('change', applySettings);
        ['set-font-size', 'set-line-height'].forEach((id) => {
            document.getElementById(id).addEventListener('input', applySettings);
        });
        form.addEventListener('reset', () => setTimeout(applySettings, 0));

        // Restore scroll position & persist debounced scroll
        const savedScroll = window.OrvStorage.getSavedScroll(slug, chapterNumber);
        if (savedScroll !== undefined && savedScroll !== null) {
            window.scrollTo(0, parseInt(savedScroll, 10));
        }

        const saveScroll = () => window.OrvStorage.recordScrollPosition(slug, chapterNumber, window.scrollY);
        window.addEventListener('scroll', debounce(saveScroll, 500));
        window.addEventListener('beforeunload', saveScroll);

        // Save last read chapter after brief reading dwell
        setTimeout(() => {
            const state = window.OrvStorage.getReaderState();
            if (!state.last_read) state.last_read = {};
            state.last_read[slug] = chapterNumber;
            window.OrvStorage.saveReaderState(state);
        }, 4000);

        // Drawers management
        const drawers = ['chapters-drawer', 'settings-drawer', 'download-drawer'];
        const backdrop = document.getElementById('drawer-backdrop');

        function openDrawer(id) {
            drawers.forEach((d) => {
                const node = document.getElementById(d);
                if (node) node.style.display = d === id ? 'flex' : 'none';
            });
            if (backdrop) backdrop.style.display = 'block';
        }

        function closeAllDrawers() {
            drawers.forEach((d) => {
                const node = document.getElementById(d);
                if (node) node.style.display = 'none';
            });
            if (backdrop) backdrop.style.display = 'none';
        }

        if (backdrop) {
            backdrop.addEventListener('click', closeAllDrawers);
        }

        let loadedChapters = null;
        function renderDrawerChapters(filterText) {
            const box = document.getElementById('chapter-search-result');
            if (!box || !loadedChapters) return;
            const q = filterText.trim().toLowerCase();
            const items = q
                ? loadedChapters.filter((ch) => String(ch.title).toLowerCase().includes(q))
                : loadedChapters;
            if (!items.length) {
                box.innerHTML = '<div class="chapter_item"><p>Глава не найдена</p></div>';
                return;
            }
            box.innerHTML = items
                .map((ch) => {
                    const isCurrent = ch.number === chapterNumber ? ' id="current-chapter"' : '';
                    return `<div class="chapter_item"${isCurrent}><a href="./${ch.href}"><p>${escapeHtml(ch.title)}</p></a></div>`;
                })
                .join('');
            const currentNode = document.getElementById('current-chapter');
            if (currentNode && !q) {
                currentNode.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
        }

        document.getElementById('open-chapters-btn').addEventListener('click', () => {
            openDrawer('chapters-drawer');
            if (!loadedChapters) {
                fetch(titlesUrl)
                    .then((res) => (res.ok ? res.json() : Promise.reject(res.statusText)))
                    .then((data) => {
                        loadedChapters = data.slice().sort((a, b) => a.number - b.number);
                        renderDrawerChapters('');
                    })
                    .catch((err) => console.error('Не удалось загрузить список глав:', err));
            }
        });
        document.getElementById('find-chapter').addEventListener('input', (e) => {
            renderDrawerChapters(e.target.value);
        });
        document.getElementById('open-settings-btn').addEventListener('click', () => openDrawer('settings-drawer'));
        document.getElementById('open-download-btn').addEventListener('click', () => openDrawer('download-drawer'));
        document.getElementById('print-page-btn').addEventListener('click', () => window.print());
        document.getElementById('fullscreen-btn').addEventListener('click', () => {
            if (!document.fullscreenElement) {
                document.documentElement.requestFullscreen().catch(() => {});
            } else {
                document.exitFullscreen().catch(() => {});
            }
        });
        document.querySelectorAll('[data-close]').forEach((btn) => {
            btn.addEventListener('click', closeAllDrawers);
        });

        document.addEventListener('keydown', (e) => {
            if (e.target && ['INPUT', 'SELECT', 'TEXTAREA'].includes(e.target.tagName)) {
                if (e.key === 'Escape') closeAllDrawers();
                return;
            }
            if (e.key === 'Escape') {
                closeAllDrawers();
            } else if (e.key === 'ArrowLeft') {
                const prev = document.getElementById('prev-chapter-link');
                if (prev) window.location.href = prev.href;
            } else if (e.key === 'ArrowRight') {
                const next = document.getElementById('next-chapter-link');
                if (next) window.location.href = next.href;
            }
        });

        let wakeLock = null;
        async function requestWakeLock() {
            if (!('wakeLock' in navigator)) return;
            try {
                wakeLock = await navigator.wakeLock.request('screen');
            } catch (_err) {}
        }
        requestWakeLock();
        document.addEventListener('visibilitychange', () => {
            if (document.visibilityState === 'visible') requestWakeLock();
        });
    });
})();
