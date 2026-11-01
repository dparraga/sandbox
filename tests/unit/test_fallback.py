"""Synthetic pixel evidence and admission tests; no cloud or private photographs."""
import base64
import io
from pathlib import Path
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw

from flex_photo.fallback import (_pixel_profile, _supports, _payloads,
                                 prepare_candidates, validate_response, merge_recoveries)
from flex_photo.interpretation import FieldObservation, PhotoInterpretation


def duration_pixels():
    image = Image.new("RGB",(160,80),(3,5,7))
    draw = ImageDraw.Draw(image)
    for x in (25,40,70,85):
        draw.rectangle((x,25,x+7,49),fill=(235,240,245))
    for y in (30,40):
        draw.rectangle((57,y,59,y+2),fill=(235,240,245))
    return image


def candidate():
    image = duration_pixels()
    return {"case_id":"synthetic", "layout":"drive_info", "field_id":"trip_duration",
            "payloads":_payloads(image,[("numeric",(10,10,145,65))]),
            "pixel_evidence":_pixel_profile(image,(10,10,145,65)), "primary_evidence":[],
            "geometry":{"field_bounds":[10,10,145,65],"title_bounds":[10,1,145,9],
                        "label_bounds":[10,10,145,20],"numeric_bounds":[10,20,145,65]}}


def responses(case, value="02:14"):
    return [{"case_id":case["case_id"], "view_id":view, "title_text":"Drive Info",
             "field_label_text":"Trip Time", "readable":True,"value_text":value,
             "unit_text":None,"reason":"readable"} for view in (0,1)]


class PixelEvidenceTests(unittest.TestCase):
    def test_whole_glyph_count_and_visible_colon_required(self):
        image = duration_pixels()
        profile = _pixel_profile(image,(10,10,145,65))
        self.assertTrue(_supports(profile,"02:14"))
        self.assertFalse(_supports(profile,"002:14"))
        self.assertFalse(_supports(profile,"0214"))
        self.assertFalse(_supports(profile,"02.14"))
        ImageDraw.Draw(image).rectangle((10,10,65,65), fill=(3,5,7))
        obstructed = _pixel_profile(image,(10,10,145,65))
        self.assertFalse(_supports(obstructed,"02:14"))

    def test_boundary_crossing_and_blank_pixels_veto(self):
        self.assertIsNone(_pixel_profile(Image.new("RGB",(160,80)),(10,10,145,65)))
        self.assertIsNone(_pixel_profile(duration_pixels(),(28,10,145,65)))
        image=Image.new("RGB",(160,80))
        draw=ImageDraw.Draw(image)
        draw.rectangle((20,20,25,27),fill="white")
        draw.rectangle((40,20,50,59),fill="white")
        self.assertIsNone(_pixel_profile(image,(10,10,145,65)))

    def test_tall_or_narrow_leading_component_cannot_disappear(self):
        for box in ((12,15,20,55),(12,25,13,49),(12,30,20,42)):
            image=duration_pixels()
            ImageDraw.Draw(image).rectangle(box,fill=(235,240,245))
            with self.subTest(box=box):
                self.assertFalse(_supports(_pixel_profile(image,(10,10,145,65)),"02:14"))

    def test_single_hour_digit_preserves_frozen_duration_grammar(self):
        image=duration_pixels()
        ImageDraw.Draw(image).rectangle((20,20,35,55),fill=(3,5,7))
        profile=_pixel_profile(image,(10,10,145,65))
        self.assertTrue(_supports(profile,"2:14"))
        case=candidate()
        case["pixel_evidence"]=profile
        self.assertEqual(validate_response(case,responses(case,"2:14")).value,"02:14")

    def test_metadata_free_minimal_views(self):
        image = duration_pixels()
        image.info["private"] = "must disappear"
        payloads = _payloads(image,[("numeric",(10,10,145,65))])
        self.assertEqual([p["view_id"] for p in payloads],[0,1])
        self.assertNotEqual(payloads[0]["pixel_sha256"],payloads[1]["pixel_sha256"])
        for p in payloads:
            with Image.open(io.BytesIO(base64.b64decode(p["png_base64"]))) as crop:
                self.assertFalse(crop.info)
                self.assertLess(crop.width*crop.height,image.width*image.height)
        with patch("flex_photo.fallback._SCALED_PIXELS",1):
            self.assertEqual(_payloads(image,[("numeric",(10,10,145,65))]),[])


class AdmissionTests(unittest.TestCase):
    def test_scalar_requires_literal_unit_and_visible_decimal(self):
        case=candidate()
        case["field_id"]="trip_distance"
        case["pixel_evidence"]={"digits":3,"colons":0,"decimals":1,"signs":0}
        case["geometry"]["unit_bounds"]=[120,20,140,50]
        r=responses(case,"42.5")
        for item in r:
            item.update(field_label_text="Trip Distance",unit_text="mi")
        self.assertEqual(validate_response(case,r).value,"42.5")
        r[0]["unit_text"]="km"
        self.assertIsNone(validate_response(case,r))
        r[0]["unit_text"]="mi"
        r[0]["value_text"]="425"
        self.assertIsNone(validate_response(case,r))

    def test_reading_and_primary_complete_conflict(self):
        case = candidate()
        result = validate_response(case,responses(case))
        self.assertEqual((result.value,result.unit),("02:14",None))
        case["primary_evidence"] = [{"views":["03:14"]}]
        self.assertIsNone(validate_response(case,responses(case)))

    def test_schema_identity_literals_format_and_abstention(self):
        case = candidate()
        changes = [{"case_id":"wrong"},{"view_id":True},{"title_text":"Trip Summary"},
                   {"field_label_text":"Trip Distance"},{"unit_text":"mi"},
                   {"readable":False,"value_text":None,"reason":"unreadable"},
                   {"value_text":"02:64"},{"value_text":"2:14 extra"},
                   {"reason":"readable","unknown":1}]
        for change in changes:
            r = responses(case)
            r[0].update(change)
            with self.subTest(change=change):
                self.assertIsNone(validate_response(case,r))
        r=responses(case)
        r[1]["view_id"]=0
        self.assertIsNone(validate_response(case,r))

    def test_fake_matching_claims_on_obstructed_pixels_fail(self):
        case=candidate()
        image=duration_pixels()
        ImageDraw.Draw(image).rectangle((10,10,65,65),fill=(3,5,7))
        case["pixel_evidence"]=_pixel_profile(image,(10,10,145,65))
        self.assertIsNone(validate_response(case,responses(case)))

    def test_geometry_and_duplicate_render_veto(self):
        case=candidate()
        case["geometry"]["numeric_bounds"]=[0,0,150,70]
        self.assertIsNone(validate_response(case,responses(case)))
        case=candidate()
        case["payloads"][1]["pixel_sha256"]=case["payloads"][0]["pixel_sha256"]
        self.assertIsNone(validate_response(case,responses(case)))

    def test_merge_preserves_clear_absent_and_unresolved_layout_anchors(self):
        clear=FieldObservation("trip_duration","clear",value="01:00")
        absent=FieldObservation("odometer","absent")
        photo=PhotoInterpretation(Path("photo.heic"),"drive_info",(clear,absent))
        result=merge_recoveries(photo,[FieldObservation("trip_duration","clear",value="02:14"),
                                      FieldObservation("odometer","clear",value="123")])
        self.assertEqual(result.observations[1],clear)
        self.assertEqual(result.observations[3],absent)
        unresolved=PhotoInterpretation(Path("photo.heic"),"unresolved")
        result=merge_recoveries(unresolved,[clear],layout="drive_info")
        self.assertEqual(result.layout,"unresolved")


class EligibilityTests(unittest.TestCase):
    def test_excluded_nonmatch_and_failures_never_search_pixels(self):
        image=Image.new("RGB",(800,600))
        baselines=[{"layout":"excluded"},{"layout":"nonmatch"},
                   {"layout":"unresolved","error":"native failure"},
                   {"layout":"unresolved","issues":["individual native execution or containment failure"]}]
        with patch("flex_photo._interpretation_worker._title_components") as detector:
            for baseline in baselines:
                self.assertEqual(prepare_candidates(image,baseline),[])
            detector.assert_not_called()

    def test_clear_and_absent_fields_never_crop(self):
        image=Image.new("RGB",(800,600))
        baseline={"layout":"drive_info","observations":[
            {"field_id":"trip_distance","status":"clear"},
            {"field_id":"trip_duration","status":"absent"}]}
        with patch("flex_photo._interpretation_worker._title_components",return_value=[(400,140,480,156)]), \
                patch("flex_photo.fallback._pixel_profile") as pixels:
            self.assertEqual(prepare_candidates(image,baseline),[])
            pixels.assert_not_called()

    def test_oversize_and_ambiguous_geometry_veto(self):
        image=Image.new("RGB",(4001,4000))
        with patch("flex_photo._interpretation_worker._title_components") as detector:
            self.assertEqual(prepare_candidates(image,{"layout":"unresolved"}),[])
            detector.assert_not_called()
        image=Image.new("RGB",(800,600))
        with patch("flex_photo._interpretation_worker._title_components",return_value=[(400,140,480,156),(410,145,490,161)]):
            self.assertEqual(prepare_candidates(image,{"layout":"unresolved"}),[])
