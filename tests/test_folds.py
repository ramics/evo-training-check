"""Tests for A2.2's fold universe and its reference structure set.

Two groups, and they guard different failures.

The universe tests guard the membership rule. D-166 established that selecting these folds one
level up imports lectins, adenylyl cyclases and bZIP transcription factors, and that regex over
family names matches a phage tail protein under HIV's envelope name. The rule that avoids all of
that is an enumerated list of exact family identifiers, so what has to be tested is that the
lists stay disjoint, stay exact, and stay separate from the identifiers D-169 deliberately
excluded — a family drifting from the excluded list into an included one is the regression that
would put peptide-N-glycanase back in the capsid reference set without anything failing.

The cutting tests guard the geometry. A reference domain is a residue range inside a chain, and
`foldseek createdb` makes one database entry per *chain*: the first build of this set turned 141
domains into 152 targets because each segment of a discontinuous domain got its own chain, which
quietly defeats D-167's target coverage floor. These tests pin one chain per domain.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from amazebio import folds

ROOT = Path(__file__).resolve().parent.parent


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def build_tool():
    return _load("build_fold_reference", "tools/build_fold_reference.py")


# --------------------------------------------------------------------------------------
# The membership rule
# --------------------------------------------------------------------------------------


def test_three_folds_with_distinct_ids():
    assert [f.fold_id for f in folds.FOLDS] == [
        "jelly_roll_capsid",
        "viral_rdrp",
        "class_i_fusion",
    ]


def test_no_family_belongs_to_two_folds():
    """A family in two folds would be one detection counted twice in A3.2's merge."""
    seen: dict[str, str] = {}
    for fold in folds.FOLDS:
        for fam in fold.families:
            assert fam not in seen, f"{fam} is in both {seen.get(fam)} and {fold.fold_id}"
            seen[fam] = fold.fold_id


def test_excluded_families_are_not_also_included():
    """The exclusions are the correction D-169 made; drifting back in is silent contamination."""
    included = {fam for fold in folds.FOLDS for fam in fold.families}
    for name, excluded in (
        ("cellular capsid", folds.EXCLUDED_CELLULAR_CAPSID),
        ("unnamed capsid", folds.EXCLUDED_UNNAMED_CAPSID),
        ("host RNAi", folds.EXCLUDED_HOST_RNAI),
    ):
        overlap = included & set(excluded)
        assert not overlap, f"{name} families also selected: {sorted(overlap)}"


def test_the_cellular_capsid_families_name_the_measured_ones():
    """Spot-check the exclusions that motivated D-169, by identifier rather than by count."""
    excluded = set(folds.EXCLUDED_CELLULAR_CAPSID)
    # Nucleoplasmin itself — the cellular protein ECOD's H-group is named "like".
    assert "10.2.1.31" in excluded
    # Peptide-N-glycanase, whose domain e1pgsA1 sits in the group's unnamed family.
    assert {"10.2.1.46", "10.2.1.47", "10.2.1.72"} <= excluded
    assert "10.2.1.0" in set(folds.EXCLUDED_UNNAMED_CAPSID)


def test_host_rnai_polymerases_are_excluded_from_rdrp():
    """D-166: a eukaryotic RNAi polymerase has the fold and is not viral-derived content."""
    rdrp = set(folds.VIRAL_RDRP)
    assert not rdrp & set(folds.EXCLUDED_HOST_RNAI)
    assert "3588.1.1.1" in set(folds.EXCLUDED_HOST_RNAI)


def test_rdrp_carries_both_halves_of_the_fold():
    """Palm and thumb are filed under two topologies; selecting one halves sensitivity."""
    palm = [f for f in folds.VIRAL_RDRP if f.startswith("304.48.")]
    thumb = [f for f in folds.VIRAL_RDRP if f.startswith("4967.1.1.")]
    assert palm and thumb


def test_fold_for_family_matches_exactly_not_by_prefix():
    """`10.2.1.1` and `10.2.1.10` are different families; a prefix test conflates them."""
    assert folds.fold_for_family("10.2.1.1").fold_id == "jelly_roll_capsid"
    assert folds.fold_for_family("10.2.1.100") is None  # DUF7154, excluded as cellular
    assert folds.fold_for_family("10.2.1") is None
    assert folds.fold_for_family("") is None


def test_curation_marks_the_fusion_class_as_this_project():
    """§A2's fusion class has no ECOD node; the write-up must be able to say so."""
    by_id = {f.fold_id: f for f in folds.FOLDS}
    assert by_id["class_i_fusion"].curation == "this_project"
    assert by_id["viral_rdrp"].curation != "this_project"


def test_duplicate_family_in_a_fold_is_refused():
    with pytest.raises(folds.FoldError, match="duplicate"):
        folds.Fold(fold_id="x", name="x", families=("1.1.1.1", "1.1.1.1"), curation="t", note="")


def test_the_pinned_release_carries_a_digest_not_a_versioned_url():
    """ECOD serves the current release under a moving filename, so the pin is version+digest."""
    assert folds.ECOD_V295_2.version == "v295.2"
    assert len(folds.ECOD_V295_2.sha256) == 64
    assert "latest" in folds.ECOD_V295_2.url


# --------------------------------------------------------------------------------------
# Reading the release
# --------------------------------------------------------------------------------------

HEADER = "\t".join(folds.REQUIRED_COLUMNS)


def _row(**kw) -> str:
    base = dict.fromkeys(folds.REQUIRED_COLUMNS, "")
    base.update(
        {
            "manual_rep": "True",
            "valid_structure": "True",
            "x_name": "jelly-roll",
            "h_name": "Nucleoplasmin-like/VP (viral coat and capsid proteins)",
        }
    )
    base.update(kw)
    return "\t".join(base[c] for c in folds.REQUIRED_COLUMNS)


def _write(tmp_path: Path, *rows: str) -> Path:
    p = tmp_path / "ecod.txt"
    p.write_text("# ECOD Domain List\n# Version: test\n" + HEADER + "\n" + "\n".join(rows) + "\n")
    return p


def test_iter_domains_refuses_a_header_missing_a_column(tmp_path):
    p = tmp_path / "ecod.txt"
    p.write_text("# c\nuid\tf_id\n0\t10.2.1.1\n")
    with pytest.raises(folds.FoldError, match="missing"):
        list(folds.iter_domains(p))


def test_reference_domains_verifies_the_digest(tmp_path):
    p = _write(tmp_path, _row(uid="1", ecod_domain_id="e1abcA1", f_id="10.2.1.1", pdb="1abc"))
    with pytest.raises(folds.FoldError, match="sha256"):
        folds.reference_domains(p)


def test_reference_domains_keeps_only_fetchable_representatives(tmp_path):
    p = _write(
        tmp_path,
        # kept
        _row(
            uid="1",
            ecod_domain_id="e1abcA1",
            f_id="10.2.1.1",
            pdb="1ABC",
            chain="A",
            pdb_range="A:1-99",
        ),
        # not a representative
        _row(
            uid="2",
            ecod_domain_id="e2abcA1",
            f_id="10.2.1.1",
            pdb="2abc",
            chain="A",
            pdb_range="A:1-99",
            manual_rep="False",
        ),
        # structure not valid
        _row(
            uid="3",
            ecod_domain_id="e3abcA1",
            f_id="10.2.1.1",
            pdb="3abc",
            chain="A",
            pdb_range="A:1-99",
            valid_structure="False",
        ),
        # no PDB entry (a predicted-model domain)
        _row(
            uid="4", ecod_domain_id="X4_nD1", f_id="10.2.1.1", pdb="", chain="A", pdb_range="1-99"
        ),
        # no range
        _row(
            uid="5", ecod_domain_id="e5abcA1", f_id="10.2.1.1", pdb="5abc", chain="A", pdb_range=""
        ),
        # family not in any fold
        _row(
            uid="6",
            ecod_domain_id="e6abcA1",
            f_id="10.2.1.31",
            pdb="6abc",
            chain="A",
            pdb_range="A:1-99",
        ),
    )
    got = folds.reference_domains(p, verify=False)
    assert [d.domain_id for d in got] == ["e1abcA1"]
    assert got[0].pdb == "1abc", "the PDB id is lower-cased for the download URL"
    assert got[0].fold_id == "jelly_roll_capsid"
    assert got[0].filename == "e1abcA1.cif"


def test_reference_domains_refuses_an_empty_selection(tmp_path):
    p = _write(tmp_path, _row(uid="1", ecod_domain_id="e1abcA1", f_id="10.2.1.31", pdb="1abc"))
    with pytest.raises(folds.FoldError, match="no reference domains"):
        folds.reference_domains(p, verify=False)


# --------------------------------------------------------------------------------------
# ECOD's range syntax
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("segment", "chain", "lo", "hi"),
    [
        ("A:1-99", "A", 1, 99),
        ("A:1B-99A", "A", 1, 99),  # insertion codes, kept inclusively
        ("1:1-134", "1", 1, 134),  # numeric chain names exist in viral assemblies
        ("L:87-165", "L", 87, 165),
        ("A:-5-99", "A", -5, 99),  # author numbering can start below 1
    ],
)
def test_segment_regex_parses_ecod_ranges(build_tool, segment, chain, lo, hi):
    m = build_tool.SEGMENT.match(segment)
    assert m is not None, segment
    assert m["chain"] == chain
    assert (int(m["lo"]), int(m["hi"])) == (lo, hi)


def test_segment_regex_rejects_nonsense(build_tool):
    for bad in ("A1-99", "A:", "A:x-99", ""):
        assert build_tool.SEGMENT.match(bad) is None, bad


# --------------------------------------------------------------------------------------
# Cutting a domain out of an entry
# --------------------------------------------------------------------------------------


@pytest.fixture
def entry(tmp_path):
    """A two-chain synthetic entry with author numbering 1..200, written as gzipped mmCIF."""
    import gzip

    import gemmi

    st = gemmi.Structure()
    st.name = "test"
    st.spacegroup_hm = "P 1"
    model = gemmi.Model("1")
    for chain_name in ("A", "B"):
        chain = gemmi.Chain(chain_name)
        for i in range(1, 201):
            res = gemmi.Residue()
            res.name = "ALA"
            res.seqid = gemmi.SeqId(i, " ")
            atom = gemmi.Atom()
            atom.name = "CA"
            atom.element = gemmi.Element("C")
            atom.pos = gemmi.Position(float(i), 0.0, 0.0)
            res.add_atom(atom)
            chain.add_residue(res)
        model.add_chain(chain)
    st.add_model(model)
    st.setup_entities()
    path = tmp_path / "test.cif.gz"
    path.write_bytes(gzip.compress(st.make_mmcif_document().as_string().encode()))
    return path


def _domain(**kw) -> folds.ReferenceDomain:
    base = {
        "uid": "1",
        "domain_id": "e1testA1",
        "fold_id": "jelly_roll_capsid",
        "family_id": "10.2.1.1",
        "family_name": "Rhv",
        "t_name": "t",
        "pdb": "test",
        "chain": "A",
        "pdb_range": "A:10-60",
    }
    base.update(kw)
    return folds.ReferenceDomain(**base)


def test_cut_takes_only_the_named_range(build_tool, entry, tmp_path):
    out = tmp_path / "cut"
    out.mkdir()
    got = build_tool.cut_domain(entry, _domain(pdb_range="A:10-60"), out)
    assert got["residues"] == 51
    import gemmi

    st = gemmi.read_structure(str(out / "e1testA1.cif"))
    assert [r.seqid.num for r in st[0]["A"]][:3] == [10, 11, 12]


def test_a_discontinuous_domain_stays_one_chain(build_tool, entry, tmp_path):
    """The regression that turned 141 domains into 152 foldseek targets."""
    import gemmi

    out = tmp_path / "cut"
    out.mkdir()
    got = build_tool.cut_domain(entry, _domain(pdb_range="A:10-20,A:100-120"), out)
    assert got["residues"] == 11 + 21
    st = gemmi.read_structure(str(out / "e1testA1.cif"))
    assert len(st[0]) == 1, "one chain per domain, whatever its segment count"
    nums = [r.seqid.num for r in st[0][0]]
    assert nums[:2] == [10, 11]
    assert 100 in nums and 21 not in nums, "the gap between segments is a numbering gap"


def test_a_domain_spanning_two_chains_is_refused(build_tool, entry, tmp_path):
    """Merging them would collide author residue numbers; none exist in this universe."""
    out = tmp_path / "cut"
    out.mkdir()
    with pytest.raises(build_tool.ReferenceError, match="spans chains"):
        build_tool.cut_domain(entry, _domain(pdb_range="A:10-60,B:10-60"), out)


def test_a_range_selecting_nothing_is_refused(build_tool, entry, tmp_path):
    """foldseek would accept a 0-residue target and it would match nothing, silently."""
    out = tmp_path / "cut"
    out.mkdir()
    with pytest.raises(build_tool.ReferenceError, match="selected no residues"):
        build_tool.cut_domain(entry, _domain(pdb_range="A:900-999"), out)


def test_a_missing_chain_is_refused(build_tool, entry, tmp_path):
    out = tmp_path / "cut"
    out.mkdir()
    with pytest.raises(build_tool.ReferenceError, match="no chain"):
        build_tool.cut_domain(entry, _domain(pdb_range="Z:10-60"), out)


def test_an_unparseable_range_is_refused(build_tool, entry, tmp_path):
    out = tmp_path / "cut"
    out.mkdir()
    with pytest.raises(build_tool.ReferenceError, match="cannot parse"):
        build_tool.cut_domain(entry, _domain(pdb_range="A10-60"), out)


# --------------------------------------------------------------------------------------
# The shipped manifest
# --------------------------------------------------------------------------------------


def test_universe_manifest_carries_the_rule_and_the_exclusions(build_tool):
    """D-166 requires the list to ship with the table; D-169 requires the exclusions with it."""
    body = build_tool.universe_manifest([_domain()])
    assert body["registry_version"] == "v295.2"
    assert body["registry_sha256"] == folds.ECOD_V295_2.sha256
    assert "enumerated identifier" in body["selection_level"]
    assert set(body["decisions"]) == {"D-166", "D-169"}
    assert [f["fold_id"] for f in body["folds"]] == [f.fold_id for f in folds.FOLDS]
    assert body["folds"][0]["families"] == list(folds.JELLY_ROLL_CAPSID)
    assert body["excluded"]["host_rnai_families"] == list(folds.EXCLUDED_HOST_RNAI)
    assert body["excluded"]["cellular_capsid_families"] == list(folds.EXCLUDED_CELLULAR_CAPSID)
