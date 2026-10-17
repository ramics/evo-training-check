"""The pinned profile registries, the viral selection, and the threshold arithmetic — A2.1."""

from __future__ import annotations

import gzip
import math

import pytest

from amazebio.profiles import (
    PFAM_38_2,
    PINNED_E_VALUE,
    PINNED_Z,
    REGISTRIES,
    RVDB_PROT_32_0,
    ProfileError,
    ProfileHeader,
    clan_name_additions,
    iter_family_meta,
    iter_profile_headers,
    md5_of,
    registry,
    rvdb_labels,
    select_viral_families,
)

DAT = """\
# STOCKHOLM 1.0
#=GF ID   Ebola_NP
#=GF AC   PF05505.16
#=GF DE   Ebola nucleoprotein
#=GF GA   25.0; 25.0;
#=GF TP   Family
#=GF ML   400
#=GF CL   CL0156
//
# STOCKHOLM 1.0
#=GF ID   7tm_1
#=GF AC   PF00001.25
#=GF DE   7 transmembrane receptor (rhodopsin family)
#=GF GA   21.1; 21.1;
#=GF TP   Family
#=GF ML   268
#=GF CL   CL0192
//
# STOCKHOLM 1.0
#=GF ID   Phage_integrase
#=GF AC   PF00589.26
#=GF DE   Phage integrase family
#=GF GA   20.5; 20.5;
#=GF TP   Domain
#=GF ML   171
//
# STOCKHOLM 1.0
#=GF ID   Transposase_11
#=GF AC   PF01609.25
#=GF DE   Transposase DDE domain
#=GF GA   22.0; 22.0;
#=GF TP   Domain
#=GF ML   150
//
"""


@pytest.fixture
def dat(tmp_path):
    path = tmp_path / "Pfam-A.hmm.dat.gz"
    with gzip.open(path, "wt") as handle:
        handle.write(DAT)
    return path


def test_family_meta_reads_the_fields_the_selection_needs(dat):
    families = {m.accession: m for m in iter_family_meta(dat)}
    assert set(families) == {"PF05505", "PF00001", "PF00589", "PF01609"}
    ebola = families["PF05505"]
    assert ebola.name == "Ebola_NP"
    assert ebola.gathering == (25.0, 25.0)
    assert ebola.model_length == 400
    assert ebola.clan == "CL0156"
    assert ebola.entry_type == "Family"


def test_accessions_are_stripped_of_their_point_release(dat):
    # A universe keyed on PF05505.16 would change denominator whenever Pfam re-cuts one
    # alignment, which would move the headline for a reason that is not about the corpus.
    assert all("." not in m.accession for m in iter_family_meta(dat))


def test_selection_takes_viral_families_and_leaves_cellular_ones(dat):
    selected = select_viral_families(dat)
    assert "PF00589" in selected  # Phage_integrase: "Phage"
    assert "PF00001" not in selected  # 7tm_1: a cellular receptor
    assert all(m.selected_by == "family-name" for m in selected.values())


def test_selection_leaves_mobile_element_machinery_alone(dat):
    # D-075: `integrase` and `transposase` are deliberately absent from the vocabulary, because
    # a bacterial transposase counted as viral content inflates the numerator of the headline.
    selected = select_viral_families(dat)
    assert "PF01609" not in selected
    # The phage integrase is in — but on the strength of "Phage", not of "integrase".
    assert "PF00589" in selected


def test_selection_refuses_an_empty_universe(tmp_path):
    path = tmp_path / "empty.dat.gz"
    with gzip.open(path, "wt") as handle:
        handle.write(
            "# STOCKHOLM 1.0\n#=GF ID   7tm_1\n#=GF AC   PF00001.25\n#=GF GA   1; 1;\n//\n"
        )
    with pytest.raises(ProfileError, match="no viral families"):
        select_viral_families(path)


def test_selection_refuses_a_family_with_no_curated_cutoff(tmp_path):
    path = tmp_path / "no-ga.dat.gz"
    with gzip.open(path, "wt") as handle:
        handle.write("# STOCKHOLM 1.0\n#=GF ID   Phage_coat\n#=GF AC   PF05505.16\n//\n")
    with pytest.raises(ProfileError, match="no gathering cutoff"):
        select_viral_families(path)


def test_the_selections_blind_spot_is_pinned_rather_than_rediscovered(dat, tmp_path):
    # D-083. A family named for a virus taxon carries no word from the vocabulary: `Ebola_NP`
    # is described as "Ebola nucleoprotein" and matches none of `virus`, `viral`, `capsid` or
    # the rest. It is outside the Pfam universe and RVDB-prot is what covers it.
    assert "PF05505" not in select_viral_families(dat)

    clans = tmp_path / "Pfam-A.clans.tsv.gz"
    with gzip.open(clans, "wt") as handle:
        handle.write("PF05505\tCL0156\tNucleocapsid\tEbola_NP\tEbola nucleoprotein\n")
        handle.write("PF00001\tCL0192\tGPCR_A\t7tm_1\t7 transmembrane receptor\n")
    additions = clan_name_additions(dat, clans)
    assert "PF05505" in additions
    assert additions["PF05505"][1] == "Nucleocapsid"
    # And the narrower rule is still not the one used: it admits families on the strength of a
    # clan name, which is a weaker claim than the family's own.
    assert "PF00001" not in additions


HMM = """\
HMMER3/f [3.4 | Aug 2023]
NAME  FAM000001
ACC   RVDB000001
LENG  120
STATS LOCAL MSV      -9.0  0.70
STATS LOCAL VITERBI  -9.5  0.70
STATS LOCAL FORWARD  -7.0  0.69
HMM          A        C
//
HMMER3/f [3.4 | Aug 2023]
NAME  Ebola_NP
ACC   PF05505.16
LENG  400
GA    25.0 25.0
STATS LOCAL FORWARD  -6.0  0.71
HMM          A        C
//
"""


def test_profile_headers_read_name_length_and_calibration(tmp_path):
    path = tmp_path / "test.hmm"
    path.write_text(HMM)
    headers = list(iter_profile_headers(path))
    assert [h.name for h in headers] == ["FAM000001", "Ebola_NP"]
    assert headers[0].length == 120
    assert headers[0].forward == (-7.0, 0.69)
    assert headers[0].gathering is None
    assert headers[1].gathering == (25.0, 25.0)


def test_bit_threshold_inverts_hmmer_s_own_e_value_formula():
    # HMMER's sequence E-value is Z * exp(-lambda * (score - tau)), so the bit score at a given
    # E-value is tau + ln(Z/E)/lambda. The threshold has to be exactly that or a hit accepted by
    # the search would be rejected by the invariant on `survival.Detection`.
    header = ProfileHeader("f", None, 100, (-7.0, 0.69), None)
    expected = -7.0 + math.log(PINNED_Z / PINNED_E_VALUE) / 0.69
    assert header.bit_threshold() == pytest.approx(expected)
    # And it is independent of how much corpus was searched, which is the whole point (D-076).
    assert header.bit_threshold(z=PINNED_Z) == header.bit_threshold(z=PINNED_Z)


def test_bit_threshold_refuses_an_uncalibrated_profile():
    with pytest.raises(ProfileError, match="no calibrated Forward tail"):
        ProfileHeader("f", None, 100, None, None).bit_threshold()


def test_registries_are_pinned_to_a_version_not_to_current_release():
    for reg in REGISTRIES.values():
        for spec in reg.files:
            assert "current_release" not in spec.url, reg.key
    assert "Pfam38.2" in PFAM_38_2.file("Pfam-A.hmm.gz").url


def test_every_pinned_file_carries_a_publisher_digest_or_says_it_does_not():
    for reg in REGISTRIES.values():
        for spec in reg.files:
            assert spec.md5_source, f"{reg.key}/{spec.name}"
            if not spec.md5:
                assert "unpinned" in spec.md5_source


def test_rvdb_profile_count_is_the_publishers_own_number():
    assert RVDB_PROT_32_0.profile_count == 13_679
    assert "metadata.yaml" in RVDB_PROT_32_0.source


def test_unknown_registry_names_the_pinned_ones():
    with pytest.raises(ProfileError, match="pinned registries"):
        registry("rvdb")


def test_md5_of_streams(tmp_path):
    path = tmp_path / "x"
    path.write_bytes(b"amazebio")
    assert md5_of(path, chunk=3) == md5_of(path)


def rvdb_db(tmp_path):
    """A miniature of the release's annotation database: no names, only keyword frequencies."""
    import sqlite3

    path = tmp_path / "rvdb.sqlite"
    c = sqlite3.connect(path)
    c.executescript(
        """
        CREATE TABLE family(id INTEGER PRIMARY KEY, size INTEGER, nbseq INTEGER,
                            LCAtaxid INTEGER);
        CREATE TABLE keyword(id INTEGER PRIMARY KEY, str CHAR(30) UNIQUE);
        CREATE TABLE fam_kw_seqnames(famId INTEGER, kwId INTEGER, freq INTEGER,
                                     PRIMARY KEY(famId, kwId));
        CREATE TABLE fam_kw_ref(famId INTEGER, kwId INTEGER, freq INTEGER,
                                PRIMARY KEY(famId, kwId));
        INSERT INTO family VALUES (69, 509, 81, 10239), (4230, 192, 40, 10239);
        INSERT INTO keyword VALUES (1,'helicase'), (2,'virus'), (3,'rna'), (4,'dependent'),
                                   (5,'protease'), (6,'clp');
        INSERT INTO fam_kw_seqnames VALUES (69,1,48), (69,2,40), (69,3,32), (69,4,27),
                                           (4230,2,24), (4230,5,23);
        INSERT INTO fam_kw_ref VALUES (69,1,100), (4230,5,40), (4230,6,40);
        """
    )
    c.commit()
    c.close()
    return path


def test_labels_are_derived_from_the_releases_own_keyword_frequencies(tmp_path):
    labels = rvdb_labels(rvdb_db(tmp_path))
    assert labels["FAM000069"].label == "helicase virus rna dependent"
    assert labels["FAM000069"].lca_taxid == 10239
    assert labels["FAM000069"].sequences == 81


def test_family_id_is_the_identity_and_the_label_is_not(tmp_path):
    # D-097. RVDB assigns no descriptive name, so the label is this project's summary and only
    # `family_id` may be cited as the family. Zero-padded to the release's own form.
    labels = rvdb_labels(rvdb_db(tmp_path))
    assert set(labels) == {"FAM000069", "FAM004230"}
    assert all(label.family_id == key for key, label in labels.items())


def test_reference_keywords_stay_out_of_the_label(tmp_path):
    # They describe the domain literature rather than the sequences, and mixing the two would
    # make a derived label look like a curated title.
    labels = rvdb_labels(rvdb_db(tmp_path))
    assert labels["FAM004230"].label == "virus protease"
    assert labels["FAM004230"].reference_keywords == ("protease", "clp")


def test_label_truncation_is_the_top_keywords_in_frequency_order(tmp_path):
    labels = rvdb_labels(rvdb_db(tmp_path), top=2)
    assert labels["FAM000069"].label == "helicase virus"


def test_an_empty_annotation_database_is_refused(tmp_path):
    import sqlite3

    path = tmp_path / "empty.sqlite"
    c = sqlite3.connect(path)
    c.executescript(
        """
        CREATE TABLE family(id INTEGER PRIMARY KEY, size INTEGER, nbseq INTEGER,
                            LCAtaxid INTEGER);
        CREATE TABLE keyword(id INTEGER PRIMARY KEY, str CHAR(30) UNIQUE);
        CREATE TABLE fam_kw_seqnames(famId INTEGER, kwId INTEGER, freq INTEGER);
        CREATE TABLE fam_kw_ref(famId INTEGER, kwId INTEGER, freq INTEGER);
        """
    )
    c.commit()
    c.close()
    with pytest.raises(ProfileError, match="no family annotations"):
        rvdb_labels(path)
