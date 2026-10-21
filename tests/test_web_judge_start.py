"""/judge as a start page (18 Oct judge walk, item #3): one-tap samples with London set,
the best demo first, and a line on what is staged. The code itself never appears."""

import re

from herbtwin.web.style import STATIC
from tests.test_web_judge import CODE, _client


def _picks(page: str) -> list[tuple[str, str]]:
    return re.findall(
        r'<a class="judge-pick" href="(/static/samples/[^"]+)"[^>]*data-to="([^"]+)"', page
    )


def test_the_judge_page_starts_with_one_tap_samples_basil_flowering_first(tmp_path):
    for page in (
        _client(tmp_path).get("/judge").text,
        _client(tmp_path).post("/judge", data={"code": CODE}).text,  # after the code too
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
    for _ in range(10):
        blocked = tries.post("/judge", data={"code": CODE}).text
    for page in (
        _client(tmp_path).get("/judge").text,
        _client(tmp_path).post("/judge", data={"code": CODE}).text,
        wrong,
        blocked,
    ):
        assert "Staged" in page and "Did you do it?" in page and "reminder" in page
        assert CODE not in page


def test_a_plant_tap_keeps_the_photo_for_the_answer_page(tmp_path):
    # 18 Oct: a gallery retake had no photo in the answer's hero; the answer page reads a
    # copy the sending page leaves in sessionStorage, and only the home form wrote one
    from pathlib import Path

    page = _client(tmp_path).get("/judge").text
    script = page.split("<script>", 1)[1]
    assert 'sessionStorage.setItem("herbtwin-photo-pending"' in script
    assert 'if (tile.dataset.to === "/analyse") await keepPhoto(blob);' in script
    result = Path(__file__).parents[1] / "src/herbtwin/web/templates/result.html"
    assert '"herbtwin-photo-pending"' in result.read_text()  # the key the answer reads


def test_with_the_spot_answer_on_the_bed_sample_goes_to_what_can_i_grow(tmp_path):
    env = {"HERBTWIN_JUDGE_CODE": CODE, "HERBTWIN_SPOT_ENABLED": "1"}
    picks = _picks(_client(tmp_path, env).get("/judge").text)
    assert picks[-1] == ("/static/samples/7-pea-bed.jpg", "/spots")
    assert (STATIC / "samples/7-pea-bed.jpg").is_file()
    assert [to for _, to in picks].count("/spots") == 1
