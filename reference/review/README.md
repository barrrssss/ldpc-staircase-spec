# Independence review round

Evidence for completion criterion 5 of
[decision 0002](../../docs/decisions/0002-independent-reference-checker.md): *a reviewer
confirms the independence rules*.

The verdict itself lives in [`independence-review.md`](independence-review.md). This file
describes how the evidence was produced, so a later reader can judge how much weight it
carries and reproduce the round.

## Why a review is not enough on its own

The independence rules of decision 0002 do not all have the same evidential status, and
running them together as one checklist would overstate what any review can establish.

Rules 2 to 5 are properties of the artifacts. Whether the checker's control flow,
naming, and data structures resemble a production implementation, whether it solves the
whole system rather than reproducing the peel-then-residual procedure, whether the
peeling routine is separate, and whether anything is imported or invoked — all of that
can be read off the files by anyone, and rule 5 is additionally asserted by the checker's
own self-tests.

Rule 1 is different. *"Its implementer works from `SPEC.md` … Production Java and .NET
source are not used as implementation templates"* is a claim about a past process, not a
property of a file. No reviewer can confirm it by reading the result. It can be
**corroborated** — the artifact differs from the production code in ways that copying
would not produce — or **falsified** — the artifact resembles it too closely to be
coincidence. It cannot be confirmed. Any review that reports rule 1 as confirmed is
overclaiming, and this round does not.

## What the round does instead

Two exercises, aimed at the two halves.

**Blind re-derivation, for the mathematics.** Independent agents receive a self-contained
packet and implement the specification from scratch, then compute results for the same
differential corpus. This does not audit the checker at all. It produces a further
independent calculation of the same answers, which is stronger evidence than any reading
of the checker could be: it attacks the shared-misreading failure mode that decision 0002
exists to address, rather than asking whether one artifact looks like another.

**Similarity audit, for the copying claim.** A separate agent receives the checker *and*
both production implementations and is asked to hunt for evidence of translation, with
instructions to distinguish genuine evidence of copying from convergence the
specification forces on any correct implementation. This is the strongest available
corroboration of rule 1 and the direct test of rules 2 to 5.

Neither exercise closes criterion 5 by itself. Together they are the evidence; a human
grants the confirmation.

## The packet

[`BRIEF.md`](BRIEF.md) is the brief as issued. Each blind seat received exactly:

- `BRIEF.md`
- `SPEC.md`, the normative specification
- `vectors/`, the committed conformance vectors and manifest, for self-checking
- `corpus.json`, the differential corpus in the anonymised form kept here as
  [`corpus-anonymised.json`](corpus-anonymised.json)

Deliberately withheld: `reference/` in any form (the checker, its self-tests, and its
README), decision 0002, `HISTORY.md`, the repository README, and all Java and .NET
source. Each of those either contains the checker's design rationale or points at it.

The corpus was anonymised rather than shipped as committed, because the committed form
leaks its own answers. Case names such as `k100-r50-rank-deficient` and
`k250-r125-n1_7-residual` state the expected outcome category, and each case's `note`
field describes what the decode is expected to do. In the packet every case is renamed
`case-01` through `case-31` and the notes are stripped; the mapping back to real names
was kept outside the packet and applied only when scoring. The parameters, seeds, and
loss sets are unchanged.

The committed vectors *were* included. They carry no corpus answers, and letting a seat
validate its PRNG, matrix construction, and encoding against the specification's own
conformance data keeps the comparison focused on genuine differences in reading rather
than on transcription slips.

## Isolation, and its limits

Each blind seat ran in its own directory containing only its copy of the packet, with no
seat able to see another's return, and was instructed not to read anything outside that
directory, not to search the machine for an existing implementation, and not to consult
the web.

**This isolation is directory-scoped and instruction-based, not sandboxed.** A local
agent retains the ability to read elsewhere on the filesystem. Each seat was asked to
confirm in its notes that it worked only from the packet, and those confirmations are
recorded with the returns, but they are self-reports. A reader who wants stronger
isolation should re-run the round with the packet on a machine that has no copy of this
repository.

Model diversity matters here for the same reason it does in any multi-reviewer round: two
seats from the same model family share training and therefore share blind spots. The
seats and their models are listed in [`independence-review.md`](independence-review.md).

## Reproducing the round

1. Build the packet: `SPEC.md`, `vectors/`, and an anonymised `corpus.json` with `note`
   fields stripped and case names replaced, keeping the mapping outside the packet.
2. Give each seat its own copy, with `BRIEF.md` and the isolation instruction.
3. Score each return against the checker's own output for the same corpus, joining on the
   anonymised names:

   ```sh
   python reference/ldpc_staircase_reference.py emit-corpus reference/corpus.json --out baseline.json
   ```

   then compare the twelve outcome fields listed in `BRIEF.md` case by case.
4. Run the similarity audit against the checker and both production implementations.
5. Record every disagreement, and treat each one as a question about the specification
   before treating it as a defect in any implementation.
