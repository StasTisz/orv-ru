# `orv-ru` — Движок читалки, EPUB-сборщик и пайплайн перевода (ORV Side Stories)

Чистая **Clean-Room** реализация на Python (ООП по **GRASP** и **SOLID** без сторонних runtime-зависимостей) для перевода и чтения побочных историй веб-новеллы *Omniscient Reader's Viewpoint* на русском языке.

> [!NOTE]
> В репозитории хранится **только код движка, шаблоны интерфейса, тесты, документация и глоссарий**. Тексты глав, иллюстрации и собранные артефакты исключены через [`.gitignore`](.gitignore) (`data/`, `output/`).

---

## Возможности

- **Парсер и структурный валидатор (`parsing/`):** разбирает `.txt`-разметку ORV (`<!>`, `<@>`, `<#>`, `<&>`, `<?>`, `+`, `++`, `<cover>`, `<img>`, `***`), гарантирует 100% round-trip и проверяет перевод по `structural_signature()` (ноль потерянных тегов и `<br>`).
- **Статический веб-ридер 1:1 (`rendering/` + `web/`):**
  - 13 цветовых тем (включая OLED Midnight, Sepia, Forest, Lavender и их тёмные версии);
  - настройка шрифта, размера, межстрочного интервала и начертания;
  - все режимы **Rich Text** (голубые голограммы системных окон, скобки созвездий, рамки Внешних Богов, сноски);
  - сохранение прогресса чтения и позиции скролла в `localStorage`, живой поиск по главам, горячие клавиши (`←` / `→` / `Esc`), Wake Lock и режим печати.
- **EPUB 3-сборщик (`epub_builder.py`):** упаковывает валидный русский EPUB со стилями системных окон и концевыми сносками (`epub:type="endnotes"`).
- **Конвейер перевода (`translation/`):**
  - подбор релевантного глоссария под каждую главу (`glossary/orv_glossary.toml`, 240 терминов, 9 правил);
  - Protected Payload (`export-packet` / `import-translation`) для безопасной работы ИИ-агентов;
  - чанкинг со скользящим контекстом, self-healing ретраями и проверкой русских падежей в `GlossaryChecker`;
  - опциональный адаптер [`GeminiLLMClient`](src/orv_ru/translation/clients.py) на актуальном `google-genai` SDK.

---

## Быстрый старт

```bash
# 1. Прогнать все юнит- и интеграционные тесты
pytest

# 2. Посмотреть прогресс перевода
PYTHONPATH=src python3 -m orv_ru status --json

# 3. Выгрузить следующую непереведённую главу для агента
python3 scripts/next_packet.py

# 4. Импортировать и проверить переведённый JSON-пакет
PYTHONPATH=src python3 -m orv_ru import-translation 553 data/work/translated_553.json --strict-glossary --json

# 5. Оценить бюджет токенов для автоматического перевода через Gemini API
PYTHONPATH=src python3 -m orv_ru translate --next 5 --dry-run --json

# 6. Проверить всё и собрать русский сайт + EPUB
python3 scripts/verify_and_build.py --with-tests

# 7. Открыть локальный веб-ридер в браузере
PYTHONPATH=src python3 -m orv_ru serve --port 8080
```

---

## Документация проекта

- [`ARCHITECTURE.md`](ARCHITECTURE.md) — карта слоёв, GRASP/SOLID-решения и описание «чёрных ящиков».
- [`AGENTS.md`](AGENTS.md) — пошаговый регламент для агентов-переводчиков и стандарты стиля.
- [`glossary/orv_glossary.toml`](glossary/orv_glossary.toml) — канонический словарь терминов ORV.
