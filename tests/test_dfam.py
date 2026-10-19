"""The pinned Dfam release, its family universe and the threshold policy — A2.3, D-183.

The HMM fixtures here are written in the format the publisher's reader emits, including the
per-species `TH` lines that must not be mistaken for a family's threshold. That mistake is the
one the threshold policy exists to prevent, so it gets a test of its own rather than a comment.
"""

from __future__ import annotations

import pytest

from amazebio.dfam import (
    ERV_SUBTYPES,
    EXPECTED_ERV_MODELS,
    EXPECTED_LTR_MODELS,
    EXPECTED_WITHOUT_THRESHOLD,
    FILES,
    RELEASE,
    DfamError,
    classify,
    is_erv,
    iter_models,
    universe,
)


def model(
    name: str,
    accession: str,
    *,
    length: int = 1200,
    ga: float | None = 30.15,
    species_thresholds: bool = True,
) -> str:
    """One HMMER3 model block as the export writes it."""
    lines = [
        "HMMER3/f [3.1b2 | February 2015]",
        f"NAME  {name}",
        f"ACC   {accession}",
        "DESC  a family",
        f"LENG  {length}",
        "ALPH  DNA",
    ]
    if ga is not None:
        lines += [f"GA    {ga:.2f};", f"TC    {ga:.2f};", f"NC    {ga:.2f};"]
    if species_thresholds:
        # Deliberately *higher* than the general cutoff, so a parser that read one of these as
        # the family threshold would produce a visibly different number.
        lines += [
            "TH    TaxId:9606; TaxName:Homo sapiens; GA:99.90; TC:99.90; NC:99.90; fdr:0.002;",
            "TH    TaxId:10090; TaxName:Mus musculus; GA:88.80; TC:88.80; NC:88.80; fdr:0.002;",
        ]
    lines += ["HMM          A        C        G        T", "//"]
    return "\n".join(lines) + "\n"


# --- the pin -------------------------------------------------------------------------------


def test_the_pin_names_the_curated_component_and_nothing_else():
    names = [f.name for f in FILES]
    assert names == [
        "dfam40.0.h5.gz",
        "dfam40.curated.hmm.0.h5.gz",
        "dfam40.curated.hmm.1.h5.gz",
    ]
    assert not any("uncurated" in n for n in names)
    assert RELEASE == "4.0"


def test_every_pinned_file_carries_a_digest_and_a_size():
    for pinned in FILES:
        assert len(pinned.md5) == 32
        assert int(pinned.md5, 16) >= 0
        assert pinned.gz_bytes > 0
        assert pinned.url.startswith("https://www.dfam.org/releases/Dfam_4.0/")


# --- classification ------------------------------------------------------------------------


def test_classify_splits_the_class_the_export_carries():
    assert classify("HERV16#LTR/ERVL") == ("LTR", "ERVL")
    assert classify("Charlie1#DNA/hAT-Charlie") == ("DNA", "hAT-Charlie")
    assert classify("SomeFamily#LTR") == ("LTR", None)


def test_a_name_without_a_classification_is_not_guessed_at():
    assert classify("BareName") == ("", None)


def test_is_erv_covers_exactly_the_declared_subtypes():
    for subtype in ERV_SUBTYPES:
        assert is_erv(subtype)
    for subtype in ("Gypsy", "Copia", "Pao", "Ngaro", "DIRS", None):
        assert not is_erv(subtype)


# --- parsing -------------------------------------------------------------------------------


def test_iter_models_reads_accession_length_and_the_general_threshold():
    text = model("HERV16#LTR/ERVL", "DF000000123.4", length=950, ga=25.5)
    (parsed,) = list(iter_models(text.splitlines(keepends=True)))

    assert parsed.accession == "DF000000123.4"
    assert parsed.name == "HERV16"
    assert parsed.type == "LTR"
    assert parsed.subtype == "ERVL"
    assert parsed.length == 950
    assert parsed.threshold == 25.5
    assert parsed.is_erv
    assert parsed.classification == "LTR/ERVL"


def test_a_per_species_threshold_is_never_read_as_the_familys_threshold():
    """The failure the threshold policy exists to prevent (D-183)."""
    text = model("HERV16#LTR/ERVL", "DF000000123.4", ga=25.5, species_thresholds=True)
    (parsed,) = list(iter_models(text.splitlines(keepends=True)))
    assert parsed.threshold == 25.5  # not 99.90, the first TH line


def test_a_family_with_no_general_threshold_parses_as_having_none():
    text = model("NoCut#LTR/ERV1", "DF000000999.1", ga=None)
    (parsed,) = list(iter_models(text.splitlines(keepends=True)))
    assert parsed.threshold is None


def test_many_models_are_each_yielded_once():
    text = "".join(model(f"F{i}#LTR/ERVK", f"DF{i:09d}.1", length=100 + i) for i in range(1, 25))
    parsed = list(iter_models(text.splitlines(keepends=True)))
    assert len(parsed) == 24
    assert len({p.accession for p in parsed}) == 24
    assert [p.length for p in parsed] == [100 + i for i in range(1, 25)]


def test_a_model_without_an_accession_raises():
    text = model("F#LTR/ERVK", "DF1.1").replace("ACC   DF1.1\n", "")
    with pytest.raises(DfamError, match="no ACC line"):
        list(iter_models(text.splitlines(keepends=True)))


def test_a_model_without_a_length_raises():
    text = model("F#LTR/ERVK", "DF1.1").replace("LENG  1200\n", "")
    with pytest.raises(DfamError, match="no LENG line"):
        list(iter_models(text.splitlines(keepends=True)))


def test_a_final_model_with_no_terminator_is_still_yielded():
    """An export truncated of its last `//` must not silently lose a family."""
    text = model("F#LTR/ERVK", "DF1.1").replace("//\n", "")
    (parsed,) = list(iter_models(text.splitlines(keepends=True)))
    assert parsed.accession == "DF1.1"


# --- the universe --------------------------------------------------------------------------


def synthetic_export(*, ltr: int, erv: int, no_threshold: int) -> list[str]:
    """An export with a controlled universe, plus non-LTR families that must be ignored."""
    blocks = []
    for i in range(erv):
        blocks.append(model(f"E{i}#LTR/ERVK", f"DF{i:09d}.1"))
    for i in range(erv, ltr - no_threshold):
        blocks.append(model(f"G{i}#LTR/Gypsy", f"DF{i:09d}.1"))
    for i in range(ltr - no_threshold, ltr):
        blocks.append(model(f"N{i}#LTR/ERV1", f"DF{i:09d}.1", ga=None))
    for i in range(5):
        blocks.append(model(f"D{i}#DNA/hAT-Ac", f"DF{900000 + i:09d}.1"))
    return "".join(blocks).splitlines(keepends=True)


def test_the_universe_separates_searchable_from_declared_exclusions():
    models = list(iter_models(synthetic_export(ltr=100, erv=60, no_threshold=7)))
    result = universe(models, strict=False)

    assert result["ltr_models"] == 100  # the DNA families are not in the universe
    assert result["excluded_no_threshold"] == 7
    assert result["searchable"] == 93
    assert len(result["excluded_accessions"]) == 7
    assert result["excluded_accessions"] == sorted(result["excluded_accessions"])


def test_an_erv_without_a_threshold_is_excluded_rather_than_counted():
    """The exclusions are ERV1 families here, so a careless count would inflate the headline."""
    models = list(iter_models(synthetic_export(ltr=100, erv=60, no_threshold=7)))
    result = universe(models, strict=False)
    assert result["erv_models"] == 60


def test_composition_is_ordered_by_count_then_accession():
    models = list(iter_models(synthetic_export(ltr=100, erv=60, no_threshold=7)))
    composition = universe(models, strict=False)["composition"]
    counts = list(composition.values())
    assert counts == sorted(counts, reverse=True)
    assert composition["LTR/ERVK"] == 60


def test_the_universe_carries_a_denominator_restriction():
    """D-173: a registry the rule does not name must not arrive with no restriction."""
    models = list(iter_models(synthetic_export(ltr=10, erv=5, no_threshold=1)))
    denominator = universe(models, strict=False)["denominator"]
    assert denominator["comparable_across_registries"] is False
    assert "Never quote" in denominator["restriction"]
    assert denominator["authority"]


def test_a_changed_denominator_stops_the_run():
    """A re-export that silently became a different universe is the D-074 failure."""
    models = list(iter_models(synthetic_export(ltr=100, erv=60, no_threshold=7)))
    with pytest.raises(DfamError, match="denominator has changed"):
        universe(models, strict=True)


def test_the_strict_check_passes_on_the_counts_d183_measured():
    models = list(
        iter_models(
            synthetic_export(
                ltr=EXPECTED_LTR_MODELS,
                erv=EXPECTED_ERV_MODELS,
                no_threshold=EXPECTED_WITHOUT_THRESHOLD,
            )
        )
    )
    result = universe(models, strict=True)
    assert result["ltr_models"] == EXPECTED_LTR_MODELS
    assert result["excluded_no_threshold"] == EXPECTED_WITHOUT_THRESHOLD
