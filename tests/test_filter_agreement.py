"""A8.1's pass, end to end over a synthetic tier, and the refusals it carries."""

from __future__ import annotations

import gzip
import importlib.util
import json
import pathlib
import zipfile

import pytest

from amazebio import agreement

ROOT = pathlib.Path(__file__).resolve().parent.parent

# Enough of the real taxonomy for one record of each kind the cross-tab distinguishes.
NODES = [
    "1\t|\t1\t|\tno rank\t|",
    "10239\t|\t1\t|\tsuperkingdom\t|",
    "2559587\t|\t10239\t|\trealm\t|",  # Riboviria — a stop taxon
    "2732408\t|\t2559587\t|\tkingdom\t|",  # Orthornavirae
    "2732506\t|\t2732408\t|\tphylum\t|",  # Pisuviricota — a stop taxon
    "464095\t|\t2732506\t|\torder\t|",  # Picornavirales — denylisted order
    "12058\t|\t464095\t|\tfamily\t|",  # Picornaviridae — denylisted family
    "12283\t|\t464095\t|\tfamily\t|",  # Dicistroviridae — reached by the order rule only
    "2731619\t|\t10239\t|\tclass\t|",  # Caudoviricetes — viral, no realm assigned
    "2\t|\t1\t|\tsuperkingdom\t|",
    "562\t|\t2\t|\tspecies\t|",  # Escherichia coli
]
NAMES = [
    "1\t|\troot\t|\t\t|\tscientific name\t|",
    "10239\t|\tViruses\t|\t\t|\tscientific name\t|",
    "2559587\t|\tRiboviria\t|\t\t|\tscientific name\t|",
    "2732408\t|\tOrthornavirae\t|\t\t|\tscientific name\t|",
    "2732506\t|\tPisuviricota\t|\t\t|\tscientific name\t|",
    "464095\t|\tPicornavirales\t|\t\t|\tscientific name\t|",
    "12058\t|\tPicornaviridae\t|\t\t|\tscientific name\t|",
    "12283\t|\tDicistroviridae\t|\t\t|\tscientific name\t|",
    "2731619\t|\tCaudoviricetes\t|\t\t|\tscientific name\t|",
    "2\t|\tBacteria\t|\t\t|\tscientific name\t|",
    "562\t|\tEscherichia coli\t|\t\t|\tscientific name\t|",
]


@pytest.fixture
def tool():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location(
        "filter_agreement", ROOT / "tools" / "filter_agreement.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _stubs() -> tuple[list[str], list[str]]:
    """Every other name the real rules cite, as a stub node directly under Viruses.

    The predicate refuses a rule whose taxon the dump does not carry — deliberately, because
    a renamed taxon silently removing nothing is what A9.1 exists to measure — so a fixture
    cannot name a subset of the rules. These stubs carry no members and change no count; they
    exist so the test runs the *real* rule set rather than a convenient three of it.
    """
    from amazebio import policyspec

    policy = policyspec.load_policy_dir(ROOT / "policies" / "specs")["evo1-literal"]
    wanted: list[tuple[str, str]] = []
    for rule in policy.rules:
        if rule.kind == "remove_if_taxon_in":
            wanted += [(n, rule.params["rank"]) for n in rule.params["names"]]
        elif rule.kind == "remove_if_unspecific":
            wanted += [(n, "no rank") for n in rule.params["stop_taxa"]]
    have = {line.split("\t|\t")[1] for line in NAMES}
    nodes, names, taxid = [], [], 9000000
    for name, rank in wanted:
        if name in have:
            continue
        have.add(name)
        taxid += 1
        nodes.append(f"{taxid}\t|\t10239\t|\t{rank}\t|")
        names.append(f"{taxid}\t|\t{name}\t|\t\t|\tscientific name\t|")
    return nodes, names


@pytest.fixture
def taxdump(tmp_path):  # type: ignore[no-untyped-def]
    extra_nodes, extra_names = _stubs()
    path = tmp_path / "taxdmp.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("nodes.dmp", "\n".join(NODES + extra_nodes))
        archive.writestr("names.dmp", "\n".join(NAMES + extra_names))
    return path


def member(uniref100: str, taxid: int | None, *, representative: bool = False) -> str:
    tag = "representativeMember" if representative else "member"
    taxon = f'<property type="NCBI taxonomy" value="{taxid}"/>' if taxid is not None else ""
    return (
        f'<{tag}><dbReference type="UniProtKB ID" id="{uniref100}_X">'
        f'<property type="UniRef50 ID" value="UniRef50_Z"/>'
        f'<property type="UniRef100 ID" value="{uniref100}"/>'
        f"{taxon}</dbReference></{tag}>\n"
    )


def entry(cluster_id: str, members: str) -> bytes:
    return (
        f'<entry id="{cluster_id}" updated="2023-01-01">\n'
        f'<property type="common taxon ID" value="10239"/>\n'
        f"{members}"
    ).encode()


def tier_gz(path, entries: list[bytes]) -> None:  # type: ignore[no-untyped-def]
    doc = (
        b'<?xml version="1.0" encoding="UTF-8"?>\n'
        b'<UniRef90 releaseDate="2023-05-03" version="2023_02">\n'
        + b"</entry>\n".join(entries)
        + b"</entry>\n</UniRef90>\n"
    )
    with gzip.open(path, "wb") as fh:
        fh.write(doc)


def run(tool, taxdump, tmp_path, entries):  # type: ignore[no-untyped-def]
    source = tmp_path / "uniref90.xml.gz"
    tier_gz(source, entries)
    outdir = tmp_path / "out"
    code = tool.main(
        [
            "--tier",
            "uniref90",
            "--taxdump",
            str(taxdump),
            "--source",
            str(source),
            "--outdir",
            str(outdir),
            "--workers",
            "1",
            "--allow-dirty",
        ]
    )
    assert code == 0
    return json.loads((outdir / "agreement-2023_02-uniref90.json").read_text())


def test_the_pass_cross_tabulates_a_tier_end_to_end(tool, taxdump, tmp_path):  # type: ignore[no-untyped-def]
    payload = run(
        tool,
        taxdump,
        tmp_path,
        [
            # A denylisted virus, alone: both filters remove it.
            entry("UniRef90_1", member("UniRef100_P", 12058, representative=True)),
            # A phage with a cellular co-member: the similarity predicate reaches both, the
            # taxon rules reach neither — and the cellular one was never Evo's to judge.
            entry(
                "UniRef90_2",
                member("UniRef100_V", 2731619, representative=True) + member("UniRef100_C", 562),
            ),
            # An all-cellular cluster: out of scope, and no seed in sight.
            entry("UniRef90_3", member("UniRef100_C2", 562, representative=True)),
        ],
    )
    cells = payload["counts"]["cells"]
    # Caudoviricetes has no realm, so Evo's specificity rule removes it too: that is a
    # removal, not a disagreement, and its cluster covers a seed because it is one.
    assert cells[agreement.CELL_BOTH] == 2
    assert cells[agreement.CELL_LABEL_ONLY] == 0
    assert cells[agreement.CELL_SIMILARITY_ONLY] == 0
    # One cellular record rides in on the phage's cluster; the other is in a cluster of its
    # own and neither filter touches it.
    assert cells[agreement.CELL_OUT_OF_SCOPE_REMOVED] == 1
    assert cells[agreement.CELL_OUT_OF_SCOPE] == 1
    assert payload["counts"]["clusters"] == 3
    assert payload["counts"]["covering_clusters"] == 2
    assert payload["cellular_in_covering_clusters"] == 1
    assert payload["compressed_bytes_read"] > 0
    assert payload["decompressed_bytes_read"] > 0


def test_the_artefact_names_the_rules_it_could_not_run(tool, taxdump, tmp_path):  # type: ignore[no-untyped-def]
    payload = run(tool, taxdump, tmp_path, [entry("UniRef90_1", member("UniRef100_P", 12058))])
    skipped = {pair[0].split(":", 1)[1] for pair in payload["rules_not_runnable"]}
    assert "keep-high-confidence" in skipped
    assert "keep-one-per-votu" in skipped
    assert payload["readings"] == ["evo1-literal", "evo1-charitable", "evo1-strict"]
    assert payload["identity"] == 0.90


def test_the_confound_travels_in_the_output_not_only_the_paper(tool, taxdump, tmp_path):  # type: ignore[no-untyped-def]
    payload = run(tool, taxdump, tmp_path, [entry("UniRef90_1", member("UniRef100_P", 12058))])
    assert "measures the predicates and not the deployments" in payload["confound"]


def test_the_order_rule_is_reported_apart_from_the_family_rule(tool, taxdump, tmp_path):  # type: ignore[no-untyped-def]
    payload = run(
        tool,
        taxdump,
        tmp_path,
        [
            entry("UniRef90_1", member("UniRef100_P", 12058)),
            entry("UniRef90_2", member("UniRef100_D", 12283)),
        ],
    )
    assert payload["counts"]["rank_by_cell"][agreement.CELL_BOTH] == {
        "family": 1,
        "order": 1,
        "unspecific": 0,
    }


def test_a_reading_whose_taxon_rules_diverged_is_refused(tool, monkeypatch):  # type: ignore[no-untyped-def]
    from amazebio import policyspec

    policies = policyspec.load_policy_dir(ROOT / "policies" / "specs")
    strict = policies["evo1-strict"]
    rule = next(r for r in strict.rules if r.id == "remove-denylisted-families")
    object.__setattr__(rule, "params", {**rule.params, "names": ["Filoviridae"]})
    with pytest.raises(SystemExit, match="no longer share one set of taxon rules"):
        tool.taxon_rules(policies)
