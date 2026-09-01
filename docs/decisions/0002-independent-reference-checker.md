# 0002 — Use an independent dependency-free reference checker

- Status: Accepted; implemented 2026-09-01
- Date: 2026-08-31

## Context

The normative LDPC-Staircase contract has two optimized implementations, one for
Java and one for .NET. Both reproduce the committed conformance vectors exactly.
Those vectors intentionally have one generator, currently the Java implementation,
so there is one unambiguous byte-level oracle for cross-runtime compatibility.

That arrangement proves that the implementations agree with each other and with the
published vector set. It does not fully exclude a different failure mode: the vector
generator and both implementations could share the same interpretation mistake. More
tests written against the same production code would increase coverage without adding
an independent calculation of the expected answer.

The project therefore needs a small third checker whose value comes from being easy
to inspect, structurally different from the production decoders, and derived from
[`SPEC.md`](../../SPEC.md) rather than from either implementation.

## Decision

The specification repository will contain a standalone reference checker under
`reference/`, implemented in Python using only the standard library.

The checker is **verification tooling**, not a third production library and not a
second normative vector generator. `SPEC.md` and the committed vectors remain the
normative contract. The Java generator remains the only tool authorized to rewrite
`vectors/`; the reference checker treats that directory as read-only.

### Runtime and repository shape

The initial implementation will contain:

- `reference/ldpc_staircase_reference.py` — the auditable reference arithmetic and
  command-line entry point;
- `reference/test_reference_checker.py` — standard-library `unittest` coverage for
  the checker itself; and
- `reference/README.md` — usage, supported Python version, independence record, and
  reproduction commands.

It will support Python 3.11 or newer and have no PyPI, native, network, Java, or .NET
dependency. Running it must not require Gradle, a JDK, the .NET SDK, or either
implementation repository.

### Independence rules

The checker must be independently derived:

1. Its implementer works from `SPEC.md`, the vector manifest schema, and the cited
   RFC material where necessary. Production Java and .NET source are not used as
   implementation templates.
2. Code, control flow, naming, and data structures must not be copied or mechanically
   translated from either production implementation.
3. The decoder uses a deliberately simple whole-system GF(2) linear-algebra oracle to
   decide recoverability and recover source values. It must not duplicate the
   production peeling-plus-one-residual-solve control flow merely to obtain the same
   answer.
4. A small direct peeling routine may be included to check peeling-only vector cases,
   but it remains separate from the whole-system oracle.
5. The checker must not import production code, load production assemblies or JARs,
   or invoke either implementation as a subprocess.
6. The implementation review records its source provenance and confirms these rules
   before the checker is accepted as independent evidence.

Independence is a process and design property, not a claim that Python is inherently
more trustworthy than Java or .NET.

### Required checks

The checker will calculate and verify, directly from the specification:

- Park–Miller raw and bounded pseudo-random values, including the required IEEE 754
  bounded-scaling behavior;
- parity-check matrix construction and canonical matrix serialization;
- repair-symbol encoding for arbitrary positive symbol lengths;
- source recoverability and recovered source bytes for a supplied received set;
- the explicit `R = 0` behavior;
- canonical vector file lengths and SHA-256 digests; and
- every committed PRNG, matrix, encode, and decode vector, including expected
  unrecoverable cases.

The whole-system solver answers the mathematical question: whether the received
equations uniquely determine the missing source symbols and, if so, what those bytes
are. Java/.NET conformance tests continue to verify the profile-specific operational
metadata, such as production decode stage and pass counts. This division keeps the
new oracle algorithmically independent while preserving the complete public decoder
contract.

### Deterministic differential corpus

In addition to checking the committed vectors, the reference tool will define a
deterministic differential corpus with committed seeds and parameter lists. It must
cover:

- `R = 0`, single-source, single-repair, and default-`N1` boundaries;
- multiple valid `N1` values and seeds at both ends of the allowed range;
- odd and even symbol lengths;
- peeling-success, residual-required, and rank-deficient received sets;
- source-only, repair-only, mixed, scattered, and contiguous losses; and
- selected larger matrix/encode shapes, while keeping the deliberately simple Python
  solver small enough for an ordinary verification run.

The checker will emit deterministic, machine-readable results for this corpus. The
Java and .NET test suites will compare their results with that output. Generated
scratch output belongs outside `vectors/` and is not committed unless a later decision
promotes a case into the canonical conformance set.

### Command and failure behavior

At minimum, the command line will provide one release-gate command equivalent to:

```sh
python reference/ldpc_staircase_reference.py check-vectors vectors/MANIFEST.json
```

It will print a concise summary and exit nonzero on a malformed manifest, digest
mismatch, arithmetic mismatch, unexpected recovery success, unexpected recovery
failure, or recovered-byte mismatch. Results must be deterministic across supported
Python versions.

A disagreement stops the release gate. It does not automatically declare the Python
checker, Java implementation, .NET implementation, or existing vectors correct. The
specification and all three calculations must be examined, and any normative change
follows the versioning rules in [decision 0001](0001-versioning-and-protocol-neutral-optimizations.md).

## Completion criteria

The independent-oracle evidence is complete only when all of the following are true:

1. The checker, its self-tests, and its usage/provenance documentation are committed.
2. It verifies every existing canonical vector without importing or invoking a
   production implementation.
3. Java, .NET, and the checker agree on the deterministic differential corpus.
4. The corpus includes successful and unsuccessful recovery and exercises both small
   boundary cases and representative larger construction/encoding shapes.
5. A reviewer confirms the independence rules above.
6. The normal pre-release checklist runs the checker and records the command and
   result.

Until those criteria are met, the repository may say that an independent checker is
planned or in progress, but not that independent-oracle validation is closed.

### Status at implementation, 2026-09-01

1. **Met.** [`reference/ldpc_staircase_reference.py`](../../reference/ldpc_staircase_reference.py),
   [`reference/test_reference_checker.py`](../../reference/test_reference_checker.py),
   [`reference/corpus.json`](../../reference/corpus.json), and
   [`reference/README.md`](../../reference/README.md) are committed.
2. **Met.** `check-vectors vectors/MANIFEST.json` passes every committed PRNG, matrix,
   encode, and decode vector, plus every blob length and digest, using only the Python
   standard library.
3. **Met.** `ReferenceCorpusTest` (Java) and `ReferenceCorpusTests` (.NET) run the
   corpus and compare every reported field with the checker's answer. Both suites pass,
   and both were confirmed to fail when the checker's answer is deliberately perturbed.
4. **Met.** The corpus covers `R = 0`, `K = 1`, `R = 1`, `N1` from 1 to `R` including the
   default 7, seeds at both ends of the allowed range, odd and even symbol lengths from
   `S = 1`, peeling-only, residual-required, and rank-deficient outcomes, every loss
   shape listed above, and shapes up to `K = 500`, `R = 250`. The 2026-09-01 review round
   found that section 4.3 was exercised by nothing — it added no entry in any committed
   vector or corpus case. Five corpus cases closed the corpus half, and specification
   0.1.1 added three matrix vectors and one encode vector that close the vector half.
5. **Evidence complete; human confirmation outstanding.** A review round was run on
   2026-09-01 and is recorded in
   [`reference/review/independence-review.md`](../../reference/review/independence-review.md).
   Two agents independently implemented `SPEC.md` from scratch, in JavaScript and Python,
   with no access to the checker or to either implementation; both reproduced every
   committed vector and agree with the checker and with each other on all 36 corpus cases
   and all twelve compared fields. A hostile similarity audit against both production
   implementations returned PASS on rules 2, 3, 4, and 5. Rule 1 is corroborated but not
   confirmed, because it is a claim about process rather than a property of the artifacts.
   The self-tests assert rule 5's dependency and read-only properties only. No agent may
   grant this criterion; it closes on a human signature in that record.
6. **Pending.** This repository has no written pre-release checklist yet. The commands
   and the required-mode environment variables are documented in
   [`reference/README.md`](../../reference/README.md), and folding them into a checklist
   is left to whoever writes one.

The checker's first differential run produced one finding, recorded in
[`HISTORY.md`](../../HISTORY.md): the specification did not say that decoding requires at
least one present symbol, while both implementations enforced it. `SPEC.md` section 6
now states the rule. This is the intended behavior of the gate — a disagreement was
examined, and the specification, not an implementation, turned out to be at fault.

## Non-goals

The checker will not:

- become a supported application/runtime dependency;
- compete with the managed implementations on speed or memory use;
- implement excluded profile features such as rateless repair, inactivation, or
  repeated elimination-to-peeling cycles;
- redefine decoder operational metadata or regenerate canonical vectors;
- establish performance, loss-margin, or resource-use guarantees; or
- provide a legal or patent-freedom opinion.

## Consequences

- A shared interpretation defect can be detected even when Java and .NET agree with
  each other.
- The specification repository gains a directly runnable example of its math without
  adding dependencies to either production package.
- Verification becomes slower than the optimized test suites, which is acceptable for
  a release gate and bounded deterministic corpus.
- Every future normative specification change must update and re-run the checker in
  addition to regenerating vectors and updating both implementations.
- Implementation-only optimizations that preserve the contract require no checker
  change, but the checker remains part of their regression evidence.

## Alternatives considered

### Treat Java/.NET agreement as sufficient

Rejected as the only evidence. Cross-runtime agreement is essential, but both
implementations and the canonical vectors can still share one specification
interpretation mistake.

### Make .NET a second vector generator

Rejected. Two authoritative generators create ambiguity when they disagree and still
encourage the second implementation to mirror the first. The existing single-generator
rule remains clearer.

### Use an external codec implementation as the only oracle

Rejected as the primary plan. External implementations may use a different profile,
decoder policy, PRNG scaling, or licensing model. They may be useful as additional
research evidence, but they cannot replace a checker for this exact constrained
contract.

### Formally prove the full implementation

Deferred. Formal verification could provide stronger evidence, but it would add much
more tooling and maintenance than the small independently derived checker needed for
the current release line.

## References

- [Normative LDPC-Staircase specification](../../SPEC.md)
- [Canonical conformance-vector manifest](../../vectors/MANIFEST.json)
- [Decision 0001: Versioning and protocol-neutral optimizations](0001-versioning-and-protocol-neutral-optimizations.md)
- [RFC 5170: LDPC-Staircase and LDPC-Triangle FEC Schemes](https://www.rfc-editor.org/rfc/rfc5170.html)
