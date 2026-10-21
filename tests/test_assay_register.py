"""B2.4's register, and the licence claim it is not allowed to overstate.

The register's job is to be the thing a reader trusts about provenance, so the tests here are
mostly about the ways it could be confidently wrong rather than merely incomplete: an article's
licence standing in for a licence on data nobody granted, a deposit assumed to be the bytes we
read because the file sizes matched, a licence URL nobody recognised passing through as if it
had been read, and a check that passes because there was nothing in it.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib

import pytest

_spec = importlib.util.spec_from_file_location(
    "assay_register",
    pathlib.Path(__file__).resolve().parent.parent / "tools" / "assay_register.py",
)
assert _spec and _spec.loader
ar = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ar)

REPO = pathlib.Path(__file__).resolve().parent.parent
CC_BY = "https://creativecommons.org/licenses/by/4.0/"
NC_ND = "https://creativecommons.org/licenses/by-nc-nd/4.0/"


def work(doi, urls=(), **kw):
    return {
        "doi": doi,
        "retrieved": True,
        "publisher": kw.get("publisher", "A Publisher"),
        "container": kw.get("container", "A Journal"),
        "title": kw.get("title", "A paper"),
        "year": kw.get("year", 2020),
        "licenses": [{"url": u, "content_version": "vor"} for u in urls],
    }


def evidence(works=(), *, match="digest", licence="mit-license"):
    return {
        "retrieved_on": "2026-10-20",
        "deposit": {
            "record": "15293562",
            "url": "https://zenodo.org/records/15293562",
            "doi": "10.5281/zenodo.15293562",
            "license": licence,
            "files": [],
        },
        "release": {"version": "v1.3", "downloaded_from": "https://example.org/pg"},
        "deposit_match": [{"file": "DMS_ProteinGym_substitutions.zip", "match": match}],
        "works": list(works),
    }


def assay(dms_id, doi, **kw):
    return {
        "dms_id": dms_id,
        "uniprot_id": dms_id.split("_")[0],
        "organism": {"taxid": kw.get("taxid", 1), "name": kw.get("organism", "a virus")},
        "family": kw.get("family", "Someviridae"),
        "order": kw.get("order", "Someorder"),
        "excluded_by": kw.get("excluded_by", {"evo1-literal": True, "evo1-strict": True}),
        "undecidable_by": {"esm3-open-literal": "by similarity"},
        "selection_type": "Growth",
        "msa_depth_category": "Medium",
        "n_variants": 100,
        "seq_len": 50,
        "doi": doi,
    }


def built(assays, works, *, controls=(), **kw):
    return ar.build(
        {"assays": assays},
        {"control_set": {"assays": list(controls)}},
        evidence(works, **kw),
    )


class TestClassifyingAnArticlesTerms:
    def test_a_recognised_open_licence_is_permissive(self):
        out = ar.classify([CC_BY])
        assert out["position"] == "permissive" and out["permits_redistribution"] is True

    def test_a_no_derivatives_licence_is_restrictive_with_its_reason(self):
        out = ar.classify([NC_ND])
        assert out["position"] == "restrictive"
        assert "no derivatives" in out["restrictive"][NC_ND]

    def test_nothing_deposited_is_not_the_same_as_permissive(self):
        """Absent evidence and evidence of permission are opposite things, and defaulting the
        first to the second is how a register starts asserting licences nobody granted."""
        out = ar.classify([])
        assert out["position"] == "none deposited"
        assert out["permits_redistribution"] is None

    def test_an_unrecognised_url_is_flagged_rather_than_guessed(self):
        out = ar.classify(["https://example.org/some-bespoke-terms"])
        assert out["position"] == "unclassified"
        assert out["permits_redistribution"] is None

    def test_deposits_that_disagree_are_reported_as_disagreeing(self):
        """Taking the most permissive would overstate it and the most restrictive would
        understate it. Neither is a reading the register is entitled to make."""
        out = ar.classify([CC_BY, NC_ND])
        assert out["position"] == "mixed"
        assert out["permits_redistribution"] is None
        assert out["permissive"] == [CC_BY] and NC_ND in out["restrictive"]


class TestTheRegisterKeepsTheTwoLicencesApart:
    def test_the_grant_relied_on_is_the_deposits_not_the_articles(self):
        reg = built([assay("A_X", "10.1/a")], [work("10.1/a", [NC_ND])])
        assert reg["licence_relied_on"]["licence"] == "mit-license"
        assert reg["assays"][0]["source"]["article_terms"]["position"] == "restrictive"

    def test_a_restrictive_article_does_not_make_the_assay_unusable(self):
        """The project redistributes no assay data, so the article's terms constrain a reader
        going back to the source, not this pipeline. The register has to say so."""
        reg = built([assay("A_X", "10.1/a")], [work("10.1/a", [NC_ND])])
        assert "not as a constraint this project is operating under" in reg["coverage"]["note"]

    def test_the_deposit_block_states_that_mit_on_data_is_not_settled(self):
        reg = built([assay("A_X", "10.1/a")], [work("10.1/a", [CC_BY])])
        assert any("software licence" in x for x in reg["licence_relied_on"]["limits"])

    def test_it_states_that_the_deposit_does_not_relicense_the_studies(self):
        reg = built([assay("A_X", "10.1/a")], [work("10.1/a", [CC_BY])])
        assert any("does not reach back" in x for x in reg["licence_relied_on"]["limits"])


class TestWhatTheRegisterCovers:
    def test_each_assay_carries_where_its_bytes_were_read_from(self):
        reg = built([assay("A_X", "10.1/a")], [work("10.1/a", [CC_BY])])
        prov = reg["assays"][0]["provenance"]
        assert prov["read_from"] == "DMS_ProteinGym_substitutions.zip"
        assert prov["key"] == "A_X.csv" and prov["version"] == "v1.3"

    def test_the_control_tag_comes_from_b2_3_and_carries_its_reason(self):
        reg = built(
            [assay("A_X", "10.1/a"), assay("B_X", "10.1/a")],
            [work("10.1/a", [CC_BY])],
            controls=[{"dms_id": "A_X", "retained_because": "no family node"}],
        )
        tagged = {a["dms_id"]: a for a in reg["assays"]}
        assert tagged["A_X"]["within_study_positive_control"] is True
        assert tagged["A_X"]["control_because"] == "no family node"
        assert tagged["B_X"]["within_study_positive_control"] is False

    def test_counts_are_by_study_and_organism_not_only_by_assay(self):
        reg = built(
            [assay("A_X", "10.1/a", taxid=7), assay("B_X", "10.1/a", taxid=7)],
            [work("10.1/a", [CC_BY])],
        )
        assert reg["coverage"] == {
            **reg["coverage"],
            "assays": 2,
            "studies": 1,
            "organisms": 1,
        }


class TestTheCheck:
    def test_an_assay_with_no_doi_cannot_be_traced_and_fails(self):
        reg = built([assay("A_X", None)], [])
        assert any("no source DOI" in p for p in ar.check(reg, evidence()))

    def test_an_unrecognised_licence_url_fails_rather_than_passing_through(self):
        reg = built([assay("A_X", "10.1/a")], [work("10.1/a", ["https://example.org/terms"])])
        problems = ar.check(reg, evidence([work("10.1/a", ["https://example.org/terms"])]))
        assert any("unrecognised licence URL" in p for p in problems)

    def test_a_size_only_deposit_match_fails_the_licence_claim(self):
        """Matching sizes make the deposit probably the same file. The register says the
        deposit's grant *is* the grant on our bytes, and only a digest shows that."""
        ev = evidence([work("10.1/a", [CC_BY])], match="size only")
        reg = ar.build({"assays": [assay("A_X", "10.1/a")]}, {"control_set": {"assays": []}}, ev)
        assert any("not established to be the deposit's bytes" in p for p in ar.check(reg, ev))

    def test_a_changed_deposit_licence_fails(self):
        ev = evidence([work("10.1/a", [CC_BY])], licence="cc-by-nc-4.0")
        reg = ar.build({"assays": [assay("A_X", "10.1/a")]}, {"control_set": {"assays": []}}, ev)
        assert any("not the MIT grant" in p for p in ar.check(reg, ev))

    def test_an_empty_register_is_not_a_pass(self):
        ev = evidence()
        reg = ar.build({"assays": []}, {"control_set": {"assays": []}}, ev)
        assert any("no assays" in p for p in ar.check(reg, ev))

    def test_an_unreadable_source_is_named(self):
        ev = evidence([{"doi": "10.1/a", "retrieved": False, "blocker": "403"}])
        reg = ar.build({"assays": [assay("A_X", "10.1/a")]}, {"control_set": {"assays": []}}, ev)
        assert any("unreadable for: 10.1/a" in p for p in ar.check(reg, ev))

    def test_a_control_tagged_without_a_reason_fails(self):
        ev = evidence([work("10.1/a", [CC_BY])])
        reg = ar.build(
            {"assays": [assay("A_X", "10.1/a")]},
            {"control_set": {"assays": [{"dms_id": "A_X", "retained_because": None}]}},
            ev,
        )
        assert any("tagged a control with no reason" in p for p in ar.check(reg, ev))


class TestTheCommittedRegister:
    """The register is the deliverable, so these read what is actually on disk."""

    def test_it_is_present_and_passes_its_own_check(self):
        reg = json.loads(ar.REGISTER.read_text())
        assert ar.check(reg, json.loads(ar.EVIDENCE.read_text())) == []

    def test_every_assay_in_it_has_a_traceable_study(self):
        reg = json.loads(ar.REGISTER.read_text())
        assert all(a["source"]["url"].startswith("https://doi.org/") for a in reg["assays"])

    def test_the_markdown_beside_it_is_not_stale(self):
        reg = json.loads(ar.REGISTER.read_text())
        assert ar.markdown(reg) + "\n" == ar.REGISTER_MD.read_text()


class TestPublishing:
    def test_a_run_written_elsewhere_publishes_nothing(self, tmp_path):
        assert ar.durable_for(tmp_path) is None

    def test_the_canonical_directory_publishes(self):
        assert ar.durable_for(ar.CANONICAL_OUT).endswith("/results/b2-4")


@pytest.mark.parametrize("url", sorted(ar.PERMISSIVE | set(ar.RESTRICTIVE)))
def test_no_licence_url_is_classified_both_ways(url):
    assert (url in ar.PERMISSIVE) != (url in ar.RESTRICTIVE)
