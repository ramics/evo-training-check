"""A9.1's replay, on synthetic releases so the separations are pinned without 1.7 GB of dumps."""

from __future__ import annotations

import zipfile

import pytest

from amazebio import decay

NAMED = {"family": ["Picornaviridae", "Reoviridae"], "order": ["Picornavirales"]}
REALMS = ("Riboviria",)


def dump(tmp_path, date, nodes, names, merged=(), synonyms=(), with_merged=True):  # type: ignore[no-untyped-def]
    """Write a minimal dated dump. `nodes` is {taxid: (parent, rank)}."""
    path = tmp_path / f"taxdmp_{date}.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "nodes.dmp", "\n".join(f"{t}\t|\t{p}\t|\t{r}\t|" for t, (p, r) in nodes.items())
        )
        rows = [f"{t}\t|\t{n}\t|\t\t|\tscientific name\t|" for t, n in names.items()]
        rows += [f"{t}\t|\t{n}\t|\t\t|\tsynonym\t|" for n, t in synonyms]
        archive.writestr("names.dmp", "\n".join(rows))
        if with_merged:
            archive.writestr("merged.dmp", "\n".join(f"{o}\t|\t{n}\t|" for o, n in merged))
    return decay.Release.from_zip(path, date)


BASE_NODES = {
    1: (1, "no rank"),
    10239: (1, "superkingdom"),
    100: (10239, "realm"),
    200: (100, "order"),
    300: (200, "family"),
    400: (200, "family"),
}
BASE_NAMES = {
    1: "root",
    10239: "Viruses",
    100: "Riboviria",
    200: "Picornavirales",
    300: "Picornaviridae",
    400: "Reoviridae",
}


@pytest.fixture
def baseline(tmp_path):  # type: ignore[no-untyped-def]
    return decay.Baseline.of(dump(tmp_path, "2023-04-01", BASE_NODES, BASE_NAMES))


def test_a_name_that_became_a_synonym_of_another_rank_is_unreachable(tmp_path, baseline):  # type: ignore[no-untyped-def]
    nodes = {**BASE_NODES}
    del nodes[400]
    nodes[401] = (100, "order")  # Reoviridae is now Reovirales, an order
    names = {**BASE_NAMES}
    del names[400]
    names[401] = "Reovirales"
    later = dump(tmp_path, "2026-10-01", nodes, names, synonyms=[("Reoviridae", 401)])
    m = decay.measure(later, baseline, named=NAMED, realms=REALMS)
    assert [n for n, _ in m.unreachable_names] == ["Reoviridae"]
    assert m.unreachable_names[0][1] == "a order, not a family"


def test_a_renumbering_is_not_new_diversity(tmp_path, baseline):  # type: ignore[no-untyped-def]
    """NCBI retires a taxid by pointing it at its successor; reading nodes.dmp alone would
    report the successor as material the filter never covered."""
    nodes = {**BASE_NODES}
    del nodes[300]
    nodes[301] = (200, "family")
    names = {**BASE_NAMES}
    del names[300]
    names[301] = "Picornaviridae"
    later = dump(tmp_path, "2026-10-01", nodes, names, merged=[(300, 301)])
    m = decay.measure(later, baseline, named=NAMED, realms=REALMS)
    assert m.renumbered == 1
    assert m.new_not_named == 0
    assert m.new_named == 0


def test_a_new_family_outside_the_list_is_the_decay(tmp_path, baseline):  # type: ignore[no-untyped-def]
    nodes = {**BASE_NODES, 500: (100, "order"), 501: (500, "family")}
    names = {**BASE_NAMES, 500: "Newvirales", 501: "Newviridae"}
    later = dump(tmp_path, "2026-10-01", nodes, names)
    m = decay.measure(later, baseline, named=NAMED, realms=REALMS)
    assert m.new_not_named == 2
    assert m.new_named == 0


def test_a_new_genus_under_a_named_family_is_not_decay(tmp_path, baseline):  # type: ignore[no-untyped-def]
    nodes = {**BASE_NODES, 600: (300, "genus")}
    names = {**BASE_NAMES, 600: "Newvirus"}
    later = dump(tmp_path, "2026-10-01", nodes, names)
    m = decay.measure(later, baseline, named=NAMED, realms=REALMS)
    assert m.new_named == 1
    assert m.new_not_named == 0


def test_a_rename_that_moves_nothing_is_churn_not_decay(tmp_path, baseline):  # type: ignore[no-untyped-def]
    names = {**BASE_NAMES, 300: "Picornaviridae sensu lato"}
    later = dump(tmp_path, "2026-10-01", BASE_NODES, names)
    m = decay.measure(later, baseline, named=NAMED, realms=REALMS)
    assert m.renamed == 1
    assert m.new_not_named == 0
    # And the rename does cost reach, which is the point: the same taxon, no longer named.
    assert m.reach < len(baseline.viral)


def test_a_rerank_is_counted_apart_from_a_rename(tmp_path, baseline):  # type: ignore[no-untyped-def]
    nodes = {**BASE_NODES, 400: (200, "subfamily")}
    later = dump(tmp_path, "2026-10-01", nodes, BASE_NAMES)
    m = decay.measure(later, baseline, named=NAMED, realms=REALMS)
    assert m.reranked == 1
    assert m.renamed == 0


def test_a_taxon_that_became_viral_is_its_own_category(tmp_path, baseline):  # type: ignore[no-untyped-def]
    """It is neither new material nor churn: the baseline had it, outside the viral root."""
    base_nodes = {**BASE_NODES, 2: (1, "superkingdom"), 700: (2, "species")}
    base_names = {**BASE_NAMES, 2: "Bacteria", 700: "Something"}
    base = decay.Baseline.of(dump(tmp_path, "2023-04-01", base_nodes, base_names))
    nodes = {**base_nodes, 700: (300, "species")}
    later = dump(tmp_path, "2026-10-01", nodes, base_names)
    m = decay.measure(later, base, named=NAMED, realms=REALMS)
    assert m.reassigned_into_viral == 1
    assert m.new_not_named == 0


def test_the_computed_rule_follows_the_release_and_the_list_does_not(tmp_path, baseline):  # type: ignore[no-untyped-def]
    """The contrast §A9 asks for: a new family under a known realm is outside the static
    list and inside the rule that asks the release its own question."""
    nodes = {**BASE_NODES, 500: (100, "order"), 501: (500, "family")}
    names = {**BASE_NAMES, 500: "Newvirales", 501: "Newviridae"}
    later = dump(tmp_path, "2026-10-01", nodes, names)
    m = decay.measure(later, baseline, named=NAMED, realms=REALMS)
    assert m.computed_rule_reach == m.viral_taxa - 1  # everything but the viral root itself
    assert m.reach < m.computed_rule_reach


def test_a_dump_without_a_merge_table_says_so(tmp_path, baseline):  # type: ignore[no-untyped-def]
    later = dump(tmp_path, "2026-10-01", BASE_NODES, BASE_NAMES, with_merged=False)
    assert decay.measure(later, baseline, named=NAMED, realms=REALMS).has_merged_dmp is False


def test_reach_shares_are_over_the_release_not_the_baseline(tmp_path, baseline):  # type: ignore[no-untyped-def]
    nodes = {**BASE_NODES, 500: (100, "order")}
    names = {**BASE_NAMES, 500: "Newvirales"}
    later = dump(tmp_path, "2026-10-01", nodes, names)
    m = decay.measure(later, baseline, named=NAMED, realms=REALMS)
    assert m.reach_share == pytest.approx(m.reach / m.viral_taxa)
    assert m.viral_taxa == len(baseline.viral) + 1
