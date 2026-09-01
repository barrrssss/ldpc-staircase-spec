#!/usr/bin/env python3
"""Standard-library self-tests for the independent reference checker.

Run from the repository root:

    python -m unittest discover -s reference -t reference -v

These tests cover the checker itself. They exercise the specification rules it
implements, its failure reporting, and its command line, so a defect in the
checker cannot quietly pass a release gate. They use only ``unittest`` and the
standard library, and never touch a production implementation.
"""

from __future__ import annotations

import hashlib
import io
import itertools
import json
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ldpc_staircase_reference as ref  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
VECTORS = REPO_ROOT / "vectors"
MANIFEST = VECTORS / "MANIFEST.json"
CORPUS = REPO_ROOT / "reference" / "corpus.json"

MODULUS = 2147483647


class ParkMillerTest(unittest.TestCase):
    def test_rfc_5170_validation_criterion(self):
        """SPEC.md section 3: seed 1 must yield 1043618065 at ordinal 10000."""
        prng = ref.ParkMiller(1)
        value = 0
        for _ in range(10000):
            value = prng.next_raw()
        self.assertEqual(value, 1043618065)

    def test_first_values_follow_the_recurrence(self):
        prng = ref.ParkMiller(1)
        self.assertEqual(prng.next_raw(), 16807)
        self.assertEqual(prng.next_raw(), 282475249)
        self.assertEqual(prng.next_raw(), 1622650073)

    def test_raw_values_stay_in_range(self):
        prng = ref.ParkMiller(0x7FFFFFFE)
        for _ in range(5000):
            value = prng.next_raw()
            self.assertGreaterEqual(value, 1)
            self.assertLessEqual(value, MODULUS - 1)

    def test_seed_range_is_enforced(self):
        for seed in (0, -1, MODULUS, 0x7FFFFFFF):
            with self.assertRaises(ref.SpecViolation):
                ref.ParkMiller(seed)
        ref.ParkMiller(1)
        ref.ParkMiller(0x7FFFFFFE)

    def test_bounded_stays_in_range(self):
        prng = ref.ParkMiller(12345)
        for maxv in (1, 2, 3, 100, 65537, 1 << 30):
            for _ in range(200):
                value = prng.bounded(maxv)
                self.assertGreaterEqual(value, 0)
                self.assertLess(value, maxv)

    def test_bounded_rejects_non_positive_maxv(self):
        prng = ref.ParkMiller(1)
        with self.assertRaises(ref.SpecViolation):
            prng.bounded(0)

    def test_bounded_uses_binary64_not_exact_integer_arithmetic(self):
        """SPEC.md section 3 forbids the exact 64-bit integer formulation.

        With this seed the very first raw state is 2147483645, and at
        ``maxv = 2**30`` the normative IEEE 754 form and the exact integer form
        disagree by one. Getting this wrong silently changes matrix
        construction, so the divergence is pinned here.
        """
        seed = 1479613294
        maxv = 1 << 30
        prng = ref.ParkMiller(seed)
        raw = ref.ParkMiller(seed).next_raw()
        self.assertEqual(raw, 2147483645)
        self.assertEqual(prng.bounded(maxv), 1073741823)
        self.assertEqual((maxv * raw) // MODULUS, 1073741822)


class MatrixConstructionTest(unittest.TestCase):
    def test_zero_repair_produces_an_empty_matrix(self):
        matrix = ref.build_matrix(4, 0, 1, 1)
        self.assertEqual(matrix.r, 0)
        self.assertEqual(matrix.n, 4)
        self.assertEqual(matrix.entry_count(), 0)
        self.assertEqual(matrix.serialize(), (0).to_bytes(4, "big") + (4).to_bytes(4, "big"))

    def test_every_source_column_carries_at_least_n1_ones(self):
        for k, r, n1, seed in ((16, 8, 3, 1), (64, 32, 7, 42), (10, 5, 3, 0x7FFFFFFE)):
            matrix = ref.build_matrix(k, r, n1, seed)
            for column in range(k):
                self.assertGreaterEqual(len(matrix.rows_of_column(column)), n1)

    def test_low_degree_rows_are_raised(self):
        matrix = ref.build_matrix(64, 32, 7, 42)
        for row in range(matrix.r):
            self.assertGreaterEqual(matrix.left_degree(row), 2)

    def test_k1_rows_are_raised_only_to_degree_one(self):
        """SPEC.md section 4.3: the K >= 2 guard is this specification's rule."""
        matrix = ref.build_matrix(1, 1, 1, 7)
        self.assertEqual(matrix.left_degree(0), 1)
        self.assertEqual(matrix.rows[0], {0, 1})

    def test_staircase_shape(self):
        k, r = 16, 8
        matrix = ref.build_matrix(k, r, 3, 1)
        right = set(range(k, k + r))
        self.assertEqual(matrix.rows[0] & right, {k})
        for row in range(1, r):
            self.assertEqual(matrix.rows[row] & right, {k + row, k + row - 1})

    def test_construction_is_deterministic(self):
        first = ref.build_matrix(32, 16, 7, 999).serialize()
        second = ref.build_matrix(32, 16, 7, 999).serialize()
        self.assertEqual(first, second)

    def test_different_seeds_give_different_graphs(self):
        first = ref.build_matrix(32, 16, 7, 1).serialize()
        second = ref.build_matrix(32, 16, 7, 2).serialize()
        self.assertNotEqual(first, second)

    def test_serialization_layout(self):
        matrix = ref.build_matrix(1, 1, 1, 7)
        blob = matrix.serialize()
        self.assertEqual(int.from_bytes(blob[0:4], "big"), 1)
        self.assertEqual(int.from_bytes(blob[4:8], "big"), 2)
        self.assertEqual(int.from_bytes(blob[8:12], "big"), 2)
        columns = [int.from_bytes(blob[12 + 4 * i : 16 + 4 * i], "big") for i in range(2)]
        self.assertEqual(columns, sorted(columns))
        self.assertEqual(len(blob), 8 + 4 + 4 * 2)

    def test_parameter_validation(self):
        with self.assertRaises(ref.SpecViolation):
            ref.build_matrix(0, 4, 1, 1)
        with self.assertRaises(ref.SpecViolation):
            ref.build_matrix(4, -1, 1, 1)
        with self.assertRaises(ref.SpecViolation):
            ref.build_matrix(4, 2, 3, 1)  # N1 > R
        with self.assertRaises(ref.SpecViolation):
            ref.build_matrix(4, 2, 0, 1)  # N1 < 1
        with self.assertRaises(ref.SpecViolation):
            ref.build_matrix(4, 2, 1, 0)  # seed out of range

    def test_n1_below_one_is_rejected_even_when_r_is_zero(self):
        """SPEC.md section 2 requires N1 >= 1 always.

        N1 is unused when R = 0, so the earlier wording constrained it only when
        R >= 1 and a nonsensical N1 slipped through. Both production
        implementations rejected it regardless; the specification now says so and
        this pins it.
        """
        for n1 in (0, -1, -7):
            with self.assertRaises(ref.SpecViolation):
                ref.build_matrix(4, 0, n1, 1)
            with self.assertRaises(ref.SpecViolation):
                ref.build_matrix(4, 2, n1, 1)
        ref.build_matrix(4, 0, 1, 1)

    def test_setting_an_existing_entry_is_rejected(self):
        matrix = ref.ParityCheckMatrix(4, 2, 1, 1)
        matrix.set(0, 0)
        with self.assertRaises(ref.SpecViolation):
            matrix.set(0, 0)


class EncodeTest(unittest.TestCase):
    def _case(self, k=16, r=8, n1=3, seed=1, symbol_len=9, payload_seed=0xBEEF):
        matrix = ref.build_matrix(k, r, n1, seed)
        source = ref.corpus_source_symbols(payload_seed, k, symbol_len)
        return matrix, source, ref.encode(matrix, source)

    def test_every_parity_equation_xors_to_zero(self):
        matrix, source, repair = self._case()
        codeword = list(source) + list(repair)
        for row in range(matrix.r):
            accumulator = bytearray(len(codeword[0]))
            for column in matrix.rows[row]:
                for index, value in enumerate(codeword[column]):
                    accumulator[index] ^= value
            self.assertFalse(any(accumulator), f"row {row} does not XOR to zero")

    def test_repair_symbols_have_the_right_shape(self):
        matrix, _, repair = self._case()
        self.assertEqual(len(repair), matrix.r)
        for symbol in repair:
            self.assertEqual(len(symbol), 9)

    def test_zero_repair_encoding_is_a_no_op(self):
        matrix = ref.build_matrix(4, 0, 1, 1)
        source = ref.corpus_source_symbols(1, 4, 16)
        self.assertEqual(ref.encode(matrix, source), [])

    def test_encode_rejects_a_wrong_symbol_count(self):
        matrix = ref.build_matrix(4, 2, 1, 1)
        with self.assertRaises(ref.SpecViolation):
            ref.encode(matrix, ref.corpus_source_symbols(1, 3, 8))

    def test_encode_rejects_ragged_symbols(self):
        matrix = ref.build_matrix(2, 1, 1, 1)
        with self.assertRaises(ref.SpecViolation):
            ref.encode(matrix, [b"\x01\x02", b"\x03"])

    def test_encode_rejects_empty_symbols(self):
        matrix = ref.build_matrix(2, 1, 1, 1)
        with self.assertRaises(ref.SpecViolation):
            ref.encode(matrix, [b"", b""])

    def test_repair_chain_matches_the_staircase_definition(self):
        """SPEC.md section 5: repair p is repair p-1 XOR row p's left part."""
        matrix, source, repair = self._case()
        previous = None
        for row in range(matrix.r):
            expected = bytearray(len(source[0]))
            for column in matrix.left_columns(row):
                for index, value in enumerate(source[column]):
                    expected[index] ^= value
            if previous is not None:
                for index, value in enumerate(previous):
                    expected[index] ^= value
            self.assertEqual(repair[row], bytes(expected))
            previous = repair[row]


class RecoveryTest(unittest.TestCase):
    def _session(self, missing, k=32, r=16, n1=7, seed=5, symbol_len=11):
        matrix = ref.build_matrix(k, r, n1, seed)
        source = ref.corpus_source_symbols(0xFEED, k, symbol_len)
        codeword = source + ref.encode(matrix, source)
        absent = set(missing)
        present = [index not in absent for index in range(matrix.n)]
        received = [codeword[i] if present[i] else None for i in range(matrix.n)]
        return matrix, codeword, received, present, symbol_len

    def test_complete_received_set_needs_nothing(self):
        matrix, _, received, present, length = self._session([])
        outcome = ref.solve_whole_system(matrix, received, present, length)
        self.assertTrue(outcome.complete)
        self.assertEqual(outcome.recovered, {})

    def test_recovered_bytes_match_the_codeword(self):
        matrix, codeword, received, present, length = self._session([1, 4, 9, 20, 34])
        outcome = ref.solve_whole_system(matrix, received, present, length)
        self.assertTrue(outcome.complete)
        for column, value in outcome.recovered.items():
            self.assertEqual(value, codeword[column])

    def test_unrecoverable_loss_is_reported_not_guessed(self):
        matrix, _, received, present, length = self._session(range(0, 32))
        outcome = ref.solve_whole_system(matrix, received, present, length)
        self.assertFalse(outcome.complete)
        self.assertTrue(outcome.missing_source)
        for column in outcome.missing_source:
            self.assertIsNone(outcome.symbols[column])

    def test_zero_repair_cannot_recover_anything(self):
        matrix = ref.build_matrix(4, 0, 1, 1)
        source = ref.corpus_source_symbols(3, 4, 8)
        received = [source[0], None, source[2], source[3]]
        outcome = ref.solve_whole_system(matrix, received, [True, False, True, True], 8)
        self.assertFalse(outcome.complete)
        self.assertEqual(outcome.missing_source, [1])

    def test_peeling_and_the_whole_system_agree_when_peeling_completes(self):
        for missing in ([2], [0, 7, 15], list(range(32, 48))):
            matrix, codeword, received, present, length = self._session(missing)
            peeled = ref.peel(matrix, received, present, length)
            whole = ref.solve_whole_system(matrix, received, present, length)
            if not peeled.complete:
                continue
            self.assertTrue(whole.complete)
            for column, value in peeled.recovered.items():
                self.assertEqual(value, codeword[column])
                self.assertEqual(whole.symbols[column], value)

    def test_the_whole_system_is_never_weaker_than_peeling(self):
        """The RREF oracle yields the maximal determined set, so it dominates."""
        for missing in ([1, 5, 9], list(range(0, 32, 2)), list(range(10, 40))):
            matrix, _, received, present, length = self._session(missing)
            peeled = ref.peel(matrix, received, present, length)
            whole = ref.solve_whole_system(matrix, received, present, length)
            self.assertLessEqual(set(peeled.recovered), set(whole.recovered))

    def test_an_empty_received_set_is_rejected(self):
        """SPEC.md section 6: at least one symbol must be present.

        With nothing received the symbol length is undefined, so this is a caller
        error rather than an incomplete decode. Both production implementations
        reject it, and the checker must not answer a question they refuse.
        """
        matrix, _, _, _, length = self._session([])
        empty = [None] * matrix.n
        absent = [False] * matrix.n
        with self.assertRaises(ref.SpecViolation):
            ref.solve_whole_system(matrix, empty, absent, length)
        with self.assertRaises(ref.SpecViolation):
            ref.peel(matrix, empty, absent, length)

    def test_a_corpus_case_may_not_lose_everything(self):
        with self.assertRaises(ref.SpecViolation):
            ref.run_corpus_case(
                {
                    "name": "everything-lost",
                    "k": 2,
                    "r": 1,
                    "n1": 1,
                    "seed": 1,
                    "symbolLen": 4,
                    "payloadSeed": 1,
                    "missing": [0, 1, 2],
                }
            )

    def test_contradictory_symbol_data_is_rejected(self):
        matrix, codeword, received, present, length = self._session([])
        corrupted = list(received)
        corrupted[0] = bytes(byte ^ 0xFF for byte in codeword[0])
        with self.assertRaises(ref.SpecViolation):
            ref.solve_whole_system(matrix, corrupted, present, length)


class CorpusPayloadTest(unittest.TestCase):
    def test_payload_is_deterministic_and_the_right_length(self):
        for length in (1, 7, 8, 9, 16, 17, 64):
            first = ref.corpus_symbol(0x1234, 3, length)
            second = ref.corpus_symbol(0x1234, 3, length)
            self.assertEqual(first, second)
            self.assertEqual(len(first), length)

    def test_payload_is_keyed_by_esi_and_seed(self):
        self.assertNotEqual(ref.corpus_symbol(1, 0, 16), ref.corpus_symbol(1, 1, 16))
        self.assertNotEqual(ref.corpus_symbol(1, 0, 16), ref.corpus_symbol(2, 0, 16))

    def test_payload_prefix_is_stable_across_symbol_lengths(self):
        long_symbol = ref.corpus_symbol(0x99, 5, 32)
        short_symbol = ref.corpus_symbol(0x99, 5, 7)
        self.assertEqual(long_symbol[:7], short_symbol)

    def test_splitmix64_matches_the_published_stream(self):
        """The corpus payload constants are checked against SplitMix64 itself.

        Seeding the state at zero must reproduce the published SplitMix64
        output stream, so the payload rule is anchored to the public algorithm
        rather than to whatever this file happens to compute.
        """
        state = 0
        outputs = []
        for _ in range(4):
            state, word = ref._splitmix64(state)
            outputs.append(word)
        self.assertEqual(
            outputs,
            [
                0xE220A8397B1DCDAF,
                0x6E789E6AA1B965F4,
                0x06C45D188009454F,
                0xF88BB8A8724C81EC,
            ],
        )

    def test_payload_pins_the_documented_rule(self):
        """A digest lock so the cross-language payload rule cannot drift."""
        digest = hashlib.sha256(
            b"".join(ref.corpus_source_symbols(0x0100, 8, 24))
        ).hexdigest()
        self.assertEqual(
            digest, "598cd96735fa256ad821c2d8c68a3a4aa4652026e17a85cde2d35ecc40147eb8"
        )


class ReportTest(unittest.TestCase):
    def test_report_counts_and_records_failures(self):
        report = ref.CheckReport()
        report.expect(True, "fine")
        report.expect_equal(1, 1, "equal")
        report.expect_equal(1, 2, "different")
        self.assertEqual(report.checks, 3)
        self.assertEqual(len(report.failures), 1)
        self.assertIn("different", report.failures[0])


class VectorGateTest(unittest.TestCase):
    """The release-gate command, against the committed vectors and against damage."""

    def test_committed_vectors_pass(self):
        report = ref.CheckReport()
        ref.check_vectors(MANIFEST, report)
        self.assertEqual(report.failures, [], "\n".join(report.failures[:10]))
        self.assertGreater(report.checks, 100)

    def _copy_vectors(self, tmp: Path) -> Path:
        destination = tmp / "vectors"
        shutil.copytree(VECTORS, destination)
        return destination / "MANIFEST.json"

    def _run_cli(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = ref.main(argv)
        return code, out.getvalue() + err.getvalue()

    def test_cli_passes_on_the_committed_vectors(self):
        code, output = self._run_cli(["check-vectors", str(MANIFEST)])
        self.assertEqual(code, 0, output)
        self.assertIn("OK", output)

    def test_a_corrupted_blob_fails_the_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = self._copy_vectors(Path(tmp))
            blob = manifest.parent / "enc-k16-r8-n1_3-s1-len32-rep.bin"
            data = bytearray(blob.read_bytes())
            data[0] ^= 0xFF
            blob.write_bytes(bytes(data))
            code, output = self._run_cli(["check-vectors", str(manifest)])
            self.assertEqual(code, 1, output)
            self.assertIn("sha256", output)

    def test_a_wrong_expected_prng_value_fails_the_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = self._copy_vectors(Path(tmp))
            document = json.loads(manifest.read_text(encoding="utf-8"))
            document["prngRaw"][0]["values"][0]["value"] += 1
            manifest.write_text(json.dumps(document), encoding="utf-8")
            code, output = self._run_cli(["check-vectors", str(manifest)])
            self.assertEqual(code, 1, output)
            self.assertIn("prngRaw", output)

    def test_a_wrong_expected_decode_outcome_fails_the_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = self._copy_vectors(Path(tmp))
            document = json.loads(manifest.read_text(encoding="utf-8"))
            for case in document["decode"]:
                if case["name"] == "dec-max-loss-failure":
                    case["expectComplete"] = True
                    case["expectMissingSource"] = []
            manifest.write_text(json.dumps(document), encoding="utf-8")
            code, output = self._run_cli(["check-vectors", str(manifest)])
            self.assertEqual(code, 1, output)
            self.assertIn("dec-max-loss-failure", output)

    def test_a_wrong_expected_stage_fails_the_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = self._copy_vectors(Path(tmp))
            document = json.loads(manifest.read_text(encoding="utf-8"))
            for case in document["decode"]:
                if case["name"] == "dec-source-band":
                    case["expectStage"] = "RESIDUAL_SOLVE"
            manifest.write_text(json.dumps(document), encoding="utf-8")
            code, output = self._run_cli(["check-vectors", str(manifest)])
            self.assertEqual(code, 1, output)
            self.assertIn("RESIDUAL_SOLVE", output)

    def test_a_missing_blob_fails_the_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = self._copy_vectors(Path(tmp))
            (manifest.parent / "mtx-k16-r8-n1_3-s1.bin").unlink()
            code, output = self._run_cli(["check-vectors", str(manifest)])
            self.assertNotEqual(code, 0, output)

    def test_a_malformed_manifest_exits_two(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "MANIFEST.json"
            manifest.write_text("{ not json", encoding="utf-8")
            code, output = self._run_cli(["check-vectors", str(manifest)])
            self.assertEqual(code, 2, output)

    def test_an_unsupported_manifest_version_exits_two(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "MANIFEST.json"
            manifest.write_text(json.dumps({"manifestVersion": 2}), encoding="utf-8")
            code, output = self._run_cli(["check-vectors", str(manifest)])
            self.assertEqual(code, 2, output)

    def test_a_missing_manifest_exits_two(self):
        code, output = self._run_cli(["check-vectors", str(VECTORS / "nope.json")])
        self.assertEqual(code, 2, output)


class DifferentialCorpusTest(unittest.TestCase):
    def test_the_committed_corpus_runs_and_is_deterministic(self):
        first = ref.run_corpus(CORPUS)
        second = ref.run_corpus(CORPUS)
        self.assertEqual(ref.canonical_json(first), ref.canonical_json(second))
        self.assertGreaterEqual(first["caseCount"], 20)

    def test_the_corpus_covers_every_required_category(self):
        """Decision 0002 lists the shapes the corpus must exercise."""
        document = ref.run_corpus(CORPUS)
        cases = document["cases"]
        self.assertTrue(any(case["r"] == 0 for case in cases), "R = 0")
        self.assertTrue(any(case["k"] == 1 for case in cases), "single source")
        self.assertTrue(any(case["r"] == 1 for case in cases), "single repair")
        self.assertTrue(any(case["n1"] == 7 for case in cases), "default N1")
        self.assertGreaterEqual(len({case["n1"] for case in cases}), 4, "several N1 values")
        self.assertTrue(any(case["seed"] == 1 for case in cases), "lowest seed")
        self.assertTrue(any(case["seed"] == 0x7FFFFFFE for case in cases), "highest seed")
        self.assertTrue(any(case["symbolLen"] % 2 == 1 for case in cases), "odd symbol length")
        self.assertTrue(any(case["symbolLen"] % 2 == 0 for case in cases), "even symbol length")
        self.assertTrue(
            any(case["missingCount"] and case["peelingSuffices"] for case in cases),
            "a peeling-only recovery",
        )
        self.assertTrue(
            any(case["complete"] and not case["peelingSuffices"] for case in cases),
            "a recovery that needs the residual solve",
        )
        self.assertTrue(
            any(not case["complete"] for case in cases), "a rank-deficient received set"
        )
        self.assertTrue(any(case["k"] >= 250 for case in cases), "a larger construction shape")

    def test_recovered_source_digest_matches_the_source_digest_when_complete(self):
        for case in ref.run_corpus(CORPUS)["cases"]:
            if case["complete"]:
                self.assertEqual(
                    case["recoveredSourceSha256"],
                    case["sourceSha256"],
                    f"{case['name']}: a complete decode must reproduce the source exactly",
                )
            else:
                self.assertNotEqual(case["recoveredSourceSha256"], case["sourceSha256"])

    def test_compare_reports_no_difference_against_itself(self):
        document = ref.run_corpus(CORPUS)
        self.assertEqual(ref.compare_corpus(document, document), [])

    def test_compare_detects_a_changed_field(self):
        document = ref.run_corpus(CORPUS)
        mutated = json.loads(ref.canonical_json(document))
        mutated["cases"][0]["recoveredCount"] += 1
        differences = ref.compare_corpus(document, mutated)
        self.assertTrue(differences)
        self.assertIn("recoveredCount", differences[0])

    def test_compare_detects_a_missing_case(self):
        document = ref.run_corpus(CORPUS)
        mutated = json.loads(ref.canonical_json(document))
        dropped = mutated["cases"].pop()["name"]
        differences = ref.compare_corpus(document, mutated)
        self.assertTrue(any(dropped in line for line in differences))

    def test_emit_then_check_round_trips(self):
        out, err = io.StringIO(), io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            results = Path(tmp) / "corpus-results.json"
            with redirect_stdout(out), redirect_stderr(err):
                emitted = ref.main(["emit-corpus", str(CORPUS), "--out", str(results)])
                checked = ref.main(["check-corpus", str(CORPUS), str(results)])
            self.assertEqual(emitted, 0)
            self.assertEqual(checked, 0)

    def test_check_corpus_fails_on_a_tampered_results_file(self):
        out, err = io.StringIO(), io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            results = Path(tmp) / "corpus-results.json"
            results.write_text(ref.canonical_json(ref.run_corpus(CORPUS)), encoding="utf-8")
            document = json.loads(results.read_text(encoding="utf-8"))
            document["cases"][0]["complete"] = not document["cases"][0]["complete"]
            results.write_text(json.dumps(document), encoding="utf-8")
            with redirect_stdout(out), redirect_stderr(err):
                code = ref.main(["check-corpus", str(CORPUS), str(results)])
        self.assertEqual(code, 1)
        self.assertIn("complete", out.getvalue() + err.getvalue())

    def test_an_out_of_range_missing_index_is_rejected(self):
        with self.assertRaises(ref.SpecViolation):
            ref.run_corpus_case(
                {
                    "name": "bad",
                    "k": 4,
                    "r": 2,
                    "n1": 1,
                    "seed": 1,
                    "symbolLen": 8,
                    "payloadSeed": 1,
                    "missing": [99],
                }
            )


class ExhaustiveCriterionTest(unittest.TestCase):
    """Check SPEC.md section 6.2's recovery criterion against the definition.

    Section 6.2 gives a *shortcut*: a lost symbol is recovered exactly when it is a
    pivot variable whose RREF row contains no other variable. The definition that
    shortcut stands for is plainer: a lost symbol is determined exactly when it holds
    the same value in every assignment consistent with the received symbols.

    Everything else in this repository — the checker, both production
    implementations, and the differential corpus — computes recoverability by some
    form of Gaussian elimination, so all of them would reproduce a mistake in the
    criterion itself rather than catch it. These tests compute the definition the dumb
    way instead, by enumerating every candidate assignment and keeping the consistent
    ones. No row reduction, no pivots, no peeling.

    A wider sweep of the same comparison is recorded in
    ``review/independence-review.md``; what runs here is the bounded subset.
    """

    @staticmethod
    def _determined_by_enumeration(matrix, codeword, present, symbol_len):
        """Symbols holding one value across every consistent assignment.

        One bit plane at a time: over GF(2) the coefficient matrix is the same for
        every bit position, so a symbol is determined exactly when all of its bits are.
        """
        unknown = [c for c in range(matrix.n) if not present[c]]
        position = {column: index for index, column in enumerate(unknown)}
        width = len(unknown)

        masks = []
        for row in range(matrix.r):
            mask = 0
            for column in matrix.rows[row]:
                if not present[column]:
                    mask |= 1 << position[column]
            masks.append(mask)

        bits = {column: [] for column in unknown}
        for byte_index in range(symbol_len):
            for bit in range(8):
                rhs = []
                for row in range(matrix.r):
                    value = 0
                    for column in matrix.rows[row]:
                        if present[column]:
                            value ^= (codeword[column][byte_index] >> bit) & 1
                    rhs.append(value)

                solutions = []
                for candidate in range(1 << width):
                    for row in range(matrix.r):
                        if bin(masks[row] & candidate).count("1") & 1 != rhs[row]:
                            break
                    else:
                        solutions.append(candidate)
                if not solutions:
                    raise AssertionError("the codeword itself is always a consistent assignment")

                for column in unknown:
                    values = {(s >> position[column]) & 1 for s in solutions}
                    bits[column].append(values.pop() if len(values) == 1 else None)

        determined = {}
        for column in unknown:
            if all(b is not None for b in bits[column]):
                out = bytearray(symbol_len)
                for index, bit in enumerate(bits[column]):
                    if bit:
                        out[index // 8] |= 1 << (index % 8)
                determined[column] = bytes(out)
        return determined

    CONFIGURATIONS = (
        (2, 4, 1, 1),
        (3, 4, 2, 7),
        (4, 4, 3, 4242),
        (2, 6, 1, 1),
        (5, 3, 2, 12345),
        (4, 5, 1, MODULUS - 1),
        (6, 2, 2, 99),
        (1, 3, 1, 7),
    )

    def _sweep(self):
        """Yield (config, missing, truth, claimed) over every small loss pattern."""
        for k, r, n1, seed in self.CONFIGURATIONS:
            matrix = ref.build_matrix(k, r, n1, seed)
            source = ref.corpus_source_symbols(0x5EED ^ seed, k, 1)
            codeword = source + ref.encode(matrix, source)
            for size in range(1, matrix.n):
                for missing in itertools.combinations(range(matrix.n), size):
                    absent = set(missing)
                    present = [i not in absent for i in range(matrix.n)]
                    received = [codeword[i] if present[i] else None for i in range(matrix.n)]
                    truth = self._determined_by_enumeration(matrix, codeword, present, 1)
                    claimed = ref.solve_whole_system(matrix, received, present, 1).recovered
                    yield (k, r, n1, seed), missing, truth, claimed, codeword

    def test_criterion_matches_exhaustive_enumeration(self):
        cases = 0
        for config, missing, truth, claimed, codeword in self._sweep():
            cases += 1
            label = f"K={config[0]} R={config[1]} N1={config[2]} seed={config[3]} missing={missing}"
            self.assertEqual(
                sorted(truth), sorted(claimed),
                f"{label}: section 6.2 disagrees with the definition about which "
                "symbols the received set determines",
            )
            for column, value in truth.items():
                self.assertEqual(claimed[column], value, f"{label}: wrong bytes for symbol {column}")
                self.assertEqual(codeword[column], value, f"{label}: symbol {column} is not the original")
        self.assertGreater(cases, 500, "the sweep collapsed to too few cases to mean anything")

    def test_the_sweep_is_not_trivially_easy(self):
        """Guard the guard: the sweep must contain cases where recovery is incomplete.

        If every pattern in the sweep were fully recoverable the comparison above would
        pass without ever exercising the part of the criterion that decides a symbol is
        *not* determined.
        """
        full = partial = nothing = 0
        for _, missing, truth, _, _ in self._sweep():
            if len(truth) == len(missing):
                full += 1
            elif truth:
                partial += 1
            else:
                nothing += 1
        self.assertGreater(full, 0, "no fully recovered case")
        self.assertGreater(partial, 0, "no partially recovered case")
        self.assertGreater(nothing, 0, "no unrecoverable case")


class IndependenceTest(unittest.TestCase):
    """Guard the structural half of the decision 0002 independence rules."""

    SOURCE = (Path(__file__).resolve().parent / "ldpc_staircase_reference.py").read_text(
        encoding="utf-8"
    )

    def test_only_standard_library_imports(self):
        allowed = {
            "argparse",
            "hashlib",
            "json",
            "sys",
            "pathlib",
            "typing",
            "__future__",
        }
        imported = set()
        for line in self.SOURCE.splitlines():
            stripped = line.strip()
            if stripped.startswith("import "):
                imported.add(stripped.split()[1].split(".")[0])
            elif stripped.startswith("from "):
                imported.add(stripped.split()[1].split(".")[0])
        self.assertTrue(
            imported <= allowed, f"unexpected imports: {sorted(imported - allowed)}"
        )

    def test_no_subprocess_or_dynamic_loading(self):
        for forbidden in ("subprocess", "ctypes", "socket", "urllib", "importlib", "os.system"):
            self.assertNotIn(forbidden, self.SOURCE, f"{forbidden} must not appear")

    def test_the_vectors_directory_is_only_ever_read(self):
        for forbidden in ("write_bytes", "write_text("):
            occurrences = [
                line
                for line in self.SOURCE.splitlines()
                if forbidden in line and "out_path" not in line
            ]
            self.assertEqual(
                occurrences, [], f"the checker must not write vectors: {occurrences}"
            )


if __name__ == "__main__":
    unittest.main()
