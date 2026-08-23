# 0001 — Versioning and protocol-neutral optimizations

- Status: Accepted
- Date: 2026-08-04; amended 2026-08-23

## Context

The normative LDPC-Staircase contract and its Java and .NET implementations live in
separate repositories. A large near-threshold decode on a mobile runtime exposed a
major implementation cost in the dense tail of Java's residual Gauss–Jordan solve.
The solution changed internal storage and pivot ordering without changing the graph,
equations, encoded symbols, recoverability, public API, or wire representation.

Without an explicit policy, such a change creates two problems: maintainers cannot
tell whether conformance artifacts need to change, and package versions can drift or
be bumped in lockstep even when only one runtime changed.

## Decision

The normative specification and the implementation release line use **independent
semantic versions** while they are pre-1.0:

- `ldpc-staircase-spec` versions the normative math, deterministic construction,
  serialization, decoder contract, and conformance vectors.
- `ldpc-staircase-java` and `ldpc-staircase-dotnet` share one implementation package
  version so Maven and NuGet coordinates communicate the same family release.

A compatible implementation-only bug fix, performance optimization, resource-use
improvement, test improvement, or packaging correction advances the shared
implementation patch version. An implementation without the runtime change receives a
companion packaging release whose changelog states that its API, codec behavior,
specification, and conformance vectors are unchanged.

A normative change to the graph, PRNG, encoding equations, symbol interpretation,
required decode semantics, or canonical vectors changes the specification version.
Each implementation then adopts that specification in its own subsequent release.
The compatibility impact determines whether the pre-1.0 change is patch or minor;
incompatible changes must never be hidden in a patch release.

Documentation-only clarification that does not alter normative meaning is recorded
under the current specification version and does not require new vectors.

## Classification of the Java residual-solver change

The Java 0.1.1 change is protocol-neutral:

1. Packing right-hand-side symbol bytes into `long[]` rows changes only the internal
   representation used while applying XOR row operations.
2. Ordering unresolved repair variables before source variables changes only which
   valid Gauss–Jordan pivots are considered first. Reduced systems determine the same
   values regardless of column order.
3. The parity-check matrix, encoder, external symbol arrays, and decode API are
   unchanged.
4. Existing conformance vectors pass byte-for-byte without regeneration.
5. Old/new differential testing agrees on encoded bytes, result metadata, presence
   masks, and every output symbol, including unsuccessful rank-deficient cases.

Therefore:

- specification remains `0.1.0`;
- Java advances from `0.1.0` to `0.1.1`; and
- .NET remains `0.1.0` at that point because its implementation did not change.

## Publication amendment (2026-08-23)

The Java tip later added protocol-neutral flat primitive graph storage and publication
metadata after the documented 0.1.1 implementation. Reusing 0.1.1 for that changed
binary would make the changelog and artifacts ambiguous. The first public package line
therefore advances both implementations to 0.1.2:

- specification remains `0.1.0`;
- Java is `0.1.2`; and
- .NET is `0.1.2` as a packaging-only companion release, with no codec/API change.

## Consequences

- Consumers must track both the specification version and the implementation package
  version. The specification number need not equal the package number, but Java and
  .NET package numbers must match for each family release.
- Implementation release notes must identify the issue abstractly, state whether the
  wire contract changed, and name the conformance or differential evidence.
- Protocol-neutral changes must not regenerate vectors just to produce a visible
  version change.
- Java and .NET package tags should match their shared declared package version when
  a release is published.
