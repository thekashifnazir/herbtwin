"""/judge as a start page (18 Oct judge walk, item #3): one-tap samples with London set,
the best demo first, and a line on what is staged. The code itself never appears."""

import re

from herbtwin.web.style import STATIC
from tests.test_web_judge import CODE, _client


def _in(tmp_path, env: dict[str, str] | None = None) -> str:
    """/judge as a judge comes back to it: the code typed once, then the page again."""
    c = _client(tmp_path, env)
    c.post("/judge", data={"code": CODE})
    return c.get("/judge").text


def _picks(page: str) -> list[tuple[str, str]]:
    return re.findall(
        r'<a class="judge-pick" href="(/static/samples/[^"]+)"[^>]*data-to="([^"]+)"', page
    )


def test_the_judge_page_starts_with_one_tap_samples_basil_flowering_first(tmp_path):
    (tmp_path / "b").mkdir()
    for page in (
        _client(tmp_path).post("/judge", data={"code": CODE}).text,  # right after the code
        _in(tmp_path / "b"),  # and back again with the cookie
    ):
        picks = _picks(page)
        assert picks and picks[0][0] == "/static/samples/3-basil-yellow-leaves.jpg"
        assert {to for _, to in picks} == {"/analyse"}
        for href, _ in picks:
            assert (STATIC / href.removeprefix("/static/")).is_file(), href
        form = page.split('<form class="judge-try"', 1)[1].split("</form>", 1)[0]
        assert 'enctype="multipart/form-data"' in form
        assert '<input type="hidden" name="place" value="London">' in form
        assert "DataTransfer" in page and "form.submit()" in page


def test_the_judge_page_says_what_is_staged_and_never_shows_the_code(tmp_path):
    tries = _client(tmp_path)
    wrong = tries.post("/judge", data={"code": "nope"}).text
    for _ in range(9):  # a right code uses no try: ten wrong ones, then even the right is refused
        tries.post("/judge", data={"code": "nope"})
    blocked = tries.post("/judge", data={"code": CODE}).text
    assert "Too many tries today" in blocked
    (tmp_path / "b").mkdir()
    for page in (_client(tmp_path).post("/judge", data={"code": CODE}).text, _in(tmp_path / "b")):
        assert "Staged" in page and "Did you do it?" in page and "reminder" in page
        # 22 Oct walk 2: "The gallery" named one the site doesn't have; it is Devpost's
        assert "Our Devpost gallery shows" in page and "The gallery shows" not in page
        assert CODE not in page
    # before the code, only the code box (23 Oct): nothing staged, no samples
    (tmp_path / "c").mkdir()
    for page in (_client(tmp_path / "c").get("/judge").text, wrong, blocked):
        assert 'class="judge-staged"' not in page and 'class="judge-pick"' not in page
        assert CODE not in page


def test_a_plant_tap_keeps_the_photo_for_the_answer_page(tmp_path):
    # 18 Oct: a gallery retake had no photo in the answer's hero; the answer page reads a
    # copy the sending page leaves in sessionStorage, and only the home form wrote one
    from pathlib import Path

    page = _in(tmp_path)
    script = page.split("<script>\n(() => {\n  // a tap loads", 1)[1]
    assert 'sessionStorage.setItem("herbtwin-photo-pending"' in script
    assert 'if (tile.dataset.to === "/analyse") await keepPhoto(blob);' in script
    result = Path(__file__).parents[1] / "src/herbtwin/web/templates/result.html"
    assert '"herbtwin-photo-pending"' in result.read_text()  # the key the answer reads


def test_with_the_spot_answer_on_the_bed_sample_goes_to_what_can_i_grow(tmp_path):
    env = {"HERBTWIN_JUDGE_CODE": CODE, "HERBTWIN_SPOT_ENABLED": "1"}
    picks = _picks(_in(tmp_path, env))
    assert picks[-1] == ("/static/samples/7-pea-bed.jpg", "/spots")
    assert (STATIC / "samples/7-pea-bed.jpg").is_file()
    assert [to for _, to in picks].count("/spots") == 1
