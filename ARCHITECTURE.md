# Архитектура `orv-ru` (GRASP + SOLID + «Чёрные ящики»)

Проект строится по принципу **Clean-Room Hexagonal / Layered Architecture**: вся бизнес-логика и доменные модели изолированы в центре, а внешние детали (парсинг `.txt`, файловая система, HTML/EPUB-генерация, LLM-провайдеры) вынесены в сменные адаптеры за интерфейсами (`Protocol`).

---

## 1. Карта зависимостей (стрелки идут только внутрь)

```text
  [ App / CLI Controllers ]   (Этапы 3–4: сценарии сборки и перевода)
        │        │        │
        ▼        ▼        ▼
  ┌──────────┐ ┌──────────┐ ┌─────────────┐ ┌──────────────┐
  │ parsing/ │ │ storage/ │ │ rendering/  │ │ translation/ │  ◀── Чёрные ящики (адаптеры)
  │ (Этап 2) │ │ (Этап 2) │ │  (Этап 3)   │ │   (Этап 4)   │
  └────┬─────┘ └────┬─────┘ └──────┬──────┘ └──────┬───────┘
       │            │              │               │
       └────────────┴──────┬───────┴───────────────┘
                           ▼
               ┌───────────────────────┐
               │        ports/         │  ◀── Контракты (typing.Protocol)
               └───────────┬───────────┘
                           ▼
               ┌───────────────────────┐
               │        domain/        │  ◀── Чистое ООП-ядро (0 зависимостей от I/O)
               └───────────────────────┘
```

**Золотое правило:** `domain/` не импортирует **ничего** из `parsing/`, `storage/`, `rendering/`, `translation/` и даже из `config.py`. Это значит, что модель главы можно тестировать в памяти за миллисекунды без единого файла на диске.

---

## 2. Четыре «чёрных ящика» системы

| Чёрный ящик | Контракт (что на входе и выходе) | Что скрыто внутри (при желании можно разобрать) |
| :--- | :--- | :--- |
| **`parsing/`** *(Этап 2 — готов)* | `raw_text -> Chapter`, `Chapter -> raw_text`, `validate_translation(src, dst) -> ValidationReport` | Конечный автомат строк для `+`/`++`, регулярные выражения тегов, восстановление пробелов (`762.txt`), проверка `structural_signature()`. |
| **`storage/`** *(Этап 2 — готов)* | `ChapterReader` / `ChapterRepository` (`load`, `load_all`, `save`, `list_chapter_numbers`) | Поиск `<число>.txt`, числовая сортировка (`553..1068`), атомарная запись (`mkstemp` + `os.replace`), инъекция парсера и сериализатора. |
| **`rendering/`** *(Этап 3 — готов)* | `Chapter` + `StoryMetadata` → готовый статический сайт (`SiteBuildReport`) и `.epub` (`EpubBuildReport`) | Безопасное экранирование HTML/XHTML, кэшированный `AssetResolver` (вкл. `.jpeg`/`.jpg` fallback), табличная диспетчеризация блоков в HTML и XHTML, упаковка EPUB 3 (`mimetype`, `nav.xhtml`, `toc.ncx`, `content.opf`, сноски), шаблоны `web/`. |
| **`translation/`** *(Этап 4 — готов)* | `Chapter` + глоссарий → переведённый `Chapter` с гарантией 0 сломанных тегов | Однопроходный longest-first индекс `Glossary` (`find_in_text`), Protected Payload (`extract_packet`/`apply_payload`), `ChapterChunker` со скользящим контекстом, `GlossaryChecker` (учёт падежей и `ё`/`е`), `GeminiLLMClient`, self-healing ретраи. |
| **`app/`** *(Контроллер + CLI)* | `WorkspaceController` + `models.py` (`WorkspaceStatus`, `ValidationSummary`) + `cli.py` | Строгий DIP через `ports/`-протоколы, табличная диспетчеризация подкоманд и `--json`-вывод для автономных агентов. |

---

## 2.1. Рабочее поле для агента и пользователя (`app/` CLI)

Контроллер `WorkspaceController` и CLI (`python3 -m orv_ru`) дают автономную самопроверку с детерминированными кодами возврата (`0` / `1`) и флагом `--json`:

```bash
PYTHONPATH=src python3 -m orv_ru status --json
PYTHONPATH=src python3 -m orv_ru validate --json
PYTHONPATH=src python3 -m orv_ru export-packet 553 --json
PYTHONPATH=src python3 -m orv_ru import-translation 553 translated_553.json --json
PYTHONPATH=src python3 -m orv_ru check-glossary --json
PYTHONPATH=src python3 -m orv_ru translate --next 5 --dry-run --json
PYTHONPATH=src python3 -m orv_ru build-site --source --limit 10 --json
PYTHONPATH=src python3 -m orv_ru build-epub --source --limit 10 --json
PYTHONPATH=src python3 -m orv_ru serve --port 8080
```

---

## 3. Где применены все 9 паттернов GRASP

1. **Information Expert (Информационный эксперт):** `Chapter` сам считает `word_count`, `reading_time_minutes()` и `translatable_blocks()`; каждый `Block` сам знает свой `plain_text()`, `counts_toward_word_count` и `structural_signature()`.
2. **Creator (Создатель):** `OrvMarkupParser` создаёт объекты `Chapter` и конкретные подклассы `Block`, так как владеет разобранными строками и тегами.
3. **Controller (Контроллер):** сценарии верхнего уровня (сборка сайта, запуск пакета перевода — Этапы 3–4) координируют порты, не содержат деталей парсинга или HTTP.
4. **Low Coupling (Низкая связанность):** `FileSystemChapterRepository` зависит только от абстракций `ChapterParser` и `ChapterSerializer`, а не от деталей их реализации.
5. **High Cohesion (Высокое зацепление):** парсинг (`parser.py`), сериализация (`serializer.py`) и структурная проверка (`validator.py`) разделены на три узких класса.
6. **Polymorphism (Полиморфизм):** вместо громоздких `if/elif` по строковым тегам в бизнес-логике используются методы и свойства подклассов `Block` (`SystemMessageBlock`, `SystemWindowBlock`, `CoverBlock` и др.).
7. **Pure Fabrication (Чистая выдумка):** `StructuralValidator`, `OrvMarkupSerializer` и `FileSystemChapterRepository` — сервисные сущности, не существующие в предметной области книги, но необходимые для чистой архитектуры.
8. **Indirection (Перенаправление):** пакет `ports/` (`ChapterReader`, `ChapterWriter`, `LLMClient`, `BlockRenderer`) служит буфером между бизнес-логикой и конкретными библиотеками/диском.
9. **Protected Variations (Защита от изменений):** если формат хранения глав изменится (например, с `.txt` на SQLite) или сменится LLM-провайдер, `domain/` и контроллеры не изменятся ни на строку — достаточно подставить новый адаптер под `Protocol`.

---

## 4. Где применены все 5 принципов SOLID

- **S — Single Responsibility:** `Chapter` хранит структуру главы, `OrvMarkupParser` только разбирает текст, `OrvMarkupSerializer` только собирает текст обратно, `StructuralValidator` только проверяет инварианты.
- **O — Open/Closed:** добавить новый тип блока (новый тег) можно новым подклассом `Block` и записью в таблице диспетчеризации без переписывания `Chapter` или `FileSystemChapterRepository`.
- **L — Liskov Substitution:** любой наследник `Block` безопасно подставляется везде, где ожидается `Block` (`word_count`, `structural_signature`, `translatable_blocks`).
- **I — Interface Segregation:** в `ports/repository.py` разделены `ChapterReader` (только чтение — нужен билдерам сайта/EPUB) и `ChapterWriter` (запись — нужен переводчику). Читатель не зависит от методов записи.
- **D — Dependency Inversion:** классы верхнего уровня и хранилище получают зависимости через конструктор и зависят от `Protocol`-интерфейсов из `ports/`, а не от конкретных реализаций.
