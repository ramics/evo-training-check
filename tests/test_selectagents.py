"""Tests for the select-agent list reconstruction.

Two kinds here. Most run against the committed CFR captures and an inline fixture, so CI
exercises the parser and the reading table on every commit. The ones that need the 60 MB
pinned taxonomy skip when it is not staged — but they are the ones that matter most, because
they are what catches a curated taxon pointing at the wrong kingdom, so they are written to
run the moment the dump is present rather than left as a manual check.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from amazebio import selectagents as sa
from amazebio.seeds import Taxonomy

ROOT = Path(__file__).resolve().parent.parent
MAPPING = ROOT / "policies" / "specs" / "select-agents-2024-06-01.json"
TAXDUMP = ROOT / "data" / "taxdmp_2023-04-01.zip"

needs_taxonomy = pytest.mark.skipif(not TAXDUMP.exists(), reason="pinned taxonomy dump not staged")

#: Which capture each section is parsed out of. 121.4 is listed because the dedupe is part of
#: what is being tested: it must be dropped even when it is offered.
SECTION_CAPTURES = {
    "73.3": "cfr-title42-part73-2024-06-01.xml",
    "73.4": "cfr-title42-part73-2024-06-01.xml",
    "121.3": "cfr-title9-part121-2024-06-01.xml",
    "121.4": "cfr-title9-part121-2024-06-01.xml",
    "331.3": "cfr-title7-part331-2024-06-01.xml",
}


def capture(name: str) -> bytes:
    return (ROOT / "policies" / "captures" / name).read_bytes()


@pytest.fixture(scope="module")
def entries() -> tuple[sa.ListEntry, ...]:
    return sa.parse_all((section, capture(name)) for section, name in SECTION_CAPTURES.items())


@pytest.fixture(scope="module")
def mapping() -> dict[str, sa.MappedEntry]:
    return sa.load_mapping(MAPPING)


@pytest.fixture(scope="module")
def taxonomy() -> Taxonomy:
    return Taxonomy.from_taxdump_zip(TAXDUMP)


@pytest.fixture(scope="module")
def names() -> sa.NameIndex:
    return sa.NameIndex.from_taxdump_zip(TAXDUMP)


# --- the pinned captures match what they are pinned as -------------------------------------


def test_captures_match_their_recorded_digests() -> None:
    """Every pinned part is the bytes its digest says, or no result from it is reproducible."""
    import hashlib

    for pin in sa.PINS_2024:
        path = ROOT / pin.capture
        assert path.exists(), f"{pin.capture} is not stored"
        blob = path.read_bytes()
        assert hashlib.sha256(blob).hexdigest() == pin.sha256, pin.capture
        assert len(blob) == pin.bytes, pin.capture


# --- the parser ----------------------------------------------------------------------------


def test_every_section_yields_its_entries(entries: tuple[sa.ListEntry, ...]) -> None:
    """All four contributing sections parse, which the length heuristic used to prevent.

    9 CFR 121.3 is the regression that matters: its whole list is one semicolon-separated
    paragraph, longer than any footnote in the part, so a footnote rule based on length
    discarded the entire veterinary-services list while leaving 42 CFR 73 parsing perfectly.
    """
    by_section: dict[str, int] = {}
    for entry in entries:
        by_section[entry.section] = by_section.get(entry.section, 0) + 1
    assert by_section == {"73.3": 38, "73.4": 11, "121.3": 14, "331.3": 7}


def test_the_duplicated_overlap_list_is_dropped(entries: tuple[sa.ListEntry, ...]) -> None:
    """9 CFR 121.4 restates 42 CFR 73.4, so counting both doubles every overlap agent."""
    assert not [e for e in entries if e.section == "121.4"]
    assert "121.4" in SECTION_CAPTURES, "the dedupe is only tested if 121.4 was offered"


def test_footnote_bodies_do_not_become_entries(entries: tuple[sa.ListEntry, ...]) -> None:
    """A footnote is prose about an agent, not an agent.

    The two parts mark footnotes differently — 42 CFR 73 leaves the marker as literal text,
    9 CFR 121 wraps it in an `SU` — so a leading-digit rule catches one part's and not the
    other's. Both are pruned structurally instead.
    """
    for entry in entries:
        assert "intracerebral pathogenicity index" not in entry.text
        assert "Cysteine residues are all present" not in entry.text
        assert not entry.text[:1].isdigit(), entry.text


def test_footnote_markers_do_not_glue_onto_names(entries: tuple[sa.ListEntry, ...]) -> None:
    """The two real cases in the 2024 text, which a name match then fails on."""
    texts = {e.text for e in entries}
    assert "Rathayibacter toxicus" in texts, "trailing ';j' marker not stripped"
    assert "Peste des petits ruminants virus" in texts, "leading '1 ' marker not stripped"


def test_tier_one_agents_are_flagged(entries: tuple[sa.ListEntry, ...]) -> None:
    """The asterisk is a severity designation, and it must not survive into the key."""
    tier1 = {e.text for e in entries if e.tier1}
    assert "Yersinia pestis" in tier1
    assert "Coxiella burnetii" not in tier1
    assert not any("*" in e.text for e in entries)


def test_the_numbered_layout_parses_too() -> None:
    """The December 2024 amendment renumbered the lists, and a re-pin must not need new code."""
    xml = """<DIV1><DIV8 N="73.3" TYPE="SECTION"><HEAD>Sec. 73.3</HEAD>
      <P>(b) HHS select agents and toxins:</P>
      <FP-1>(1) Abrin.</FP-1>
      <FP-1>(2) Coxiella burnetii.<SU>1</SU></FP-1>
      <FTNT><P><SU>1</SU> A footnote that is not an agent.</P></FTNT>
      <P>(c) Genetic elements.</P>
    </DIV8></DIV1>"""
    parsed = sa.parse_list_entries(xml, "73.3")
    assert [e.text for e in parsed] == ["Abrin", "Coxiella burnetii"]


def test_paragraph_c_onwards_is_not_the_list() -> None:
    """Paragraph (c) regulates genetic elements, which are not organisms on the list."""
    xml = """<DIV1><DIV8 N="73.4" TYPE="SECTION"><HEAD>Sec. 73.4</HEAD>
      <P>(b) Overlap select agents and toxins:</P>
      <FP-1>Hendra virus</FP-1>
      <P>(c) Genetic Elements:</P>
      <FP-1>Nucleic acids that can produce infectious forms.</FP-1>
    </DIV8></DIV1>"""
    assert [e.text for e in sa.parse_list_entries(xml, "73.4")] == ["Hendra virus"]


def test_a_missing_section_is_an_error_not_an_empty_list() -> None:
    with pytest.raises(KeyError):
        sa.parse_list_entries("<DIV1><DIV8 N='73.3'><P>(b) x:</P></DIV8></DIV1>", "121.3")


# --- normalisation -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("(3) Botulinum neurotoxins.*", "Botulinum neurotoxins"),
        ("Bacillus anthracis *", "Bacillus anthracis"),
        ("*Foot-and-mouth disease virus;", "Foot-and-mouth disease virus"),
        ("Junín mammarenavirus", "Junin mammarenavirus"),
        ("  Ralstonia   solanacearum  ", "Ralstonia solanacearum"),
    ],
)
def test_normalise_makes_the_two_layouts_key_alike(raw: str, expected: str) -> None:
    assert sa.normalise(raw) == expected


def test_normalise_preserves_case() -> None:
    """The regulation's capitalisation is what separates a genus from a common name."""
    assert sa.normalise("Abrin") == "Abrin"


# --- the reading table ---------------------------------------------------------------------


def test_every_entry_has_a_recorded_reading(
    entries: tuple[sa.ListEntry, ...], mapping: dict[str, sa.MappedEntry]
) -> None:
    missing = sorted({e.key for e in entries} - set(mapping))
    assert not missing, f"list entries with no recorded reading: {missing}"


def test_the_table_has_no_entries_the_list_does_not(
    entries: tuple[sa.ListEntry, ...], mapping: dict[str, sa.MappedEntry]
) -> None:
    """An orphan reading means the regulation moved under the table and nobody noticed."""
    orphans = sorted(set(mapping) - {e.key for e in entries})
    assert not orphans, f"readings for entries not in the pinned list: {orphans}"


def test_an_unmapped_entry_raises_rather_than_being_skipped() -> None:
    """Silently dropping an entry would understate the denylist, which §2 forbids."""
    entry = sa.ListEntry(section="73.3", ordinal=0, text="Something newly listed", tier1=False)
    with pytest.raises(KeyError, match="no recorded reading"):
        sa.seed_taxa([entry], {})


def test_every_reading_carries_its_reasoning(mapping: dict[str, sa.MappedEntry]) -> None:
    """The table is the provenance of the whole arm; a bare taxid is not a reading."""
    for key, mapped in mapping.items():
        assert mapped.note.strip(), f"{key} has no recorded reasoning"


def test_entries_that_contribute_no_taxon_are_the_expected_kinds(
    entries: tuple[sa.ListEntry, ...], mapping: dict[str, sa.MappedEntry]
) -> None:
    """Toxins, constructs, predicates and absent taxa are counted, not silently zero."""
    from collections import Counter

    kinds = Counter(u.kind.value for u in sa.unresolved(entries, mapping))
    assert kinds == {"toxin": 9, "unresolvable": 4, "construct": 2, "predicate": 1}


def test_taxon_bearing_kinds_actually_carry_taxa(mapping: dict[str, sa.MappedEntry]) -> None:
    for key, mapped in mapping.items():
        if mapped.kind in (sa.EntryKind.ORGANISM, sa.EntryKind.STRAIN):
            assert mapped.taxids, f"{key} is an organism entry with no taxon"
        if mapped.kind in (sa.EntryKind.CONSTRUCT, sa.EntryKind.PREDICATE):
            assert not mapped.taxids, f"{key} is not a taxon but carries one"


# --- the readings, as switches -------------------------------------------------------------


def test_the_toxin_reading_is_a_switch(
    entries: tuple[sa.ListEntry, ...], mapping: dict[str, sa.MappedEntry]
) -> None:
    """ESM3 says "organisms", so the literal reading drops toxins; the producer reading does
    not, and the difference has to be measurable rather than argued."""
    literal = sa.seed_taxa(entries, mapping)
    producers = sa.seed_taxa(entries, mapping, include_toxin_producers=True)
    assert literal.named < producers.named
    ricinus = 3988
    assert ricinus not in literal.named
    assert ricinus in producers.named


def test_sars_cov_descent_is_refused(
    entries: tuple[sa.ListEntry, ...], mapping: dict[str, sa.MappedEntry]
) -> None:
    """The node that contains SARS-CoV also contains SARS-CoV-2, which is not listed.

    This is the single most consequential mapping call in the table: descending it would
    import the largest viral sequence space in UniProt and overstate what the filter should
    have removed. It belongs in the exact set, never the descend set.
    """
    sars_related = 694009
    taxa = sa.seed_taxa(entries, mapping)
    assert sars_related in taxa.exact
    assert sars_related not in taxa.descend


def test_expansion_descends_only_what_is_permitted() -> None:
    """A synthetic taxonomy, so the two paths are checked rather than inferred."""
    taxonomy = Taxonomy({1: 1, 10: 1, 11: 10, 20: 1, 21: 20})
    taxa = sa.SeedTaxa(descend=frozenset({10}), exact=frozenset({20}))
    assert taxa.expand(taxonomy) == frozenset({10, 11, 20})


def test_expansion_is_stable_under_a_cycle() -> None:
    """A malformed dump must not hang the pass."""
    taxonomy = Taxonomy({1: 1, 5: 6, 6: 5})
    assert sa.SeedTaxa(frozenset({5}), frozenset()).expand(taxonomy) == frozenset({5, 6})


# --- what the pinned taxonomy has to confirm ------------------------------------------------


@needs_taxonomy
def test_every_curated_taxon_exists_in_the_pinned_taxonomy(
    mapping: dict[str, sa.MappedEntry], names: sa.NameIndex
) -> None:
    absent = [
        (key, taxid)
        for key, mapped in mapping.items()
        for taxid in mapped.taxids + mapped.producer_taxids + mapped.alternative_taxids
        if taxid not in names.rank
    ]
    assert not absent, f"curated taxa absent from the pinned taxonomy: {absent}"


@needs_taxonomy
def test_no_viral_entry_is_mapped_outside_the_viruses(
    entries: tuple[sa.ListEntry, ...],
    mapping: dict[str, sa.MappedEntry],
    names: sa.NameIndex,
) -> None:
    """The plant-genus error class, as a test rather than as a near miss.

    `Sabia` is a genus of flowering plants under the scientific-name index, `Chapare` matches
    an orchid, `Junin` a grass mouse. A name-matching implementation would have seeded all
    three, and nothing else in this suite would have noticed.
    """
    strays = [
        (entry.text, taxid, names.names.get(taxid))
        for entry in entries
        if "virus" in entry.text.lower()
        for taxid in mapping[entry.key].taxids
        if not names.is_under(taxid, sa.VIRAL_ROOT)
    ]
    assert not strays, f"viral entries mapped outside the Viruses: {strays}"


@needs_taxonomy
def test_the_arenavirus_sub_entries_are_the_viruses_not_the_plants(
    mapping: dict[str, sa.MappedEntry], names: sa.NameIndex
) -> None:
    """Named explicitly, because these five are the reason curation decides the mapping.

    The pinned names are not uniform — four are "<name> mammarenavirus" and Sabia's
    scientific name is "Sabia virus", with "Sabia mammarenavirus" only an equivalent name — so
    the assertion is that each taxon is the virus of that name and is not the homonym a name
    match would have found.
    """
    keys = ("Chapare", "Guanarito", "Junin", "Machupo", "Sabia")
    taxa = {}
    for key in keys:
        (taxid,) = mapping[key].taxids
        assert names.is_under(taxid, sa.VIRAL_ROOT), key
        taxa[key] = taxid

    # Lineage, not name. Checking that the taxon's name contains the regulation's word is the
    # very assumption this module exists to refute: Junin's pinned scientific name is
    # "Argentinian mammarenavirus" and Sabia's is "Sabia virus", so four of the five fail a
    # name test while being exactly right. What they do share is the arenavirus lineage.
    ancestries = [set(names.lineage(taxid)) for taxid in taxa.values()]
    shared = set.intersection(*ancestries) - {1, sa.VIRAL_ROOT}
    assert any(
        "arenavir" in (names.names.get(anc) or "").lower() for anc in shared
    ), f"the five sub-entries share no arenavirus ancestor: {taxa}"

    sabia_the_plant_genus = 13663
    assert taxa["Sabia"] != sabia_the_plant_genus
    assert not names.is_under(sabia_the_plant_genus, sa.VIRAL_ROOT)


@needs_taxonomy
def test_the_declared_taxonomy_is_the_one_the_table_was_built_against(
    mapping: dict[str, sa.MappedEntry],
) -> None:
    declared = json.loads(MAPPING.read_text())["taxonomy"]
    assert declared == TAXDUMP.name


@needs_taxonomy
def test_expansion_runs_once_rather_than_once_per_root(
    entries: tuple[sa.ListEntry, ...],
    mapping: dict[str, sa.MappedEntry],
    taxonomy: Taxonomy,
) -> None:
    """Fifty-three roots against a few million nodes, so a per-root rebuild is quadratic.

    This is a correctness test with a timing assertion attached rather than a benchmark: the
    bound is loose enough to pass on a slow machine and tight enough to fail if the per-root
    rebuild comes back.
    """
    import time

    taxa = sa.seed_taxa(entries, mapping)
    started = time.monotonic()
    expanded = taxa.expand(taxonomy)
    elapsed = time.monotonic() - started
    assert expanded >= taxa.named
    assert elapsed < 30, f"expansion took {elapsed:.0f}s; per-root rebuild is back"


# --- Per-entry expansion (D-146) -------------------------------------------------------


def test_expand_by_entry_keeps_entries_apart_and_respects_each_descent_flag() -> None:
    """Descent is per-entry, so a pooled walk cannot be split up after the fact."""
    nodes = "\n".join(
        [
            "1\t|\t1\t|\tno rank\t|",
            "10\t|\t1\t|\tspecies\t|",
            "11\t|\t10\t|\tstrain\t|",
            "20\t|\t1\t|\tspecies\t|",
            "21\t|\t20\t|\tstrain\t|",
        ]
    )
    taxonomy = Taxonomy.from_nodes_dmp(nodes.splitlines())
    entries = (
        sa.ListEntry(section="73.3", ordinal=1, text="Descending agent", tier1=False),
        sa.ListEntry(section="73.3", ordinal=2, text="Exact agent", tier1=False),
    )
    mapping = {
        entries[0].key: sa.MappedEntry(
            key=entries[0].key, kind=sa.EntryKind.ORGANISM, taxids=(10,), note="", descend=True
        ),
        entries[1].key: sa.MappedEntry(
            key=entries[1].key, kind=sa.EntryKind.ORGANISM, taxids=(20,), note="", descend=False
        ),
    }
    by_entry = sa.expand_by_entry(entries, mapping, taxonomy)
    assert by_entry[entries[0].key] == {10, 11}
    assert by_entry[entries[1].key] == {20}


def test_an_entry_contributing_nothing_is_present_and_empty() -> None:
    """A missing key reads as an oversight; an empty set is the reported finding."""
    taxonomy = Taxonomy.from_nodes_dmp(["1\t|\t1\t|\tno rank\t|"])
    entry = sa.ListEntry(section="73.3", ordinal=1, text="Abrin", tier1=False)
    mapping = {
        entry.key: sa.MappedEntry(
            key=entry.key,
            kind=sa.EntryKind.TOXIN,
            taxids=(),
            note="",
            producer_taxids=(1,),
        )
    }
    assert sa.expand_by_entry([entry], mapping, taxonomy) == {entry.key: frozenset()}
    producers = sa.expand_by_entry([entry], mapping, taxonomy, include_toxin_producers=True)
    assert producers == {entry.key: frozenset({1})}


def test_an_unmapped_entry_is_an_error_here_too() -> None:
    """Same refusal as `seed_taxa`: a re-pin that adds an entry must not silently drop it."""
    taxonomy = Taxonomy.from_nodes_dmp(["1\t|\t1\t|\tno rank\t|"])
    entry = sa.ListEntry(section="73.3", ordinal=1, text="Something new", tier1=False)
    with pytest.raises(KeyError):
        sa.expand_by_entry([entry], {}, taxonomy)


@needs_taxonomy
def test_the_per_entry_expansion_unions_to_the_pooled_one_exactly(
    entries: tuple[sa.ListEntry, ...], mapping: dict[str, sa.MappedEntry], taxonomy: Taxonomy
) -> None:
    """The decomposition has to be *of* the seed set, not merely near it.

    Two functions walking the taxonomy separately is exactly the arrangement that drifts, and
    a reconciliation built on a decomposition that no longer sums to the measurement would be
    worse than no decomposition at all.
    """
    for toxins, alternatives in ((False, False), (True, False), (False, True)):
        pooled = sa.seed_taxa(
            entries, mapping, include_toxin_producers=toxins, use_alternatives=alternatives
        ).expand(taxonomy)
        by_entry = sa.expand_by_entry(
            entries,
            mapping,
            taxonomy,
            include_toxin_producers=toxins,
            use_alternatives=alternatives,
        )
        assert frozenset().union(*by_entry.values()) == pooled


@needs_taxonomy
def test_one_entry_carries_almost_the_whole_expansion(
    entries: tuple[sa.ListEntry, ...], mapping: dict[str, sa.MappedEntry], taxonomy: Taxonomy
) -> None:
    """D-146's finding, pinned as a measurement rather than left in a decision entry.

    The avian influenza entry reads onto Influenza A entire, which is the most heavily
    sequenced thing on the list by a wide margin. If a re-pin or a re-reading ever changes
    that, this test is where it should be noticed — the figure drives both the reconciliation
    and the cost of the pass that follows it.
    """
    by_entry = sa.expand_by_entry(entries, mapping, taxonomy)
    largest = max(by_entry.items(), key=lambda kv: len(kv[1]))
    total = len(frozenset().union(*by_entry.values()))
    assert "influenza" in largest[0].lower()
    assert len(largest[1]) / total > 0.95
