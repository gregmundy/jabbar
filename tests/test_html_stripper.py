from src.preprocess.html_stripper import strip_html, get_email_body


def test_strip_html_basic():
    html = "<p>Hello <b>world</b></p>"
    result = strip_html(html)
    assert "Hello" in result
    assert "world" in result
    assert "<p>" not in result
    assert "<b>" not in result


def test_strip_html_removes_style():
    html = "<html><head><style>body{color:red;}</style></head><body><p>Content</p></body></html>"
    result = strip_html(html)
    assert "Content" in result
    assert "color:red" not in result


def test_strip_html_removes_script():
    html = "<html><body><script>alert('x')</script><p>Safe</p></body></html>"
    result = strip_html(html)
    assert "Safe" in result
    assert "alert" not in result


def test_strip_html_block_elements_newlines():
    html = "<div>Line1</div><div>Line2</div><p>Line3</p>"
    result = strip_html(html)
    lines = [l for l in result.split("\n") if l.strip()]
    assert len(lines) >= 3


def test_strip_html_collapses_whitespace():
    html = "<p>  lots   of   spaces  </p>"
    result = strip_html(html)
    assert "  " not in result.replace("\n", " ").strip() or "lots of spaces" in result


def test_get_email_body_plain_text():
    raw = b"Content-Type: text/plain\r\n\r\nPlain text body here with enough content to pass the threshold."
    body, source = get_email_body(raw)
    assert "Plain text body" in body
    assert source == "plain"


def test_get_email_body_html_only():
    raw = b"Content-Type: text/html\r\n\r\n<html><body><p>HTML content here that is long enough</p></body></html>"
    body, source = get_email_body(raw)
    assert "HTML content" in body
    assert source == "html_stripped"


def test_get_email_body_truncates():
    long_text = "A" * 10000
    raw = f"Content-Type: text/plain\r\n\r\n{long_text}".encode()
    body, source = get_email_body(raw, max_chars=8000)
    assert len(body) <= 8000
