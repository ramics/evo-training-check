"""B2.3's control set, and the premise it is not allowed to assume.

§B2 says phage is in Evo 2's training data and therefore acts as a within-study positive
control. The curation half of that is a filter over B2.2's register; the half these tests
mostly pin is the other one, because it is where the task can quietly go wrong. A control
whose organisms turn out to be absent from the corpus is not a control, and the failure is
invisible unless the count is taken and reported with its denominator.
"""

from __future__ import annotations

import importlib.util
import pathlib

import pytest

_spec = importlib.util.spec_from_file_location(
    "control_set",
    pathlib.Path(__file__).resolve().parent.parent / "tools" / "control_set.py",
)
assert _spec and _spec.loader
cs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cs)

NO_RANK = "(no node at this rank)"


def assay(dms_id, taxid, name, *, family=NO_RANK, order=NO_RANK, excluded=False, **kw):
    return {
        "dms_id": dms_id,
        "uniprot_id": kw.get("uniprot_id", dms_id.split("_")[0]),
        "organism": {"taxid": taxid, "name": name},
        "family": family,
        "order": order,
        "excluded_by": {"evo1-literal": excluded, "evo1-strict": excluded},
        "selection_type": kw.get("readout", "cDNA display proteolysis"),
        "n_variants": kw.get("n_variants", 100),
        "seq_len": kw.get("seq_len", 55),
        "doi": kw.get("doi", "10.1/a"),
    }


class TestChoosingTheControlArm:
    def test_an_assay_every_reading_retains_is_in(self):
        reg = {"assays": [assay("A_X", 1, "phage A")]}
        assert [a["dms_id"] for a in cs.retained(reg)] == ["A_X"]

    def test_an_assay_every_reading_excludes_is_out(self):
        reg = {"assays": [assay("A_X", 1, "phage A", excluded=True)]}
        assert cs.retained(reg) == []

    def test_an_assay_the_readings_disagree_about_is_out(self):
        """Its membership would depend on which reading B5 ran, so it is not a control."""
        a = assay("A_X", 1, "phage A")
        a["excluded_by"] = {"evo1-literal": True, "evo1-strict": False}
        assert cs.retained({"assays": [a]}) == []


class TestWhyAnAssayWasRetained:
    def test_no_family_and_no_order_means_the_rules_cannot_fire(self):
        why = cs.why_retained(assay("A_X", 1, "phage A"), NO_RANK)
        assert "can fire" in why and "neither" in why

    def test_a_named_family_is_reported_as_a_family_no_denylist_names(self):
        why = cs.why_retained(assay("A_X", 1, "p", family="Autographiviridae"), NO_RANK)
        assert "Autographiviridae" in why and "no denylist names" in why

    def test_the_two_are_not_the_same_statement(self):
        """Retained by decision and retained by absence of a node are different claims, and
        collapsing them would overstate what the developer decided about phage."""
        absent = cs.why_retained(assay("A_X", 1, "p"), NO_RANK)
        named = cs.why_retained(assay("B_X", 2, "q", order="Caudovirales"), NO_RANK)
        assert absent != named


class TestWhatTheSetSpans:
    def test_it_counts_organisms_and_studies_not_only_assays(self):
        reg = {
            "assays": [
                assay("A_L", 10, "lambda", doi="10.1/one"),
                assay("B_L", 10, "lambda", doi="10.1/one"),
                assay("C_T", 20, "T7", doi="10.1/two", family="Autographiviridae"),
            ]
        }
        spans = cs.control_set(reg, NO_RANK)["spans"]
        assert spans["assays"] == 3
        assert spans["organisms"] == 2
        assert spans["studies"] == 2

    def test_each_organism_carries_the_assays_that_rest_on_it(self):
        reg = {"assays": [assay("A_L", 10, "lambda"), assay("B_L", 10, "lambda")]}
        orgs = cs.control_set(reg, NO_RANK)["organisms"]
        assert len(orgs) == 1
        assert orgs[0]["assays"] == ["A_L", "B_L"]


class TestReadingTheCorpus:
    def _served(self, monkeypatch, rows: list[str]):
        header = "\t".join(["UVIG", "vOTU", "Confidence", "Taxonomic classification"])
        body = "".join(f"u\tv\thigh\t{r}\n" for r in rows)
        payload = (header + "\n" + body).encode()

        class _Fake:
            def __init__(self, *a, **k):
                self._buf = payload
                self._at = 0

            def read(self, n=-1):
                chunk = (
                    self._buf[self._at :]
                    if n is None or n < 0
                    else self._buf[self._at : self._at + n]
                )
                self._at += len(chunk)
                return chunk

        monkeypatch.setattr(cs.objectstore, "S3RandomRead", _Fake)
        monkeypatch.setattr(cs.objectstore, "client", lambda: None)

    def test_it_counts_a_genus_at_the_genus_field(self, monkeypatch):
        self._served(
            monkeypatch,
            ["c__Caudoviricetes;;g__Lambdavirus;", "c__Caudoviricetes;;g__Other;"],
        )
        out = cs.corpus_presence("b", "k", {"genus": {"Lambdavirus"}, "class": set()})
        assert out["counts"]["genus"] == {"Lambdavirus": 1}
        assert out["rows"] == 2

    def test_a_name_in_the_wrong_rank_field_is_not_counted(self, monkeypatch):
        """A substring match on the whole line would count a species named after the genus."""
        self._served(monkeypatch, ["c__Caudoviricetes;;s__Lambdavirus-like phage sp.;"])
        out = cs.corpus_presence("b", "k", {"genus": {"Lambdavirus"}})
        assert out["counts"]["genus"] == {}

    def test_rows_with_no_classification_are_excluded_from_the_denominator(self, monkeypatch):
        self._served(monkeypatch, ["c__Caudoviricetes;;g__Lambdavirus;", ";;;", ";;;;"])
        out = cs.corpus_presence("b", "k", {"genus": {"Lambdavirus"}})
        assert out["rows"] == 3
        assert out["rows_with_a_classification"] == 1

    def test_a_bounded_scan_says_it_is_partial(self, monkeypatch):
        self._served(monkeypatch, ["c__Caudoviricetes;;g__Lambdavirus;"] * 10)
        assert cs.corpus_presence("b", "k", {"genus": {"L"}}, max_rows=3)["partial"] is True


class TestTheVerdictPerOrganism:
    def _presence(self, counts, classified=1000):
        return {"rows": classified, "rows_with_a_classification": classified, "counts": counts}

    def test_the_tightest_rank_with_anything_is_the_verdict(self):
        out = cs.premise(
            [{"taxid": 1, "name": "lambda", "assays": ["A"]}],
            {1: {"genus": "Lambdavirus", "class": "Caudoviricetes"}},
            self._presence({"genus": {"Lambdavirus": 58}, "class": {"Caudoviricetes": 900}}),
        )
        assert out["by_organism"][0]["tightest_rank_present"] == "genus"
        assert out["by_organism"][0]["votus_at_that_rank"] == 58

    def test_an_empty_genus_falls_through_to_the_rank_that_has_something(self):
        out = cs.premise(
            [{"taxid": 1, "name": "T7", "assays": ["A"]}],
            {1: {"genus": "Teseptimavirus", "class": "Caudoviricetes"}},
            self._presence({"genus": {}, "class": {"Caudoviricetes": 900}}),
        )
        org = out["by_organism"][0]
        assert org["tightest_rank_present"] == "class"
        assert org["at_rank"]["genus"]["votus"] == 0

    def test_an_organism_absent_at_every_rank_gets_no_verdict_rather_than_a_default(self):
        out = cs.premise(
            [{"taxid": 1, "name": "ghost", "assays": ["A"]}],
            {1: {"genus": "Nothing"}},
            self._presence({"genus": {}}),
        )
        assert out["by_organism"][0]["tightest_rank_present"] is None
        assert out["by_organism"][0]["votus_at_that_rank"] == 0

    def test_the_denominator_travels_with_the_counts(self):
        """A presence count without one is not a measurement: 58 of three million and 58 of
        a hundred are opposite findings."""
        out = cs.premise([], {}, self._presence({}, classified=2_817_417))
        assert out["denominator"]["votus_with_a_classification"] == 2_817_417


class TestTheControlLogicIsWrittenDown:
    def _blocks(self, votus, rank="genus"):
        spans = {"assays": 7, "organisms": 3, "proteins": 4, "studies": 2}
        premise = {
            "by_organism": [
                {
                    "name": "lambda",
                    "assays": ["A"],
                    "tightest_rank_present": rank,
                    "votus_at_that_rank": votus,
                }
            ]
        }
        return spans, premise

    def test_a_thin_corpus_shows_up_as_a_stated_limit(self):
        spans, premise = self._blocks(4)
        logic = cs.control_logic(spans, premise)
        assert any("homology to related corpus sequence" in x for x in logic["limits"])

    def test_a_well_represented_organism_adds_no_such_limit(self):
        spans, premise = self._blocks(22_969)
        logic = cs.control_logic(spans, premise)
        assert not any("homology to related corpus sequence" in x for x in logic["limits"])

    def test_presence_only_at_class_is_thin_however_many_votus(self):
        """Caudoviricetes is most of the corpus; it says nothing about these organisms."""
        spans, premise = self._blocks(900_000, rank="class")
        assert any(
            "homology to related corpus sequence" in x
            for x in cs.control_logic(spans, premise)["limits"]
        )

    def test_the_null_interpretation_refuses_the_convenient_reading(self):
        logic = cs.control_logic(*self._blocks(58))
        assert "does not show the filter had no effect" in logic["what_a_null_means"]

    def test_the_set_is_tagged_for_separable_analysis(self):
        logic = cs.control_logic(*self._blocks(58))
        assert logic["separable_in_b5"]["tag"] == "within_study_positive_control"
        assert logic["separable_in_b5"]["dms_ids"] == ["A"]


class TestPublishing:
    def test_a_run_written_elsewhere_publishes_nothing(self, tmp_path):
        assert cs.durable_for(tmp_path) is None

    def test_the_canonical_directory_publishes(self):
        assert cs.durable_for(cs.canonical_out()).endswith("/results/b2-3")


@pytest.mark.parametrize("rank", cs.PRESENCE_RANKS)
def test_every_reported_rank_has_a_prefix_to_read_it_by(rank):
    """A rank in the reported list with no prefix would silently count zero everywhere."""
    assert rank in cs.RANK_PREFIX
