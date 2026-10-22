"""22 Oct site walk: `curl -I /about` got 303 to /. A HEAD now answers as its GET would,
with no body, so uptime and link checkers see the page's own status."""

from tests.test_web import _client


def test_a_head_request_gets_the_pages_own_status_and_no_body(tmp_path):
    c = _client(tmp_path, [], [])
    for path in ("/", "/about", "/privacy"):
        got, head = c.get(path), c.head(path, follow_redirects=False)
        assert head.status_code == got.status_code == 200, path
        assert head.content == b"", path
        assert head.headers["content-type"] == got.headers["content-type"], path
    assert c.head("/no-such-page", follow_redirects=False).status_code == 404
    old = c.head("/credits", follow_redirects=False)
    assert old.status_code == 301 and old.headers["location"] == "/about#credits"
