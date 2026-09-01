# Blind derivation notes — ldpc-staircase

Producer: Claude (Anthropic), model `claude-opus-5`, blind-derivation seat.
Language: Python 3.12.6, standard library only (`hashlib`, `json`).

## Isolation confirmation

I worked **only** from the files in `packet/` (`BRIEF.md`, `SPEC.md`, `corpus.json`,
`vectors/`). I did not read, list, glob, grep, or open anything outside my seat
directory. I did not look for `ldpc-staircase-spec`, `-java`, `-dotnet`, a `reference`
directory, or any other implementation of this codec on this machine. I did not use
web search or web fetch, and did not consult RFC 5170 or any external LDPC-Staircase
implementation. I did not look for the other seat's work. Every line of
`ldpc_staircase.py` was written from `SPEC.md`.

## Files in this folder

| File | Purpose |
| --- | --- |
| `ldpc_staircase.py` | the implementation: PRNG (§3), matrix (§4), encode (§5), decode (§6), canonical serialization (§7.1), plus the BRIEF's SplitMix64 corpus payload rule |
| `check_vectors.py` | validates against every committed vector in `packet/vectors/MANIFEST.json` |
| `run_corpus.py` | computes the 31 corpus cases and writes `results.json` |
| `check_robust.py` | order-independence and post-stage-2 checks that do not use any expected answer |
| `results.json` | the deliverable |

## How I built it

Straight transcription of `SPEC.md`, section by section, with the pseudocode kept
structurally identical so it can be diffed against the spec by eye.

- **§3 PRNG.** Park–Miller `state <- (16807*state) mod 2147483647`, exact integer
  arithmetic (Python ints are arbitrary precision, so Schrage is unnecessary).
  `rand(maxv) = int(float(maxv) * float(next()) / 2147483647.0)`. Python floats are
  IEEE 754 binary64 and `int()` truncates toward zero, so this is the required form.
  I deliberately did **not** use the integer formulation the spec warns against.
- **§4 matrix.** `H` as a list of `R` `set`s of column indices; `has`/`set` are set
  membership and insertion. One PRNG stream shared across 4.2 and 4.3; 4.4 draws
  nothing.
- **§5 encode.** Symbols held as big-endian Python ints for XOR (bytewise-identical to
  byte-array XOR), running `prev` chained in ascending ESI order.
- **§6 decode.** Peeling with a work stack over rows whose `unknown` count hits 1,
  maintaining `unknown(i)` and `accum(i)` incrementally; then at most one RREF over
  GF(2) of the residual system, with each row carried as
  `(coefficient bitmask over U, right-hand-side symbol)` so a row operation is two
  integer XORs.

## Decoding procedure I chose, and why

Exactly the two stages §6 mandates, with no iteration between them.

**Stage 1** is degree-one peeling run to its fixed point over the *whole* matrix —
variables are all `N` encoding symbols, not only the `K` source ones, so peeling
determines missing repair symbols too. That is forced by the committed vector
`dec-all-repair-missing`, which expects `expectStage: PEELING` and
`expectRecoveredSymbols: 60` for a loss set consisting entirely of repair symbols.

**Stage 2** builds `U` = every still-unknown variable (source *and* repair) and
`M` = every row with `unknown(i) >= 2`, reduces the `|M| x |U|` coefficient matrix to
reduced row echelon form applying every operation to the symbol right-hand sides, and
recovers exactly those variables that are a pivot with a singleton RREF row.

I chose RREF over the cheaper "solve for the pivot variables of a row-echelon form"
because the spec asks for the *maximal determined set*, and only RREF gives it. The
justification, which I checked rather than assumed: a variable `v` is determined by the
received set iff the unit vector `e_v` lies in the row space of the residual
coefficient matrix. In RREF each pivot column is zero in every other row, so if
`e_v = ⊕(subset of RREF rows)` then each chosen row contributes its own pivot column
uncancelled; a single-nonzero result therefore forces the subset to be one row whose
only entry is `v`. So "pivot row with no other variable" is exactly the determined set,
and no post-solve peeling pass can add anything — consistent with the profile
forbidding one.

I did not implement the optional `|U|` resource bound of §6.2 (no bound is supplied by
the corpus, and it only ever causes a decode to be reported as failed).

### Independent verification of the decode semantics

Because the residual-solve semantics are the part of this exercise most likely to
diverge, I checked my answer two ways rather than one:

1. **Rank cross-check (`run_corpus.py`).** For every corpus case that reached stage 2,
   I independently recomputed the determined set as
   `{ v : rank(A) == rank(A ∪ {e_v}) }` using a completely separate GF(2) rank routine
   that never touches symbol payloads. It agreed with the RREF result on all cases; a
   mismatch would have aborted the run.
2. **Peeling order-independence (`check_robust.py`).** The spec does not say which
   degree-one row to pick. I ran the fixed point three ways — FIFO queue, LIFO stack,
   and repeated sweeps in a shuffled row order — over all 31 cases and got identical
   known-sets every time. So `peelingSuffices` is well defined.
3. **Post-stage-2 peel is a no-op (`check_robust.py`).** Ran a further peeling pass
   after stage 2 on all 31 cases; it never added a symbol, confirming §6.2's maximality
   claim empirically as well as by proof.
4. Every symbol my decoder claims to know is asserted equal to the true encoded bytes,
   in both the vector harness and the corpus run.

## Committed vectors

**All committed vectors reproduced. 70/70 checks pass, first run, none failed.**

- 3 `prngRaw` cases including the RFC validation criterion (seed 1, ordinal 10000 →
  `1043618065`).
- 3 `prngBounded` cases (44 draws total), which pin the floating-point `rand` form.
- 16 `files` entries: length and SHA-256 of every blob.
- 6 `matrix` cases: `entryCount` and byte-exact canonical serialization.
- 5 `encode` cases: repair blobs byte-exact, including `R = 0` (empty output) and
  `K = 1, R = 1`.
- 6 `decode` cases × 5 assertions each: `expectComplete`, `expectStage`,
  `expectRecoveredSymbols`, `expectMissingSource`, plus a value check. This includes
  `dec-max-loss-failure`, whose expected 22-element `expectMissingSource` list matched
  exactly — that case is what pins the residual-solve semantics.

I also confirmed the BRIEF's SplitMix64 self-check (raw state 0 → `0xE220A8397B1DCDAF`,
`0x6E789E6AA1B965F4`, `0x06C45D188009454F`, `0xF88BB8A8724C81EC`).

## Corpus

All **31** cases computed. None was skipped, and no field is `null`.

Summary of what I got: 24 complete, 7 not complete (cases 02, 06, 08, 14, 22 fail to
recover every source symbol; 02/06/08/14 recover nothing at all). 18 cases were
satisfied by peeling alone; 13 needed the residual solve or failed.

I verified that every corpus case has at least one present symbol, so §6's
"empty received set is a caller error" rule is never triggered.

## Ambiguities in SPEC.md

Ordered roughly by how much they could matter.

### A1. §4.3 (raise low-degree rows) is exercised by nothing in this packet — HIGH RISK

I instrumented my build. **Neither branch of §4.3 fires for any of the six committed
matrix vectors, nor for any of the 15 distinct `(K,R,N1,seed)` parameter sets in the
corpus.** Every matrix has exactly `N1*K + (2R-1)` entries, i.e. left part plus
staircase and nothing else. The pool construction of §4.2 spreads `N1*K` ones over `R`
rows, so a row of left-degree < 2 essentially requires `N1*K < 2R`, which no case here
has.

Consequence: two implementations could disagree completely about §4.3 — the sequential
vs. exclusive reading of the two `if`s, the re-evaluation of `degree(i)` between them,
the `K >= 2` guard, the PRNG draws consumed — and **this entire round would still show
perfect agreement.** Agreement between the two seats is therefore *not* evidence that
§4.3 is implemented consistently. That looks like a genuine gap in the conformance
vectors rather than a spec defect.

My reading: the two `if`s are sequential and `degree(i)` is re-evaluated between them,
so a degree-0 row is raised to 1 by the first and to 2 by the second (the spec states
this explicitly). `degree(i)` is left-part-only, and since §4.4 has not run yet, that
equals the row's total size.

### A2. `R = 0` and §4

§4.2 begins `u[h] <- h mod R`, which is a division by zero when `R = 0`, and §4.4
unconditionally does `set(0, K)` when there is no row 0. §2 resolves it — "the matrix
is empty, encoding is a no-op" — but §4 itself does not carry the guard.

**Reading chosen:** skip §4 entirely when `R = 0`, consume no PRNG draws, and serialize
as `u32 R=0, u32 N=K` (8 bytes total). This is confirmed by the committed vector
`mtx-k4-r0-n1_1-s1.bin` (8 bytes), so it is not actually open — but an implementer
reading §4 alone could crash. Affects cases 01, 02, 03.

Related: §2's `1 <= N1 <= R` constraint is explicitly conditioned on `R >= 1`, so
`n1: 1, r: 0` in cases 01–03 is legal and `N1` is simply unused.

### A3. §4.2's forward scan result is computed and then discarded

The pseudocode assigns `i <- smallest index in [t, N1*K) with not has(u[i], j)`, then
inside `if i < N1*K` immediately overwrites `i` in the `repeat` loop. So the scan is
purely an existence test; its returned index is never used.

**Reading chosen:** exactly that — scan only to decide which branch to take, then draw.
A reader who instead used the scanned index when it was already acceptable (skipping
the draw) would consume a different number of PRNG values and produce a *completely
different matrix* from the first divergence onward. The vectors catch this immediately,
so it is well pinned, but the pseudocode's variable reuse invites the mistake.

The `else` branch (pool exhausted for column `j`) *is* exercised: by 3 of the 6 matrix
vectors and by corpus case-13's parameter set. Note it draws `rand(R)` over all rows
with no `t` offset — a different index space from the `if` branch.

### A4. §6.1 does not specify which degree-one row to pick

"While some row has `unknown(i) = 1`" leaves the selection order open. The fixed point
is in fact order-independent (a row that becomes peelable stays peelable, since rows
only lose unknowns), and I verified this empirically with three different orders across
all 31 cases. So `peelingSuffices` and the stage-1 known-set are well defined despite
the ambiguity. Worth stating in the spec anyway.

### A5. §6.2's entry condition is "any **source** symbol still unknown"

Read literally, a decode where peeling leaves every source symbol known but some repair
symbol unknown never runs the residual solve, and those repair symbols are reported as
not determined even if the system determines them.

**Reading chosen:** the literal one. I checked the sensitivity: **no corpus case is
affected** — there is no case where peeling ends with all source known and some symbol
still unknown. So this ambiguity cannot explain any disagreement between the seats on
this corpus. A reading of "any symbol still unknown" would give identical results here.

### A6. Whether peeling should determine repair symbols at all

§6 says decoding "is not required to reconstruct missing repair symbols", which could
be read as licence for a decoder to stop as soon as all source is known, reporting 0
recovered in a repair-only loss. The vector `dec-all-repair-missing` settles it
(`expectRecoveredSymbols: 60`, stage `PEELING`): symbols peeling happens to determine
do count. This matters for the BRIEF's `recoveredRepair` field in cases 05, 16, 19, 20,
21, 22, 28, 29, 31.

### A7. §6.2 does not fix the variable ordering for RREF

No column order for `U` is given. I used ascending ESI. The determined set is provably
independent of column order (it is exactly `{v : e_v ∈ rowspace}`), and I confirmed
this with the independent rank test, so this ambiguity is harmless — but a spec that
says "reduced row echelon form" without an ordering is under-specified on its face.

Similarly, §6.2 defines `M` as rows with `unknown(i) >= 2` and excludes `unknown(i) = 0`
rows as carrying no information about `U`. That is correct (they are pure consistency
checks), and I followed it.

### A8. Vector payload generation is not documented in the packet

`vectors/MANIFEST.json` says payloads come from "a documented SplitMix64 PRNG; see
VectorGenerator", but `VectorGenerator` is not in the packet and the keying is not
described. The BRIEF's corpus rule does **not** reproduce the vector source blobs — I
tried `payloadSeed` 0..4099 against the first symbol of
`enc-k16-r8-n1_3-s1-len32-src.bin` with no match, so the vector generator keys its
streams differently. This is harmless (the vector blobs ship their bytes explicitly and
the BRIEF is explicit that its rule is corpus-only test data), but the manifest's
forward reference is a dangling one from inside this packet.

### A9. Minor / noted but inert

- §2 requires `S > 0`; every corpus `symbolLen` is at least 1.
- The BRIEF says `missingCount` is the number of **distinct** ESIs; no corpus case
  contains a duplicate, so the distinctness rule is never load-bearing. I still
  de-duplicate.
- Byte order for the XOR is unspecified and irrelevant (GF(2) bytewise); I used
  big-endian integers, which is bit-identical to bytewise XOR.
- `repairSha256` with `R = 0` is the empty-string digest per the BRIEF
  (`e3b0c442...b855`), matching the zero-length `enc-k4-r0-...-rep.bin` vector.
- §2's "`N1 * K` representable as signed int32" bound is far from binding here
  (max `7 * 500 = 3500`).

## Things worth flagging about specific corpus results

- **case-14** (`k=32, r=16, n1=16`) recovers **nothing** from 5 lost source symbols
  despite all 16 repair symbols being present. With `N1 = R = 16` the pool forces every
  source column into every row, so the left part of `H` is the all-ones 16×32 matrix and
  every parity equation reduces to the *same* equation
  `x4 ⊕ x9 ⊕ x15 ⊕ x23 ⊕ x30 = accum`. The residual system has rank 1 over 5 unknowns.
  This is a real structural degeneracy at `N1 = R`, not a decode failure of chance, and
  it is the corpus case I would most expect to expose a difference in stage-2 semantics.
- **case-22** is the only partial recovery: 16 of 48 lost symbols determined
  (9 source + 7 repair), 26 source symbols left unknown, `complete = false`.
- **cases 02, 06, 08** fail for straightforward structural reasons: `R = 0` with a
  source symbol lost (02); a single parity row with two of its unknowns lost (06, 08).

## Anything I could not compute

Nothing. Every field of every case is populated; no `null` appears in `results.json`.
