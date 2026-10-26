# A7.5 test fixture

`records.fasta` holds two synthetic nucleotide records. `fixture_r1` carries one open
reading frame, built by back-translating a pseudo-random amino-acid string under a fixed
seed; `fixture_r2` is a low-complexity record with no callable gene. `protein.txt` is the
protein `pyrodigal` calls on `fixture_r1` in metagenomic mode, recorded so the test can
build a profile from it and have something to find.

Synthetic throughout. No corpus sequence is committed anywhere in this repository (D-103).
