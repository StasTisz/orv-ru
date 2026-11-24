(function (global) {
    const STORAGE_KEY = 'orv_ru_state';
    const MAX_SCROLL_HISTORY = 5;

    function getReaderState() {
        try {
            const raw = localStorage.getItem(STORAGE_KEY);
            return raw ? JSON.parse(raw) : {};
        } catch (err) {
            console.error('Ошибка чтения localStorage:', err);
            return {};
        }
    }

    function saveReaderState(state) {
        try {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
        } catch (err) {
            console.error('Ошибка записи localStorage:', err);
        }
    }

    function recordScrollPosition(slug, chapterNumber, scrollY) {
        const state = getReaderState();
        if (!state.scroll_positions) state.scroll_positions = {};
        if (!state.scroll_history) state.scroll_history = {};

        const key = `scrollY_${slug}_${chapterNumber}`;
        state.scroll_positions[key] = scrollY;

        let history = state.scroll_history[slug] || [];
        history = history.filter((item) => item !== key);
        history.unshift(key);

        while (history.length > MAX_SCROLL_HISTORY) {
            const oldest = history.pop();
            delete state.scroll_positions[oldest];
        }

        state.scroll_history[slug] = history;
        saveReaderState(state);
    }

    function getSavedScroll(slug, chapterNumber) {
        const state = getReaderState();
        const key = `scrollY_${slug}_${chapterNumber}`;
        return state.scroll_positions ? state.scroll_positions[key] : undefined;
    }

    global.OrvStorage = {
        getReaderState,
        saveReaderState,
        recordScrollPosition,
        getSavedScroll,
    };
})(window);
