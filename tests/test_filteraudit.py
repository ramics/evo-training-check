"""A5.1's shippable interface, run end to end on a corpus small enough to check by hand.

The fixture is nine records across three components, with one family universe of four
families. Every number the audit reports here is countable on the page above it, which is the
only way "the tool runs end to end in CI" is worth asserting: a fixture whose expected output
came out of the tool proves nothing.
"""

from __future__ import annotations

import dataclasses

import pytest

from amazebio import filteraudit, quantify
from amazebio.detect import DetectionTable, FamilyRow, ManifestRef
from amazebio.filteraudit import AuditError, AuditRequest, audit
from amazebio.policyspec import Evidence, Policy, Record, Rule, Scope
from amazebio.survival import Route

SEED = 20261020

#: Three components. The policy's scope names only the first two, so the third exercises the
#: out-of-scope route without any rule being applied to it.
COMPONENTS = ("viruses", "plasmids", "genomes")

#: Nine records. Two carry a denylisted family and are removed; two carry a realm and survive
#: by design; the rest carry no taxonomy at all and are therefore unresolved — which is the
#: shape of the real corpora, where most records cannot be decided from what was published.
RECORDS = {
    "viruses": [
        Record(
            id="v1", component="viruses", taxonomy={"realm": "Riboviria", "family": "Coronaviridae"}
        ),
        Record(
            id="v2", component="viruses", taxonomy={"realm": "Riboviria", "family": "Filoviridae"}
        ),
        Record(
            id="v3",
            component="viruses",
            taxonomy={"realm": "Riboviria", "family": "Picornaviridae"},
        ),
        Record(id="v4", component="viruses", taxonomy={}),
    ],
    "plasmids": [
        Record(
            id="p1",
            component="plasmids",
            taxonomy={"realm": "Monodnaviria", "family": "Inoviridae"},
        ),
        Record(id="p2", component="plasmids", taxonomy={}),
    ],
    "genomes": [
        Record(id="g1", component="genomes", taxonomy={}),
        Record(id="g2", component="genomes", taxonomy={}),
        Record(id="g3", component="genomes", taxonomy={}),
    ],
}

UNIVERSE = quantify.RegistryUniverse(registry="fixture", version="1.0", restriction=None, size=4)


@dataclasses.dataclass
class FixtureCorpus:
    """A corpus held in a dict. The same three methods a staged release implements."""

    release: str = "fixture-release"
    carries_taxonomy: bool = True

    def components(self):  # type: ignore[no-untyped-def]
        return COMPONENTS

    def records(self, component: str):  # type: ignore[no-untyped-def]
        return iter(RECORDS[component])

    def evidence(self, component: str) -> Evidence:
        if not self.carries_taxonomy:
            return Evidence()
        return Evidence(taxonomy_ranks=frozenset({"realm", "family"}))


def policy() -> Policy:
    return Policy(
        id="fixture-literal",
        model="Fixture model",
        reading="literal",
        source="S",
        scope=Scope(components=["viruses", "plasmids"]),
        rules=[
            Rule(
                id="remove-denylisted-families",
                kind="remove_if_taxon_in",
                params={"rank": "family", "names": ["Coronaviridae", "Filoviridae"]},
                source="S",
            ),
        ],
    )


def detector(name: str, hits: dict[str, int]):  # type: ignore[no-untyped-def]
    """A detector that reports a fixed per-family hit count on the surviving records."""

    def run(survivors):  # type: ignore[no-untyped-def]
        searched = sorted(c for c in survivors if survivors[c])
        rows = [
            FamilyRow(
                family_id=f"FAM{i}",
                name=f"family {i}",
                hits=hits.get(f"FAM{i}", 0),
                records=hits.get(f"FAM{i}", 0),
                best_score=None,
                threshold=1.0,
                routes=(
                    {Route.RETAINED_BY_DESIGN.value: hits[f"FAM{i}"]} if hits.get(f"FAM{i}") else {}
                ),
                element_kinds=({"free_virus": hits[f"FAM{i}"]} if hits.get(f"FAM{i}") else {}),
            )
            for i in range(1, UNIVERSE.size + 1)
        ]
        return DetectionTable(
            task="A5.1",
            detector=name,
            registry=UNIVERSE.registry,
            registry_version=UNIVERSE.version,
            manifest=ManifestRef(
                policy_id="fixture-literal",
                release="fixture-release",
                path="manifest-fixture.json",
                sha256="0" * 64,
                removed_records=2,
            ),
            sources=[
                {"component": c, "records": len(survivors[c]), "searched": True} for c in searched
            ],
            rows=rows,
        ).to_dict()

    return run


def request(**kw):  # type: ignore[no-untyped-def]
    return AuditRequest(
        policy=kw.pop("policy", policy()),
        corpus=kw.pop("corpus", FixtureCorpus()),
        universes={"fixture/1.0": UNIVERSE},
        detectors=kw.pop("detectors", {"stub": detector("stub", {"FAM1": 3, "FAM2": 1})}),
        seed=kw.pop("seed", SEED),
        resamples=kw.pop("resamples", 200),
    )


class TestTheRequestRefusesWhatCannotBeReported:
    def test_an_audit_with_no_family_universe_is_refused(self) -> None:
        with pytest.raises(AuditError, match="counts survival against nothing"):
            AuditRequest(policy=policy(), corpus=FixtureCorpus(), universes={}, seed=SEED)

    def test_an_unseeded_audit_is_refused_rather_than_defaulted(self) -> None:
        with pytest.raises(AuditError, match="cannot be regenerated"):
            AuditRequest(
                policy=policy(),
                corpus=FixtureCorpus(),
                universes={"fixture/1.0": UNIVERSE},
            )


class TestEndToEnd:
    def test_the_policy_removes_exactly_the_two_denylisted_records(self) -> None:
        report = audit(request())
        assert report.manifest.removed_records == 2

    def test_a_component_outside_scope_is_routed_not_examined(self) -> None:
        report = audit(request())
        genomes = next(s for s in report.manifest.sources if s.component == "genomes")
        assert genomes.uniform_outcome == Route.OUT_OF_SCOPE.value
        assert genomes.enumerated is False

    def test_an_empty_lineage_in_a_carried_channel_is_data_not_missing_evidence(self) -> None:
        report = audit(request())
        viruses = next(s for s in report.manifest.sources if s.component == "viruses")
        assert viruses.counts["removed"] == 2
        # v3 and v4 both survive and both are `retained`, which is the semantics worth
        # pinning: the release declares it carries taxonomy, so v4's empty lineage is data —
        # "no family assigned" — and not missing evidence. `unresolved` is reserved for a
        # channel the release does not carry at all, which the next test exercises.
        assert viruses.counts["retained"] == 2
        assert "unresolved" not in viruses.counts

    def test_a_release_carrying_no_taxonomy_decides_nothing_at_all(self) -> None:
        report = audit(request(corpus=FixtureCorpus(carries_taxonomy=False)))
        assert report.manifest.removed_records == 0
        viruses = next(s for s in report.manifest.sources if s.component == "viruses")
        assert viruses.counts == {"unresolved": 4}

    def test_survival_is_reported_against_the_pinned_universe_not_the_hits(self) -> None:
        report = audit(request())
        assert len(report.groups) == 1
        document = report.groups[0].document
        assert document["families_in_universe"] == 4
        assert document["m1_families_with_a_hit"] == 2  # FAM1 and FAM2
        assert document["m1_fraction"] == pytest.approx(0.5)

    def test_every_estimate_carries_its_interval(self) -> None:
        document = audit(request()).groups[0].document
        assert document["m1_ci_low"] < document["m1_fraction"] < document["m1_ci_high"]

    def test_a_detector_that_searched_nothing_is_reported_as_absent(self) -> None:
        report = audit(
            request(
                detectors={
                    "stub": detector("stub", {"FAM1": 3, "FAM2": 1}),
                    "never-ran": lambda survivors: None,
                }
            )
        )
        assert report.detectors_run == ["stub"]
        assert report.detectors_absent == ["never-ran"]


class TestLimitationsTravelWithTheCounts:
    def test_every_route_in_the_report_carries_its_limitation(self) -> None:
        report = audit(request())
        assert report.limitations
        for route in report.limitations:
            assert route in filteraudit.ROUTE_LIMITATIONS

    def test_a_route_with_no_stated_limitation_is_refused(self) -> None:
        with pytest.raises(AuditError, match="has no stated limitation"):
            filteraudit.limitations_for(["a_new_route_nobody_documented"])

    def test_the_report_says_the_routes_do_not_pool(self) -> None:
        document = audit(request()).to_dict()
        assert any("never pooled" in line for line in document["reading_this_report"])


class TestTheCommandLineRunsEndToEnd:
    """The §A5 Done-when: the tool runs end to end on a fixture corpus in CI."""

    def tool(self):  # type: ignore[no-untyped-def]
        import importlib.util
        import pathlib

        path = pathlib.Path(__file__).resolve().parent.parent / "tools" / "filter_audit.py"
        spec = importlib.util.spec_from_file_location("filter_audit", path)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_the_fixture_run_produces_a_report(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        tool = self.tool()
        assert tool.main(["--outdir", str(tmp_path), "--allow-dirty"]) == 0
        reports = sorted(tmp_path.glob("report-*.json"))
        assert len(reports) == 1

    def test_the_summary_names_every_route_it_counted(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        tool = self.tool()
        report = audit(request())
        text = tool.summarise(report)
        for route in report.limitations:
            assert route in text
