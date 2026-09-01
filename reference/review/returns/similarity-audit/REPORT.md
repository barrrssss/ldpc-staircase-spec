---
seat: similarity-audit
role: hostile similarity audit of the reference checker against both production implementations
model: Claude Opus 5 (Anthropic), agent session
date: 2026-09-01
access: read-only access to the checker, its self-tests, decision 0002, SPEC.md, and the
  full Java and .NET production source
rules_audited: decision 0002 independence rules 2, 3, 4, 5
---

# Hostile similarity audit — `reference/ldpc_staircase_reference.py` vs. the Java and .NET production implementations

Audited against decision 0002 independence rules 2–5. All files read read-only; nothing
was modified.

**Artifacts examined:** `reference/ldpc_staircase_reference.py` (1079 lines),
`reference/test_reference_checker.py` (628 lines), `reference/README.md`,
`reference/corpus.json`, `docs/decisions/0002-independent-reference-checker.md`,
`SPEC.md` (299 lines), `vectors/MANIFEST.json` (schema); Java `LdpcStaircase.java`,
`ParityCheckMatrix.java`, `PmmsRandom.java`, `Symbols.java`, `DecodeResult.java`; .NET
`LdpcStaircaseCodec.cs`, `ParityCheckMatrix.cs`, `PmmsRandom.cs`; direction check
`ReferenceCorpusTest.java` and `ReferenceCorpusTests.cs`.

## 1. Verdict

I went looking for translation and did not find it. The three places where the checker's
shape genuinely matches production — the three-phase matrix build, the Park–Miller
`rand(maxv)` expression, and the "RREF pivot row with no other variable" recovery
criterion — are all places where `SPEC.md` is normative pseudocode or normative prose, so
any correct implementation converges there; and in each of those places the checker's
naming and data structures track the specification rather than production
(`has(row, column)` in spec argument order vs. Java's reversed
`columnContains(column, row)`; `0x7FFFFFFE` in the spec's hex vs. production's decimal
`2147483646`; `left_degree(row)` computed from the spec's left-part-only definition where
production instead relies on a phase-ordering invariant and calls the total row degree).

The decode half — the part rules 3 and 4 govern — is not merely renamed: the checker
performs no peeling before its solve, builds a system measurably larger than production's
residual system on every loss case, and runs a full Gauss-Jordan elimination on 16 of 28
corpus loss cases where production does no linear algebra at all.

My positive findings are two: one substantive reservation on rule 3 (behavioral, not
structural — the oracle is provably answer-identical to production's procedure, so it
excludes coding mistakes but cannot by construction exclude a misreading baked into
`SPEC.md` §6.2 itself), and one on the honesty of the self-tests, which assert only rule 5
and a read-only property while decision 0002 claimed the "structural rules" are asserted
by them.

**Rule 2: PASS. Rule 3: PASS. Rule 4: PASS. Rule 5: PASS.** Decision 0002's claim about
the self-tests is overstated and should be narrowed.

## 2. Per-rule findings

### Rule 2 — no copied or mechanically translated code, control flow, naming, or data structures — PASS

**What I searched:** function-by-function ordering of the Python module against both
production files; a mechanical shared-n-gram scan (6-word windows, punctuation/case
normalized) between the checker and all six production files, subtracting every n-gram
also occurring in `SPEC.md`, to isolate wording shared with production but *not* available
from the spec; every production-specific identifier (`sourceSymbolCount`,
`repairSymbolCount`, `leftDegree`, `encodingSymbolCount`,
`rowOffsets`/`rowEntries`/`columnOffsets`/`columnEntries`, `RowColumnsInternal`,
`PmmsRandom`, `nextBounded`, `DecodeState`, `DecodeResult`, `residualSolve`,
`columnOfSymbol`, `symbolOfColumn`, `pivotColumn`, `recoveredSource`/`recoveredTotal`,
`peelPasses`, `residualSolvePasses`, `Progress`, `NO_INDICES`); the packed-word bit idiom
(`>>> 6`, `& 63`, `1L <<`, `bitCount`/`PopCount`); and degenerate-case/off-by-one handling
line by line.

**Correspondences that exist, and why they are spec-forced — category (b).** There *is* a
one-to-one, same-order correspondence for the matrix construction half:

| checker | Java | .NET | source |
|---|---|---|---|
| `build_matrix` (`:154`) | `ParityCheckMatrix.build:136` | `Build:83` | SPEC §4 "built in exactly three ordered phases … The order is normative" |
| `_fill_left_part:170` | `fillLeftPart:166` | `FillLeftPart:137` | SPEC §4.2 pseudocode |
| `_raise_low_degree_rows:202` | `raiseLowDegreeRows:216` | `RaiseLowDegreeRows:200` | SPEC §4.3 pseudocode |
| `_add_staircase:220` | `fillStaircase:238` | `FillStaircase:229` | SPEC §4.4 pseudocode |
| `ParityCheckMatrix.serialize:127` | `serialize:302` | — | SPEC §7.1 |
| `ParkMiller.bounded:70` | `nextBounded:71` | — | SPEC §3 |

I claim **(b)** for all of these. The spec is normative *pseudocode* here and the PRNG draw
order is explicitly normative, so the phase decomposition, phase order,
forward-scan-then-draw structure, the `repeat … until not has(…)` rejection loops, the
swap-remove, and the sequential (not exclusive) `if degree==0` / `if degree==1 and K>=2`
pair are all mandated.

Two supporting observations that would be hard to fake: the function names track the
**spec headings**, not production (SPEC §4.3 "raise low-degree rows" →
`_raise_low_degree_rows`; where the spec heading is "Right part: the staircase" the checker
says `_add_staircase` while *both* productions say `fillStaircase`/`FillStaircase` — the
checker picked a different verb from the one both implementations share); and the checker
follows the **spec's argument order** where production does not — SPEC §4.1 defines
`has(i, c)`/`set(i, c)`, the checker is `has(self, row, column)`/`set(self, row, column)`,
while Java's builder is `columnContains(int column, int row)`, reversed. A mechanical
translation would inherit that reversal.

**Concrete divergences that argue against translation:**

1. **Pool initialization direction.** SPEC §4.2 writes `u[h] <- h mod R for h = N1*K - 1
   down to 0`, and both productions transcribe the descending loop literally
   (`for (int h = pool - 1; h >= 0; h--)`). The checker uses an ascending comprehension,
   `pool = [h % r for h in range(pool_size)]`. A mechanical translation would have carried
   the descending loop across.
2. **Left degree computed from the spec definition, not a phase-ordering invariant.**
   SPEC §4 defines `degree(i)` as ones "of the left part only". Production exploits that
   §4.3 runs before the staircase is added and calls the *total* row degree —
   `builder.rowDegree(i) == 0`, `rows[i].Count == 0` — each with a comment explaining why
   that is safe. The checker implements the definition literally (`left_degree`) and
   *reuses* it after the staircase exists, in `check_matrix_invariants`. Production's
   helper cannot be reused that way.
3. **Distinct meaning for a same-looking name.** Java's `leftDegree()` means `N1`. The
   checker's `left_degree(row)` means a row's left-part degree, and it stores `N1` as
   `self.n1`. A translator does not repurpose an identifier.
4. **`set()` enforces SPEC §4.1's "never called for an entry that is already set"** —
   raises `SpecViolation`. Neither production checks this.
5. **Notation follows the spec's formatting:** `PRNG_MAX_SEED = 0x7FFFFFFE` matches SPEC
   §2's hex; both productions write decimal.
6. **No production data structure survives.** Java stores flat CSR
   (`rowOffsets`/`rowEntries`/`columnOffsets`/`columnEntries`) built through a linked-list
   edge accumulator; .NET stores `int[][]` built from `List<int>[]`; the checker stores
   `List[Set[int]]` both directions. The packed-`long[]`/`ulong[]` bit-row idiom that
   dominates both production solvers is **absent** — the checker uses one
   arbitrary-precision Python `int` per row and a big-endian `int.from_bytes` view of the
   symbol as RHS.
7. **Validation differs in content and order.** The checker drops production's `K + R`
   overflow check and its `N1*K + 4R` bound — the latter is specific to *Java's flat
   builder sizing* and has no spec basis, so its absence is informative. See finding 5.1.
8. **Decode-half ordering is inverted.** Both productions define `peel` before
   `residualSolve`. The checker defines `solve_whole_system` *before* `peel`. Production
   has 7 decode-side members; the checker has 3 and none of production's operational
   metadata (`stage`, `residualRank`, `residualUnknownCount`, `residualRowCount`,
   `peelPassCount`, `residualSolvePassCount`, `residualSolveSkipped`, `DecodeOptions`,
   `ProgressListener`).
9. **Residual column ordering.** Java deliberately maps repair variables before source for
   sparsity, with a comment explaining why. The checker uses plain ascending column order.
   That distinctive quirk is exactly what survives translation. It did not.

**The strongest similarities I found, honestly stated.** The n-gram scan returned **20**
shared 6-grams between the checker and the union of six production files, of which **16**
do not occur in `SPEC.md`. Every one of the 16 is a fragment of the same four
docstring/comment summary lines or of a `(k, r, n1, seed)` parameter list:

- `"SPEC.md section 4.3 - raise rows with fewer than two left-part ones."` (checker) vs.
  `"SPEC.md section 4.3 — raise rows with fewer than two ones in the left part."` (Java).
  My closest textual match: seven words in sequence not verbatim in the spec. **I classify
  it (c), neutral.** The spec heading supplies "raise" and the first body sentence supplies
  "Rows with fewer than two `1`s in the left part"; both authors compressed the same
  heading plus first body sentence into a one-liner, and the tails diverge. I could not
  construct a version both accurate and materially different.
- `"place N1 ones in every source column"` (checker / Java). SPEC §4.2 contains the inline
  comment `// place N1 ones in this column`; both substituted "every source" for "this".
  **(b).**
- `"The canonical serialization of SPEC.md section 7.1"`. SPEC §7.1's heading is "Canonical
  matrix serialization". **(b)** — a cross-reference, not content.
- `"Consumes no PRNG draws."` SPEC §4.4: "The staircase consumes no PRNG draws." Dropping
  the subject when the function is named for it is the obvious compression. **(c), very
  weak.**
- The `k, r, n1, seed` parameter-list n-grams. SPEC §2 states "`(K, R, N1, seed)` fully
  determines the code", and Java uses these short names only in *private* helpers. **(b).**

One coincidence the scan does not surface, flagged deliberately: `_xor_into(target,
source)` matches Java's `Symbols.xorInto(byte[] dst, byte[] src)` in name and argument
order, and `xorInto`/`xor_into` appears nowhere in `SPEC.md`. **I classify this (c),
weak.** "xor into" with destination first is a near-universal idiom, and nothing else about
the two matches: Java uses a `VarHandle` eight-bytes-per-instruction loop with a scalar
tail, the checker is a four-line `enumerate` loop.

Notably absent from the shared set: any comment explaining a *mechanism*. The two
production comments carrying real reasoning a copier would find attractive — Java's
"Scanning first is what guarantees the draw loop below terminates" and "A row is pushed
only on the transition to exactly one unknown, and `unknown` never rises, so one slot per
row is enough" — have **no** counterpart in the checker, which says only "The normative
forward scan over the still-available pool slots", borrowing the spec's own phrase "forward
scan". I found no comment, ordering quirk, off-by-one, or degenerate-case handling that
only makes sense if its author had read either production.

### Rule 3 — whole-system GF(2) oracle, not a relabelled peel-then-residual — PASS

**Is it the same algorithm relabelled? No.** `solve_whole_system` does not peel first, at
all. It takes the full variable set — *every* missing symbol including ones a degree-one
pass would resolve immediately — and the full equation set: every row of `H` with at least
one unknown. Production's residual system is by construction the strict subset that
survives peeling: `U` = symbols still unknown *after* the fixed point, `M` = rows with
`unknown[i] >= 2`.

I measured the difference on the committed corpus — the checker's `(|U|, |M|)` exactly as
`solve_whole_system` builds them, versus the residual system production would build after
peeling:

```
case                              |U| whole  |M| whole  |U| resid  |M| resid
k100-r50-mixed-stride                    30         47         28         45
k100-r50-tail-contiguous                 30         47         26         43
k250-r125-n1_7-residual                  90        125         79        114
k500-r250-n1_7-source-band              160        247        155        241
k500-r250-n1_7-residual                 180        242        125        185
```

More decisively: of the 28 `R > 0` corpus loss cases, **16 are resolved entirely by
peeling** — production builds *no* coefficient matrix and performs *zero* row operations,
while the checker still constructs and Gauss-Jordan-reduces a full system for every one. On
57% of the corpus one of the two does no linear algebra whatsoever.

Structural differences inside the elimination itself:

| | production | checker |
|---|---|---|
| coefficient row | `long[]`/`ulong[]` words, `column >>> 6`, `1L << (column & 63)` | one Python `int` bit set, `1 << position[column]` |
| right-hand side | `byte[]` or packed `long[]` + `Symbols.xorInto` | `int.from_bytes(value, "big")`, one integer `^` |
| echelon maintenance | physical row **swap** into a rank-ordered prefix, `rank` cursor | rows never move; `consumed[]` flag + `pivot_row_of` dict mapping variable → equation |
| pivot search window | `for row = rank .. rowCount` | `for candidate in range(len(equations))`, skipping consumed |
| recovery test | iterate **pivot rows**, popcount across words with early exit at 2 | iterate **variables**, exact integer equality `mask == (1 << index)` |
| variable ordering | Java maps repair-before-source for sparsity | plain ascending column index |

The one genuine common ancestor is the *criterion*, and it is normative spec text —
SPEC §6.2: "Reduce … to **reduced row echelon form** … A variable is then recovered exactly
when it is a pivot variable whose RREF row contains no other variable." All three restate
it. **(b).**

**Behaviors the checker has that production does not:** a fully-received-row consistency
check raising `SpecViolation` when a row whose symbols are all present does not XOR to zero
— production discards such rows silently (`if (missing == 0) continue;`); and rows with
exactly one unknown at entry are ordinary equations to the checker, never peeling triggers.

**The reservation I want on record (a limit, not a violation).** `solve_whole_system` and
production's peel-then-residual are *provably* answer-identical — peeling is a special case
of Gaussian elimination, and the RREF determined-set is invariant under elimination order.
That is what makes the checker a valid oracle, and what decision 0002 asks for. But it
bounds what independence buys: because both compute the same mathematical object, the
checker can detect a *coding* error in either production and a misreading of SPEC §§2–5
(construction, PRNG, encode), while a misreading embedded in SPEC §6.2's own recovery
criterion would be reproduced by all three. Decision 0002 does not claim otherwise and the
README is careful ("Independence here is a process and design property"), so this is a
scope note, not a finding against rule 3. It does mean the decode-side independence
evidence is weaker than the construction-side evidence, where the checker genuinely
re-derives from pseudocode.

### Rule 4 — the peeling routine stays separate from the oracle — PASS

`peel` shares no state with `solve_whole_system`; each takes the received set fresh and
returns its own `RecoveryOutcome`. Every call site traced:

- `check_decodes` → `solve_whole_system` for `complete`, recovered count, recovered bytes,
  `missing_source`. `peel` is not called.
- `check_stage_consistency` → `peel` **only**, and only to decide whether the manifest's
  `expectStage` of `PEELING`/`RESIDUAL_SOLVE` is consistent with whether degree-one peeling
  alone finishes. Exactly the "peeling-only vector cases" allowance rule 4 grants.
- `check_zero_repair` → `solve_whole_system` only.
- `run_corpus_case` → both, independently. Every recoverability field in the emitted record
  (`complete`, `recoveredCount`, `recoveredSource`, `recoveredRepair`,
  `missingSourceAfter`, `recoveredSourceSha256`) comes from `outcome`; `peel` contributes
  exactly one field, `peelingSuffices`.

No path feeds `peel`'s output into the oracle or short-circuits the oracle when peeling
succeeds. The docstring's claim ("It is never used to answer the recoverability question
itself") is accurate.

The checker's `peel` is also not a translation of production's. Production tracks an
integer count per row plus the global present-mask, and recovers the variable by
*rescanning the row* for the first not-present column. The checker keeps a `Set[int]` of
unresolved columns per row and reads the variable straight out of the set
(`next(iter(unresolved[row]))`) — no rescan exists. Production's defensive
`if (variable < 0) continue` has no counterpart; it cannot arise in the set formulation.
Production nulls dead accumulators for heap reasons; the checker does not. Production's
`if (other == row) continue` self-skip becomes `if column in unresolved[other]`, which
subsumes it because the row's own set was cleared first. The shared LIFO worklist with a
stale-entry re-check on pop is the textbook lazy-deletion pattern, effectively forced by
SPEC §6.1's "repeat until no row has `unknown(i) = 1`" — **(b)/(c)**, not evidence.

Vocabulary note: SPEC §6.1 supplies `unknown(i)` and `accum(i)`. Production uses
`unknown[]` and `accumulator[]`. The checker uses `accumulator` (shared with both spec and
production) but names the other `unresolved` — it is a set, not a count, so the spec's name
would not have fit. Weak, in the independence direction.

### Rule 5 — no import, load, or subprocess invocation of production — PASS

Exhaustive grep of `ldpc_staircase_reference.py` for `import`, `from`, `subprocess`,
`ctypes`, `cffi`, `socket`, `urllib`, `importlib`, `__import__`, `exec(`, `eval(`, `Popen`,
`os.system`, `jpype`, `py4j`, `clr`, `dll`, `.jar`, `dotnet`, `gradle`, `javac`, `java `
returned exactly the import block:

```
from __future__ import annotations
import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple
```

Standard library only, no dynamic loading, no process spawning, no network. The only
filesystem reads are `vectors/MANIFEST.json`, the referenced `*.bin` blobs, and
`reference/corpus.json`; the only write is `--out` in `_cmd_emit_corpus`. `reference/`
contains no other Python module that could be a back door.

I verified the invocation direction is production → checker, not the reverse:
`ReferenceCorpusTest.java` and `ReferenceCorpusTests.cs` spawn the Python checker via
`ProcessBuilder`/`ProcessStartInfo`. Rule 5 constrains the checker, so this is compliant —
and it is the safe direction, since the checker computes its answers without ever seeing
production's.

Confirmed end to end by running the gate and self-tests:

```
$ python reference/ldpc_staircase_reference.py check-vectors vectors/MANIFEST.json -v
OK: vectors vectors\MANIFEST.json: 804 checks passed
No production implementation was imported, loaded, or invoked.     (exit 0)

$ python -m unittest discover -s reference -t reference
Ran 61 tests — OK
```

## 3. Do the self-tests test what they claim?

`IndependenceTest` has three methods. Its own docstring says it guards "the structural
half" of the rules, which is honest as far as it goes. But decision 0002 stated "the
structural rules are asserted by the checker's own self-tests", and that is an
overstatement.

- `test_only_standard_library_imports` — reads its own source and prefix-matches
  `import X` / `from X`. **Tests roughly what it claims for rule 5.** Gaps: it does not
  parse, so `__import__("sub" + "process")` or an `exec()` of an import string passes;
  `exec(`/`eval(` are not checked at all. Multi-name imports (`import json, subprocess`)
  happen to fail only because the trailing comma leaves the token unmatched — accidental,
  not designed.
- `test_no_subprocess_or_dynamic_loading` — plain substring search for `subprocess`,
  `ctypes`, `socket`, `urllib`, `importlib`, `os.system`. **Tests rule 5's obvious cases.**
  Gaps: `__import__` is absent from the list; and being a raw substring test it fires on
  the words appearing in a *comment*, so the module cannot document its own abstention.
  Brittle but effective for the realistic case.
- `test_the_vectors_directory_is_only_ever_read` — greps for `write_bytes` and
  `write_text(`, excluding any line containing `out_path`. **Weaker than it claims.** It
  says nothing about the *destination*: the excluded `out_path` write accepts any `--out`
  path, including one inside `vectors/`. And `open(p, "w")`, `os.remove`, `shutil` are not
  covered. This is a name-based convention check, not enforcement.

**Nothing in the self-test suite asserts rule 2, rule 3, or rule 4.** The two tests that
come closest are in `RecoveryTest`: `test_the_whole_system_is_never_weaker_than_peeling`
(asserts `set(peeled.recovered) <= set(whole.recovered)`) and
`test_peeling_and_the_whole_system_agree_when_peeling_completes`. **Both would be satisfied
— trivially, and more strongly — by a checker that violated rule 3**, e.g. one whose
`solve_whole_system` began by calling `peel` and then solved only the residual; in that
implementation the subset relation holds by construction rather than by mathematics. So
these tests cannot detect the exact failure mode rule 3 exists to prevent. Rules 2–4 are,
and can only be, established by human review of the kind in section 2. **Recommend
narrowing decision 0002 to say the self-tests assert the dependency and read-only
properties (rule 5), and that rules 2–4 rest on review.**

The rest of the suite is sound: `VectorGateTest` verifies the gate actually *fails* on a
corrupted blob, a wrong PRNG value, a wrong decode outcome, a wrong stage, a missing blob,
and malformed/unsupported/missing manifests — it tests that the checker can say no, which
is the property that matters for a release gate.
`test_bounded_uses_binary64_not_exact_integer_arithmetic` pins the one subtle SPEC §3
requirement.

## 4. What I could NOT determine from the artifacts

1. **Whether the author actually never read the production source.** This is a claim about
   a process, made in `reference/README.md`. It is unfalsifiable from the artifacts.
   Everything I can check is consistent with it, and several details (§2 divergences 1, 2,
   3, 5, 7, 9) would be surprising if it were false — but code evidence can only bound the
   probability, never settle it.
2. **Commit history.** The auditor's working root was not itself a Git repository and the
   audit was read-only, so it did not examine timestamps, authorship, or the order in
   which the checker and the two `ReferenceCorpus*` test classes were written. Commit history inside
   each library repo would be the strongest available corroboration of the README's
   provenance claim — specifically, whether `ldpc_staircase_reference.py` was complete
   before `ReferenceCorpusTest.java` first appeared. I recommend a reviewer check that.
3. **Whether `SPEC.md` §6.2 itself faithfully states the intended recovery semantics.** The
   checker validates implementations against the spec; nothing here validates the spec
   against RFC 5170 or against intent. A defect at that level is invisible to all three
   calculations.
4. **The .NET source's own independence from Java.** Out of scope for rules 2–5, but noted
   incidentally: `LdpcStaircaseCodec.cs` and `LdpcStaircase.java` are near-line-for-line
   counterparts, including identical comments. That is by design — they are the two
   production implementations — but it does mean the "two implementations agree" evidence
   is weaker than two independent derivations would be, which is precisely the gap decision
   0002 was written to close.

## 5. Anything else that struck me

**5.1 A real behavioral divergence between the checker and both productions, currently
unexercised.** `validate_parameters` reads `if r >= 1 and not (1 <= n1 <= r)`, so with
`R = 0` the checker accepts `N1 = 0` or a negative `N1`. Both productions reject `N1 < 1`
unconditionally. The checker follows SPEC §2's letter — "Requires `1 <= N1 <= R` **when
`R >= 1`**" — so on the current spec text the *implementations* are the stricter party, not
the checker. All three `R = 0` corpus cases use `n1: 1`, so the gate never touches this. It
is the same *shape* of finding as the one decision 0002 already recorded and resolved by
amending SPEC §6: a place where the spec is silent or permissive and both implementations
independently agreed to be stricter. Worth either a sentence in SPEC §2 or a corpus case —
and worth noting that the checker's design *did* surface it, mild positive evidence that it
reasons from the spec rather than mirroring production.

**5.2 The `R = 0` guard placement is the one structural echo of Java over .NET.** The
checker early-returns before constructing the PRNG, as Java does; .NET instead wraps the
three phases in `if (r > 0)`. I classify this **(b)**: the guard is *forced* — SPEC §4.2's
`u[h] <- h mod R` is undefined at `R = 0` — and "return early" vs. "wrap in an if" is a
two-way coin flip. Mentioned only because I committed to reporting the closest matches
rather than only the comfortable ones.

**5.3 The checker's structural invariant checks are its most valuable independent content,
and the least like production.** `check_matrix_invariants` re-derives, post-construction,
that every source column carries at least `N1` ones, that every row's *left* degree meets
the §4.3 minimum (with the `K >= 2` degenerate rule), and that row 0's right part is
exactly `{K}` while row `i`'s is exactly `{K+i, K+i-1}`. Neither production computes any of
this. These would catch a construction bug that reproduced the vectors by reproducing the
same wrong PRNG consumption — the closest thing in the artifacts to genuinely orthogonal
evidence.

**5.4 On the corpus payload rule.** `corpus_symbol` uses SplitMix64, whose constants are
published; `test_splitmix64_matches_the_published_stream` pins them against that published
stream rather than any production helper, as the README claims. I did not independently
verify the pinned values against an external SplitMix64 reference (that would need network
access I did not use), but the rule is corpus test data, not normative codec behavior, so
an error there would cause a loud cross-implementation disagreement rather than a silent
shared misreading.
