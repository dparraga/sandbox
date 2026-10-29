"""Approved observation semantics; mocked execution is not OCR evidence."""

from dataclasses import FrozenInstanceError
import builtins
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from flex_photo.interpretation import (
    FieldObservation, InterpretationAssets, SharedAssetError, _parse_field,
    interpret_photo, validate_interpretation_assets,
)
from flex_photo.metadata import CaptureMetadata, MetadataError
import flex_photo._interpretation_worker as worker


class ReadingGrammarTests(unittest.TestCase):
    def test_exact_decimal_precision_sign_zero_and_literal_units(self):
        for field, label, unit in [("trip_distance", "Trip Distance ", "mi"),
                                   ("trip_average_mpg", "Trip Average ", "MPG"),
                                   ("odometer", "", "mi")]:
            for value in ("0", "0.0", "42.00", "-0.0", "-12.5"):
                with self.subTest(field=field, value=value):
                    self.assertEqual(_parse_field(field, label + value + " " + unit),
                                     (value, unit))

    def test_rejects_incomplete_numeric_tokens_and_inferred_units(self):
        for text in ("1e3 mi", "NaN mi", "inf mi", ".5 mi", "5. mi", "+5 mi",
                     "1,000 mi", "1.2.3 mi", "42", "42 mI", "42 km", "42 mi extra"):
            with self.subTest(text=text):
                self.assertIsNone(_parse_field("trip_distance", "Trip Distance " + text))
        for text in ("Trip Average 42 mPG", "Trip Average 42 mpg", "Trip Distance 42 MPG",
                     "42 MPG", "Range 42 MPG"):
            self.assertIsNone(_parse_field("trip_average_mpg", text))

    def test_duration_uses_unbounded_hours_and_valid_minutes(self):
        for raw, expected in (("0:00", "00:00"), ("2:09", "02:09"),
                              ("99:59", "99:59"), ("125:10", "125:10")):
            self.assertEqual(_parse_field("trip_duration", "Trip Time " + raw), (expected, None))
        for raw in ("02:60", "2:9", "2.5", "-2:00", "02:10 hours", "02:10:00", ""):
            self.assertIsNone(_parse_field("trip_duration", "Trip Time " + raw))

    def test_field_association_is_required(self):
        for text in ("42 mi", "Trip Average 42 mi", "Trip DistanceX 42 mi"):
            self.assertIsNone(_parse_field("trip_distance", text))
        self.assertEqual(_parse_field("trip_distance", "Trip Distance\n42.0 mi"), ("42.0", "mi"))


class InterpretationOutcomeTests(unittest.TestCase):
    def setUp(self):
        self.path = Path("authored.heic")
        self.assets = InterpretationAssets(Path("engine"), Path("models"), "0" * 64)

    def interpret_payload(self, payload, *, metadata=None, error=None):
        with patch("flex_photo.interpretation._validate_assets"), \
             patch("flex_photo._interpretation_worker.run_bounded", return_value=payload), \
             patch("flex_photo.interpretation.read_capture_metadata", return_value=metadata,
                   side_effect=error) as reader:
            result = interpret_photo(self.path, self.assets)
        return result, reader

    def test_observations_survive_metadata_failure_and_remain_immutable(self):
        fields = [{"field_id": name, "status": status, "value": value, "unit": unit}
                  for name, status, value, unit in (
                      ("trip_distance", "clear", "0.0", "mi"),
                      ("trip_duration", "unclear", None, None),
                      ("trip_average_mpg", "clear", "42.00", "MPG"),
                      ("odometer", "absent", None, None))]
        error = MetadataError(self.path, None, "file unavailable")
        result, reader = self.interpret_payload({"layout": "trip_summary", "observations": fields,
            "issues": ["unexpected trip duration"]}, error=error)
        self.assertEqual(result.layout, "trip_summary")
        self.assertIs(result.metadata_error, error)
        self.assertIsNone(result.metadata)
        self.assertEqual(tuple(item.field_id for item in result.observations),
                         ("trip_distance", "trip_duration", "trip_average_mpg", "odometer"))
        self.assertEqual(result.observations[0].value, "0.0")
        self.assertEqual(result.observations[2].value, "42.00")
        self.assertTrue(result.issues)
        reader.assert_called_once_with(self.path)
        with self.assertRaises(FrozenInstanceError):
            result.observations[0].value = "5"

    def test_original_capture_text_is_preserved_on_match(self):
        raw = CaptureMetadata("2030:02:03 04:05:06", "-00:00", "0123456789")
        result, _ = self.interpret_payload({"layout": "drive_info", "observations": []}, metadata=raw)
        self.assertIs(result.metadata, raw)

    def test_nonmatch_and_execution_failure_do_not_require_metadata(self):
        result, reader = self.interpret_payload({"layout": "nonmatch"})
        self.assertEqual(result.layout, "nonmatch")
        reader.assert_not_called()
        for reason in ("decode failed", "OCR timeout", "memory limit exceeded"):
            result, reader = self.interpret_payload({"error": reason})
            self.assertEqual(result.layout, "unresolved")
            self.assertEqual(result.observations, ())
            self.assertEqual(result.issues[0].path, self.path)
            self.assertEqual(result.issues[0].action, "preserve/report/continue")
            reader.assert_not_called()

    def test_shared_asset_loss_is_never_an_individual_skip(self):
        with self.assertRaises(SharedAssetError):
            self.interpret_payload({"shared_error": "model unavailable"})
        with patch("flex_photo.interpretation._validate_assets", side_effect=SharedAssetError("missing")):
            with self.assertRaises(SharedAssetError):
                interpret_photo(self.path, self.assets)

    def test_shared_asset_loss_after_individual_failure_still_stops(self):
        with patch("flex_photo.interpretation._validate_assets",
                   side_effect=[None, SharedAssetError("asset disappeared")]), \
             patch("flex_photo._interpretation_worker.run_bounded", return_value={"error": "decode failed"}):
            with self.assertRaises(SharedAssetError):
                interpret_photo(self.path, self.assets)

    def test_missing_assets_fail_before_photo_decoding(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            assets = InterpretationAssets(root / "missing-engine", root / "models", "0" * 64)
            with self.assertRaises(SharedAssetError):
                interpret_photo(root / "missing-photo.heic", assets)


class RecognitionSemanticsTests(unittest.TestCase):
    """Injected bounded OCR strings test decisions, not recognition accuracy."""

    def setUp(self):
        from PIL import Image
        self.image = Image.new("RGB", (800, 600))
        self.image.putpixel((0, 0), (1, 1, 1))
        self.assets = InterpretationAssets(Path("engine"), Path("models"), "0" * 64)

    def test_clock_group_is_rejected_before_selecting_lower_title_for_ocr(self):
        from PIL import ImageDraw
        draw = ImageDraw.Draw(self.image)
        for x in (374, 395, 416, 437):
            draw.rectangle((x, 133, x + 13, 156), fill="white")
        for index in range(9):
            x = 531 + index * 11
            draw.rectangle((x, 276, x + 6, 295), fill="white")
        candidates = worker._title_components(self.image)
        self.assertEqual(len(candidates), 1)
        self.assertGreater(candidates[0][1], 250)
        with patch.object(worker, "_ocr", return_value=("Drive Info", "Drive Info")) as ocr:
            worker._interpret(self.image, self.assets, Path("unused"))
        self.assertTrue(ocr.called)
        self.assertTrue(all(call.args[1][1] > 250 for call in ocr.call_args_list))

    def test_right_shifted_title_is_not_clipped_at_old_search_edge(self):
        from PIL import ImageDraw
        draw = ImageDraw.Draw(self.image)
        for index in range(11):
            x = 516 + index * 14
            draw.rectangle((x, 230, x + 8, 252), fill="white")
        candidates = worker._title_components(self.image)
        self.assertEqual(len(candidates), 1)
        self.assertGreater(candidates[0][2], 650)

    def test_detached_dots_do_not_turn_clock_into_eight_title_glyphs(self):
        from PIL import ImageDraw
        draw = ImageDraw.Draw(self.image)
        for index in range(4):
            x = 375 + index * 20
            draw.rectangle((x, 130, x + 8, 152), fill="white")
        for x, y in ((390, 134), (390, 146), (430, 134), (430, 146)):
            draw.rectangle((x, y, x + 1, y + 1), fill="white")
        self.assertEqual(worker._title_glyph_count(self.image, (370, 125, 460, 160)), 4)

    def test_label_edge_punctuation_keeps_literal_words_and_both_views_required(self):
        cases = (("Trip Time:", True), ("Trip Time;", True),
                 ("TripTime:", False), ("Tr1p Time:", False),
                 ("trip Time:", False), ("Trip :Time", False),
                 ("Trip Time:Other", False))
        for label, accepted in cases:
            responses = [("Drive Info",) * 2, ("Trip Distance",) * 2,
                         ("42.0",) * 3, ("mi",) * 6,
                         (label, "Trip Time."), ("2:16",) * 3]
            with self.subTest(label=label), \
                 patch.object(worker, "_title_components", return_value=[(400, 150, 560, 175)]), \
                 patch.object(worker, "_segment_reading", return_value=((0, 0, 10, 10), (11, 0, 20, 10))), \
                 patch.object(worker, "_ocr", side_effect=responses):
                result = worker._interpret(self.image, self.assets, Path("unused"))
            self.assertEqual(result["layout"], "drive_info" if accepted else "unresolved")
            if accepted:
                self.assertEqual(result["observations"][1]["value"], "02:16")

    def reading_components(self):
        from PIL import Image, ImageDraw
        image = Image.new("RGB", (320, 160))
        draw = ImageDraw.Draw(image)
        draw.rectangle((90, 15, 125, 96), fill="white")
        draw.rectangle((145, 15, 180, 102), fill="white")
        draw.rectangle((220, 50, 235, 90), fill="white")
        return image, draw, (10, 10, 300, 140)

    def test_height_filter_cannot_silently_drop_taller_leading_digit(self):
        image, draw, bounds = self.reading_components()
        self.assertIsNotNone(worker._segment_reading(image, bounds))
        draw.rectangle((35, 15, 60, 124), fill="white")
        self.assertIsNone(worker._segment_reading(image, bounds))

    def test_thin_leading_minus_cannot_be_removed_from_reading(self):
        image, draw, bounds = self.reading_components()
        draw.rectangle((70, 60, 83, 62), fill="white")
        self.assertIsNone(worker._segment_reading(image, bounds))

    def test_ink_continuing_outside_reading_crop_is_not_a_complete_token(self):
        image, draw, bounds = self.reading_components()
        self.assertIsNone(worker._segment_reading(image, (10, 30, 300, 140)))

    def interpret_texts(self, title, readings):
        fields = ("trip_distance", "trip_duration") if title == "Drive Info" else (
            "trip_distance", "trip_duration", "trip_average_mpg", "odometer")
        labels = {"trip_distance": "Trip Distance", "trip_duration": "Trip Time",
                  "trip_average_mpg": "Trip Average", "odometer": ""}
        responses = [(title, title)]
        for field, texts in zip(fields, readings):
            label = labels[field]
            if label:
                responses.append(tuple(label if text.startswith(label + " ") else text for text in texts))
            parts = [text[len(label) + 1:] if label and text.startswith(label + " ") else text
                     for text in texts]
            if field == "trip_duration":
                responses.append(tuple(parts) + ("",))
            else:
                split = [text.split(" ", 1) for text in parts]
                responses.append(tuple(value[0] for value in split) + ("",))
                responses.append(tuple(value[1] if len(value) == 2 else "" for value in split) + ("",) * 4)
        with patch.object(worker, "_title_components", return_value=[(400, 150, 560, 175)]), \
             patch.object(worker, "_segment_reading", return_value=((0, 0, 10, 10), (11, 0, 20, 10))), \
             patch.object(worker, "_ocr", side_effect=responses):
            return worker._interpret(self.image, self.assets, Path("unused"))

    def test_drive_info_retains_clear_zero_and_independent_absence(self):
        result = self.interpret_texts("Drive Info", [
            ("Trip Distance 0.0 mi", "Trip Distance 0.0 mi"),
            ("Trip Time 2:00", "Trip Time 2:00")])
        self.assertEqual(result["layout"], "drive_info")
        observations = {item["field_id"]: item for item in result["observations"]}
        self.assertEqual(observations["trip_distance"]["value"], "0.0")
        self.assertEqual(observations["trip_duration"]["value"], "02:00")
        self.assertEqual(observations["trip_average_mpg"]["status"], "absent")
        self.assertEqual(observations["odometer"]["status"], "absent")

    def test_malformed_duration_and_disagreeing_unit_do_not_erase_distance(self):
        result = self.interpret_texts("Trip Summary", [
            ("Trip Distance 42.00 mi", "Trip Distance 42.00 mi"),
            ("Trip Time 02:70", "Trip Time 02:70"),
            ("Trip Average 41 MPG", "Trip Average 41 mPG"),
            ("12345 mi", "12346 mi")])
        self.assertEqual(result["layout"], "trip_summary")
        observations = {item["field_id"]: item for item in result["observations"]}
        self.assertEqual(observations["trip_distance"]["value"], "42.00")
        for field in ("trip_duration", "trip_average_mpg", "odometer"):
            self.assertEqual(observations[field]["status"], "unclear")
            self.assertIsNone(observations[field]["value"])
            self.assertIsNone(observations[field]["unit"])
        self.assertTrue(result["issues"])

    def test_unexpected_dashboard_text_is_not_retained_in_unclear_evidence(self):
        result = self.interpret_texts("Trip Summary", [
            ("Trip Distance 42.00 mi", "Trip Distance 42.00 mi"),
            ("Trip Time 02:16", "Trip Time 02:16"),
            ("Trip Average 41 MPG EV Ratio 10%", "Trip Average 41 MPG EV Ratio 10%"),
            ("12345 mi Range 200 mi", "12345 mi Speed 65 MPH")])
        self.assertEqual(result["layout"], "trip_summary")
        observations = {item["field_id"]: item for item in result["observations"]}
        self.assertEqual(observations["trip_distance"]["value"], "42.00")
        self.assertEqual(observations["trip_duration"]["value"], "02:16")
        for field in ("trip_average_mpg", "odometer"):
            self.assertEqual(observations[field]["status"], "unclear")
        retained = json.dumps(result)
        for excluded in ("EV Ratio", "10%", "Range", "Speed", "MPH"):
            self.assertNotIn(excluded, retained)

    def test_title_and_unit_alone_cannot_establish_layout(self):
        result = self.interpret_texts("Drive Info", [("42 mi", "42 mi"), ("02:00", "02:00")])
        self.assertEqual(result["layout"], "unresolved")
        self.assertFalse(result.get("observations"))
        with patch.object(worker, "_title_components", return_value=[(400, 150, 560, 175)]), \
             patch.object(worker, "_ocr", return_value=("Drive Info", "Trip Summary")):
            self.assertEqual(worker._interpret(self.image, self.assets, Path("unused"))["layout"],
                             "unresolved")

    def test_no_candidate_and_ambiguous_candidates_remain_unresolved(self):
        with patch.object(worker, "_title_components", return_value=[]):
            self.assertEqual(worker._interpret(self.image, self.assets, Path("unused"))["layout"],
                             "unresolved")
        with patch.object(worker, "_title_components", return_value=[(400, 150, 560, 175),
                                                                    (590, 150, 750, 175)]), \
             patch.object(worker, "_ocr") as recognize:
            self.assertEqual(worker._interpret(self.image, self.assets, Path("unused"))["layout"],
                             "unresolved")
            recognize.assert_not_called()

    def test_exactly_uniform_image_is_nonmatch_without_ocr(self):
        from PIL import Image
        for color in ((0, 0, 0), (255, 255, 255), (17, 23, 91)):
            with self.subTest(color=color), patch.object(worker, "_ocr") as recognize:
                result = worker._interpret(Image.new("RGB", (800, 600), color), self.assets, Path("unused"))
                self.assertEqual(result["layout"], "nonmatch")
                self.assertFalse(result.get("observations"))
                recognize.assert_not_called()

    def test_crop_guard_rejects_before_ocr_execution(self):
        from PIL import Image
        image = Image.new("RGB", (2001, 2000))
        with patch.object(worker, "_validate_assets"), patch.object(worker.subprocess, "run") as execute:
            with self.assertRaisesRegex(ValueError, "crop pixel limit"):
                worker._ocr(image, (0, 0, 2001, 2000), self.assets, Path("unused"))
            execute.assert_not_called()

    def test_ocr_environment_removes_ambient_model_and_python_overrides(self):
        with patch.dict("os.environ", {"TESSDATA_PREFIX": "untrusted", "OMP_NUM_THREADS": "99",
                                       "PYTHONPATH": "untrusted", "SYSTEMROOT": "system"}):
            environment = worker._environment()
        self.assertNotIn("TESSDATA_PREFIX", environment)
        self.assertNotIn("OMP_NUM_THREADS", environment)
        self.assertNotIn("PYTHONPATH", environment)
        self.assertEqual(environment["OMP_THREAD_LIMIT"], "1")
        self.assertEqual(environment["SYSTEMROOT"], "system")


class FiniteViewAgreementTests(unittest.TestCase):
    """Authored fixed-view candidates test voting semantics, not OCR accuracy."""

    def test_empty_and_invalid_views_do_not_vote_or_leak(self):
        parsed, retained = worker._agree_readings("trip_distance",
            ("42.00", "EV Ratio 10%", "42.00"),
            ("mi", "Range 200 mi", "mi", "", "mI", ""))
        self.assertEqual(parsed, ("42.00", "mi"))
        for excluded in ("EV Ratio", "10%", "Range", "mI"):
            self.assertNotIn(excluded, str(retained))
        self.assertTrue(retained)

    def test_cartesian_pairs_cannot_replace_distinct_component_support(self):
        for numeric, units in ((("42", "", ""), ("mi",) * 6),
                               (("42",) * 3, ("mi", "", "", "", "", ""))):
            with self.subTest(numeric=numeric, units=units):
                parsed, _ = worker._agree_readings("trip_distance", numeric, units)
                self.assertIsNone(parsed)
        parsed, _ = worker._agree_readings("trip_distance", ("42", "42", ""),
                                            ("mi", "mi", "", "", "", ""))
        self.assertEqual(parsed, ("42", "mi"))

    def test_components_cannot_borrow_missing_number_or_unit_from_other_crop(self):
        for numeric, units in ((("",) * 3, ("42 mi",) * 6),
                               (("42 mi", "42 mi", ""), ("",) * 6),
                               (("42", "42 mi", "42 mi"), ("mi", "", "", "", "", "")),
                               (("42", "", ""), ("mi", "42 mi", "42 mi", "", "", ""))):
            with self.subTest(numeric=numeric, units=units):
                parsed, _ = worker._agree_readings("trip_distance", numeric, units)
                self.assertIsNone(parsed)

    def test_one_complete_minority_conflict_vetoes_majority(self):
        parsed, _ = worker._agree_readings("trip_distance", ("42", "42", "43"), ("mi",) * 6)
        self.assertIsNone(parsed)
        parsed, _ = worker._agree_readings("trip_duration", ("02:10", "02:10", "02:11"))
        self.assertIsNone(parsed)

    def test_literal_unit_is_required_and_never_repaired(self):
        for units in (("mPG",) * 6, ("mpg",) * 6, ("",) * 6):
            with self.subTest(units=units):
                parsed, _ = worker._agree_readings("trip_average_mpg", ("41",) * 3, units)
                self.assertIsNone(parsed)
        parsed, _ = worker._agree_readings("trip_average_mpg", ("41",) * 3,
                                           ("MPG", "MPG", "mPG", "", "", ""))
        self.assertEqual(parsed, ("41", "MPG"))

    def test_field_association_is_required_despite_valid_components(self):
        parsed, _ = worker._agree_readings("trip_distance", ("42",) * 3, ("mi",) * 6,
                                           associated=False)
        self.assertIsNone(parsed)

    def test_duration_bounds_and_two_numeric_ids(self):
        for value, expected in (("0:00", "00:00"), ("125:59", "125:59")):
            with self.subTest(value=value):
                parsed, _ = worker._agree_readings("trip_duration", (value, value, ""))
                self.assertEqual(parsed, (expected, None))
        for values in (("02:60",) * 3, ("02:09", "2:9", ""), ("-2:00",) * 3):
            with self.subTest(values=values):
                parsed, _ = worker._agree_readings("trip_duration", values)
                self.assertIsNone(parsed)
        parsed, _ = worker._agree_readings("trip_duration", ("02:59", "02:59", "02:60"))
        self.assertEqual(parsed, ("02:59", None))

    def test_native_timeout_crash_and_shared_loss_are_not_empty_votes(self):
        from PIL import Image
        image = Image.new("RGB", (20, 10), "white")
        assets = InterpretationAssets(Path("engine"), Path("models"), "0" * 64)
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / "models").mkdir()
            model = b"authored model surrogate"
            (folder / "models/eng.traineddata").write_bytes(model)
            model_hash = hashlib.sha256(model).hexdigest()
            failures = ((subprocess.TimeoutExpired("engine", 15), subprocess.TimeoutExpired),
                        (subprocess.CompletedProcess("engine", 1, ""), RuntimeError))
            for failure, expected_error in failures:
                with self.subTest(error=expected_error.__name__), \
                     patch.object(worker, "_validate_assets"), \
                     patch.object(worker, "_MODEL_SHA256", model_hash), \
                     patch.object(worker.subprocess, "run") as execute:
                    if isinstance(failure, Exception):
                        execute.side_effect = failure
                    else:
                        execute.return_value = failure
                    with self.assertRaises(expected_error):
                        worker._ocr(image, (0, 0, 20, 10), assets, folder, kind="numeric")
            with patch.object(worker, "_validate_assets", side_effect=SharedAssetError("model unavailable")):
                with self.assertRaises(SharedAssetError):
                    worker._ocr(image, (0, 0, 20, 10), assets, folder, kind="numeric")

    def test_fixed_ocr_view_counts_without_extra_attempts(self):
        from PIL import Image
        image = Image.new("RGB", (20, 10), "white")
        assets = InterpretationAssets(Path("engine"), Path("models"), "0" * 64)
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / "models").mkdir()
            model = b"authored model surrogate"
            (folder / "models/eng.traineddata").write_bytes(model)
            for kind, count in (("anchor", 2), ("numeric", 3), ("unit", 6)):
                with self.subTest(kind=kind), patch.object(worker, "_validate_assets"), \
                     patch.object(worker, "_MODEL_SHA256", hashlib.sha256(model).hexdigest()), \
                     patch.object(worker.subprocess, "run", return_value=subprocess.CompletedProcess(
                         "engine", 0, "authored unrecognized output")) as execute:
                    texts = worker._ocr(image, (0, 0, 20, 10), assets, folder, kind=kind)
                    self.assertEqual(len(texts), count)
                    self.assertEqual(execute.call_count, count)
                    for call in execute.call_args_list:
                        arguments = call.args[0]
                        self.assertEqual(arguments[arguments.index("--oem") + 1], "1")
                        if kind == "unit":
                            self.assertFalse(any("whitelist" in item for item in arguments))


class DecoderBoundaryTests(unittest.TestCase):
    def test_shared_native_probe_uses_no_photo_and_requires_success(self):
        assets = InterpretationAssets(Path("engine"), Path("models"), "0" * 64)
        with patch("flex_photo.interpretation._validate_assets"), \
             patch.object(worker, "run_bounded", return_value={"validated": True}) as run:
            validate_interpretation_assets(assets)
            run.assert_called_once_with(None, assets)
        for payload in ({"shared_error": "decoder unavailable"}, {"error": "worker crashed"}, {}):
            with self.subTest(payload=payload), \
                 patch("flex_photo.interpretation._validate_assets"), \
                 patch.object(worker, "run_bounded", return_value=payload):
                with self.assertRaises(SharedAssetError):
                    validate_interpretation_assets(assets)

    def test_missing_decoder_runtime_is_shared_asset_failure(self):
        original_import = builtins.__import__

        def unavailable(name, *args, **kwargs):
            if name == "pillow_heif":
                raise ImportError("private native loader detail")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=unavailable):
            with self.assertRaisesRegex(SharedAssetError, "shared decoder runtime unavailable"):
                worker._decode(Path("unused.heic"))

    def test_oversized_primary_rejected_before_pixel_conversion(self):
        from unittest.mock import MagicMock, Mock
        import pillow_heif
        primary = Mock(size=(16_000_001, 1))
        decoded = MagicMock(primary_index=0)
        decoded.__getitem__.return_value = primary
        with patch.object(pillow_heif, "open_heif", return_value=decoded):
            with self.assertRaisesRegex(ValueError, "primary pixel limit"):
                worker._decode(Path("unused.heic"))
        primary.to_pillow.assert_not_called()


if __name__ == "__main__":
    unittest.main()
