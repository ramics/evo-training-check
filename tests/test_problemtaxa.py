"""Tests for `amazebio.problemtaxa` — task A2.5, implementing DECISIONS.md D-187.

Matching a taxon name against a set is not what needs pinning. What needs pinning is the set of
ways a *label-based* problem-taxa sweep comes out clean and wrong, because every one of them
fails in the same direction — toward a reassuring zero:

* **A detection reported as "could not tell".** `f__Mimiviridae` with no phylum field is a
  giant virus. A verdict that only compares ranks directly returns `UNLABELLED` for it, and a
  category whose members sit at phylum would then miss every record labelled at family. This is
  the bug this module actually had, and it is the worst of the set: it loses a positive.
* **"Could not tell" reported as absent.** The inverse, and the way a sweep over a corpus
  labelled only to class manufactures a clean bill of health. `AGENTS.md` forbids designing any
  part of the pipeline so that a null is harder to see.
* **Refuting a category on evidence that does not refute it.** Absence has to be *established*,
  at the member's rank or a coarser one that genuinely excludes it. A record whose class is
  `Caudoviricetes` cannot be a `Cystoviridae`, and that inference has to hold in the right
  direction only.
* **`>1 accession` read as segmented.** The VMR lists several accessions for plenty of
  monopartite genomes, so the naive rule admits Adenoviridae, Poxviridae and Phycodnaviridae —
  an error in the admitting direction that would inflate every segmented count.
* **A taxonomy gap charged to the corpus.** A taxon the reference knows but does not place
  (`Dinodnavirus`) and a taxon it does not know at all are different findings, and neither is
  "the corpus labelled this too shallowly".
* **Summing satellite viruses with satellite nucleic acids.** D-187 keeps them apart because
  only one encodes a capsid, and a single satellite number would be the one a reader quotes.
"""

from __future__ import annotations

import pathlib

import pytest

from amazebio import ictv
from amazebio import problemtaxa as pt
from amazebio.conformance import parse_lineage_tag

# --------------------------------------------------------------------------------------
# A miniature VMR, carrying one row per case the predicates have to get right
# --------------------------------------------------------------------------------------

_LINEAGES = {
    # NCLDV: a giant-virus family with a full lineage, so lifting has something to lift.
    "Mimivirus bradfordmassiliense": dict(
        realm="Varidnaviria",
        kingdom="Bamfordvirae",
        phylum="Nucleocytoviricota",
        class_="Megaviricetes",
        order="Imitervirales",
        family="Mimiviridae",
        genus="Mimivirus",
    ),
    # Segmented, labelled: the case the rule must admit.
    "Cystovirus phi6": dict(
        realm="Riboviria",
        kingdom="Orthornavirae",
        phylum="Duplornaviricota",
        class_="Cystoviricetes",
        order="Mindivirales",
        family="Cystoviridae",
        genus="Cystovirus",
    ),
    # Monopartite but multi-accession: the case the rule must exclude.
    "Duck atadenovirus A": dict(
        realm="Varidnaviria",
        kingdom="Bamfordvirae",
        phylum="Preplasmiviricota",
        class_="Tectiliviricetes",
        order="Rowavirales",
        family="Adenoviridae",
        genus="Atadenovirus",
    ),
    # Phage, to stand in for the bulk of Evo 1's surviving component.
    "Escherichia virus T4": dict(
        realm="Duplodnaviria",
        kingdom="Heunggongvirae",
        phylum="Uroviricota",
        class_="Caudoviricetes",
        family="Straboviridae",
        genus="Tequatrovirus",
    ),
    # Satellite nucleic acid: no rank above family at all, exactly as the VMR has it.
    "Ageratum yellow vein Singapore alphasatellite": dict(
        family="Alphasatellitidae", genus="Ageyesisatellite"
    ),
    # Satellite virus: family-unassigned genus inside a realm.
    "Tobacco albetovirus 1": dict(realm="Riboviria", genus="Albetovirus"),
    # Known to the reference but placed at no rank above itself.
    "Heterocapsa circularisquama DNA virus 01": dict(genus="Dinodnavirus"),
}


def _exemplar(
    species: str, accessions: tuple[tuple[str | None, str], ...], row: int
) -> ictv.Exemplar:
    lineage = {("class" if k == "class_" else k): v for k, v in _LINEAGES[species].items()}
    lineage["species"] = species
    return ictv.Exemplar(
        species=species,
        lineage=lineage,
        accessions=accessions,
        coverage="Complete genome",
        host_source="",
        is_exemplar=True,
        row=row,
    )


@pytest.fixture
def checklist() -> pt.Checklist:
    rows = [
        _exemplar("Mimivirus bradfordmassiliense", ((None, "AY653733"),), 2),
        # Labelled segments -> Cystoviridae is segmented.
        _exemplar("Cystovirus phi6", (("L", "M17461"), ("M", "M17462"), ("S", "M12921")), 3),
        # Two accessions, no labels -> Adenoviridae must NOT be segmented.
        _exemplar("Duck atadenovirus A", ((None, "Y09598"), (None, "AC_000004")), 4),
        _exemplar("Escherichia virus T4", ((None, "AF158101"),), 5),
        _exemplar("Ageratum yellow vein Singapore alphasatellite", ((None, "AJ416153"),), 6),
        _exemplar("Tobacco albetovirus 1", ((None, "X02980"),), 7),
        _exemplar("Heterocapsa circularisquama DNA virus 01", ((None, "AB353464"),), 8),
    ]
    return pt.build_checklist(rows, reference="TEST")


def verdict(checklist: pt.Checklist, tag: str, category: pt.Category) -> pt.VerdictDetail:
    return checklist.verdict(parse_lineage_tag(tag).taxonomy, category)


# --------------------------------------------------------------------------------------
# The positive that a rank-only comparison loses
# --------------------------------------------------------------------------------------


def test_a_family_level_label_detects_a_phylum_level_category(checklist: pt.Checklist) -> None:
    """`f__Mimiviridae` is a giant virus even with no phylum field. This is the regression."""
    got = verdict(checklist, ";;;;;f__Mimiviridae;;", pt.Category.NCLDV)
    assert got.verdict is pt.Verdict.PRESENT
    assert got.matched == ("phylum", "Nucleocytoviricota")
    assert got.decided_at == "family"


@pytest.mark.parametrize(
    "tag",
    [
        "r__Varidnaviria;k__Bamfordvirae;p__Nucleocytoviricota;;;;;",
        ";;;;;f__Mimiviridae;;",
        ";;;;;;g__Mimivirus;",
        ";;;;;;;s__Mimivirus bradfordmassiliense",
    ],
)
def test_ncldv_is_found_at_every_rank_at_or_below_its_own(
    checklist: pt.Checklist, tag: str
) -> None:
    """A label at phylum or anywhere finer must find the category. Only coarser may not."""
    assert verdict(checklist, tag, pt.Category.NCLDV).verdict is pt.Verdict.PRESENT


def test_a_label_coarser_than_the_category_cannot_detect_it(checklist: pt.Checklist) -> None:
    """Varidnaviria holds both NCLDV and non-NCLDV phyla, so realm alone decides nothing."""
    got = verdict(checklist, "r__Varidnaviria;;;;;;;", pt.Category.NCLDV)
    assert got.verdict is pt.Verdict.UNLABELLED


# --------------------------------------------------------------------------------------
# Absence has to be established, and unlabelled must not drift into it
# --------------------------------------------------------------------------------------


def test_class_refutes_a_phylum_category_and_the_rank_is_recorded(
    checklist: pt.Checklist,
) -> None:
    """Evo 1's bulk case: class `Caudoviricetes` excludes NCLDV, so this is a measured zero."""
    got = verdict(checklist, ";;;;c__Caudoviricetes;;;", pt.Category.NCLDV)
    assert got.verdict is pt.Verdict.ABSENT
    assert got.decided_at == "class"


def test_class_does_not_settle_a_family_category(checklist: pt.Checklist) -> None:
    """The same record cannot answer a genus-keyed category. It must stay `UNLABELLED`."""
    got = verdict(checklist, ";;;;c__Caudoviricetes;;;", pt.Category.SATELLITE_VIRUS)
    assert got.verdict is pt.Verdict.UNLABELLED
    assert got.decided_at is None


def test_an_empty_label_is_unlabelled_for_every_category(checklist: pt.Checklist) -> None:
    """A record with no taxonomy is evidence of nothing, and says so for all four."""
    got = checklist.classify(parse_lineage_tag(";;;;;;;").taxonomy)
    assert {v.verdict for v in got.values()} == {pt.Verdict.UNLABELLED}
    assert {v.why for v in got.values()} == {"no taxonomic label at any rank"}


def test_absent_reports_the_finest_rank_it_needed(checklist: pt.Checklist) -> None:
    """`decided_at` is the label the zero rests on, so a reader can weigh it."""
    got = verdict(checklist, ";;;;;f__Straboviridae;;", pt.Category.SEGMENTED)
    assert got.verdict is pt.Verdict.ABSENT
    assert got.decided_at == "family"


# --------------------------------------------------------------------------------------
# The segment-label discriminator
# --------------------------------------------------------------------------------------


def test_labelled_segments_make_a_family_segmented(checklist: pt.Checklist) -> None:
    assert ("family", "Cystoviridae") in checklist.definition(pt.Category.SEGMENTED).members
    assert verdict(checklist, ";;;;;f__Cystoviridae;;", pt.Category.SEGMENTED).verdict is (
        pt.Verdict.PRESENT
    )


def test_unlabelled_multi_accession_does_not(checklist: pt.Checklist) -> None:
    """Adenoviridae is monopartite and lists two accessions. `>1` alone would admit it."""
    assert ("family", "Adenoviridae") not in checklist.definition(pt.Category.SEGMENTED).members
    assert verdict(checklist, ";;;;;f__Adenoviridae;;", pt.Category.SEGMENTED).verdict is (
        pt.Verdict.ABSENT
    )


def test_segmented_counts_species_the_rule_cannot_place(checklist: pt.Checklist) -> None:
    """A labelled multi-segment species with no family contributes to no set, and is counted."""
    rows = [
        _exemplar("Cystovirus phi6", (("L", "M17461"), ("M", "M17462")), 3),
        ictv.Exemplar(
            species="unplaced segmented sp.",
            lineage={"realm": "Riboviria", "species": "unplaced segmented sp."},
            accessions=(("RNA1", "AA000001"), ("RNA2", "AA000002")),
            coverage="Complete genome",
            host_source="",
            is_exemplar=True,
            row=9,
        ),
    ]
    built = pt.build_checklist(rows, reference="TEST")
    note = built.definition(pt.Category.SEGMENTED).note
    assert "1 labelled multi-segment species carry no family" in note


# --------------------------------------------------------------------------------------
# Satellites: two categories, never one
# --------------------------------------------------------------------------------------


def test_satellite_nucleic_acid_is_found_at_family(checklist: pt.Checklist) -> None:
    got = verdict(checklist, ";;;;;f__Alphasatellitidae;;", pt.Category.SATELLITE_NUCLEIC_ACID)
    assert got.verdict is pt.Verdict.PRESENT


def test_a_satellite_nucleic_acid_is_not_a_satellite_virus(checklist: pt.Checklist) -> None:
    """The two are disjoint. A sweep that summed them would report one satellite count."""
    tag = ";;;;;f__Alphasatellitidae;;"
    assert verdict(checklist, tag, pt.Category.SATELLITE_VIRUS).verdict is not pt.Verdict.PRESENT
    members = checklist.definition(pt.Category.SATELLITE_VIRUS).members
    assert ("family", "Alphasatellitidae") not in members


def test_satellite_virus_is_found_at_genus(checklist: pt.Checklist) -> None:
    got = verdict(checklist, ";;;;;;g__Albetovirus;", pt.Category.SATELLITE_VIRUS)
    assert got.verdict is pt.Verdict.PRESENT
    assert got.decided_at == "genus"


def test_ribozyviria_is_in_neither_satellite_category(checklist: pt.Checklist) -> None:
    """D-187's stated boundary, pinned so it cannot drift in silently."""
    for category in (pt.Category.SATELLITE_VIRUS, pt.Category.SATELLITE_NUCLEIC_ACID):
        names = {t for _, t in checklist.definition(category).members}
        assert "Kolmioviridae" not in names
        assert "Ribozyviria" not in names


# --------------------------------------------------------------------------------------
# Three ways of not knowing, kept apart
# --------------------------------------------------------------------------------------


def test_a_taxon_the_reference_does_not_know_says_so(checklist: pt.Checklist) -> None:
    got = verdict(checklist, ";;;;;;g__Totallymadeupvirus;", pt.Category.NCLDV)
    assert got.verdict is pt.Verdict.UNLABELLED
    assert got.why == "taxon_unknown_to_reference"


def test_a_taxon_the_reference_knows_but_does_not_place_says_so(
    checklist: pt.Checklist,
) -> None:
    """`Dinodnavirus` is a VMR genus with nothing above it. No phylum rule can reach it, and
    that is a gap in the taxonomy rather than in the corpus's labelling."""
    got = verdict(checklist, ";;;;;;g__Dinodnavirus;", pt.Category.NCLDV)
    assert got.verdict is pt.Verdict.UNLABELLED
    assert got.why == "taxon_unplaced_in_reference above phylum"


def test_a_truncated_label_is_not_called_unplaced(checklist: pt.Checklist) -> None:
    """A missing *finer* rank is truncation. Only a missing coarser one is unplaced.

    `Sarthroviridae` is absent from this miniature reference, so the satellite-virus category
    has a member that cannot be refuted at class — which is the same shape the real release
    produces for the segmented category, for the reason the next test pins.
    """
    got = verdict(checklist, ";;;;c__Caudoviricetes;;;", pt.Category.SATELLITE_VIRUS)
    assert got.verdict is pt.Verdict.UNLABELLED
    assert got.why.startswith("label stops above")
    assert "unplaced" not in got.why


# --------------------------------------------------------------------------------------
# Guards
# --------------------------------------------------------------------------------------


def test_an_empty_category_is_refused() -> None:
    """An empty member set would make every record absent and publish that as a result."""
    with pytest.raises(pt.ProblemTaxaError, match="no members"):
        pt.CategoryDefinition(category=pt.Category.NCLDV, members=frozenset(), species_count=0)


def test_a_member_at_an_unknown_rank_is_refused() -> None:
    with pytest.raises(pt.ProblemTaxaError, match="rank"):
        pt.CategoryDefinition(
            category=pt.Category.NCLDV,
            members=frozenset({("subphylum", "Nope")}),
            species_count=1,
        )


def test_an_empty_vmr_is_refused() -> None:
    with pytest.raises(pt.ProblemTaxaError, match="no exemplar rows"):
        pt.build_checklist([], reference="TEST")


@pytest.mark.parametrize(
    ("accession", "expected"),
    [
        ("IMGVR_UViG_GVMAG-M-2140918012-1_000001", True),
        ("IMGVR_UViG_GVMAG-S-3300000115-12_000001", True),
        ("IMGVR_UViG_3300027833_000001", False),
        ("", False),
    ],
)
def test_gvmag_accessions(accession: str, expected: bool) -> None:
    """IMG/VR's own giant-virus MAG marker, which survives an empty lineage column. Matched on
    the letter-agnostic infix so a release adding an assembly route is not silently uncounted."""
    assert pt.is_gvmag(accession) is expected


# --------------------------------------------------------------------------------------
# Against the real pinned release, when it has been staged
# --------------------------------------------------------------------------------------

_VMR = pathlib.Path(__file__).resolve().parent.parent / "data" / "ictv"


@pytest.mark.skipif(
    not (_VMR / ictv.release("MSL37.3").filename).exists(),
    reason="the pinned VMR is not staged in this checkout",
)
def test_the_pinned_release_yields_the_sets_d187_records() -> None:
    """D-187 quotes 7 NCLDV families, 48 segmented families and 216 satellite nucleic acid
    species. A later release changing them is A9.1's decay result, not a broken test — which is
    why this is pinned against the named release and skipped when it is absent."""
    vmr = ictv.read_vmr(_VMR / ictv.release("MSL37.3").filename)
    built = pt.build_checklist(vmr, reference="MSL37.3")

    assert len(built.definition(pt.Category.SEGMENTED).members) == 48
    assert built.definition(pt.Category.SEGMENTED).species_count == 1058
    assert built.definition(pt.Category.NCLDV).species_count == 149
    assert built.definition(pt.Category.SATELLITE_NUCLEIC_ACID).species_count == 216
    assert built.definition(pt.Category.SATELLITE_VIRUS).species_count == 7

    note = built.definition(pt.Category.NCLDV).note
    for family in ("Mimiviridae", "Poxviridae", "Iridoviridae", "Phycodnaviridae"):
        assert family in note

    segmented = {t for _, t in built.definition(pt.Category.SEGMENTED).members}
    assert {"Cystoviridae", "Orthomyxoviridae", "Geminiviridae"} <= segmented
    assert not {"Adenoviridae", "Poxviridae", "Phycodnaviridae"} & segmented


@pytest.mark.skipif(
    not (_VMR / ictv.release("MSL37.3").filename).exists(),
    reason="the pinned VMR is not staged in this checkout",
)
def test_a_class_label_refutes_ncldv_but_cannot_refute_segmented() -> None:
    """The asymmetry that decides how Evo 1's result reads, and it is not about the corpus.

    `c__Caudoviricetes` with nothing below it — 2,628,513 of Evo 1's surviving records — settles
    the giant-virus category outright, because every NCLDV family sits under a class that is not
    this one. It cannot settle the segmented category, because **three of that category's 48
    families are themselves unplaced above family in MSL37.3**: Birnaviridae, Polymycoviridae
    and Polydnaviriformidae have no phylum and no class, so no class-level label can exclude
    them. The limit is in the reference taxonomy, not in the corpus's labelling, and a sweep
    that refuted them anyway would report a zero it had not established.
    """
    vmr = ictv.read_vmr(_VMR / ictv.release("MSL37.3").filename)
    built = pt.build_checklist(vmr, reference="MSL37.3")
    taxonomy = parse_lineage_tag(";;;;c__Caudoviricetes;;;").taxonomy

    ncldv = built.verdict(taxonomy, pt.Category.NCLDV)
    assert ncldv.verdict is pt.Verdict.ABSENT
    assert ncldv.decided_at == "class"

    segmented = built.verdict(taxonomy, pt.Category.SEGMENTED)
    assert segmented.verdict is pt.Verdict.UNLABELLED

    unplaced = {
        taxon
        for rank, taxon in built.definition(pt.Category.SEGMENTED).members
        if not (built.ancestors.get((rank, taxon)) or {}).get("class")
    }
    assert unplaced == {"Birnaviridae", "Polymycoviridae", "Polydnaviriformidae"}
