# Independent reference checker

A small, dependency-free Python checker for the LDPC-Staircase contract defined in
[`SPEC.md`](../SPEC.md), added by
[decision 0002](../docs/decisions/0002-independent-reference-checker.md).

It exists to close one specific gap. The Java and .NET implementations agree with each
other and with [`vectors/`](../vectors/), but those vectors have a single generator
(Java), so agreement alone cannot rule out one shared misreading of this specification.
This checker calculates the expected answers a second time, from the specification
rather than from either implementation.

It is **verification tooling**, not a third production library. `SPEC.md` and the
committed vectors remain the normative contract, the Java generator remains the only
tool authorized to write `vectors/`, and this checker treats that directory as
read-only.

## Requirements

Python **3.11 or newer**, standard library only. No PyPI package, native library,
network access, JDK, .NET SDK, Gradle, or implementation repository is needed.

## Commands

Run from the repository root.

Verify every committed conformance vector — the release-gate command:

```bash
python reference/ldpc_staircase_reference.py check-vectors vectors/MANIFEST.json
```

Compute the differential corpus results into a scratch file:

```bash
python reference/ldpc_staircase_reference.py emit-corpus reference/corpus.json --out build/corpus-results.json
```

Compare an existing results file against a fresh computation:

```bash
python reference/ldpc_staircase_reference.py check-corpus reference/corpus.json build/corpus-results.json
```

Run the checker's own self-tests:

```bash
python -m unittest discover -s reference -t reference
```

Every command prints a one-line summary and exits `0` on success, `1` on a disagreement,
and `2` on malformed input such as an unreadable manifest or an unsupported version.
Results are deterministic across supported Python versions.

## What `check-vectors` verifies

Directly from the specification, with nothing taken from an implementation:

- Park–Miller raw values at the manifest's ordinals, plus RFC 5170's own `seed = 1` /
  10,000th value criterion (SPEC.md section 3);
- the IEEE 754 bounded scaling into `[0, maxv)`, in the normative multiply-divide-truncate
  order;
- parity check matrix construction and the canonical serialization of section 7.1, plus
  structural invariants: at least `N1` ones per source column, the section 4.3 minimum
  row degree, and the exact staircase shape of the right part;
- repair symbol encoding at every committed symbol length, and the independent check
  that every parity equation XORs to zero over the finished codeword;
- source recoverability and recovered bytes for each decode case, and the source indices
  expected to remain missing;
- whether degree-one peeling alone completes, cross-checked against each case's recorded
  stage;
- the explicit `R = 0` bypass; and
- the byte length and SHA-256 digest of every file the manifest references.

## The decoder is deliberately not the production decoder

The profile decodes by peeling to a fixed point and then, at most once, solving the
residual system (SPEC.md section 6). Reimplementing that control flow in Python would
reproduce the production answer by reproducing the production procedure, which is
exactly the shared-mistake risk the checker is meant to exclude.

Instead `solve_whole_system` asks the underlying mathematical question directly: it takes
every parity equation at once, treats the missing symbols as variables, folds the
received symbols into the right-hand sides, and reduces the complete system over GF(2) to
reduced row echelon form. A variable is recoverable exactly when it is a pivot whose
reduced row contains no other variable. That is the maximal set of symbols the received
set determines, independent of any decoder policy or elimination order.

A separate, deliberately simple `peel` routine implements section 6.1 alone. It is used
only to answer "would degree-one peeling by itself have finished?", never to decide
recoverability.

The checker does not reproduce production decode metadata such as pass counters or
residual rank. Those stay in the Java and .NET conformance suites, which keeps the new
oracle algorithmically independent while the complete public decoder contract is still
covered.

## The differential corpus

[`corpus.json`](corpus.json) is a committed set of parameters, seeds, and explicit loss
sets covering, per decision 0002:

- `R = 0`, single-source (`K = 1`), single-repair (`R = 1`), and default-`N1` boundaries;
- several valid `N1` values, including `N1 = 1` and `N1 = R`, with seeds at both ends of
  the allowed `[1, 2147483646]` range;
- odd and even symbol lengths, from the minimum `S = 1` upward;
- peeling-success, residual-required, and rank-deficient received sets;
- source-only, repair-only, mixed, scattered, and contiguous losses; and
- larger construction and encoding shapes up to `K = 500`, `R = 250`.

Loss sets are stored as explicit index lists so no implementation needs selection logic
of its own.

`emit-corpus` writes a machine-readable result document. The Java and .NET test suites
run the same cases and compare every field: matrix entry count and serialization digest,
source and repair digests, the completion flag, the recovered symbol count, the recovered
source and repair index lists, the source indices still missing, whether peeling alone
sufficed, and a digest of the source bytes as they stand after the decode. In that last
digest an unrecovered source symbol contributes `symbolLen` zero bytes, so a decode that
quietly left a hole cannot produce the same digest as one that filled it.

The emitted results are scratch output. They belong outside `vectors/` and are not
committed; the corpus is not a conformance vector set, and promoting a case into the
canonical set would be a separate decision.

### Corpus payload rule

Corpus source symbols are generated, not stored. Each symbol is an independent
SplitMix64 stream keyed by the case's `payloadSeed` and the symbol's ESI:

```
state = payloadSeed XOR ((esi + 1) * 0x9E3779B97F4A7C15)      (mod 2^64)

next():
    state = state + 0x9E3779B97F4A7C15                        (mod 2^64)
    z = state
    z = (z XOR (z >>> 30)) * 0xBF58476D1CE4E5B9                (mod 2^64)
    z = (z XOR (z >>> 27)) * 0x94D049BB133111EB                (mod 2^64)
    return z XOR (z >>> 31)
```

The stream is emitted as little-endian 64-bit words and truncated to `S` bytes. Keying
per ESI keeps a symbol's bytes independent of the case's `K`, `R`, and symbol length, so
the same ESI carries the same prefix in every case sharing a payload seed.

This rule is corpus test data only. It is **not** part of the normative codec, and it is
unrelated to how `vectors/` payloads were produced.

## Running the corpus from the implementations

Both implementation repositories consume this repository as a submodule at
`external/ldpc-staircase-spec` and locate the checker there.

- **Java** — `ReferenceCorpusTest` runs as part of `./gradlew test`. Set
  `-Dldpc.referenceCorpus.required=true` (or `LDPC_REFERENCE_CORPUS_REQUIRED=1`) to make
  a missing Python interpreter a failure rather than a skip. `-Dldpc.python=<path>` or
  `LDPC_PYTHON` selects a specific interpreter.
- **.NET** — `ReferenceCorpusTests` runs as part of `dotnet test`, with the same
  `LDPC_REFERENCE_CORPUS_REQUIRED` and `LDPC_PYTHON` environment variables.

Both invoke the checker as an ordinary subprocess and read its JSON output. Neither
imports it, and the checker never invokes them.

## Independence record

Decision 0002 requires the implementation review to record the checker's provenance.

- The checker was written from [`SPEC.md`](../SPEC.md), the
  [`vectors/MANIFEST.json`](../vectors/MANIFEST.json) schema, and
  [RFC 5170](https://www.rfc-editor.org/rfc/rfc5170.html) section 5.7 and section 6.
  No production Java or .NET source was read while it was written; the implementations'
  public APIs were consulted afterwards, only to write the two comparison test classes
  that live in those repositories.
- Its control flow differs by construction: a whole-system RREF oracle instead of
  peeling plus one residual solve, sets of column indices instead of flat primitive
  adjacency arrays, and Python integers used as GF(2) bit vectors instead of packed
  `long[]` rows.
- It imports only `argparse`, `hashlib`, `json`, `sys`, `pathlib`, and `typing`. It has
  no subprocess, dynamic loading, socket, or network use, and does not load either
  implementation's assemblies or JARs. `test_reference_checker.py` asserts these
  structural properties so they cannot erode.
- The SplitMix64 constants of the corpus payload rule are checked against that
  algorithm's published output stream rather than against either implementation's test
  helpers.
- Its answers were compared against both implementations only after it was complete. The
  first comparison run reproduced every committed vector and agreed on 30 of the 31
  corpus cases; the single disagreement was a real specification gap, recorded below.

Independence here is a process and design property. It is not a claim that Python is
inherently more trustworthy than Java or .NET.

## Findings

**Decode requires at least one received symbol.** The first differential run included a
`K = 1`, `R = 1` case with both symbols missing. The checker answered "incomplete
decode"; both implementations rejected the call outright, because the symbol length `S`
is read from a received symbol and an empty received set leaves it undefined. Both
implementations were right and the specification was silent, so `SPEC.md` section 6 now
states the precondition, the checker enforces it, and the corpus covers unrecoverable
loss with cases that still receive something.
