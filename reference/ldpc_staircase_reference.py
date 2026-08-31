#!/usr/bin/env python3
"""Independent reference checker for the ldpc-staircase specification.

This module is *verification tooling*, not a third production implementation. It
is derived from ``SPEC.md`` alone, uses only the Python standard library, and
never imports, loads, or invokes the Java or .NET implementations. See
``reference/README.md`` for the provenance record and the independence rules of
decision 0002.

The decoder here is deliberately naive: instead of reproducing the profile's
peeling-plus-one-residual-solve control flow, it asks the underlying
mathematical question directly by reducing the *whole* parity-check system over
GF(2) to reduced row echelon form. A variable is recoverable exactly when the
received equations determine it uniquely. A small, separate peeling routine is
kept alongside it only to distinguish peeling-only cases from cases that
genuinely need the residual solve.

Usage:

    python reference/ldpc_staircase_reference.py check-vectors vectors/MANIFEST.json
    python reference/ldpc_staircase_reference.py emit-corpus reference/corpus.json --out OUT.json
    python reference/ldpc_staircase_reference.py check-corpus reference/corpus.json OUT.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

if sys.version_info < (3, 11):  # pragma: no cover - guarded at import time
    raise SystemExit("ldpc_staircase_reference requires Python 3.11 or newer")


# --------------------------------------------------------------------------
# SPEC.md section 3 - Park-Miller "minimal standard" generator
# --------------------------------------------------------------------------

PRNG_MULTIPLIER = 16807
PRNG_MODULUS = 2147483647
PRNG_MIN_SEED = 1
PRNG_MAX_SEED = 0x7FFFFFFE
INT32_MAX = 0x7FFFFFFF


class SpecViolation(Exception):
    """Raised when inputs fall outside the normative profile, or data is malformed."""


class ParkMiller:
    """The multiplicative congruential generator required by SPEC.md section 3."""

    __slots__ = ("state",)

    def __init__(self, seed: int) -> None:
        if not (PRNG_MIN_SEED <= seed <= PRNG_MAX_SEED):
            raise SpecViolation(
                f"seed {seed} outside the required range [{PRNG_MIN_SEED}, {PRNG_MAX_SEED}]"
            )
        self.state = seed

    def next_raw(self) -> int:
        """Advance the stream and return the raw state, in [1, 2147483646]."""
        self.state = (PRNG_MULTIPLIER * self.state) % PRNG_MODULUS
        return self.state

    def bounded(self, maxv: int) -> int:
        """``rand(maxv)`` of SPEC.md section 3, in [0, maxv - 1].

        The scaling is evaluated in IEEE 754 binary64 in the normative order:
        multiply, divide, then truncate toward zero. Python floats are binary64
        with correctly rounded arithmetic, so ``float(maxv) * float(raw)``
        reproduces the specified rounding rather than the exact-integer result
        the specification explicitly rejects.
        """
        if maxv < 1:
            raise SpecViolation(f"rand(maxv) requires maxv >= 1, got {maxv}")
        raw = self.next_raw()
        return int(float(maxv) * float(raw) / 2147483647.0)


# --------------------------------------------------------------------------
# SPEC.md section 4 - parity check matrix
# --------------------------------------------------------------------------


class ParityCheckMatrix:
    """An ``R x N`` GF(2) parity check matrix, stored as one column set per row."""

    __slots__ = ("k", "r", "n1", "seed", "n", "rows", "_columns")

    def __init__(self, k: int, r: int, n1: int, seed: int) -> None:
        self.k = k
        self.r = r
        self.n1 = n1
        self.seed = seed
        self.n = k + r
        self.rows: List[Set[int]] = [set() for _ in range(r)]
        self._columns: List[Set[int]] = [set() for _ in range(self.n)]

    # SPEC.md section 4.1 notation -----------------------------------------
    def has(self, row: int, column: int) -> bool:
        return column in self.rows[row]

    def set(self, row: int, column: int) -> None:
        if column in self.rows[row]:
            raise SpecViolation(f"set({row}, {column}) called for an entry already 1")
        self.rows[row].add(column)
        self._columns[column].add(row)

    def rows_of_column(self, column: int) -> Set[int]:
        return self._columns[column]

    def left_degree(self, row: int) -> int:
        """``degree(i)`` of SPEC.md section 4: ones in the left (source) part only."""
        return sum(1 for column in self.rows[row] if column < self.k)

    def entry_count(self) -> int:
        return sum(len(row) for row in self.rows)

    def left_columns(self, row: int) -> List[int]:
        return sorted(column for column in self.rows[row] if column < self.k)

    def serialize(self) -> bytes:
        """The canonical serialization of SPEC.md section 7.1."""
        out = bytearray()
        out += self.r.to_bytes(4, "big")
        out += self.n.to_bytes(4, "big")
        for row in self.rows:
            columns = sorted(row)
            out += len(columns).to_bytes(4, "big")
            for column in columns:
                out += column.to_bytes(4, "big")
        return bytes(out)


def validate_parameters(k: int, r: int, n1: int, seed: int) -> None:
    """Enforce the parameter rules of SPEC.md section 2."""
    if k < 1:
        raise SpecViolation(f"K must be >= 1, got {k}")
    if r < 0:
        raise SpecViolation(f"R must be >= 0, got {r}")
    if r >= 1 and not (1 <= n1 <= r):
        raise SpecViolation(f"N1 must satisfy 1 <= N1 <= R, got N1={n1} R={r}")
    if not (PRNG_MIN_SEED <= seed <= PRNG_MAX_SEED):
        raise SpecViolation(f"seed {seed} outside [{PRNG_MIN_SEED}, {PRNG_MAX_SEED}]")
    if n1 * k > INT32_MAX:
        raise SpecViolation(f"N1 * K = {n1 * k} exceeds the signed 32-bit bound")


def build_matrix(k: int, r: int, n1: int, seed: int) -> ParityCheckMatrix:
    """Build ``H`` in the three normative ordered phases of SPEC.md section 4."""
    validate_parameters(k, r, n1, seed)
    matrix = ParityCheckMatrix(k, r, n1, seed)
    if r == 0:
        # SPEC.md section 2: R = 0 is the explicit no-repair bypass. The matrix
        # is empty and no PRNG draw is consumed.
        return matrix

    prng = ParkMiller(seed)
    _fill_left_part(matrix, prng)
    _raise_low_degree_rows(matrix, prng)
    _add_staircase(matrix)
    return matrix


def _fill_left_part(matrix: ParityCheckMatrix, prng: ParkMiller) -> None:
    """SPEC.md section 4.2 - place ``N1`` ones in every source column."""
    k, r, n1 = matrix.k, matrix.r, matrix.n1
    pool_size = n1 * k
    pool = [h % r for h in range(pool_size)]
    t = 0

    for column in range(k):
        for _ in range(n1):
            # The normative forward scan over the still-available pool slots.
            scan = pool_size
            for candidate in range(t, pool_size):
                if not matrix.has(pool[candidate], column):
                    scan = candidate
                    break

            if scan < pool_size:
                while True:
                    index = t + prng.bounded(pool_size - t)
                    if not matrix.has(pool[index], column):
                        break
                matrix.set(pool[index], column)
                pool[index] = pool[t]
                t += 1
            else:
                while True:
                    row = prng.bounded(r)
                    if not matrix.has(row, column):
                        break
                matrix.set(row, column)


def _raise_low_degree_rows(matrix: ParityCheckMatrix, prng: ParkMiller) -> None:
    """SPEC.md section 4.3 - raise rows with fewer than two left-part ones.

    The two conditions are sequential rather than exclusive, so a row of degree
    zero is raised to one and then to two within the same iteration.
    """
    k, r = matrix.k, matrix.r
    for row in range(r):
        if matrix.left_degree(row) == 0:
            matrix.set(row, prng.bounded(k))
        if matrix.left_degree(row) == 1 and k >= 2:
            while True:
                column = prng.bounded(k)
                if not matrix.has(row, column):
                    break
            matrix.set(row, column)


def _add_staircase(matrix: ParityCheckMatrix) -> None:
    """SPEC.md section 4.4 - the right part. Consumes no PRNG draws."""
    k, r = matrix.k, matrix.r
    matrix.set(0, k)
    for row in range(1, r):
        matrix.set(row, k + row)
        matrix.set(row, k + row - 1)


# --------------------------------------------------------------------------
# SPEC.md section 5 - encode
# --------------------------------------------------------------------------


def _xor_into(target: bytearray, source: bytes) -> None:
    for index, value in enumerate(source):
        target[index] ^= value


def encode(matrix: ParityCheckMatrix, source: Sequence[bytes]) -> List[bytes]:
    """Produce the ``R`` repair symbols of SPEC.md section 5, in ascending ESI order."""
    if len(source) != matrix.k:
        raise SpecViolation(f"expected {matrix.k} source symbols, got {len(source)}")
    symbol_len = len(source[0])
    if symbol_len < 1:
        raise SpecViolation("symbol length S must be greater than 0")
    for symbol in source:
        if len(symbol) != symbol_len:
            raise SpecViolation("all symbols in one operation must share length S")

    repair: List[bytes] = []
    previous: Optional[bytes] = None
    for row in range(matrix.r):
        accumulator = bytearray(symbol_len)
        for column in matrix.left_columns(row):
            _xor_into(accumulator, source[column])
        if previous is not None:
            _xor_into(accumulator, previous)
        previous = bytes(accumulator)
        repair.append(previous)
    return repair


# --------------------------------------------------------------------------
# SPEC.md section 6 - recovery
# --------------------------------------------------------------------------


class RecoveryOutcome:
    """What a received set determines: the recovered symbols and what is left."""

    __slots__ = ("recovered", "complete", "missing_source", "symbols")

    def __init__(
        self,
        recovered: Dict[int, bytes],
        complete: bool,
        missing_source: List[int],
        symbols: List[Optional[bytes]],
    ) -> None:
        self.recovered = recovered
        self.complete = complete
        self.missing_source = missing_source
        self.symbols = symbols


def _require_a_received_symbol(present: Sequence[bool]) -> None:
    """SPEC.md section 6: at least one symbol must be present.

    The symbol length is read from a received symbol, so an entirely empty
    received set leaves ``S`` undefined and is a caller error rather than an
    incomplete decode.
    """
    if not any(present):
        raise SpecViolation(
            "decode requires at least one present symbol; an empty received set "
            "leaves the symbol length undefined (SPEC.md section 6)"
        )


def solve_whole_system(
    matrix: ParityCheckMatrix,
    symbols: Sequence[Optional[bytes]],
    present: Sequence[bool],
    symbol_len: int,
) -> RecoveryOutcome:
    """Decide recoverability by reducing the complete GF(2) system to RREF.

    This is the independent oracle. Every parity equation of ``H`` is taken at
    once, the missing symbols are the variables, and the received symbols are
    folded into the right-hand sides. A variable is recoverable exactly when it
    is a pivot whose reduced row contains no other variable, which is the
    maximal set of variables the received symbols determine. No peeling order,
    residual partition, or stage bookkeeping is involved, so the answer does not
    depend on any decoder policy.

    Coefficient rows are carried as Python integers used as bit sets over the
    unknown variables, and each right-hand side is the big-endian integer view
    of a symbol, so one integer XOR performs a full row operation on both.
    """
    _require_a_received_symbol(present)
    unknown = [column for column in range(matrix.n) if not present[column]]
    position = {column: index for index, column in enumerate(unknown)}

    equations: List[List[int]] = []
    for row in range(matrix.r):
        mask = 0
        rhs = 0
        for column in matrix.rows[row]:
            if present[column]:
                value = symbols[column]
                if value is None:
                    raise SpecViolation(f"symbol {column} is marked present but has no bytes")
                rhs ^= int.from_bytes(value, "big")
            else:
                mask |= 1 << position[column]
        if mask:
            equations.append([mask, rhs])
        elif rhs != 0:
            raise SpecViolation(
                f"row {row} is fully received but its symbols do not XOR to zero; "
                "the supplied symbol data contradicts the parity check matrix"
            )

    # Gauss-Jordan elimination straight to reduced row echelon form.
    pivot_row_of: Dict[int, int] = {}
    consumed = [False] * len(equations)
    for index in range(len(unknown)):
        bit = 1 << index
        pivot = -1
        for candidate in range(len(equations)):
            if not consumed[candidate] and (equations[candidate][0] & bit):
                pivot = candidate
                break
        if pivot < 0:
            continue
        consumed[pivot] = True
        pivot_row_of[index] = pivot
        pivot_mask, pivot_rhs = equations[pivot]
        for other in range(len(equations)):
            if other != pivot and (equations[other][0] & bit):
                equations[other][0] ^= pivot_mask
                equations[other][1] ^= pivot_rhs

    recovered: Dict[int, bytes] = {}
    for index, column in enumerate(unknown):
        pivot = pivot_row_of.get(index)
        if pivot is None:
            continue
        mask, rhs = equations[pivot]
        if mask == (1 << index):
            recovered[column] = rhs.to_bytes(symbol_len, "big")

    resolved: List[Optional[bytes]] = list(symbols)
    for column, value in recovered.items():
        resolved[column] = value
    missing_source = [column for column in range(matrix.k) if resolved[column] is None]
    return RecoveryOutcome(recovered, not missing_source, missing_source, resolved)


def peel(
    matrix: ParityCheckMatrix,
    symbols: Sequence[Optional[bytes]],
    present: Sequence[bool],
    symbol_len: int,
) -> RecoveryOutcome:
    """SPEC.md section 6.1 alone - degree-one peeling to a fixed point.

    Kept deliberately separate from :func:`solve_whole_system` so that
    peeling-only vector cases can be distinguished from cases that genuinely
    need the residual solve. It is never used to answer the recoverability
    question itself.
    """
    _require_a_received_symbol(present)
    values: List[Optional[bytes]] = list(symbols)
    known = list(present)
    unresolved: List[Set[int]] = []
    accumulator: List[bytearray] = []
    for row in range(matrix.r):
        pending: Set[int] = set()
        accum = bytearray(symbol_len)
        for column in matrix.rows[row]:
            if known[column]:
                value = values[column]
                if value is None:
                    raise SpecViolation(f"symbol {column} is marked present but has no bytes")
                _xor_into(accum, value)
            else:
                pending.add(column)
        unresolved.append(pending)
        accumulator.append(accum)

    recovered: Dict[int, bytes] = {}
    ready = [row for row in range(matrix.r) if len(unresolved[row]) == 1]
    while ready:
        row = ready.pop()
        if len(unresolved[row]) != 1:
            continue
        column = next(iter(unresolved[row]))
        value = bytes(accumulator[row])
        unresolved[row].clear()
        values[column] = value
        known[column] = True
        recovered[column] = value
        for other in matrix.rows_of_column(column):
            if column in unresolved[other]:
                unresolved[other].discard(column)
                _xor_into(accumulator[other], value)
                if len(unresolved[other]) == 1:
                    ready.append(other)

    missing_source = [column for column in range(matrix.k) if values[column] is None]
    return RecoveryOutcome(recovered, not missing_source, missing_source, values)


# --------------------------------------------------------------------------
# Deterministic corpus payloads
# --------------------------------------------------------------------------

MASK64 = 0xFFFFFFFFFFFFFFFF
GOLDEN_GAMMA = 0x9E3779B97F4A7C15
SPLITMIX_MIX_1 = 0xBF58476D1CE4E5B9
SPLITMIX_MIX_2 = 0x94D049BB133111EB


def _splitmix64(state: int) -> Tuple[int, int]:
    state = (state + GOLDEN_GAMMA) & MASK64
    z = state
    z = ((z ^ (z >> 30)) * SPLITMIX_MIX_1) & MASK64
    z = ((z ^ (z >> 27)) * SPLITMIX_MIX_2) & MASK64
    return state, (z ^ (z >> 31)) & MASK64


def corpus_symbol(payload_seed: int, esi: int, symbol_len: int) -> bytes:
    """The differential corpus payload rule; see ``reference/README.md``.

    Each symbol is an independent SplitMix64 stream keyed by the case payload
    seed and the symbol's ESI, emitted as little-endian 64-bit words and
    truncated to ``S`` bytes. Keying per ESI keeps a symbol's bytes independent
    of the case's ``K``, ``R``, and symbol length. This rule is corpus test data
    only; it is not part of the normative codec.
    """
    state = (payload_seed ^ ((esi + 1) * GOLDEN_GAMMA)) & MASK64
    out = bytearray()
    while len(out) < symbol_len:
        state, word = _splitmix64(state)
        out += word.to_bytes(8, "little")
    return bytes(out[:symbol_len])


def corpus_source_symbols(payload_seed: int, k: int, symbol_len: int) -> List[bytes]:
    return [corpus_symbol(payload_seed, esi, symbol_len) for esi in range(k)]


# --------------------------------------------------------------------------
# Vector checking
# --------------------------------------------------------------------------


class CheckReport:
    """A running tally of individual checks and their failure messages."""

    def __init__(self) -> None:
        self.checks = 0
        self.failures: List[str] = []

    def ok(self) -> None:
        self.checks += 1

    def fail(self, message: str) -> None:
        self.checks += 1
        self.failures.append(message)

    def expect(self, condition: bool, message: str) -> bool:
        if condition:
            self.ok()
            return True
        self.fail(message)
        return False

    def expect_equal(self, actual: object, expected: object, message: str) -> bool:
        return self.expect(
            actual == expected, f"{message}: expected {expected!r}, got {actual!r}"
        )


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_blob(vectors_dir: Path, name: str) -> bytes:
    path = vectors_dir / name
    if not path.is_file():
        raise SpecViolation(f"referenced vector file is missing: {path}")
    return path.read_bytes()


def _split_symbols(blob: bytes, count: int, symbol_len: int, label: str) -> List[bytes]:
    expected = count * symbol_len
    if len(blob) != expected:
        raise SpecViolation(
            f"{label}: expected {expected} bytes for {count} symbols of {symbol_len}, "
            f"got {len(blob)}"
        )
    return [blob[i * symbol_len : (i + 1) * symbol_len] for i in range(count)]


def _require_list(manifest: dict, key: str) -> list:
    value = manifest.get(key)
    if not isinstance(value, list):
        raise SpecViolation(f"manifest section {key!r} is missing or not a list")
    return value


def check_files(manifest: dict, vectors_dir: Path, report: CheckReport) -> None:
    """Canonical vector file lengths and SHA-256 digests."""
    for entry in _require_list(manifest, "files"):
        path = vectors_dir / entry["path"]
        if not path.is_file():
            report.fail(f"files[{entry['path']}]: file is missing")
            continue
        data = path.read_bytes()
        report.expect_equal(len(data), entry["length"], f"files[{entry['path']}] length")
        report.expect_equal(_sha256(data), entry["sha256"], f"files[{entry['path']}] sha256")


def check_prng(manifest: dict, report: CheckReport) -> None:
    """Raw Park-Miller values and the IEEE 754 bounded scaling."""
    for case in _require_list(manifest, "prngRaw"):
        prng = ParkMiller(case["seed"])
        expected = {item["ordinal"]: item["value"] for item in case["values"]}
        highest = max(expected)
        for ordinal in range(1, highest + 1):
            value = prng.next_raw()
            if ordinal in expected:
                report.expect_equal(
                    value, expected[ordinal], f"prngRaw[{case['name']}] ordinal {ordinal}"
                )

    for case in _require_list(manifest, "prngBounded"):
        prng = ParkMiller(case["seed"])
        maxv = case["maxv"]
        actual = [prng.bounded(maxv) for _ in case["draws"]]
        report.expect_equal(actual, list(case["draws"]), f"prngBounded[{case['name']}] draws")

    # RFC 5170 section 5.7 validation criterion, restated in SPEC.md section 3.
    prng = ParkMiller(1)
    for _ in range(9999):
        prng.next_raw()
    report.expect_equal(prng.next_raw(), 1043618065, "RFC 5170 seed=1 10000th value")


def check_matrices(manifest: dict, vectors_dir: Path, report: CheckReport) -> None:
    """Matrix construction, canonical serialization, and structural invariants."""
    for case in _require_list(manifest, "matrix"):
        matrix = build_matrix(case["k"], case["r"], case["n1"], case["seed"])
        report.expect_equal(
            matrix.entry_count(), case["entryCount"], f"matrix[{case['name']}] entryCount"
        )
        expected = _read_blob(vectors_dir, case["file"])
        serialized = matrix.serialize()
        report.expect_equal(
            len(serialized), len(expected), f"matrix[{case['name']}] serialized length"
        )
        report.expect(
            serialized == expected,
            f"matrix[{case['name']}]: canonical serialization differs from {case['file']}",
        )
        check_matrix_invariants(matrix, case["name"], report)


def check_matrix_invariants(matrix: ParityCheckMatrix, name: str, report: CheckReport) -> None:
    """Structural properties SPEC.md section 4 guarantees, checked independently."""
    if matrix.r == 0:
        report.expect(
            matrix.entry_count() == 0, f"matrix[{name}]: R = 0 must yield an empty matrix"
        )
        return

    for column in range(matrix.k):
        ones = len(matrix.rows_of_column(column))
        report.expect(
            ones >= matrix.n1,
            f"matrix[{name}]: source column {column} has {ones} ones, "
            f"expected at least N1={matrix.n1}",
        )

    minimum_degree = 2 if matrix.k >= 2 else 1
    for row in range(matrix.r):
        degree = matrix.left_degree(row)
        report.expect(
            degree >= minimum_degree,
            f"matrix[{name}]: row {row} left degree {degree} is below the "
            f"section 4.3 minimum {minimum_degree}",
        )

    right_part = set(range(matrix.k, matrix.n))
    report.expect(
        matrix.rows[0] & right_part == {matrix.k},
        f"matrix[{name}]: row 0 right part must be exactly column K",
    )
    for row in range(1, matrix.r):
        report.expect(
            matrix.rows[row] & right_part == {matrix.k + row, matrix.k + row - 1},
            f"matrix[{name}]: row {row} right part must be the staircase pair",
        )


EncodedCase = Tuple[dict, ParityCheckMatrix, List[bytes], List[bytes]]


def check_encodes(manifest: dict, vectors_dir: Path, report: CheckReport) -> Dict[str, EncodedCase]:
    """Repair symbol generation for every committed encode vector."""
    encoded: Dict[str, EncodedCase] = {}
    for case in _require_list(manifest, "encode"):
        name = case["name"]
        symbol_len = case["symbolLen"]
        matrix = build_matrix(case["k"], case["r"], case["n1"], case["seed"])
        source = _split_symbols(
            _read_blob(vectors_dir, case["sourceBlob"]),
            case["k"],
            symbol_len,
            f"encode[{name}] source blob",
        )
        expected_repair = _split_symbols(
            _read_blob(vectors_dir, case["repairBlob"]),
            case["r"],
            symbol_len,
            f"encode[{name}] repair blob",
        )
        repair = encode(matrix, source)
        report.expect_equal(len(repair), case["r"], f"encode[{name}] repair count")
        mismatched = [
            index
            for index, (actual, wanted) in enumerate(zip(repair, expected_repair))
            if actual != wanted
        ]
        report.expect(
            not mismatched,
            f"encode[{name}]: repair symbols {mismatched[:8]} differ from the vector",
        )
        check_parity_holds(matrix, source, repair, name, report)
        encoded[name] = (case, matrix, source, repair)
    return encoded


def check_parity_holds(
    matrix: ParityCheckMatrix,
    source: Sequence[bytes],
    repair: Sequence[bytes],
    name: str,
    report: CheckReport,
) -> None:
    """Every equation of SPEC.md section 4 must XOR to zero over the codeword."""
    symbols = list(source) + list(repair)
    symbol_len = len(symbols[0])
    for row in range(matrix.r):
        accumulator = bytearray(symbol_len)
        for column in matrix.rows[row]:
            _xor_into(accumulator, symbols[column])
        if any(accumulator):
            report.fail(f"encode[{name}]: parity equation {row} does not XOR to zero")
            return
    report.ok()


def check_decodes(manifest: dict, encoded: Dict[str, EncodedCase], report: CheckReport) -> None:
    """Recoverability and recovered bytes for every committed decode vector."""
    for case in _require_list(manifest, "decode"):
        name = case["name"]
        reference = encoded.get(case["encodeCase"])
        if reference is None:
            report.fail(f"decode[{name}]: unknown encodeCase {case['encodeCase']!r}")
            continue
        encode_case, matrix, source, repair = reference
        symbol_len = encode_case["symbolLen"]
        codeword = list(source) + list(repair)

        missing = set(case["missing"])
        present = [index not in missing for index in range(matrix.n)]
        received: List[Optional[bytes]] = [
            codeword[index] if present[index] else None for index in range(matrix.n)
        ]

        outcome = solve_whole_system(matrix, received, present, symbol_len)
        report.expect_equal(outcome.complete, case["expectComplete"], f"decode[{name}] complete")
        report.expect_equal(
            len(outcome.recovered),
            case["expectRecoveredSymbols"],
            f"decode[{name}] recovered symbol count",
        )
        report.expect_equal(
            outcome.missing_source,
            list(case["expectMissingSource"]),
            f"decode[{name}] source indices still missing",
        )
        wrong = [
            column for column, value in outcome.recovered.items() if value != codeword[column]
        ]
        report.expect(
            not wrong, f"decode[{name}]: recovered symbols {sorted(wrong)[:8]} have the wrong bytes"
        )

        check_stage_consistency(matrix, received, present, symbol_len, case, report)


def check_stage_consistency(
    matrix: ParityCheckMatrix,
    received: Sequence[Optional[bytes]],
    present: Sequence[bool],
    symbol_len: int,
    case: dict,
    report: CheckReport,
) -> None:
    """Cross-check the recorded stage against a direct peeling run.

    The checker deliberately does not reproduce the production stage and pass
    counters. It can still verify the one stage claim that follows from the
    mathematics alone: whether degree-one peeling by itself reaches every source
    symbol.
    """
    name = case["name"]
    stage = case["expectStage"]
    if stage == "NONE":
        report.expect(
            all(present), f"decode[{name}]: stage NONE requires a complete received set"
        )
        return

    peeled = peel(matrix, received, present, symbol_len)
    if stage == "PEELING":
        report.expect(
            peeled.complete,
            f"decode[{name}]: stage PEELING claimed, but peeling alone leaves "
            f"{len(peeled.missing_source)} source symbols missing",
        )
    elif stage == "RESIDUAL_SOLVE":
        report.expect(
            not peeled.complete,
            f"decode[{name}]: stage RESIDUAL_SOLVE claimed, but peeling alone already completes",
        )
    else:
        report.fail(f"decode[{name}]: unrecognised stage {stage!r}")


def check_zero_repair(report: CheckReport) -> None:
    """The explicit ``R = 0`` behavior of SPEC.md section 2."""
    matrix = build_matrix(4, 0, 1, 1)
    report.expect_equal(matrix.entry_count(), 0, "R=0: the matrix must be empty")
    report.expect_equal(matrix.n, 4, "R=0: N must equal K")
    report.expect_equal(
        matrix.serialize(),
        (0).to_bytes(4, "big") + (4).to_bytes(4, "big"),
        "R=0: canonical serialization",
    )

    source = corpus_source_symbols(0xA5A5, 4, 16)
    report.expect_equal(encode(matrix, source), [], "R=0: encoding must be a no-op")

    outcome = solve_whole_system(matrix, list(source), [True] * 4, 16)
    report.expect(outcome.complete, "R=0: a complete received set must decode")

    partial: List[Optional[bytes]] = [source[0], source[1], None, source[3]]
    outcome = solve_whole_system(matrix, partial, [True, True, False, True], 16)
    report.expect(not outcome.complete, "R=0: any missing source symbol must fail")
    report.expect_equal(outcome.missing_source, [2], "R=0: the lost index must be reported")


def check_vectors(manifest_path: Path, report: CheckReport) -> None:
    """Run every vector family in the manifest against the specification."""
    vectors_dir = manifest_path.parent
    if not manifest_path.is_file():
        raise SpecViolation(f"manifest not found: {manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise SpecViolation(f"malformed manifest {manifest_path}: {error}") from error
    if not isinstance(manifest, dict):
        raise SpecViolation(f"malformed manifest {manifest_path}: top level is not an object")
    if manifest.get("manifestVersion") != 1:
        raise SpecViolation(
            f"unsupported manifestVersion {manifest.get('manifestVersion')!r}; "
            "this checker reads version 1"
        )

    check_files(manifest, vectors_dir, report)
    check_prng(manifest, report)
    check_matrices(manifest, vectors_dir, report)
    encoded = check_encodes(manifest, vectors_dir, report)
    check_decodes(manifest, encoded, report)
    check_zero_repair(report)


# --------------------------------------------------------------------------
# Deterministic differential corpus
# --------------------------------------------------------------------------

CORPUS_RESULT_VERSION = 1


def _corpus_cases(corpus: object) -> List[dict]:
    if not isinstance(corpus, dict):
        raise SpecViolation("malformed corpus definition: top level is not an object")
    if corpus.get("corpusVersion") != 1:
        raise SpecViolation(
            f"unsupported corpusVersion {corpus.get('corpusVersion')!r}; "
            "this checker reads version 1"
        )
    cases = corpus.get("cases")
    if not isinstance(cases, list) or not cases:
        raise SpecViolation("malformed corpus definition: 'cases' must be a non-empty list")
    return cases


def run_corpus_case(case: dict) -> dict:
    """Compute the deterministic result record for one differential corpus case."""
    k = case["k"]
    r = case["r"]
    n1 = case["n1"]
    seed = case["seed"]
    symbol_len = case["symbolLen"]
    payload_seed = case["payloadSeed"]

    matrix = build_matrix(k, r, n1, seed)
    source = corpus_source_symbols(payload_seed, k, symbol_len)
    repair = encode(matrix, source)
    codeword = list(source) + list(repair)

    missing = sorted(set(case["missing"]))
    for index in missing:
        if not 0 <= index < matrix.n:
            raise SpecViolation(
                f"corpus case {case['name']!r}: missing index {index} outside [0, {matrix.n})"
            )
    absent = set(missing)
    if len(absent) == matrix.n:
        raise SpecViolation(
            f"corpus case {case['name']!r}: an empty received set is not a decode "
            "(SPEC.md section 6)"
        )
    present = [index not in absent for index in range(matrix.n)]
    received: List[Optional[bytes]] = [
        codeword[index] if present[index] else None for index in range(matrix.n)
    ]

    outcome = solve_whole_system(matrix, received, present, symbol_len)
    peeled = peel(matrix, received, present, symbol_len)

    for column, value in outcome.recovered.items():
        if value != codeword[column]:
            raise SpecViolation(
                f"corpus case {case['name']!r}: recovered symbol {column} does not match the codeword"
            )

    recovered_source = b"".join(
        outcome.symbols[column] or b"\x00" * symbol_len for column in range(k)
    )

    return {
        "name": case["name"],
        "k": k,
        "r": r,
        "n1": n1,
        "seed": seed,
        "symbolLen": symbol_len,
        "payloadSeed": payload_seed,
        "missingCount": len(missing),
        "matrixEntryCount": matrix.entry_count(),
        "matrixSha256": _sha256(matrix.serialize()),
        "sourceSha256": _sha256(b"".join(source)),
        "repairSha256": _sha256(b"".join(repair)),
        "complete": outcome.complete,
        "peelingSuffices": peeled.complete,
        "recoveredCount": len(outcome.recovered),
        "recoveredSource": sorted(c for c in outcome.recovered if c < k),
        "recoveredRepair": sorted(c for c in outcome.recovered if c >= k),
        "missingSourceAfter": outcome.missing_source,
        "recoveredSourceSha256": _sha256(recovered_source),
    }


def run_corpus(corpus_path: Path) -> dict:
    """Run the whole committed differential corpus and build the result document."""
    if not corpus_path.is_file():
        raise SpecViolation(f"corpus definition not found: {corpus_path}")
    try:
        corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise SpecViolation(f"malformed corpus definition {corpus_path}: {error}") from error
    cases = _corpus_cases(corpus)
    names = [case["name"] for case in cases]
    if len(set(names)) != len(names):
        raise SpecViolation("malformed corpus definition: case names must be unique")
    return {
        "resultVersion": CORPUS_RESULT_VERSION,
        "corpusVersion": corpus["corpusVersion"],
        "corpusName": corpus.get("name", corpus_path.stem),
        "producer": "ldpc-staircase-spec reference checker",
        "caseCount": len(cases),
        "cases": [run_corpus_case(case) for case in cases],
    }


def canonical_json(document: dict) -> str:
    """The one deterministic serialization every consumer of the corpus reads."""
    return json.dumps(document, indent=2, sort_keys=True, ensure_ascii=True) + "\n"


def compare_corpus(expected: dict, actual: dict) -> List[str]:
    """Return human-readable differences between two corpus result documents."""
    differences: List[str] = []
    if expected.get("resultVersion") != actual.get("resultVersion"):
        differences.append(
            f"resultVersion: expected {expected.get('resultVersion')!r}, "
            f"got {actual.get('resultVersion')!r}"
        )
    expected_cases = {case["name"]: case for case in expected.get("cases", [])}
    actual_cases = {case["name"]: case for case in actual.get("cases", [])}
    for name in sorted(set(expected_cases) - set(actual_cases)):
        differences.append(f"case {name}: expected but absent from the actual results")
    for name in sorted(set(actual_cases) - set(expected_cases)):
        differences.append(f"case {name}: present in the actual results but not expected")
    for name in sorted(set(expected_cases) & set(actual_cases)):
        left = expected_cases[name]
        right = actual_cases[name]
        for key in sorted(set(left) | set(right)):
            if left.get(key) != right.get(key):
                differences.append(
                    f"case {name} field {key}: expected {left.get(key)!r}, got {right.get(key)!r}"
                )
    return differences


# --------------------------------------------------------------------------
# Command line
# --------------------------------------------------------------------------


def _report_exit(report: CheckReport, label: str, verbose: bool) -> int:
    if report.failures:
        print(
            f"FAIL: {label}: {len(report.failures)} of {report.checks} checks failed",
            file=sys.stderr,
        )
        for line in report.failures[:50]:
            print(f"  - {line}", file=sys.stderr)
        if len(report.failures) > 50:
            print(f"  ... and {len(report.failures) - 50} more", file=sys.stderr)
        return 1
    print(f"OK: {label}: {report.checks} checks passed")
    if verbose:
        print("No production implementation was imported, loaded, or invoked.")
    return 0


def _cmd_check_vectors(args: argparse.Namespace) -> int:
    manifest_path = Path(args.manifest)
    report = CheckReport()
    try:
        check_vectors(manifest_path, report)
    except SpecViolation as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 2
    return _report_exit(report, f"vectors {manifest_path}", args.verbose)


def _cmd_emit_corpus(args: argparse.Namespace) -> int:
    try:
        document = run_corpus(Path(args.corpus))
    except SpecViolation as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 2
    text = canonical_json(document)
    if args.out == "-":
        sys.stdout.write(text)
    else:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text, encoding="utf-8")
        print(f"OK: wrote {document['caseCount']} corpus results to {out_path}")
    return 0


def _cmd_check_corpus(args: argparse.Namespace) -> int:
    results_path = Path(args.results)
    try:
        actual = run_corpus(Path(args.corpus))
        expected = json.loads(results_path.read_text(encoding="utf-8"))
    except SpecViolation as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 2
    except OSError as error:
        print(f"FAIL: cannot read results file {results_path}: {error}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as error:
        print(f"FAIL: malformed results file {results_path}: {error}", file=sys.stderr)
        return 2
    differences = compare_corpus(expected, actual)
    if differences:
        print(f"FAIL: {len(differences)} differential corpus disagreement(s)", file=sys.stderr)
        for line in differences[:50]:
            print(f"  - {line}", file=sys.stderr)
        if len(differences) > 50:
            print(f"  ... and {len(differences) - 50} more", file=sys.stderr)
        return 1
    print(f"OK: {actual['caseCount']} corpus cases agree with {results_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ldpc_staircase_reference",
        description="Independent, dependency-free reference checker for ldpc-staircase.",
    )
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "-v", "--verbose", action="store_true", help="print extra detail on success"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="print extra detail on success"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    check = subparsers.add_parser(
        "check-vectors",
        parents=[common],
        help="verify every committed conformance vector against the specification",
    )
    check.add_argument("manifest", help="path to vectors/MANIFEST.json")
    check.set_defaults(func=_cmd_check_vectors)

    emit = subparsers.add_parser(
        "emit-corpus",
        parents=[common],
        help="compute the deterministic differential corpus results",
    )
    emit.add_argument("corpus", help="path to reference/corpus.json")
    emit.add_argument("--out", default="-", help="output path, or '-' for stdout (default)")
    emit.set_defaults(func=_cmd_emit_corpus)

    compare = subparsers.add_parser(
        "check-corpus",
        parents=[common],
        help="compare an existing corpus results file against a fresh computation",
    )
    compare.add_argument("corpus", help="path to reference/corpus.json")
    compare.add_argument("results", help="path to a previously emitted results file")
    compare.set_defaults(func=_cmd_check_corpus)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
