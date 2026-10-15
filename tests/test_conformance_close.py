"""End-to-end tests for A7.2: a synthetic IMG/VR release through both passes and both arms.

The expensive pass and the diff are tested together here, against a release small enough to
count by hand, because the failure that matters is not a crash in either one — it is a number
that is plausible and wrong. Five things are constructed to be wrong in a specific way if the
code is wrong in a specific way:

* a classification with **one** prokaryotic host finding and one with **two**, which is the
  published threshold and the difference between the host rule working and the host rule being
  a no-op;
* a classification whose records carry **no host prediction at all** and whose *classification*
  has two findings, which is the case the whole classification-level unit exists for (D-058) and
  which a per-record reading silently removes;
* a classification with eukaryotic host evidence *and* two prokaryotic findings, which is the
  only construction on which the three readings of the policy disagree — the literal reading
  keeps it, the charitable reading removes it on one strike, the strict reading removes it for
  not being exclusive;
* a **vOTU whose high-confidence records disagree about taxonomy**, which is the width of the
  retained interval and the one case where an input order nobody published changes the answer;
* a released record that is **not high-confidence** and one from a **denylisted family**, so the
  forward direction has to attribute two different rules rather than one.

The numbers below are worked out from the fixture, not copied from a run.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib

import pytest

from amazebio import conformance as cf

TOOLS = pathlib.Path(__file__).resolve().parent.parent / "tools"


def _load_tool(name: str):
    spec = importlib.util.spec_from_file_location(f"{name}_under_test", TOOLS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def scan_tool():
    return _load_tool("imgvr_conformance_scan")


@pytest.fixture(scope="module")
def close_tool():
    return _load_tool("conformance_close")


# --------------------------------------------------------------------------------------
# The synthetic release
# --------------------------------------------------------------------------------------

PHAGE = "r__Duplodnaviria;k__Heunggongvirae;p__Uroviricota;c__Caudoviricetes;;;;"
#: Survives every rule, and its records carry no host prediction of their own: the population
#: D-058 says 89.5% of Evo 1's retained records sit in.
HOSTLESS = "r__Duplodnaviria;k__Heunggongvirae;p__Uroviricota;c__Caudoviricetes;o__Crassvirales;;;"
#: One prokaryotic finding only. The published threshold is two, so the host rule removes it.
SINGLETON = "r__Duplodnaviria;k__Heunggongvirae;p__Uroviricota;c__Caudoviricetes;;f__Kyanoviridae;;"
#: Denylisted family.
CORONA = (
    "r__Riboviria;k__Orthornavirae;p__Pisuviricota;c__Pisoniviricetes;"
    "o__Nidovirales;f__Coronaviridae;;"
)
#: No assigned realm: removed by the unspecificity rule under every reading.
NO_REALM = ";;;;;f__Fuselloviridae;;"
#: Two prokaryotic findings *and* eukaryotic evidence. The only row the readings disagree about.
MIXED_HOST = (
    "r__Monodnaviria;k__Sangervirae;p__Phixviricota;c__Malgrandaviricetes;"
    "o__Petitvirales;f__Microviridae;;"
)

BACT = "d__Bacteria;p__Proteobacteria;c__Gammaproteobacteria"
BACT2 = "d__Bacteria;p__Bacillota;c__Bacilli"
ARCH = "d__Archaea;p__Thermoproteota"
EUK = "d__Eukaryota;p__Chordata"
NONE = ";;;;;;"

#: `(uvig, votu, confidence, classification, host)`. Hand-built so every count below can be
#: checked by reading the table.
ROWS = [
    # PHAGE: two prokaryotic findings, four records, three of them high-confidence over two
    # vOTUs — so one vOTU holds two high-confidence records of the same classification, which
    # must not widen the interval.
    ("IMGVR_UViG_1000000001_000001", "vOTU_00000001", "High-confidence", PHAGE, BACT),
    ("IMGVR_UViG_1000000002_000001", "vOTU_00000001", "High-confidence", PHAGE, ARCH),
    ("IMGVR_UViG_1000000003_000001", "vOTU_00000002", "High-confidence", PHAGE, NONE),
    ("IMGVR_UViG_1000000004_000001", "vOTU_00000003", "Putative", PHAGE, NONE),
    # HOSTLESS: no record carries a host, but the classification has two findings via the host
    # table alone. Two high-confidence records over two vOTUs.
    ("IMGVR_UViG_1000000005_000001", "vOTU_00000004", "High-confidence", HOSTLESS, NONE),
    ("IMGVR_UViG_1000000006_000001", "vOTU_00000005", "High-confidence", HOSTLESS, NONE),
    # SINGLETON: one prokaryotic finding. Removed by the host rule in every reading.
    ("IMGVR_UViG_1000000007_000001", "vOTU_00000006", "High-confidence", SINGLETON, BACT),
    # CORONA: denylisted family. Given two prokaryotic findings deliberately — the published
    # order puts the host rule *before* the denylists, so a classification with no host evidence
    # never reaches them and the denylist rule would never be the acting rule in this fixture.
    ("IMGVR_UViG_1000000008_000001", "vOTU_00000007", "High-confidence", CORONA, BACT),
    # NO_REALM: removed by the unspecificity rule, and for the same reason given two findings.
    ("IMGVR_UViG_1000000009_000001", "vOTU_00000008", "High-confidence", NO_REALM, BACT),
    # MIXED_HOST: two prokaryotic findings and one eukaryotic.
    ("IMGVR_UViG_1000000010_000001", "vOTU_00000009", "High-confidence", MIXED_HOST, BACT),
    ("IMGVR_UViG_1000000011_000001", "vOTU_00000009", "High-confidence", MIXED_HOST, BACT2),
    ("IMGVR_UViG_1000000012_000001", "vOTU_00000010", "High-confidence", MIXED_HOST, EUK),
    # A vOTU whose high-confidence records disagree about taxonomy: one surviving
    # classification, one removed. This is the entire width of the retained interval.
    ("IMGVR_UViG_1000000013_000001", "vOTU_00000011", "High-confidence", PHAGE, BACT),
    ("IMGVR_UViG_1000000014_000001", "vOTU_00000011", "High-confidence", CORONA, BACT2),
    ("IMGVR_UViG_1000000016_000001", "vOTU_00000013", "High-confidence", NO_REALM, BACT2),
    # A giant-virus MAG accession, which does not pack and must survive both joins anyway.
    (
        "IMGVR_UViG_GVMAG-M-2140918012-1_000001",
        "vOTU_00000012",
        "High-confidence",
        PHAGE,
        BACT,
    ),
]

SEQ_HEADER = [
    "UVIG",
    "Taxon_oid",
    "Scaffold_oid",
    "Coordinates ('whole' if the UViG is the entire contig)",
    "Ecosystem classification",
    "vOTU",
    "Length",
    "Topology",
    "geNomad score",
    "Confidence",
    "Estimated completeness",
    "Estimated contamination",
    "MIUViG quality",
    "Gene content (total genes;cds;tRNA;geNomad marker)",
    "Taxonomic classification",
    "Taxonomic classification method",
    "Host taxonomy prediction",
    "Host prediction method",
    "Sequence origin (doi)",
]
HOST_HEADER = ["UVIG", "Prediction method", "Host taxonomy prediction"]


def _seq_table() -> bytes:
    lines = ["\t".join(SEQ_HEADER)]
    for uvig, votu, confidence, classification, host in ROWS:
        row = [""] * len(SEQ_HEADER)
        row[0], row[5], row[9] = uvig, votu, confidence
        row[14], row[16] = classification, host
        lines.append("\t".join(row))
    return ("\n".join(lines) + "\n").encode()


def _host_table() -> bytes:
    lines = ["\t".join(HOST_HEADER)]
    for uvig, _votu, _confidence, _classification, host in ROWS:
        lines.append("\t".join([uvig, "k-mer match" if host != NONE else "", host]))
    # HOSTLESS carries no host of its own on either record, and its *classification* is still
    # found in a prokaryotic host twice — through extra predictions in this table. That is the
    # join the published rule describes and the one a per-record reading cannot make.
    lines.append("\t".join(["IMGVR_UViG_1000000005_000001", "CRISPR spacer match", BACT]))
    lines.append("\t".join(["IMGVR_UViG_1000000006_000001", "CRISPR spacer match", BACT2]))
    return ("\n".join(lines) + "\n").encode()


@pytest.fixture(scope="module")
def scan(scan_tool):
    """Run the real sharded pass over the synthetic release, in several shards."""
    import numpy as np
    from conftest import FakeS3

    seq, host = _seq_table(), _host_table()

    # The shard functions build their own client from `objectstore.client()`, so that is the
    # one seam to patch: everything else — the line splitting, the shard contract, the parsing
    # — is the production path.
    def run_shards(body, fn, header, *extra):
        out = []
        for start, end in scan_tool.objectstore.byte_shards(len(body), 3):
            client = FakeS3(body)
            scan_tool.objectstore.client = lambda c=client: c
            out.append(fn("b", "k", start, end, header, *extra))
        return out

    original = scan_tool.objectstore.client
    try:
        seq_shards = run_shards(seq, scan_tool._scan_seq_shard, SEQ_HEADER, None)
        host_shards = run_shards(host, scan_tool._scan_host_shard, HOST_HEADER)
    finally:
        scan_tool.objectstore.client = original

    from amazebio import imgvr

    evo2 = np.array(
        sorted({imgvr.uvig_join_key(uvig) for uvig in RELEASED_BY_EVO2}), dtype=np.int64
    )
    doc = scan_tool.merge(seq_shards, host_shards, evo2)
    doc["release"] = "2022-09-20"
    doc["version"] = "v4"
    doc["partial"] = False
    return doc


#: What the synthetic Evo 2 release contains. Deliberately imperfect against the predicate: a
#: non-high-confidence record, a denylisted-family record, two records from one vOTU, and one
#: predicted survivor left out entirely.
RELEASED_BY_EVO2 = [
    "IMGVR_UViG_1000000001_000001",  # PHAGE, hc — and its vOTU's second record is below
    "IMGVR_UViG_1000000002_000001",  # PHAGE, hc, same vOTU: two records from one vOTU
    "IMGVR_UViG_1000000004_000001",  # PHAGE, Putative: fails the high-confidence gate
    "IMGVR_UViG_1000000005_000001",  # HOSTLESS, hc: a retained record with no host of its own
    "IMGVR_UViG_1000000008_000001",  # CORONA, hc: denylisted family
    "IMGVR_UViG_GVMAG-M-2140918012-1_000001",  # the accession shape that does not pack
    # vOTU_00000005 (HOSTLESS) is predicted to survive and is absent: the converse direction.
]

#: Evo 1's released component, as a lineage histogram. `PHAGE` is released in more copies than
#: it has vOTUs to represent, which is the deduplication rule failing; `CORONA` is released at
#: all, which is a record-level rule failing.
RELEASED_BY_EVO1 = {PHAGE: 9, CORONA: 2, HOSTLESS: 1}


# --------------------------------------------------------------------------------------
# The pass
# --------------------------------------------------------------------------------------


def test_the_pass_counts_every_record_once_across_shards(scan):
    assert scan["records"] == len(ROWS)
    assert scan["records_high_confidence"] == sum(1 for r in ROWS if r[2] == "High-confidence")
    assert scan["malformed_rows"] == 0
    assert scan["confidence"]["Putative"] == 1


def test_the_giant_virus_accession_is_carried_rather_than_dropped(scan):
    shapes = scan["accession_shapes"]
    assert shapes["non_packable_accessions"] == 1
    assert shapes["join_key_injective_on_non_packable"] is True
    assert shapes["unreadable_accessions"] == 0


def test_host_findings_are_counted_over_the_classification_and_joined_back(scan):
    # The unit D-058 settles. HOSTLESS has two records, neither carrying a host prediction, and
    # its classification has two prokaryotic findings through the host table. A per-record
    # reading would give it zero.
    hostless = scan["by_classification"][HOSTLESS]
    assert hostless["seq_column_host"] == {"none": 2}
    assert hostless["host_findings"]["prokaryotic"][cf.HostUnit.RECORDS.value] == 2
    assert (
        scan["by_classification"][SINGLETON]["host_findings"]["prokaryotic"][
            cf.HostUnit.RECORDS.value
        ]
        == 1
    )


def test_the_three_host_units_are_counted_separately(scan):
    # MIXED_HOST has two records with distinct bacterial hosts and one eukaryotic. Records and
    # host rows agree here; distinct host taxa is what would differ if two records shared a host.
    findings = scan["by_classification"][MIXED_HOST]["host_findings"]
    assert findings["prokaryotic"][cf.HostUnit.RECORDS.value] == 2
    assert findings["prokaryotic"][cf.HostUnit.HOST_TAXA.value] == 2
    assert findings["eukaryotic"][cf.HostUnit.RECORDS.value] == 1


def test_the_votu_structure_separates_the_one_votu_that_straddles_taxonomy(scan):
    structure = scan["votu_structure"]
    assert structure["votus_with_several_classifications"] == 1
    assert structure["mixed_signatures"][0]["votus"] == 1
    assert sorted(structure["mixed_signatures"][0]["classifications"]) == sorted([PHAGE, CORONA])
    # A vOTU with two high-confidence records of the *same* classification is not mixed: the
    # undetermined representative cannot change the answer there.
    assert scan["by_classification"][PHAGE]["votus_owned_outright"] == 3


# --------------------------------------------------------------------------------------
# The diff
# --------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def result(close_tool, scan):
    return close_tool.analyse(scan, RELEASED_BY_EVO1)


def test_the_literal_reading_removes_exactly_the_rows_built_to_be_removed(close_tool, result):
    literal = result["per_reading"]["literal"]
    assert literal["rule_coverage_record_level"] == "5/6"
    assert literal["rule_coverage_with_own_unit"] == "6/6"
    removed = literal["record_level"]["removed_by_rule"]
    assert removed["keep-high-confidence"] == 1
    assert removed["keep-prokaryotic-host-twice"] == 1  # SINGLETON
    assert removed["remove-denylisted-families"] == 2  # CORONA, two records
    assert removed["remove-taxonomically-unspecific"] == 2  # NO_REALM, two records
    assert literal["record_level"]["classifications_surviving"] == 3


def test_the_retained_count_is_an_interval_whose_width_is_the_straddling_votu(result):
    interval = result["per_reading"]["literal"]["votu_interval"]
    # Surviving classifications own 3 (PHAGE) + 2 (HOSTLESS) + 2 (MIXED_HOST) = 7 vOTUs
    # outright, and one further vOTU holds a PHAGE record and a CORONA record.
    assert (interval["lower"], interval["upper"]) == (7, 8)
    assert interval["width"] == 1
    assert interval["votus_straddling_the_predicate"] == 1


def test_the_readings_disagree_only_about_the_row_built_to_divide_them(result):
    per_reading = result["per_reading"]
    assert per_reading["literal"]["record_level"]["classifications_surviving"] == 3
    # The charitable reading removes any classification with eukaryotic host evidence on one
    # strike; the strict reading removes it for not being exclusively prokaryotic. Both lose
    # MIXED_HOST and nothing else.
    assert per_reading["charitable"]["record_level"]["classifications_surviving"] == 2
    assert per_reading["strict"]["record_level"]["classifications_surviving"] == 2
    assert (
        per_reading["charitable"]["record_level"]["removed_by_rule"][
            "remove-eukaryotic-host-evidence"
        ]
        == 3
    )
    assert result["reading_spread"]["measurable"] is True
    assert result["reading_spread"]["classifications_surviving"]["spread"] == 1


def test_the_spread_across_readings_is_a_number_rather_than_unmeasurable(result):
    # A7.1 could only report that the spread was unmeasurable against the release, because
    # every rule the readings differ over read an input the release does not carry (D-047).
    spread = result["reading_spread"]
    for key in ("records_removed_record_level", "retained_lower_bound", "retained_upper_bound"):
        assert spread[key]["spread"] is not None
        assert set(spread[key]["per_reading"]) == {"literal", "charitable", "strict"}


def test_the_evo1_forward_direction_names_the_right_rule_for_each_excess(result):
    forward = result["per_reading"]["literal"]["evo1"]["forward"]
    # CORONA is removed by a record-level rule, so all 2 released records are that rule's
    # failure. PHAGE survives the record-level rules and is released 9 times against at most 4
    # vOTUs it could represent, so 5 records are the deduplication rule's failure. Summing the
    # two would name the wrong rule for 5 records.
    assert forward["records_removed_by_a_record_level_rule"] == 2
    assert forward["records_in_excess_of_the_votu_bound"] == 5
    assert forward["by_rule"]["remove-denylisted-families"] == 2
    assert forward["by_rule"]["keep-one-per-votu"] == 5
    attributions = {f["lineage_tag"]: f["attributed_to"] for f in forward["detail"]}
    assert attributions[CORONA] == "record-level rule"
    assert attributions[PHAGE] == "vOTU rule"


def test_the_evo1_converse_direction_is_reported_apart_from_the_forward_one(result):
    evo1 = result["per_reading"]["literal"]["evo1"]
    # HOSTLESS is predicted to survive on two vOTUs and is released once; MIXED_HOST survives
    # on two vOTUs and is not in the release at all.
    assert evo1["converse"]["shortfall_in_released_lineages"] == 1
    assert evo1["converse"]["lineages_absent_entirely"] == 1
    assert evo1["converse"]["records_in_lineages_absent_entirely"] == 2
    assert "forward" in evo1 and "converse" in evo1
    assert "mismatch_rate" not in json.dumps(
        evo1
    ), "a single combined rate would hide which direction the filter errs in"


def test_the_evo2_forward_direction_is_exact_per_record(result):
    evo2 = result["per_reading"]["literal"]["evo2"]
    assert evo2["run"] is True
    assert evo2["comparison_key"] == "source_accession"
    # Of the six released accessions: one Putative PHAGE record fails the confidence gate, one
    # CORONA record fails the family denylist. The other four are retained by the predicate.
    assert evo2["forward"]["by_rule"] == {
        "keep-high-confidence": 1,
        "remove-denylisted-families": 1,
    }
    assert evo2["forward"]["records"] == 2


def test_the_votu_rule_is_compared_at_votu_level_and_says_so(result):
    votu = result["per_reading"]["literal"]["evo2"]["votu_level"]
    assert votu["unit"] == "vOTU"
    # Predicted-surviving single-classification vOTUs: PHAGE's three and HOSTLESS's two and
    # MIXED_HOST's two. vOTU_00000001 contributed two released records; vOTU_00000004 one;
    # vOTU_00000012 one; the rest none.
    assert votu["contributed_more_than_one"] == 1
    assert votu["released_records_in_those"] == 2
    assert votu["contributed_exactly_one"] == 2
    assert votu["contributed_none"] == 4
    assert "record-level" not in votu["verdict"]


def test_the_evo2_converse_is_counted_at_votu_level_with_the_reason_stated(result):
    converse = result["per_reading"]["literal"]["evo2"]["converse"]
    assert converse["unit"] == "vOTU"
    assert converse["votus"] == 4
    assert "undetermined" in converse["why_not_per_record"]


def test_the_host_unit_sensitivity_travels_with_the_headline(result):
    sensitivity = result["host_unit"]["sensitivity"]
    assert set(sensitivity) == {u.value for u in cf.HostUnit}
    assert sensitivity[cf.PRIMARY_HOST_UNIT.value]["primary"] is True
    assert sum(1 for block in sensitivity.values() if block["primary"]) == 1
    assert result["host_unit"]["primary"] == cf.PRIMARY_HOST_UNIT.value


def test_the_published_checks_are_reported_as_checks_and_not_as_results(result):
    checks = result["per_reading"]["literal"]["published_checks"]
    assert checks["d064_retained_count"]["published"] == 2_653_046
    # The synthetic release is twelve orders of magnitude too small to land in the interval;
    # what is asserted is that the comparison is made and reported, not that it passes.
    assert checks["d064_retained_count"]["published_count_inside_the_interval"] is False
    assert checks["d064_retained_count"]["distance_to_interval"] > 0
    d058 = checks["d058_host_kingdom_unknown"]
    assert d058["published_share"] == pytest.approx(0.8951, abs=1e-4)
    assert d058["exact_on_evo2"]["records"] == len(RELEASED_BY_EVO2)


def test_a_write_up_is_produced_either_way_and_leads_with_the_verdict(close_tool, result):
    text = close_tool.summarise(result)
    assert text.startswith("# A7.2")
    assert "5/6 at record level" in text
    assert "host counting unit `records`" in text
    assert "## The spread across readings" in text
    assert "not a record-level conformance rate" in text


# --------------------------------------------------------------------------------------
# One taxon at two ranks
# --------------------------------------------------------------------------------------

#: The same family name, once where it belongs and once sitting in the realm field. This is a
#: real shape in IMG/VR v4, not a hypothetical: the publisher's strings put eleven `*viridae`
#: names in the realm field, and the published unspecificity rule tests for an assigned realm,
#: so the two forms of one family get opposite verdicts.
AT_FAMILY = ";;;;;f__Bicaudaviridae;;"
AT_REALM = "r__Bicaudaviridae;;;;;;;"


def test_one_taxon_at_two_ranks_is_reconciled_rather_than_counted_in_both_directions(
    close_tool, scan_tool, scan
):
    # Built to the proportions of the real case: the form with no realm is removed by the rule
    # and released anyway; the form with the name in the realm field is retained by the rule and
    # absent from the release. Scored per lineage and nothing else, the same records would be a
    # forward failure under one tag and a converse failure under the other.
    patched = json.loads(json.dumps(scan))
    patched["by_classification"][AT_FAMILY] = {
        "records": 10,
        "records_hc": 4,
        "seq_column_host": {"prokaryotic": 2, "none": 8},
        "host_findings": {"prokaryotic": {"records": 2, "host_rows": 2, "host_taxa": 2}},
        "votus_owned_outright": 3,
    }
    patched["by_classification"][AT_REALM] = {
        "records": 8,
        "records_hc": 2,
        "seq_column_host": {"prokaryotic": 2, "none": 6},
        "host_findings": {"prokaryotic": {"records": 2, "host_rows": 2, "host_taxa": 2}},
        "votus_owned_outright": 2,
    }
    released = dict(RELEASED_BY_EVO1)
    released[AT_FAMILY] = 5  # == 3 + 2: one record per high-confidence vOTU of both forms

    result = close_tool.analyse(patched, released)
    norm = result["per_reading"]["literal"]["rank_normalisation"]
    assert len(norm["groups"]) == 1
    group = norm["groups"][0]
    assert group["taxon_names"] == ["Bicaudaviridae"]
    assert group["released_records"] == 5
    assert group["high_confidence_votus_in_the_group"] == 5
    assert group["identity_holds"] is True
    # The two records the rule retains under the realm-field form are explained; the three it
    # removes under either form are not.
    assert norm["records_the_rule_retains_under_another_rank"] == 2
    assert norm["records_the_rule_removes_under_every_rank"] == 3
    assert norm["every_group_accounts_for_its_released_records"] is True


def test_a_lineage_pair_the_rule_treats_alike_is_not_reported_as_a_group(close_tool, scan):
    # The reconciliation is for lineages the *rule* splits. Two spellings of a taxon that the
    # rule treats identically explain nothing and would be noise in the table.
    patched = json.loads(json.dumps(scan))
    for name, votus in (
        (AT_FAMILY, 3),
        (";;;;;;;f__Bicaudaviridae".replace(";;;;;;;", ";;;;;"), 2),
    ):
        patched["by_classification"].setdefault(
            name,
            {
                "records": 4,
                "records_hc": 2,
                "seq_column_host": {"none": 4},
                "host_findings": {},
                "votus_owned_outright": votus,
            },
        )
    result = close_tool.analyse(patched, dict(RELEASED_BY_EVO1))
    names = [
        g["taxon_names"] for g in result["per_reading"]["literal"]["rank_normalisation"]["groups"]
    ]
    assert ["Bicaudaviridae"] not in names


def test_the_host_evidence_the_input_asserts_is_measured_and_reported(result):
    # Whether the readings can diverge at all is a property of the database, not of the policy:
    # every rule they differ over is keyed on eukaryotic host evidence. The fixture asserts some,
    # so the finding must say so rather than claiming the absence seen in the real release.
    host = result["host_evidence_in_the_input"]
    assert host["eukaryotic_findings"] == 1
    assert "readings can diverge" in host["finding"]
    assert result["reading_spread"]["why_it_is_zero"].startswith("The input asserts")


def test_an_input_with_no_eukaryotic_host_evidence_says_what_that_means(close_tool, scan):
    # The real case. IMG/VR v4's host field is empty, bacterial or archaeal and nothing else, so
    # the charitable and strict readings have nothing to fire on. A zero spread then says
    # something about the filter's source of evidence, not about the readings — and the write-up
    # has to be the one that says which.
    patched = json.loads(json.dumps(scan))
    for info in patched["by_classification"].values():
        info["host_findings"].pop("eukaryotic", None)
        info["seq_column_host"].pop("eukaryotic", None)
    result = close_tool.analyse(patched, dict(RELEASED_BY_EVO1))
    assert result["host_evidence_in_the_input"]["eukaryotic_findings"] == 0
    assert "never names a eukaryote" in result["host_evidence_in_the_input"]["finding"]
    spread = result["reading_spread"]
    assert spread["measurable"] is True
    assert spread["classifications_surviving"]["spread"] == 0
    assert "the cause is in the data" in spread["why_it_is_zero"]
    text = close_tool.summarise(result)
    assert "## What the input asserts about hosts" in text
