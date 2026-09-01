# Independence review — decision 0002, completion criterion 5

- Round date: 2026-09-01
- Subject: [`reference/ldpc_staircase_reference.py`](../ldpc_staircase_reference.py) and
  its differential corpus
- Method: [`README.md`](README.md); brief as issued: [`BRIEF.md`](BRIEF.md)
- **Status: evidence complete, human confirmation outstanding.**

## Outcome in one paragraph

Two agents independently implemented `SPEC.md` from scratch, in two different languages,
without access to the checker or to either production implementation. Both reproduced
every committed conformance vector and both agree with the checker on all 36 differential
corpus cases across all twelve compared fields, and with each other. A third agent audited
the checker against both production implementations hunting for evidence of translation
and returned PASS on independence rules 2, 3, 4, and 5, with one scope reservation and one
correction. The round produced three substantive findings, all now resolved or recorded.
Rule 1 is **corroborated, not confirmed** — it is a claim about process and cannot be
established from artifacts. Criterion 5 is ready for a human to sign.

## Seats

| Seat | Model | Language | Access |
| --- | --- | --- | --- |
| `codex-derivation` | OpenAI Codex, GPT-5 | JavaScript, Node standard library | packet only |
| `claude-derivation` | Claude Opus 5 | Python 3.12, standard library | packet only |
| `similarity-audit` | Claude Opus 5 | — | checker, self-tests, decision 0002, `SPEC.md`, full Java and .NET source |

Returns are under [`returns/`](returns/). The two derivation seats were given only
`BRIEF.md`, `SPEC.md`, `vectors/`, and the anonymised corpus; each ran in its own
directory and neither could see the other's work.

## Result 1 — the mathematics agree, five ways

Every calculation below is of the same 36 corpus cases, compared on `missingCount`,
`matrixEntryCount`, `matrixSha256`, `sourceSha256`, `repairSha256`, `complete`,
`peelingSuffices`, `recoveredCount`, `recoveredSource`, `recoveredRepair`,
`missingSourceAfter`, and `recoveredSourceSha256`.

| Calculation | Language | Procedure | Agreement |
| --- | --- | --- | --- |
| the checker | Python | whole-system GF(2) RREF | reference |
| `codex-derivation` | JavaScript | peel, then one residual RREF | 36/36, all fields |
| `claude-derivation` | Python | peel, then one residual RREF | 36/36, all fields |
| `ldpc-staircase-java` | Java | peel, then one residual RREF | 36/36, all fields |
| `ldpc-staircase-dotnet` | C# | peel, then one residual RREF | 36/36, all fields |

The two blind seats also agree with each other on every field, having never communicated.

The most useful part of this is the *procedural* split. The checker decides recoverability
by reducing the whole parity-check system at once; the four others follow the two-stage
procedure `SPEC.md` section 6 prescribes. Two different procedures across four languages
reach identical answers, which is what decision 0002 wanted and what neither
implementation agreement nor a code review could have shown on its own.

Both seats reproduced every committed conformance vector on their first run: 123 assertions
for the Codex seat, 70 for the Claude seat, including the RFC 5170 seed-1 criterion, every
bounded-PRNG draw, every matrix and repair blob byte-exact, and every decode expectation
including the 22-element expected-missing list of `dec-max-loss-failure`.

## Result 2 — three findings

### Finding A — section 4.3 was exercised by nothing (fixed)

Raised by `claude-derivation`. Section 4.3, which raises rows of left degree below two, was
reachable in principle but **added zero entries** across all six committed matrix vectors,
all five encode vectors, and all fifteen distinct parameter sets of the original corpus.
Every matrix had exactly `N1*K + (2R - 1)` entries. The one near miss is the `K = 1, R = 1`
vector, whose degree-one row is blocked by the `K >= 2` guard, so the guard was exercised
but neither entry-adding branch ever was.

Two implementations could therefore have disagreed completely about section 4.3 and every
gate would still have passed. Agreement on that subsection was not evidence of anything.

Verified independently before acting, then fixed: the corpus gained five cases at `N1*K`
close to or below `R`, where the pass adds 8 to 16 entries and both branches fire,
including a degree-0 row cascading into the degree-1 branch, a case at the top of the seed
range, and one loss-heavy enough to leave source symbols unrecoverable. The corpus now
holds 36 cases, and all five calculations agree on all of them.

The **committed vectors still do not exercise section 4.3.** Regenerating those is a
specification change requiring the single authorized generator, so it is out of scope here
and recorded below as an open recommendation.

### Finding B — `N1 < 1` accepted when `R = 0` (fixed)

Raised by `similarity-audit`. `SPEC.md` section 2 required `1 <= N1 <= R` only *when
`R >= 1`*. The checker followed that letter and accepted `N1 = 0` or negative `N1` when
`R = 0`; both production implementations rejected `N1 < 1` unconditionally. All three
`R = 0` corpus cases use `n1: 1`, so nothing exercised the divergence.

Same shape as the finding the checker produced on its first run: the specification was
permissive, both implementations had independently agreed to be stricter, and the
specification was the party at fault. Section 2 now requires `N1 >= 1` always, the checker
enforces it, and a self-test pins it.

Worth noting for the record that this one cuts in favour of rule 1: the checker diverged
from both implementations *because* it was following the spec text rather than mirroring
them.

### Finding C — the self-tests were oversold (corrected)

Raised by `similarity-audit`. Decision 0002's status section and `reference/README.md` both
claimed the checker's self-tests assert the structural independence properties. They do
not. The `IndependenceTest` methods are name-based source scans covering rule 5's obvious
cases; they do not parse, and `test_the_vectors_directory_is_only_ever_read` checks writing
verbs rather than destinations. Nothing in the suite asserts rules 2, 3, or 4 — and the two
tests that come closest would be satisfied *more* strongly by a checker that violated rule
3, since a `solve_whole_system` that peeled first would make the subset relation hold by
construction.

Both claims are now narrowed to say the self-tests cover rule 5's dependency and read-only
properties only, and that rules 2 to 4 rest on this review.

## Result 3 — the similarity audit

Full report: [`returns/similarity-audit/REPORT.md`](returns/similarity-audit/REPORT.md).

**Rule 2 (no copied code, control flow, naming, or data structures): PASS.** A mechanical
6-gram scan against all six production files, subtracting everything also present in
`SPEC.md`, found 16 shared fragments not available from the spec — all of them pieces of
four one-line docstring summaries or of a `(k, r, n1, seed)` parameter list, and none
explaining a mechanism. The two production comments carrying real reasoning a copier would
want have no counterpart in the checker. Against that, nine concrete divergences point away
from translation, including: the checker builds the section 4.2 pool ascending where both
productions transcribe the spec's descending loop; it computes left degree from the spec's
definition where production relies on a phase-ordering shortcut; it repurposes the
identifier `leftDegree`, which in Java means `N1`; it enforces the spec's
"never set an entry twice" rule, which neither production checks; it writes the seed bound
in the spec's hex where both productions write decimal; and it does not carry Java's
distinctive repair-before-source residual column ordering, which is exactly the quirk that
survives translation.

**Rule 3 (whole-system oracle, not a relabelled peel-then-residual): PASS.** Measured, not
asserted: the checker builds a strictly larger system than production's residual on every
loss case, and on 16 of the 28 loss cases in the original corpus production performs zero
row operations while the checker still reduces a full system. The elimination differs in
row representation, echelon maintenance, pivot search, and recovery test.

**Rule 4 (peeling kept separate): PASS.** Every call site traced. `peel` contributes
exactly one field, `peelingSuffices`, and never feeds the oracle.

**Rule 5 (no import, load, or subprocess of production): PASS.** Standard library only; the
invocation direction is production → checker, which is the safe direction.

### The audit's reservation, recorded rather than resolved

The whole-system oracle and production's peel-then-residual are *provably* answer-identical
— peeling is a special case of Gaussian elimination, and the RREF determined-set does not
depend on elimination order. That is what makes the checker a valid oracle. It also bounds
what it buys: the checker can catch a coding error in either implementation and a misreading
of sections 2 to 5, but a misreading embedded in section 6.2's own recovery criterion would
be reproduced by all of them. Decode-side independence evidence is therefore weaker than
construction-side evidence, where the checker genuinely re-derives from pseudocode.

The blind derivations do not remove this either — both seats read the same section 6.2. What
would remove it is a derivation from RFC 5170 rather than from `SPEC.md`. That is a larger
exercise and is recorded as an open recommendation.

## Rule 1: corroborated, not confirmed

> *"Its implementer works from `SPEC.md`, the vector manifest schema, and the cited RFC
> material where necessary. Production Java and .NET source are not used as implementation
> templates."*

This is a claim about a past process. No reviewer can confirm it from the artifacts, and
this review does not.

Corroborating it: the nine structural divergences above, several of which would be
surprising if the checker had been translated; the fact that the checker's naming tracks
spec headings and spec argument order where production differs; and Finding B, where the
checker diverged from *both* implementations by following the spec text.

Weakly corroborating: commit order. `reference/ldpc_staircase_reference.py` was committed at
2026-09-01T01:32:51 and `ReferenceCorpusTest.java` at 01:33:38, spec first. The audit
recommended checking exactly this. It is consistent with the claim but proves little, since
committing the specification change first is the repositories' standing cross-repo rule and
would have happened regardless of authoring order.

Not established: anything stronger. A reader who needs more than corroboration should treat
rule 1 as an attestation by the implementer, recorded in
[`../README.md`](../README.md#independence-record), and weigh it accordingly.

## Limits of this round

- **Isolation was directory-scoped and instruction-based, not sandboxed.** Both derivation
  seats ran as local agents that retained the technical ability to read elsewhere on the
  filesystem. Each confirmed in its notes that it worked only from its packet; those are
  self-reports. Stronger isolation means running the packet on a machine with no copy of
  this repository.
- **Model diversity is partial.** One derivation seat and the audit seat are the same model
  family, and share its blind spots. The cross-family agreement that carries weight is
  Codex against everything else.
- **The corpus is not a conformance vector set.** Nothing in this round changes what
  `vectors/` normatively requires.
- **Nothing here validates `SPEC.md` against RFC 5170 or against intent.** A defect at that
  level is invisible to all five calculations.

## Open recommendations

### 1. Extend the committed vectors to exercise section 4.3 — RESOLVED, specification 0.1.1

Done on 2026-09-01. Three matrix vectors and one encode vector were added through the
single authorized generator: `mtx-k2-r8-n1_1-s1`, `mtx-k8-r16-n1_2-s3`,
`mtx-k3-r6-n1_1-smax`, and `enc-k2-r8-n1_1-s1-len5`. Section 4.3 now adds 53 entries
across the vector set, where it added none before, and both of its branches fire.

The addition is purely additive — every vector committed at 0.1.0 is byte-identical at
0.1.1 — and was confirmed as such by comparing the regenerated manifest section by
section before and after. A regeneration with no changes was run first to establish that
generation is deterministic.

Because the generator is the Java implementation and section 4.3 was exactly the
subsection no gate covered, the new vectors were validated by every calculation that does
*not* share the generator's reading: the independent reference checker (804 to 899
checks), the Claude derivation seat (70 to 82 checks), and the Codex derivation seat (123
to 140 assertions). All pass.

### 2. Consider one derivation from RFC 5170 rather than from `SPEC.md` — OPEN, not recommended for now

Left open deliberately. This is the only one of the three that would address the audit's
section 6.2 reservation, and it is also the only one whose value is speculative. Three
things argue for leaving it:

- RFC 5170 describes a broader scheme than the profile section 1 constrains, so a seat
  working from the RFC would diverge on profile choices — `G = 1`, fixed rate, the single
  residual solve, the `K >= 2` degenerate rule — and produce disagreements that are
  scope differences rather than findings. Separating the two would take more judgement
  than the exercise saves.
- The reservation it addresses is narrow: a misreading embedded in section 6.2's own
  recovery criterion. That criterion is four sentences of standard linear algebra, and
  five implementations across four languages now agree on its consequences for 36 corpus
  cases and six decode vectors.
- The audit itself scoped it as conditional: worth doing only if the decode contract is
  ever in genuine doubt.

Revisit if a decode disagreement ever appears, or before the profile is extended.

### 3. `recoveredCount` and `recoveredRepair` rest on convention — RESOLVED, specification 0.1.1

Raised by `codex-derivation`. Investigating it showed the specification contradicted its
own vectors rather than merely leaving latitude: section 6 said reconstructing missing
repair symbols was not required, but `dec-all-repair-missing` loses only repair symbols
and requires a recovered count of `R`, so a decoder taking the stated latitude would fail
a normative vector.

Section 6 now states that decoding recovers and reports every symbol the received set
determines, with completion still judged on the source symbols alone. No conforming
implementation changes behavior; the prose was the part that was wrong. The corpus is
therefore comparing a field the contract does require, and the two fields stay in the
comparison.

## Sign-off

Completion criterion 5 of decision 0002 reads *"a reviewer confirms the independence rules
above."* The evidence above is offered for that confirmation. Rules 2 to 5 are supported by
the audit; rule 1 is corroborated only, as it can be.

No agent may grant this. Criterion 5 closes when a human signs here.

- Confirmed by: _________________________
- Date: _________________________
