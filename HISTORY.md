# History

This file records both normative specification releases and noteworthy
implementation releases. Implementation entries are included here when they change
performance, resource use, or operational behavior enough that all maintainers
should understand them. They do not become part of the wire contract merely by being
listed here.

## Unreleased specification documentation — 2026-09-01

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

The normative specification remains **0.1.0**.

## Unreleased specification documentation — 2026-08-23

- Kept the normative specification version independent while establishing one shared
  implementation release line for the Java and .NET packages.
- Recorded the Java residual-solver optimization described below and classified it
as protocol-neutral. `SPEC.md`, matrix construction, encoded symbols, public API,
  canonical vector payloads, and expected values are unchanged.
- Removed consuming-application references so the shared contract and implementation
  history remain general-purpose.

The normative specification remains **0.1.0**.

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
