"""Reconstruct the Select Agents and Toxins List as a set of NCBI taxonomy ids.

ESM3-open's narrow denylist is described in one sentence — "all sequences in UniProt
belonging to organisms on the Select Agents and Toxins List" — and that sentence hides two
questions the source does not answer. *Which version* of the list, and *which taxa* its
entries name. Both are readings, both are recorded in DECISIONS.md — D-137 for the mapping,
D-138 for the version — and this module is where they are executed rather than assumed.

**Which version: the list is the regulation, not the webpage.** The model card links
`selectagents.gov/sat/list.htm`, which is a summary of three codified lists — 42 CFR 73.3 and
73.4 (HHS and overlap), 9 CFR 121.3 and 121.4 (veterinary services and overlap), and 7 CFR
331.3 (plant protection). The regulation is the authority and it has dated versions; the
webpage does not, beyond a review date. So this module pins the regulation, through eCFR's
dated full-text API, at a date inside the window the source's access date falls in.

That turns out to cost nothing, which is the useful part: none of the three parts was amended
between 2022-05-27 and 2024-12-17, so every date in 2023 and in 2024 up to that December
amendment resolves to identical text. The source's unstated version is an under-specification
(DESIGN.md §A0) whose consequence is measured and nil.

**What it would have cost to read the webpage instead is not nil.** The live page reflects the
December 2024 and January 2025 amendments, which delisted five organism entries that were in
force when the filter ran and widened a sixth from a species to its genus. A seed set built
from today's page would therefore be missing agents the filter was supposed to have removed,
which biases an audit of that filter toward finding it more complete than it was.

**Which taxa: name matching is not safe, so curation decides and the taxonomy validates.**
The list's entries are regulatory prose, not taxon names, and matching them against
`names.dmp` fails in several directions at once:

* **Toxins are molecules, not organisms.** Nine entries name a toxin. ESM3's sentence says
  "organisms", so the literal reading contributes no taxon for them, and the alternative —
  the producing organism — is a separate reading this module can switch on, because it is
  large enough to be worth measuring rather than choosing blind.
* **Some entries are constructs or predicates, not taxa at all.** A reconstructed 1918
  influenza virus, a SARS-CoV/SARS-CoV-2 chimera, and "botulinum neurotoxin producing species
  of Clostridium" have no node to point at; the last is a function over a genus.
* **Some names resolve to the wrong kingdom.** The sub-entries under "South American
  hemorrhagic fever viruses" are bare words, and in the 2023-04 taxonomy "Sabia" is a genus of
  flowering plants, "Chapare" matches an orchid, and "Junin" matches a grass mouse. Matching
  on name and taking descendants would pull a plant genus into a select-agent seed set.
* **Some names are not in the taxonomy under the name the regulation uses.** "Lassa fever
  virus", "Marburg virus", "Goat pox virus" and "Peste des petits ruminants virus" all need a
  synonym or a reclassified name, and the accented scientific name for the Junín virus means
  an ASCII match misses it entirely.
* **Two listed agents have no node in the pinned taxonomy whatsoever.** `Sclerophthora
  rayssiae` is absent, and `Coniothyrium glycines` exists only under the former name the
  regulation itself supplies parenthetically. That parenthetical is load-bearing, and where
  even it does not help, the agent cannot enter the seed set — a limit of the reconstruction
  rather than a choice within it, and reported as such.

So the mapping is a committed, hand-curated table (`policies/specs/`) in which every entry
names its kind, its chosen taxa and the reading behind them, and the pinned taxonomy is used
to *check* that table rather than to build it: that every id exists, and that every id for a
viral entry actually sits under Viruses. The plant-genus error class is a test failure here,
not a silent seed.
"""

from __future__ import annotations

import json
import re
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from amazebio.seeds import Taxonomy

#: NCBI taxonomy id of the Viruses superkingdom, as in `amazebio.seeds`.
VIRAL_ROOT = 10239

#: The sections of the Code of Federal Regulations that carry the list itself. Paragraph (b)
#: of each is the list; the other paragraphs are scope, exclusions and genetic-element rules.
LIST_SECTIONS = ("73.3", "73.4", "121.3", "121.4", "331.3")

#: Sections whose content duplicates another's. 9 CFR 121.4 and 42 CFR 73.4 are the same
#: overlap list promulgated by the two agencies, so counting both would double every overlap
#: agent. The HHS copy is kept because 42 CFR 73 is the part the HHS-only list also sits in.
DUPLICATE_SECTIONS = ("121.4",)


@dataclass(frozen=True)
class CfrPin:
    """One part of the Code of Federal Regulations, pinned by as-of date and checksum.

    eCFR serves a dated snapshot rather than a revision id, so `as_of` plus the digest is
    what makes the text reproducible. `effective` records the amendment actually in force at
    that date, which is the thing a reader needs: two different `as_of` dates inside one
    amendment window are the same list, and saying so is what makes the source's unstated
    version harmless.
    """

    title: int
    part: int
    as_of: str
    effective: str
    url: str
    sha256: str
    #: Size of the stored, decompressed XML. eCFR's full-text endpoint *requires*
    #: `Accept-Encoding` to permit compression — it answers 406 otherwise — so a transfer
    #: report of bytes-on-the-wire is the compressed length and about a fifth of the file.
    #: Recorded from the stored file, which is what a later reader can check.
    bytes: int

    @property
    def capture(self) -> str:
        return f"policies/captures/cfr-title{self.title}-part{self.part}-{self.as_of}.xml"


#: The three parts as of 2024-06-01 — inside the window the source's 2024 access date falls
#: in, and identical to every other date from 2022-05-27 to 2024-12-16.
PINS_2024 = (
    CfrPin(
        title=42,
        part=73,
        as_of="2024-06-01",
        effective="2022-05-27",
        url="https://www.ecfr.gov/api/versioner/v1/full/2024-06-01/title-42.xml?part=73",
        sha256="0cb258a904669ae9b82820b3f43b920dd1c4889f7eb9c70a5f11dc0993286378",
        bytes=105138,
    ),
    CfrPin(
        title=9,
        part=121,
        as_of="2024-06-01",
        effective="2018-09-24",
        url="https://www.ecfr.gov/api/versioner/v1/full/2024-06-01/title-9.xml?part=121",
        sha256="7072274aa13527438b3f58d6a6fafcea42c2186304b614c1e3fa0600be2c9175",
        bytes=96034,
    ),
    CfrPin(
        title=7,
        part=331,
        as_of="2024-06-01",
        effective="2019-03-26",
        url="https://www.ecfr.gov/api/versioner/v1/full/2024-06-01/title-7.xml?part=331",
        sha256="72db56fa4c7f09443b9866a34419ce4c7e201439e8433e5a76cdefe2955d4d78",
        bytes=67254,
    ),
)


class EntryKind(str, Enum):
    """What kind of thing a list entry names, which decides whether it has a taxon at all.

    The distinction is not cosmetic: `TOXIN`, `CONSTRUCT` and `PREDICATE` entries have no
    node to point at, so an implementation that assumed every entry resolves would either
    drop them silently or invent a taxon for them. Naming the kind makes the gap countable.
    """

    #: A taxon the regulation names directly, mapped to that taxon and its descendants.
    ORGANISM = "organism"
    #: A taxon below species rank, already a leaf — descendants add nothing.
    STRAIN = "strain"
    #: A toxin. A molecule, not an organism; see `include_toxin_producers`.
    TOXIN = "toxin"
    #: A laboratory construct — a reconstruction or a chimera. No node exists.
    CONSTRUCT = "construct"
    #: A functional predicate over a group ("...producing species of..."). Not a taxon.
    PREDICATE = "predicate"
    #: A heading whose operative content is the sub-entries beneath it.
    HEADING = "heading"
    #: Listed, but absent from the pinned taxonomy under any name the regulation gives.
    UNRESOLVABLE = "unresolvable"


@dataclass(frozen=True)
class ListEntry:
    """One entry of paragraph (b), as the regulation words it."""

    section: str
    ordinal: int
    text: str
    tier1: bool

    @property
    def key(self) -> str:
        """The mapping table's key: the entry text, normalised but not interpreted."""
        return normalise(self.text)


@dataclass(frozen=True)
class MappedEntry:
    """The reading taken for one list entry."""

    key: str
    kind: EntryKind
    taxids: tuple[int, ...]
    note: str
    #: Taxa for the producing organism, where the entry is a toxin. Not used unless the
    #: toxin-producer reading is switched on.
    producer_taxids: tuple[int, ...] = ()
    #: Set where a broader or narrower reading was available and declined, so the sensitivity
    #: can be run without re-deriving the alternative.
    alternative_taxids: tuple[int, ...] = ()
    #: Whether descending to this entry's children stays inside what the list names.
    #:
    #: Per-entry, not global, because the pinned taxonomy's shape does not match the
    #: regulation's. `Bacillus anthracis` has 47 strain children and every one of them is an
    #: organism on the list, so descent is right. `SARS coronavirus (SARS-CoV)` sits under a
    #: species node — "Severe acute respiratory syndrome-related coronavirus" — whose 222
    #: children include SARS-CoV-2, which the regulation pointedly does *not* list, so
    #: descent there would import the largest viral sequence space in UniProt on the strength
    #: of a node name. One global flag cannot express both.
    descend: bool = True


def normalise(text: str) -> str:
    """Collapse an entry to a stable key.

    Strips the Tier 1 asterisk, trailing punctuation, any `(n)` enumerator the 2025
    amendments added, and accents — so that the same agent keys identically across the two
    layouts the regulation has used. Case is preserved, because the regulation's own
    capitalisation distinguishes a genus from a common name.
    """
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"^\(\d+\)\s*", "", text)
    text = text.replace("*", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text.rstrip(".;,").strip()


def _element_text(el: ET.Element) -> str:
    """Flatten an element, dropping the subtrees in `PRUNED_TAGS`."""
    parts: list[str] = []
    if el.text:
        parts.append(el.text)
    for child in el:
        if child.tag not in PRUNED_TAGS:
            parts.append(_element_text(child))
        if child.tail:
            parts.append(child.tail)
    return "".join(parts)


def _text_nodes(div: ET.Element) -> list[str]:
    """Every paragraph of a section in document order, with pruned subtrees left out.

    Walks rather than using `iter`, because `iter` would descend into an `FTNT` and yield the
    footnote's own `P` as if it were a list entry.
    """
    out: list[str] = []

    def walk(el: ET.Element) -> None:
        for child in el:
            if child.tag in PRUNED_TAGS:
                continue
            if child.tag in ("P", "FP-1", "FP-2", "FP"):
                text = re.sub(r"\s+", " ", _element_text(child)).strip()
                if text:
                    out.append(text)
            walk(child)

    walk(div)
    return out


#: Subtrees whose text is never a list entry. `SU` is a superscript footnote reference, which
#: flattens onto an agent's name — `Rathayibacter toxicus;j` and `1 Peste des petits ruminants
#: virus` are both real cases in the 2024 text. `FTNT` is a footnote body, and the two parts
#: mark theirs differently: 42 CFR 73 leaves the marker as literal text, 9 CFR 121 puts it in
#: an `SU`. So a "paragraph starting with a digit" rule catches one part's footnotes and not
#: the other's, and a length rule discards 9 CFR 121.3's entire list, which is one
#: semicolon-separated paragraph longer than any footnote in the part. Pruning the subtrees
#: removes both problems structurally, which is why neither heuristic is here.
PRUNED_TAGS = ("SU", "FTNT")


def parse_list_entries(xml: bytes | str, section: str) -> tuple[ListEntry, ...]:
    """Extract paragraph (b) of one list section.

    Three layouts have to work, because the regulation has used all three and the pinned 2024
    text uses two of them side by side: one agent per flush paragraph (42 CFR 73, 7 CFR 331),
    semicolon-separated prose in a single paragraph (9 CFR 121), and the numbered form the
    December 2024 amendment introduced. The parser accepts all three rather than branching on
    the part, so a re-pin at another date does not need new code.
    """
    root = ET.fromstring(xml) if isinstance(xml, str) else ET.fromstring(xml.decode("utf-8"))
    div = next((d for d in root.iter("DIV8") if d.get("N") == section), None)
    if div is None:
        raise KeyError(f"section {section} not found")

    nodes = _text_nodes(div)

    try:
        start = next(i for i, t in enumerate(nodes) if t.startswith("(b)"))
    except StopIteration as exc:  # pragma: no cover - every list section has a (b)
        raise KeyError(f"section {section} has no paragraph (b)") from exc
    end = next((i for i, t in enumerate(nodes) if i > start and t.startswith("(c)")), len(nodes))

    block = list(nodes[start:end])
    block[0] = re.sub(r"^\(b\)[^:]*:\s*", "", block[0])

    entries: list[ListEntry] = []
    for text in block:
        if not text:
            continue
        for raw in text.split(";") if ";" in text else [text]:
            tier1 = "*" in raw
            key = normalise(raw)
            if not key or len(key) < 3:
                continue
            entries.append(ListEntry(section=section, ordinal=len(entries), text=key, tier1=tier1))
    return tuple(entries)


def parse_all(captures: Iterable[tuple[str, bytes]]) -> tuple[ListEntry, ...]:
    """Every list entry across the pinned parts, with the duplicated overlap list dropped."""
    out: list[ListEntry] = []
    for section, xml in captures:
        if section in DUPLICATE_SECTIONS:
            continue
        out.extend(parse_list_entries(xml, section))
    return tuple(out)


class NameIndex:
    """Scientific names and ancestry from a pinned taxonomy dump.

    `amazebio.seeds.Taxonomy` answers the descent question this module also needs, and is the
    class to use for it. What it does not carry is names or upward lineage, which are what
    validate a curated mapping — so this is the read-only companion for checking a table, not
    a second taxonomy.
    """

    __slots__ = ("names", "parent", "rank")

    def __init__(self, names: dict[int, str], parent: dict[int, int], rank: dict[int, str]) -> None:
        self.names = names
        self.parent = parent
        self.rank = rank

    @classmethod
    def from_taxdump_zip(cls, path: str | Path) -> NameIndex:
        names: dict[int, str] = {}
        parent: dict[int, int] = {}
        rank: dict[int, str] = {}
        with zipfile.ZipFile(path) as zf:
            with zf.open("names.dmp") as fh:
                for line in fh:
                    f = [c.strip() for c in line.decode("utf-8", "replace").split("\t|")]
                    if len(f) > 3 and f[3] == "scientific name":
                        names[int(f[0])] = f[1]
            with zf.open("nodes.dmp") as fh:
                for line in fh:
                    f = [c.strip() for c in line.decode().split("\t|")]
                    taxid = int(f[0])
                    parent[taxid] = int(f[1])
                    rank[taxid] = f[2]
        return cls(names, parent, rank)

    def lineage(self, taxid: int) -> Iterator[int]:
        """`taxid` and every ancestor up to the root, which is its own parent."""
        seen: set[int] = set()
        while taxid not in seen:
            seen.add(taxid)
            yield taxid
            nxt = self.parent.get(taxid)
            if nxt is None or nxt == taxid:
                return
            taxid = nxt

    def is_under(self, taxid: int, root: int) -> bool:
        return root in self.lineage(taxid)


def load_mapping(path: str | Path) -> dict[str, MappedEntry]:
    """Load the curated reading table."""
    raw = json.loads(Path(path).read_text())
    out: dict[str, MappedEntry] = {}
    for item in raw["entries"]:
        key = normalise(item["entry"])
        out[key] = MappedEntry(
            key=key,
            kind=EntryKind(item["kind"]),
            taxids=tuple(item.get("taxids", ())),
            note=item["note"],
            producer_taxids=tuple(item.get("producer_taxids", ())),
            alternative_taxids=tuple(item.get("alternative_taxids", ())),
            descend=bool(item.get("descend", True)),
        )
    return out


@dataclass(frozen=True)
class SeedTaxa:
    """The taxa one reading of the list names, split by whether descent is in scope.

    Two sets rather than one because the expansion is not uniform (see `MappedEntry.descend`),
    and because keeping them apart lets a run report how much of its seed set came from the
    list itself and how much from descending it — which an audit that names real labs will be
    asked for.
    """

    descend: frozenset[int]
    exact: frozenset[int]

    @property
    def named(self) -> frozenset[int]:
        return self.descend | self.exact

    def expand(self, taxonomy: Taxonomy) -> frozenset[int]:
        """Every taxon in scope, descending only the entries that permit it.

        One multi-root traversal rather than one per root. `Taxonomy.descendants` rebuilds the
        whole parent-to-children map on each call, which is the right trade for the viral arm
        — one root, so the map is built once — and the wrong one here, where there are more
        than fifty roots and the map is a few million entries. Building it once and walking
        every root through it is the same answer in about a fiftieth of the work.
        """
        children: dict[int, list[int]] = {}
        for child, parent in taxonomy.parent.items():
            if child != parent:
                children.setdefault(parent, []).append(child)

        out = set(self.exact)
        stack = list(self.descend)
        while stack:
            node = stack.pop()
            if node in out:
                continue
            out.add(node)
            stack.extend(children.get(node, ()))
        return frozenset(out)


def seed_taxa(
    entries: Iterable[ListEntry],
    mapping: dict[str, MappedEntry],
    *,
    include_toxin_producers: bool = False,
    use_alternatives: bool = False,
) -> SeedTaxa:
    """The taxa the list names, under one reading.

    `include_toxin_producers` switches the toxin reading from the literal one — ESM3 says
    "organisms", a toxin is not one — to the producing-organism one. `use_alternatives` takes
    the broader or narrower reading recorded against an entry where one was declined. Both
    exist so the sensitivity can be run rather than argued about, as D-107 did for coverage.

    An entry with no recorded reading is an error rather than a skip: the list is small and
    fixed, so an unmapped entry means the regulation was re-pinned at a date that added one,
    and silently dropping it would understate the denylist.
    """
    descend: set[int] = set()
    exact: set[int] = set()
    for entry in entries:
        mapped = mapping.get(entry.key)
        if mapped is None:
            raise KeyError(f"no recorded reading for list entry: {entry.key!r}")
        if mapped.kind is EntryKind.TOXIN:
            if include_toxin_producers:
                descend.update(mapped.producer_taxids)
            continue
        chosen = (
            mapped.alternative_taxids
            if use_alternatives and mapped.alternative_taxids
            else mapped.taxids
        )
        (descend if mapped.descend else exact).update(chosen)
    return SeedTaxa(frozenset(descend), frozenset(exact - descend))


def unresolved(
    entries: Iterable[ListEntry], mapping: dict[str, MappedEntry]
) -> tuple[MappedEntry, ...]:
    """Entries that contribute no taxon, which is a reported number and not a silent zero.

    An audit that says "the filter should have removed these agents" has to say which listed
    agents its own seed set could not represent. Four kinds cannot: toxins under the literal
    reading, constructs, functional predicates, and the two agents absent from the pinned
    taxonomy.
    """
    kinds = {EntryKind.TOXIN, EntryKind.CONSTRUCT, EntryKind.PREDICATE, EntryKind.UNRESOLVABLE}
    out = []
    for entry in entries:
        mapped = mapping.get(entry.key)
        if mapped is not None and mapped.kind in kinds:
            out.append(mapped)
    return tuple(out)


def expand_by_entry(
    entries: Iterable[ListEntry],
    mapping: dict[str, MappedEntry],
    taxonomy: Taxonomy,
    *,
    include_toxin_producers: bool = False,
    use_alternatives: bool = False,
) -> dict[str, frozenset[int]]:
    """The taxa each list entry contributes, separately rather than pooled.

    `seed_taxa` answers "which taxa does the list name", which is what builds a seed set.
    This answers "which entry did each of them come from", which is what lets a reconciliation
    say *where* a discrepancy lives instead of reporting one number that is out by a factor
    and cannot be decomposed. D-146 is the case that forced it: one entry contributed 98.5% of
    the expansion, and nothing in the pooled artefact could have shown that.

    Same reading and the same descent rules as `seed_taxa`, so the union over entries is the
    pooled set exactly — a test asserts it rather than trusting the two to stay in step. The
    children map is built once and walked per entry, for the reason `SeedTaxa.expand` gives.

    Entries contributing nothing are present with an empty set, because "this entry is not
    represented in the seed set" is the reported number `unresolved` exists for and a missing
    key reads as an oversight.
    """
    children: dict[int, list[int]] = {}
    for child, parent in taxonomy.parent.items():
        if child != parent:
            children.setdefault(parent, []).append(child)

    out: dict[str, frozenset[int]] = {}
    for entry in entries:
        mapped = mapping.get(entry.key)
        if mapped is None:
            raise KeyError(f"no recorded reading for list entry: {entry.key!r}")
        if mapped.kind is EntryKind.TOXIN:
            roots = mapped.producer_taxids if include_toxin_producers else ()
            descend = True
        else:
            roots = (
                mapped.alternative_taxids
                if use_alternatives and mapped.alternative_taxids
                else mapped.taxids
            )
            descend = mapped.descend
        if not descend:
            out[entry.key] = frozenset(roots)
            continue
        seen: set[int] = set()
        stack = list(roots)
        while stack:
            node = stack.pop()
            if node in seen:
                continue
            seen.add(node)
            stack.extend(children.get(node, ()))
        out[entry.key] = frozenset(seen)
    return out
