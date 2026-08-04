# 0001 — Versioning and protocol-neutral optimizations

- Status: Accepted
- Date: 2026-08-04

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

The specification and each implementation use **independent semantic versions** while
they are pre-1.0:

- `ldpc-staircase-spec` versions the normative math, deterministic construction,
  serialization, decoder contract, and conformance vectors.
- `ldpc-staircase-java` versions the Java package and its implementation behavior.
- `ldpc-staircase-dotnet` versions the .NET package and its implementation behavior.

A compatible implementation-only bug fix, performance optimization, resource-use
improvement, test improvement, or packaging correction receives a patch release in
the implementation that changed. Other implementations do not bump merely to keep
numbers aligned.

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
- .NET remains `0.1.0` because its implementation did not change.

## Consequences

- Consumers must track both the specification version and the implementation package
  version; equal numbers across repositories are neither required nor implied.
- Implementation release notes must identify the issue abstractly, state whether the
  wire contract changed, and name the conformance or differential evidence.
- Protocol-neutral changes must not regenerate vectors just to produce a visible
  version change.
- Package tags should match the declared package version when a release is published.
