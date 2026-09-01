# Notes

## Implementation

I wrote an independent JavaScript implementation from `packet/SPEC.md`, using only Node.js standard-library modules. Matrix rows are sets of column indices. Park–Miller bounded draws use JavaScript Number operations in the specified multiply-then-divide order, which are IEEE 754 binary64. Symbols are Node.js Buffers and all parity operations are byte-wise XOR.

Decoding first runs degree-one peeling to a fixed point. If any source remains unknown, it constructs the complete residual system over every unknown source and repair variable, represents coefficient rows as arbitrary-width BigInt bitsets, and performs one full GF(2) RREF reduction while applying operations to the byte-array right-hand sides. It reports only pivot variables whose RREF row has no other variable, exactly as section 6.2 specifies, and does not run peeling again. Missing repair symbols found by either stage are included in the recovery accounting.

## Conformance vectors

All committed vectors reproduced. The program passed 123 individual assertions spanning every raw and bounded PRNG expectation, every canonical matrix blob and entry count, every repair blob, and all completion/stage/recovery/missing-source expectations in every decode case.

## Ambiguities and readings

- The general parameter rule says `N1` is constrained only when `R >= 1`, while the no-repair corpus cases still carry `n1 = 1`. I treated `R = 0` as the explicit bypass: an empty matrix, no PRNG use, and no repair symbols. A reading that tried to construct the left side would require modulo zero and contradict the bypass text.
- Section 6 says repair reconstruction is not required, while the comparison requires every symbol this decoder actually determines. I let the mandated peeling stage operate on all variables even when all source symbols were already present, and report every missing repair it determines. I invoke the residual solve only when a source remains unknown, following the explicit section 6.2 trigger. A decoder that stopped immediately once sources were complete could report fewer recovered repairs without changing `complete`.
- For `peelingSuffices`, I test source availability at the peeling fixed point, regardless of whether some repairs remain unknown; this follows the field definition.
- For duplicate ESIs in `missing`, I would count and mask distinct ESIs, as required by `missingCount`. The supplied corpus contains valid in-range indices; recovery lists naturally contain each symbol at most once.

Nothing was uncomputable, so no field is `null`.

## Independence boundary

I worked only from files under `packet/`. I did not inspect, search for, or use any implementation or information elsewhere on the machine or on the web. The only files written outside `packet/` are the requested `results.json` and `NOTES.md` in the return directory.
