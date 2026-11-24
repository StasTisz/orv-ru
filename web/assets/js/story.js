document.addEventListener('DOMContentLoaded', () => {
    const app = document.getElementById('story-app');
    if (!app) return;

    const slug = app.dataset.slug;
    const metaUrl = app.dataset.meta;
    const chaptersUrl = app.dataset.chapters;

    let chapters = [];
    let ascending = true;

    const state = window.OrvStorage.getReaderState();
    const lastRead = state.last_read && state.last_read[slug];

    function updateReadButton() {
        const readLink = document.getElementById('read-link');
        const readBtn = document.getElementById('read-btn');
        if (!readLink || !readBtn) return;

        if (!chapters.length) {
            readLink.href = '#';
            readLink.addEventListener('click', (e) => e.preventDefault());
            readBtn.disabled = true;
            readBtn.setAttribute('aria-disabled', 'true');
            readBtn.textContent = 'Скоро';
            return;
        }

        readBtn.disabled = false;
        readBtn.removeAttribute('aria-disabled');
        if (lastRead && chapters.some((ch) => Number(ch.number) === Number(lastRead))) {
            readLink.href = `./read/ch_${lastRead}.html`;
            readBtn.textContent = 'Продолжить';
            readBtn.title = `Продолжить с главы ${lastRead}`;
        } else {
            readLink.href = `./read/${chapters[0].href}`;
            readBtn.textContent = 'Читать';
        }
    }

    function escapeHtml(str) {
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
    }

    function renderChapterList(items) {
        const listEl = document.getElementById('chapter-list');
        if (!listEl) return;
        if (!chapters.length) {
            listEl.innerHTML =
                '<div class="chapter_item is-empty"><p>Перевод первых глав ещё готовится — загляните чуть позже.</p></div>';
            return;
        }
        if (!items.length) {
            listEl.innerHTML = '<div class="chapter_item"><p>Глава не найдена</p></div>';
            return;
        }
        listEl.innerHTML = items
            .map(
                (ch) =>
                    `<div class="chapter_item"><a href="./read/${ch.href}"><p>${escapeHtml(ch.title)}</p></a></div>`
            )
            .join('');
    }

    function applyFilterAndSort() {
        const searchEl = document.getElementById('chapter-search');
        const query = searchEl ? searchEl.value.trim().toLowerCase() : '';
        let list = chapters.slice();
        if (!ascending) {
            list.reverse();
        }
        if (query) {
            list = list.filter((ch) => String(ch.title).toLowerCase().includes(query));
        }
        renderChapterList(list);
    }

    fetch(metaUrl)
        .then((res) => (res.ok ? res.json() : Promise.reject(res.statusText)))
        .then((meta) => {
            const metaBox = document.getElementById('story-meta');
            if (metaBox) {
                const countText =
                    meta.source_chapters !== undefined && meta.source_chapters !== meta.chapters
                        ? `${meta.chapters} (всего ${meta.source_chapters})`
                        : `${meta.chapters}`;
                metaBox.innerHTML = `
                    <p class="story-title">${escapeHtml(meta.title)}</p>
                    <p>Автор: ${escapeHtml(meta.author)}<br>
                    Глав: ${escapeHtml(countText)}<br>
                    Статус: ${escapeHtml(meta.status)}</p>
                `;
            }
        })
        .catch(() => {});

    fetch(chaptersUrl)
        .then((res) => (res.ok ? res.json() : Promise.reject(res.statusText)))
        .then((data) => {
            chapters = data.slice().sort((a, b) => a.number - b.number);
            updateReadButton();
            applyFilterAndSort();
        })
        .catch(() => {});

    const searchInput = document.getElementById('chapter-search');
    if (searchInput) {
        searchInput.addEventListener('input', applyFilterAndSort);
    }

    const sortBtn = document.getElementById('sort-toggle');
    if (sortBtn) {
        sortBtn.addEventListener('click', () => {
            ascending = !ascending;
            sortBtn.classList.toggle('is-reversed', !ascending);
            applyFilterAndSort();
        });
    }
});
