from ui.post_view import _EMBED_TEMPLATE, _plain_text


def test_comment_is_rendered_as_escaped_text():
    out = _plain_text('<img src=x onerror=alert(1)> **bold** http://a.example')
    assert "<img" not in out
    assert "&lt;img src=x onerror=alert(1)&gt; **bold** http://a.example" in out


def test_embed_markup_only_contains_escaped_url():
    html = _EMBED_TEMPLATE.format(url="https://www.instagram.com/p/ABCDE/")
    assert 'data-instgrm-permalink="https://www.instagram.com/p/ABCDE/"' in html
    assert html.count("<script") == 1 and "https://www.instagram.com/embed.js" in html
