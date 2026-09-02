# History

This file records both normative specification releases and noteworthy
implementation releases. Implementation entries are included here when they change
performance, resource use, or operational behavior enough that all maintainers
should understand them. They do not become part of the wire contract merely by being
listed here.

## Specification 0.1.2 — 2026-09-01

Second additive change to the canonical vectors. Every vector committed at 0.1.1 is
byte-identical at 0.1.2, and no graph, PRNG, encoding equation, symbol interpretation,
or decode semantic changes. Under
[decision 0001](docs/decisions/0001-versioning-and-protocol-neutral-optimizations.md) a
change to canonical vectors bumps the specification version; the compatibility impact
makes this a patch.

- Added production-scale vectors at `K = 16000`, `R = 8192`, `N1 = 7`: one matrix case,
  one encode case, and two decode cases. Before this the canonical vectors reached
  `K = 250` for matrices and `K = 120` for encoding and decoding, while the profile is
  calibrated to `K = 16000` and `R = 8192`. Both implementations exercise large shapes in
  their own internal tests, but internal tests are not a cross-runtime oracle: nothing
  committed made the two runtimes agree on a single byte above `K = 250`.

  Scale is not a formality here. `mtx-k16000-r8192-n1_7-s8191` has 128,383 entries built
  from 112,000 bounded PRNG draws, against 1,999 entries in the largest previous matrix,
  so an implementation whose bounded scaling drifts only in a rare arm of the IEEE 754
  path now has six figures of draws to drift in. `dec-large-residual` loses 6,144 symbols
  and finishes in the residual solve, a system thousands of unknowns wide, where the
  largest previous residual solve had at most 60 — an elimination order or pivot rule that
  is subtly wrong is invisible at `K = 120` and decisive here. `dec-large-peeling` loses
  4,096 and completes by peeling alone over a 24,192-node graph.

  Symbol length for the large encode case is deliberately short (`S = 8`). Symbols are
  combined by XOR, so symbol length is independent of everything the large shape
  exercises, and a short one keeps the added blobs under 800 KB.

- Added the `missingBlob` form for decode cases (`SPEC.md` section 7.2) and raised
  `manifestVersion` from 1 to 2. The large decode cases lose thousands of symbols;
  inlining those index lists would have made the manifest mostly integers. The version
  was raised deliberately rather than relying on the addition being ignorable: a reader
  that skipped an unknown `missingBlob` field would treat the case's received set as
  complete and silently report a pass on a decode it never ran. Every reader now fails
  on the version instead, which is the loud failure a conformance artifact owes its
  consumers. A reader that understands both forms needs no other change.

- The independent reference checker validates the new cases from `SPEC.md` alone: both
  large decode cases agree on completion, recovered count, still-missing source indices,
  recovered bytes, and stage. `check-vectors` takes about 31 seconds unbounded, since the
  checker reduces the whole system to RREF in pure Python; `--max-decode-unknowns` skips
  the large solves for a fast pass and reports them as skipped, never as passed.

## Specification 0.1.1 — 2026-09-01

First change to the canonical vectors since 0.1.0. It is **additive**: every vector
committed at 0.1.0 is byte-identical at 0.1.1, and an implementation that passed 0.1.0
passes 0.1.1 unchanged. Under
[decision 0001](docs/decisions/0001-versioning-and-protocol-neutral-optimizations.md) a
change to canonical vectors bumps the specification version; the compatibility impact
makes this a patch.

- Added three matrix vectors and one encode vector that exercise `SPEC.md` section 4.3.
  The 2026-09-01 independence review found that the low-degree-raising pass added **no
  entry** in any committed vector — every one had exactly `N1*K + (2R - 1)` entries — so
  two implementations could have disagreed about that entire subsection and every gate
  would still have passed. The new cases put `N1*K` at or below `R` so rows genuinely
  leave section 4.2 below degree two: `mtx-k2-r8-n1_1-s1` and `enc-k2-r8-n1_1-s1-len5`
  fire both branches including a degree-0 row cascading into the degree-1 branch,
  `mtx-k8-r16-n1_2-s3` fires the degree-1 branch on all sixteen rows, and
  `mtx-k3-r6-n1_1-smax` does both at the top of the seed range. Section 4.3 now adds 53
  entries across the vector set, where it added 0 before.

  These vectors were produced by the single authorized generator, so they were also
  validated against the independent reference checker and against both from-scratch
  derivations from the review round, none of which shares the generator's reading of
  section 4.3.

- Aligned `SPEC.md` section 6 with what the vectors already required. Section 6 said a
  decoder "is not required to reconstruct missing repair symbols", but
  `dec-all-repair-missing` loses only repair symbols and requires a recovered count of
  `R`, so a decoder taking that latitude would fail a normative vector. Section 6 now
  states that decoding recovers and reports every symbol the received set determines,
  while completion stays judged on the source symbols alone. No conforming implementation
  changes: the vectors already settled this, and the prose was the part that was wrong.

  Raised as an ambiguity by the Codex derivation seat, which noticed the latitude while
  reading section 6 with no access to any implementation.

## Specification documentation, released in 0.1.1 — 2026-09-01

- Ran the independence review round required by decision 0002 completion criterion 5 and
  recorded it under [`reference/review/`](reference/review/). Two agents implemented
  `SPEC.md` from scratch, in JavaScript and Python, with no access to the checker or to
  either implementation; both reproduced every committed vector and agree with the checker,
  with each other, and with Java and .NET on all 36 differential corpus cases. A hostile
  similarity audit returned PASS on independence rules 2 to 5.
- Clarified `SPEC.md` section 2: `N1 >= 1` is required always, and `N1 <= R` additionally
  when `R >= 1`. The previous wording constrained `N1` only when `R >= 1`, so a value below
  1 was accepted at `R = 0` where `N1` is unused. Both implementations already rejected it
  unconditionally; the checker, following the specification's letter, did not. Second
  finding of the same shape as the section 6 precondition: the specification was permissive
  and the implementations were right.
- Added five differential corpus cases that exercise section 4.3. The review found that the
  low-degree-raising pass added no entry in any committed vector or any corpus case, so two
  implementations could have disagreed about it entirely without any gate noticing. The
  committed vectors still do not exercise section 4.3; closing that needs the authorized
  generator and its own decision.
- Closed the last open recommendation of the independence review by checking `SPEC.md`
  section 6.2's recovery criterion against the definition it stands for. Enumerating every
  consistent assignment on small systems — no row reduction, pivots, or peeling — agreed
  with the criterion on all 608,192 loss patterns across 660 configurations and 3,310,284
  missing symbols, on both which symbols are determined and their bytes. A bounded version
  is now a permanent self-test. This matters because every other calculation in the
  project reaches its answer by Gaussian elimination and would therefore reproduce a
  mistake in the criterion rather than catch it. The originally recommended derivation
  from RFC 5170 was **not** used, and the reasoning is recorded in the review: the RFC
  describes a broader scheme than this profile, and it is not the source of that criterion
  in the first place.
- Narrowed the claim that the checker's self-tests assert its structural independence
  properties. They assert the dependency and read-only properties of rule 5 only; rules 2
  to 4 are not machine-checkable and rest on the recorded review.

  Both specification changes in this entry are classified under
  [decision 0001](docs/decisions/0001-versioning-and-protocol-neutral-optimizations.md) as
  documentation-only clarification: no graph, PRNG, encoding equation, symbol
  interpretation, or canonical vector changes, and no previously valid input's result
  changes. They required no vector regeneration and were released as part of 0.1.1 above.

- Added the independent, dependency-free reference checker of
  [decision 0002](docs/decisions/0002-independent-reference-checker.md) under
  [`reference/`](reference/), together with its `unittest` self-tests, its committed
  differential corpus, and its usage and provenance record. It verifies every committed
  vector directly from `SPEC.md` without importing or invoking either implementation,
  and both implementations now compare their differential corpus results against it.
- Clarified `SPEC.md` section 6: decoding requires **at least one present symbol**, and
  all present symbols must share one length. The symbol length is read from a received
  symbol, so an entirely empty received set leaves `S` undefined and is a caller error
  rather than an incomplete decode.

  This was the first finding of the new checker. It answered "incomplete decode" for a
  fully empty received set while both implementations rejected the call. The
  implementations were right and the specification was silent, so the specification now
  states the rule the implementations already enforced.

  Classified under [decision 0001](docs/decisions/0001-versioning-and-protocol-neutral-optimizations.md)
  as documentation-only clarification: it changes no graph, PRNG, encoding equation,
  symbol interpretation, or canonical vector, and no defined input's result changes. No
  vector regeneration is required.

These entries were written while the normative specification was **0.1.0**. They
changed no normative behavior, so they carried no version of their own and shipped
with **0.1.1** above.

## Specification documentation, released in 0.1.1 — 2026-08-23

- Kept the normative specification version independent while establishing one shared
  implementation release line for the Java and .NET packages.
- Recorded the Java residual-solver optimization described below and classified it
  as protocol-neutral. `SPEC.md`, matrix construction, encoded symbols, public API,
  canonical vector payloads, and expected values are unchanged.
- Removed consuming-application references so the shared contract and implementation
  history remain general-purpose.

These entries were written while the normative specification was **0.1.0**. They
changed no normative behavior, so they carried no version of their own and shipped
with **0.1.1** above.

## Java 0.1.2 / .NET 0.1.2 — 2026-08-23

- Java replaced the parity-check matrix object forest with flat primitive adjacency
  storage, reducing allocations without changing graph construction or codec output.
- Java added Maven Central metadata and moved its Gradle build to Kotlin DSL while
  retaining Java 11 artifact compatibility.
- .NET added NuGet publication metadata and advances as a packaging-only companion;
  its codec behavior and public API are unchanged.
- Both packages continue to conform to specification 0.1.0 and the same vectors.

## Java 0.1.1 — 2026-08-04

A large near-threshold decode on a mobile runtime exposed excessive time in the dense
tail of residual Gauss–Jordan elimination. Early progress was quick, while later
pivots became much slower as rows filled in.

The Java decoder was improved in two ways:

- residual right-hand sides are packed once into ordinary `long[]` rows, avoiding
  repeated byte-array view dispatch in the elimination hot loop; and
- unresolved repair variables are ordered before source variables because staircase
  repair columns occur in at most two equations, reducing early fill-in.

The release changes neither encoding nor the decoding result. Verification included
the unchanged cross-language conformance vectors and an old/new differential suite
covering 864 cases across nine geometries, including odd symbol lengths,
near-threshold received sets, and rank-deficient failures. It compared encoded bytes,
decode metadata, presence masks, and every output symbol.

The .NET implementation did not receive this optimization and remained **0.1.0** at
that point. The later 0.1.2 public package line aligns both runtimes as described above.

## Specification 0.1.0 / Java 0.1.0 / .NET 0.1.0 — 2026-07-23

- Initial constrained RFC 5170 LDPC-Staircase profile.
- Initial canonical PRNG, matrix, encode, and decode conformance vectors.
- Initial Java 11 and .NET implementations.
