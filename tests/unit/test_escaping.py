from orv_ru.rendering.escaping import clean_container_line, escape_inline_html, format_ru_words


def test_escape_inline_html_preserves_only_br() -> None:
    raw = '<Star Stream> & "Fate"<br>Line 2<BR/>End'
    html5 = escape_inline_html(raw, xhtml=False)
    xhtml = escape_inline_html(raw, xhtml=True)

    assert "&lt;Star Stream&gt; &amp; &quot;Fate&quot;" in html5
    assert "<br>Line 2<br>End" in html5
    assert "<br/>Line 2<br/>End" in xhtml


def test_clean_container_line_strips_accidental_markers() -> None:
    assert clean_container_line("<!>[Main Scenario #45]") == "[Main Scenario #45]"
    assert clean_container_line("  <&>「Quote」") == "「Quote」"
    assert clean_container_line("Time Limit: 24h") == "Time Limit: 24h"


def test_format_ru_words_pluralization() -> None:
    assert format_ru_words(1) == "1 слово"
    assert format_ru_words(2) == "2 слова"
    assert format_ru_words(5) == "5 слов"
    assert format_ru_words(11) == "11 слов"
    assert format_ru_words(21) == "21 слово"
    assert format_ru_words(1234) == "1 234 слова"
