import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

import pytest

from herbtwin.evals.items import load_set

ROOT = Path(__file__).parents[1]
SET_FILE = ROOT / "data" / "eval" / "sets" / "seasonal_uk.jsonl"
HANDCHECK = ROOT / "data" / "eval" / "seasonal" / "handcheck.json"
NORMS_FILE = ROOT / "data" / "seasonal" / "norms_uk.json"
NORMS = {"mentha spicata", "melissa officinalis", "rosa", "acer palmatum", "ocimum basilicum"}


def _builder():
    spec = importlib.util.spec_from_file_location(
        "build_seasonal_set", ROOT / "scripts" / "build_seasonal_set.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # dataclasses look their module up while building
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def items():
    return load_set(SET_FILE)


def test_set_loads_and_is_sized_for_phase_a(items):
    assert 150 <= len(items) <= 300
    assert {i.set for i in items} == {"seasonal_uk"}
    assert {i.root for i in items} == {"external"}


def test_verdicts_are_balanced(items):
    share = Counter(i.label["verdict"] for i in items)
    assert set(share) == {"normal", "problem"}
    assert 0.35 <= share["normal"] / len(items) <= 0.65


def test_every_kind_is_present_and_matches_its_verdict(items):
    kinds = Counter((i.label["kind"], i.label["verdict"]) for i in items)
    assert set(kinds) == {
        ("normal", "normal"),
        ("problem", "problem"),
        ("counterfactual", "problem"),
        ("season_control", "problem"),
    }
    assert min(kinds.values()) >= 20  # June twins: 24 after barring every season giveaway


def test_month_alone_cannot_pass(items):
    """Within autumn months, "autumn means normal" must be close to a coin toss."""
    autumn = [i for i in items if i.label["month"] in {9, 10, 11}]
    normal = sum(i.label["verdict"] == "normal" for i in autumn)
    assert 0.30 <= normal / len(autumn) <= 0.70


def test_every_item_has_licence_tag_and_source(items):
    for i in items:
        assert i.licence.strip() and i.source.strip(), i.id
        assert i.tag in {"safe-to-train", "test-only"}, i.id
        # non-commercial or no-derivatives licences can never be training data
        if "NC" in i.licence or "ND" in i.licence:
            assert i.tag == "test-only", i.id


def test_labels_are_well_formed(items):
    for i in items:
        lab = i.label
        assert 1 <= lab["month"] <= 12, i.id
        assert lab["plant"] and lab["reason"], i.id
        assert lab["label_source"] in {
            "inat_annotation",
            "dataset_class",
            "counterfactual_month",
            "manual",
        }, i.id
        if lab["verdict"] == "normal":
            assert lab["month"] in {9, 10, 11}, i.id


def test_labels_carry_country_uk_flag_and_norm_key(items):
    for i in items:
        lab = i.label
        assert lab["uk"] == (lab["country"] in {"United Kingdom", "Ireland"}), i.id
        assert lab["norm_key"] is None or lab["norm_key"] == lab["norm_key"].lower(), i.id
        assert isinstance(lab["undated"], bool), i.id
        if lab["plant"].startswith("rosa"):
            assert lab["norm_key"] == "rosa", i.id
        if lab["plant"] == "mentha":
            assert lab["norm_key"] == "mentha", i.id  # the genus norm (#51), not a species
        if lab["plant"] in {"apiaceae", "lamiaceae", "monarda", "houseplant"}:
            assert lab["norm_key"] is None, i.id  # never borrow a norm for a vaguer plant


def test_uk_subset_is_usable_on_its_own(items):
    uk = Counter(i.label["verdict"] for i in items if i.label["uk"])
    assert uk["normal"] >= 30 and uk["problem"] >= 30


@pytest.mark.skipif(not NORMS_FILE.is_file(), reason="UK norms not on this branch yet")
def test_every_norm_key_is_a_plant_the_norms_hold(items):
    plants = {row["plant"] for row in json.loads(NORMS_FILE.read_text())}
    for i in items:
        assert i.label["norm_key"] in plants | {None}, i.id


def test_norm_key_falls_back_from_taxon_to_binomial_to_genus():
    b = _builder()
    assert b.norm_key("rosa acicularis", NORMS) == "rosa"
    assert b.norm_key("acer palmatum amoenum", NORMS) == "acer palmatum"
    assert b.norm_key("mentha spicata", NORMS) == "mentha spicata"
    assert b.norm_key("mentha", NORMS) is None
    assert b.norm_key("mentha", NORMS | {"mentha"}) == "mentha"
    assert b.norm_key("apiaceae", NORMS) is None


def test_twins_reuse_a_photo_and_change_only_the_month(items):
    by_id = {i.id: i for i in items}
    twins = [i for i in items if i.label["label_source"] == "counterfactual_month"]
    assert twins
    for t in twins:
        base_id, _, suffix = t.id.rpartition("@m")
        base = by_id.get(base_id)
        assert base is not None, t.id
        assert base.path == t.path and base.cluster == t.cluster
        assert t.label["plant"] == base.label["plant"]
        assert t.label["month"] == int(suffix) and t.label["verdict"] == "problem"
        if t.label["kind"] == "counterfactual":  # autumn-normal photo moved to June
            assert base.label["verdict"] == "normal" and t.label["month"] == 6
        else:  # summer problem photo moved to October
            assert t.label["kind"] == "season_control"
            assert base.label["verdict"] == "problem" and t.label["month"] == 10
            assert base.label["month"] not in {9, 10, 11}


def test_no_coordinates_and_no_mirage(items):
    for i in items:
        assert not {"lat", "lon", "lat_1dp", "lon_1dp", "lng"} & set(i.label), i.id
        assert not i.path.startswith("s5/"), i.id  # MIRAGE lives in s5


def test_every_photo_in_the_set_was_hand_checked(items):
    hc = json.loads(HANDCHECK.read_text())
    ok, dropped = set(hc["ok"]), set(hc["drop"])
    for i in items:
        key = i.cluster
        assert key in ok, f"{i.id} not hand-checked"
        assert key not in dropped, i.id
    barred = set(hc["no_counterfactual"])
    for i in items:
        if i.label["kind"] == "counterfactual":
            assert i.cluster not in barred, i.id


# --- builder logic, on a tiny fake holdings tree -------------------------------------

S12_HEADER = (
    "source,annotation,taxon_name,taxon_id,group,observation_id,photo_id,file,photo_url,"
    "observed_on,month,quality_grade,tier,captive,country,region,lat_1dp,lon_1dp,"
    "hemisphere,photo_licence,tag,attribution,obs_licence,width,height,status"
)


def _s12_row(pid, taxon, group, month, annotation="colored leaves", source="leaf_annotation"):
    f = f"photos/x/{pid}.jpg"
    return (
        f"{source},{annotation},{taxon},1,{group},9{pid},{pid},{f},u,2025-{month:02d}-01,"
        f"{month:02d},research,research,False,United Kingdom,r,51.5,-0.1,N,cc-by-nc,"
        f"test-only,a,cc-by-nc,500,400,ok"
    )


def _holdings(tmp_path):
    rows = [_s12_row(p, "Mentha spicata", "herb", 10) for p in range(100, 110)]
    rows += [_s12_row(200, "Salvia rosmarinus", "herb", 10)]  # evergreen: never "normal"
    rows += [_s12_row(201, "Mentha spicata", "herb", 6)]  # coloured in June: not autumn
    rows += [_s12_row(300, "Melissa officinalis", "herb", 10, "", "uk_autumn_widened")]
    pd = tmp_path / "s16" / "herb_pd_refs"
    (pd / "images" / "mint_rust").mkdir(parents=True)
    (pd / "images" / "mint_rust" / "inat_1_2.jpg").write_bytes(b"x")
    (pd / "index.csv").write_text(
        "class,source,taxon,query_taxon,file,source_url,image_url,licence,attribution,date,"
        "country_or_region,lat_0p1,lng_0p1,quality_grade,obscured,tag\n"
        "mint_rust,iNaturalist,Puccinia menthae,Puccinia menthae,images/mint_rust/inat_1_2.jpg,"
        "https://www.inaturalist.org/observations/1,u,CC BY (cc-by),a,2025-07-03,UK,51.5,-0.1,"
        "research,False,safe-to-train\n"
    )
    s12 = tmp_path / "s12"
    (s12 / "photos" / "x").mkdir(parents=True)
    for pid in [*range(100, 110), 200, 201, 300]:
        (s12 / "photos" / "x" / f"{pid}.jpg").write_bytes(b"x")
    (s12 / "manifest.csv").write_text("\n".join([S12_HEADER, *rows]) + "\n")
    return tmp_path


def test_builder_is_deterministic_and_applies_the_handcheck(tmp_path):
    b = _builder()
    ext = _holdings(tmp_path)
    hc = {"ok": [], "drop": {}, "no_counterfactual": {}, "manual_dieback": {"300": "brown"}}
    items, _ = b.build(ext, hc, NORMS)
    again, _ = b.build(ext, hc, NORMS)
    assert [i.model_dump() for i in items] == [i.model_dump() for i in again]
    normal = [i for i in items if i.label["kind"] == "normal"]
    assert {i.label["plant"] for i in normal} == {"mentha spicata", "melissa officinalis"}
    assert "seasonal_uk/inat/200" not in {i.id for i in items}
    assert "seasonal_uk/inat/201" not in {i.id for i in items}
    manual = [i for i in normal if i.label["label_source"] == "manual"]
    assert [i.id for i in manual] == ["seasonal_uk/inat/300"]
    inat = [i for i in items if i.id.startswith("seasonal_uk/inat/")]
    assert all(i.licence == "CC BY-NC" and i.tag == "test-only" for i in inat)

    first = sorted(i.id for i in normal)[0]
    dropped_key = first.removeprefix("seasonal_uk/")
    hc["drop"] = {dropped_key: "wrong"}
    hc["no_counterfactual"] = {k: "x" for k in ("inat/101", "inat/102")}
    items2, _ = b.build(ext, hc, NORMS)
    ids2 = {i.id for i in items2}
    assert first not in ids2 and f"{first}@m06" not in ids2
    for i in items2:
        if i.label["kind"] == "counterfactual":
            assert i.cluster not in hc["no_counterfactual"]
    assert any(i.label["kind"] == "counterfactual" for i in items2)


def test_drops_apply_before_the_cap_and_pull_in_the_next_candidate(tmp_path, monkeypatch):
    b = _builder()
    ext = _holdings(tmp_path)
    monkeypatch.setitem(b.CAPS, "normal/herb", 3)
    hc = {"ok": [], "drop": {}, "no_counterfactual": {}, "manual_dieback": {}}

    def normal_ids(hc):
        items, _ = b.build(ext, hc, NORMS)
        return [i.id for i in items if i.label["kind"] == "normal"]

    ranked = sorted((f"inat/{p}" for p in range(100, 110)), key=b._rank)
    assert sorted(normal_ids(hc)) == sorted(f"seasonal_uk/{k}" for k in ranked[:3])
    hc["drop"] = {ranked[0]: "wrong"}
    assert sorted(normal_ids(hc)) == sorted(f"seasonal_uk/{k}" for k in ranked[1:4])


def test_a_summer_problem_gets_an_october_twin(tmp_path):
    b = _builder()
    items, _ = b.build(_holdings(tmp_path), {"ok": [], "drop": {}}, NORMS)
    by_id = {i.id: i for i in items}
    base = by_id["seasonal_uk/herb_pd/inat_1_2"]
    twin = by_id["seasonal_uk/herb_pd/inat_1_2@m10"]
    assert base.label["month"] == 7 and base.label["verdict"] == "problem"
    assert twin.label["kind"] == "season_control" and twin.label["verdict"] == "problem"
    assert twin.path == base.path and twin.cluster == base.cluster
