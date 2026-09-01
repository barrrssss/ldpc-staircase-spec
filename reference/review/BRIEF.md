# Blind derivation brief

## Your task

Implement the LDPC-Staircase erasure code described in [`SPEC.md`](SPEC.md) from
scratch, then compute and emit a result record for each of the 31 cases in
[`corpus.json`](corpus.json).

You are producing an **independent second calculation** of these answers. Somebody else
has already computed them; you must not see their work, and your value here comes
entirely from having derived yours separately. If you agree, that is meaningful
evidence. If you disagree, that is a finding worth more than agreement.

## Rules

1. **This directory is your whole world.** Work only from the files in this packet. Do
   not read, list, search, or open anything outside it — in particular do not go looking
   for an existing implementation of this specification, in any language, anywhere on
   this machine or on the web.
2. Write your implementation from `SPEC.md`. Do not copy from any other codec.
3. Use only your language's standard library. Python 3.11+ is preferred; any language
   is acceptable if it can emit the JSON described below.
4. If `SPEC.md` is ambiguous, **do not guess silently.** Implement your best reading,
   and record the ambiguity and the reading you chose in your notes. Ambiguities you
   surface are one of the main things this exercise is for.
5. If you cannot compute a field, emit `null` for it and say why. Do not fabricate a
   plausible value.

## Self-checking against the committed vectors

`vectors/MANIFEST.json` and its `*.bin` blobs are the specification's committed
conformance vectors. Use them to check your PRNG, matrix construction, encoding, and
decoding before you compute the corpus. They will catch ordinary transcription mistakes
and let the real comparison focus on genuine differences in reading.

Report separately whether your implementation reproduces every vector.

The corpus in `corpus.json` is **not** covered by those vectors. It carries input
parameters only and no expected outcomes anywhere — no answer to any corpus case exists
in this packet.

## Corpus source symbols

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

All arithmetic is unsigned 64-bit with wraparound; `>>>` is a logical shift. The stream
is emitted as little-endian 8-byte words, concatenated, and truncated to `symbolLen`
bytes. Source symbol `esi` is drawn from its own stream, so it does not depend on `k`,
`r`, or `symbolLen`.

This rule is corpus test data only. It is not part of the codec.

As a self-check, the first four outputs of this SplitMix64 construction starting from a
raw state of `0` are `0xE220A8397B1DCDAF`, `0x6E789E6AA1B965F4`, `0x06C45D188009454F`,
`0xF88BB8A8724C81EC`.

## What to compute for each case

Build the matrix from `(k, r, n1, seed)`. Generate the `k` source symbols by the rule
above. Encode to get the `r` repair symbols. Then mark exactly the ESIs listed in
`missing` as lost, and decode from what remains.

Emit these fields per case:

| Field | Meaning |
| --- | --- |
| `name` | the case identifier, copied through unchanged |
| `k`, `r`, `n1`, `seed`, `symbolLen`, `payloadSeed` | copied through unchanged |
| `missingCount` | number of distinct ESIs in `missing` |
| `matrixEntryCount` | total number of ones in `H` |
| `matrixSha256` | SHA-256 of the canonical serialization of `H` (SPEC.md section 7.1), lowercase hex |
| `sourceSha256` | SHA-256 of source symbols `0..k-1` concatenated in ascending ESI order |
| `repairSha256` | SHA-256 of repair symbols `k..k+r-1` concatenated in ascending ESI order; the digest of the empty string when `r = 0` |
| `complete` | `true` when all `k` source symbols are available after decoding |
| `peelingSuffices` | `true` when degree-one peeling alone (SPEC.md section 6.1, run to its fixed point with no residual solve) already leaves every source symbol known. `true` when nothing was missing. |
| `recoveredCount` | how many of the missing symbols the decode determined, counting both source and repair |
| `recoveredSource` | ascending list of source ESIs that were missing and were determined |
| `recoveredRepair` | ascending list of repair ESIs that were missing and were determined |
| `missingSourceAfter` | ascending list of source ESIs still unknown after decoding |
| `recoveredSourceSha256` | SHA-256 over `k * symbolLen` bytes: source symbols `0..k-1` in order as they stand after decoding, where any source symbol still unknown contributes `symbolLen` zero bytes |

Note on `recoveredCount` and `recoveredRepair`: report every symbol your decode actually
determines, source and repair alike. SPEC.md does not require a decoder to reconstruct
missing repair symbols, but this comparison wants to know what yours determined.

## Output format

Write a single file `results.json` in your return folder:

```json
{
  "resultVersion": 1,
  "producer": "<who and what model you are>",
  "language": "<language and version you implemented in>",
  "caseCount": 31,
  "cases": [ { "name": "case-01", ... }, ... ]
}
```

Serialize with two-space indentation and sorted keys. Cases in `corpus.json` order.

Also write `NOTES.md` in the same folder covering:

- how you built it, and what decoding procedure you chose and why;
- whether every committed vector reproduced, and any that did not;
- every ambiguity you found in `SPEC.md`, the reading you chose, and what a different
  reading would have changed;
- anything you could not compute;
- confirmation that you worked only from this packet.

## What matters

Your `results.json` will be compared field by field against another independent
calculation. Take the decode semantics seriously — especially which symbols a received
set genuinely determines, and which it does not. A case where recovery fails is as
important to get right as one where it succeeds.
