"""The answer's plan column as text, read off the real answer page (result.html).

For raters who see the advice without the site, as in the Toloka clarity test: the words,
order and headings are the page's own, so the text cannot drift from the template the way a
hand copy did. Only block 1 (what to do) is kept; the buttons, scripts and pictures go."""

from html.parser import HTMLParser

from fastapi import FastAPI
from fastapi.testclient import TestClient

from herbtwin.schemas import AnalysisRecord

# whole subtrees a reader of plain text cannot use
SKIP_TAGS = {"script", "style", "button", "audio", "figure", "svg", "template"}
# links to the form; "What next" is the page's own buttons and a reminder to come back, not
# advice a rater can judge (design wave 1, D). The how-sure badge is words now, so it is kept
# (21 Oct: the 2-step meter it replaced was skipped). "See it by part" says the plan's own
# lines again, sorted (21 Oct, gardener test)
# extras: shop links; reported: GBIF's records and others' headlines, not our advice
# "told-echo": what the person told us, said back, is not advice (22 Oct site walk)
# "indoor-light": that indoor light isn't measured, and the ask for the window (22 Oct)
# "sure-open", "sure-body": How sure's disclosure, its cue and its explanation (23 Oct): what
# the level means and why, said about our sureness, not advice
# the twin front and centre (23 Oct): the card strip's head and its link ("strip-h",
# "strip-go"; its caption is the card's twin line and is kept), and the twin section's head,
# what the twin is, its finding and Compare ("ts-h", "ts-what", "ts-find", "compare"), said
# about the twin, not advice; the twin pictures' block in it is kept, as before
SKIP_CLASSES = {
    "make-surer", "next-step", "by-part", "extras", "reported", "told-echo", "indoor-light",
    "sure-open", "sure-body", "strip-h", "strip-go", "ts-h", "ts-what", "ts-find", "compare",
}  # fmt: skip
VOID = {"img", "br", "hr", "input", "meta", "link", "source"}
BLOCKS = {"p", "h2", "h3", "li", "ul", "div", "section"}  # each starts a new paragraph


class _Plan(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.blocks: list[str] = []
        self.buf: list[str] = []
        self.depth = 0  # divs open inside the plan; 0 = not in it
        self.skip: list[str] = []  # the open tags of a skipped subtree
        self.inline: list[str] = []  # what each open span/strong closes with
        self.prefix = ""  # the open block's markdown lead: "## ", "### " or "- "

    def flush(self, prefix: str = "") -> None:
        text = " ".join("".join(self.buf).split())
        self.buf = []
        if text:
            self.blocks.append(prefix + text)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        classes = set((a.get("class") or "").split())
        if not self.depth:
            if tag == "div" and "plan" in classes:
                self.depth = 1
            return
        if self.skip:
            if tag == self.skip[0] and tag not in VOID:
                self.skip.append(tag)
            return
        if tag in VOID:
            return
        if tag in SKIP_TAGS or "hidden" in a or classes & SKIP_CLASSES:
            self.skip.append(tag)
            return
        if tag == "div":
            self.depth += 1
        if tag in BLOCKS:
            self.flush(self.prefix)
            self.prefix = ""
            # the twin pictures' heading is an h3 inside the twin's own section (review of #511):
            # raters read it as before, "### Your plant in ~7 days"
            if tag == "h2" or (tag == "h3" and a.get("id") == "twin"):
                self.prefix = "## " if a.get("id") == "main-action" else "### "
            elif tag == "li":
                self.prefix = "- "
            elif tag == "h3":
                self.buf.append("**")
                self.inline.append("h3")
        elif tag in ("span", "strong"):
            mark = "**" if tag == "strong" or "tag" in classes else "*" if "lead" in classes else ""
            # screen-reader punctuation ("How sure we are:") joins the word before it
            self.buf.append(("" if "sr-only" in classes else " ") + mark)
            self.inline.append(mark)

    def handle_endtag(self, tag):
        if not self.depth:
            return
        if self.skip:
            if tag == self.skip[0]:
                self.skip.pop()
            return
        if tag in ("span", "strong") and self.inline:
            self.buf.append(self.inline.pop())
        elif tag == "h3" and self.inline:
            self.inline.pop()
            self.buf.append("**")
        if tag in BLOCKS:
            self.flush(self.prefix)
            self.prefix = ""
        if tag == "div":
            self.depth -= 1

    def handle_data(self, data):
        if self.depth and not self.skip:
            self.buf.append(data)


def plan_text(page: str) -> str:
    """Block 1 of an answer page as markdown: the main card, the photo check, Also do,
    Don't, Keep an eye on and, indoors, "Indoors in <Month>" (#340: advice, so rated) or,
    outdoors, its twin "Outdoors in <Month>" (rated the same), in the page's order and
    words."""
    p = _Plan()
    p.feed(page)
    if not p.blocks:  # the advice failed, or the template moved: never an empty rater item
        raise ValueError("no plan on this answer page")
    return "\n\n".join(p.blocks)


def answer_page(app: FastAPI, rec: AnalysisRecord) -> str:
    """The answer page for a record, through the app's own route: kept as signed out, then
    fetched by its id the way the upload page's jump fetches it."""
    app.state.answers.put(None, rec)
    r = TestClient(app).get(f"/answers/{rec.record_id}")
    r.raise_for_status()
    return r.text
