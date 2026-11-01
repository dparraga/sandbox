"""Selective cropped fallback boundaries; no transport, credentials or OCR tuning."""
import base64
from dataclasses import replace
import hashlib
import io
import json
import math
import re
from statistics import median

from .interpretation import FieldObservation, _FIELDS, _PRIMARY_PIXELS, _CROP_PIXELS, _SCALED_PIXELS

_TITLES = {"drive_info": "Drive Info", "trip_summary": "Trip Summary"}
_KEYS = {"case_id", "view_id", "title_text", "field_label_text", "readable",
         "value_text", "unit_text", "reason"}
_PAYLOAD_BUDGET = 6_000_000  # safely below the fallback worker's bounded JSON transport


def _pixel_profile(image, bounds):
    """Measure complete foreground glyphs and punctuation, not claimed text.

    This rejects missing/occluded digits and unsupported punctuation. Component
    evidence cannot prove glyph identity and is not an OCR accuracy guarantee.
    """
    from ._interpretation_worker import _crosses_reading_edge
    crop = image.crop(bounds).convert("L")
    data = bytearray(crop.point(lambda value: 255 if value > 190 else 0).tobytes())
    width, height = crop.size
    components, areas = [], {}
    for start in range(len(data)):
        if not data[start]:
            continue
        data[start] = 0
        stack, points = [start], []
        while stack:
            point = stack.pop()
            points.append(point)
            x, y = point % width, point // width
            for xx, yy in ((x-1, y), (x+1, y), (x, y-1), (x, y+1)):
                if 0 <= xx < width and 0 <= yy < height and data[yy*width+xx]:
                    data[yy*width+xx] = 0
                    stack.append(yy*width+xx)
        if len(points) >= 2:
            xs, ys = [p % width for p in points], [p // width for p in points]
            box = (min(xs), min(ys), max(xs)+1, max(ys)+1)
            components.append(box)
            areas[box] = len(points)
    glyphs = [b for b in components if b[3]-b[1] >= 8
              and .08 <= (b[2]-b[0])/(b[3]-b[1]) <= 1.3]
    if not glyphs:
        return None
    size = median(b[3]-b[1] for b in glyphs)
    glyphs = [b for b in glyphs if .75*size <= b[3]-b[1] <= 1.25*size]
    if not glyphs:
        return None
    top, bottom = min(b[1] for b in glyphs), max(b[3] for b in glyphs)
    # A clipped component must never disappear through the height filter.
    relevant = [b for b in components if min(b[3], bottom)-max(b[1], top) > 0]
    if any(_crosses_reading_edge(image, bounds, b) for b in relevant):
        return None
    signs = [b for b in components if b[2]-b[0] >= 2*(b[3]-b[1])
             and b[2] <= min(g[0] for g in glyphs)
             and top+.25*size <= (b[1]+b[3])/2 <= bottom-.25*size]
    # Camera speckles cannot supply punctuation. Require noise to be small in
    # both dimensions AND ink area relative to the measured digit height.
    # Check every original edge first and preserve even small detached signs.
    noise = [b for b in components if b not in glyphs and b not in signs
             and b[2]-b[0] < .1*size and b[3]-b[1] < .1*size
             and areas[b] < .005*size*size]
    marks = [b for b in components if b not in glyphs and b[3]-b[1] <= .4*size
             and b not in noise and b[2]-b[0] <= .4*size and top <= b[1] <= bottom]
    colon = 0
    used = set()
    for i, a in enumerate(marks):
        for j, b in enumerate(marks[i+1:], i+1):
            if (i not in used and j not in used
                    and abs((a[0]+a[2])-(b[0]+b[2])) <= .25*size
                    and .15*size <= abs(a[1]-b[1]) <= .8*size):
                colon += 1
                used.update((i, j))
    decimals = sum(i not in used and b[1] >= bottom-.35*size for i, b in enumerate(marks))
    # Height/aspect grouping may not silently discard a leading digit, sign or
    # partial glyph. Unexplained components overlapping the numeric row veto it.
    if any(b not in glyphs and b not in marks and b not in signs and b not in noise for b in relevant):
        return None
    return {"digits": len(glyphs), "colons": colon, "decimals": decimals, "signs": len(signs)}


def _supports(profile, text):
    return (profile is not None and profile["digits"] == sum(c.isdigit() for c in text)
            and profile["colons"] == text.count(":")
            and profile["decimals"] == text.count(".")
            and profile["signs"] == text.count("-"))


def _payloads(image, panels):
    from PIL import Image
    crops = [(role, image.crop(bounds).convert("RGB")) for role, bounds in panels]
    payloads = []
    for view_id in (0, 1):
        size = (max(c.width for _, c in crops)+16, sum(c.height+8 for _, c in crops)+8)
        if size[0]*size[1] > _SCALED_PIXELS:
            return []
        canvas = Image.new("RGB", size, "black")
        y, regions = 8, []
        for role, crop in crops:
            canvas.paste(crop if view_id == 0 else crop.convert("L").convert("RGB"), (8, y))
            regions.append({"role": role, "bounds": [8, y, 8+crop.width, y+crop.height]})
            y += crop.height+8
        output = io.BytesIO()
        canvas.save(output, format="PNG")  # fresh image has no source EXIF or metadata
        if output.tell() > 2_000_000:
            return []
        payloads.append({"view_id": view_id, "png_base64": base64.b64encode(output.getvalue()).decode("ascii"),
                         "pixel_sha256": hashlib.sha256(canvas.tobytes()).hexdigest(), "panels": regions})
    return payloads


def prepare_candidates(image, baseline):
    """Called inside the bounded decode worker, never by an uncontained decoder.

    Known layouts reuse their geometry; unresolved layouts require the unchanged
    title detector's unique plausible upper title. Failed native processing is
    never a fallback trigger.
    """
    from ._interpretation_worker import (_title_components, _drive_label_bottom,
                                         _segment_reading)
    if (image.width*image.height > _PRIMARY_PIXELS or baseline.get("error")
            or baseline.get("shared_error") or baseline.get("excluded")
            or baseline.get("layout") not in (*_TITLES, "unresolved")):
        return []
    if any("failure" in issue or "resource" in issue for issue in baseline.get("issues", ())):
        return []
    observations = {o["field_id"]: o for o in baseline.get("observations", ())}
    candidates = _title_components(image)
    if not candidates or (len(candidates)>1 and abs(candidates[1][1]-candidates[0][1]) <= 10):
        return []
    left, top, right, bottom = candidates[0]
    width = right-left
    layout = baseline["layout"]
    if layout == "unresolved":
        layout = "drive_info" if width < 130 else "trip_summary"
    def native(box):
        return (max(0, math.floor(box[0]*image.width/800)), max(0, math.floor(box[1]*image.height/600)),
                min(image.width, math.ceil(box[2]*image.width/800)), min(image.height, math.ceil(box[3]*image.height/600)))
    if layout == "drive_info":
        boxes = {"trip_distance": (left-.6*width, top+.31*width, right+.6*width, top+.88*width),
                 "trip_duration": (left-.6*width, top+.98*width, right+.6*width, top+1.54*width)}
    else:
        boxes = {"trip_distance": (left-.62*width, top+.25*width, right+.57*width, top+.49*width),
                 "trip_duration": (left-.62*width, top+.52*width, right+.44*width, top+.76*width),
                 "trip_average_mpg": (left-.62*width, top+1.07*width, right+.7*width, top+1.34*width),
                 "odometer": (max(0, left-2.2*width), top+1.80*width, left-1.1*width, top+2.12*width)}
    result = []
    title = native(candidates[0])
    for field, box in boxes.items():
        primary = observations.get(field, {})
        if primary.get("status") in ("clear", "absent"):
            continue
        bounds = native(box)
        x0, y0, x1, y1 = bounds
        if x0 >= x1 or y0 >= y1 or (x1-x0)*(y1-y0) > _CROP_PIXELS:
            continue
        label = None
        number = bounds
        if layout == "drive_info":
            cut = y0+int((y1-y0)*.46)
            label = (x0, y0, x1, _drive_label_bottom(image, bounds, cut))
            number = (x0+int((x1-x0)*.30), cut, x1, y1)
        elif field != "odometer":
            cut = x0+int((x1-x0)*.60)
            label, number = (x0,y0,cut,y1), (cut,y0,x1,y1)
        unit = None
        if field != "trip_duration":
            parts = _segment_reading(image, number)
            if parts is None:
                continue
            number, unit = parts
        profile = _pixel_profile(image, number)
        if profile is None or (field == "trip_duration" and (profile["digits"] < 3 or profile["colons"] != 1)):
            continue
        panels = [("title",title)] + ([("label",label)] if label else []) + [("numeric",number)]
        if unit:
            panels.append(("unit",unit))
        if any(b[0]>=b[2] or b[1]>=b[3] or (b[2]-b[0])*(b[3]-b[1])>_CROP_PIXELS for _,b in panels):
            continue
        payloads = _payloads(image, panels)
        if len(payloads) != 2:
            continue
        identity = hashlib.sha256((layout+field+"".join(p["pixel_sha256"] for p in payloads)).encode()).hexdigest()
        candidate = {"case_id": identity, "layout": layout, "field_id": field, "payloads": payloads,
                     "pixel_evidence": profile, "primary_evidence": primary.get("evidence", []),
                     "geometry": {"field_bounds": list(bounds), **{role+"_bounds": list(b) for role,b in panels}}}
        if len(json.dumps(result+[candidate]).encode("utf-8")) <= _PAYLOAD_BUDGET:
            result.append(candidate)
    return result


def validate_response(candidate, responses):
    """Admit only two exact, pixel-supported readings with no complete conflict."""
    from ._interpretation_worker import _LABELS, _agree_readings
    field, layout = candidate.get("field_id"), candidate.get("layout")
    if field not in _FIELDS or layout not in _TITLES or not isinstance(responses, (list,tuple)) or len(responses)!=2:
        return None
    payloads = candidate.get("payloads", [])
    if (len(payloads) != 2 or {p.get("view_id") for p in payloads} != {0,1}
            or len({p.get("pixel_sha256") for p in payloads}) != 2):
        return None
    geometry = candidate.get("geometry", {})
    def valid(box):
        return (isinstance(box,(list,tuple)) and len(box)==4 and all(type(v) is int for v in box)
                and 0 <= box[0] < box[2] and 0 <= box[1] < box[3]
                and (box[2]-box[0])*(box[3]-box[1]) <= _CROP_PIXELS)
    field_bounds = geometry.get("field_bounds")
    roles = ("numeric", "label") if field != "odometer" else ("numeric",)
    if field != "trip_duration":
        roles += ("unit",)
    if not valid(field_bounds) or not valid(geometry.get("title_bounds")):
        return None
    for role in roles:
        box = geometry.get(role+"_bounds")
        if not valid(box) or not (field_bounds[0]<=box[0]<box[2]<=field_bounds[2]
                                 and field_bounds[1]<=box[1]<box[3]<=field_bounds[3]):
            return None
    label = _LABELS[field]
    numbers, units = [], []
    ids = set()
    for r in responses:
        if not isinstance(r,dict) or set(r)!=_KEYS:
            return None
        if (r["case_id"] != candidate["case_id"] or type(r["view_id"]) is not int
                or r["view_id"] not in (0,1) or r["view_id"] in ids
                or type(r["readable"]) is not bool or r["readable"] is not True
                or r["reason"] != "readable" or r["title_text"] != _TITLES[layout]
                or (r["field_label_text"] not in (None, "") if field == "odometer"
                    else r["field_label_text"] != label) or not isinstance(r["value_text"],str)
                or not _supports(candidate.get("pixel_evidence"), r["value_text"])):
            return None
        ids.add(r["view_id"])
        number, unit = r["value_text"], r["unit_text"]
        if field == "trip_duration":
            if unit is not None or not re.fullmatch(r"[0-9]+:[0-5][0-9]",number):
                return None
        elif unit != ("MPG" if field == "trip_average_mpg" else "mi") or not re.fullmatch(r"-?[0-9]+(?:\.[0-9]+)?",number):
            return None
        numbers.append(number)
        if unit is not None:
            units.append(unit)
    # Native complete candidates retain veto authority; model agreement cannot outvote them.
    evidence = candidate.get("primary_evidence", [])
    original_numbers = evidence[0].get("views", []) if evidence else []
    original_units = evidence[1].get("views", []) if len(evidence)>1 else []
    value, retained = _agree_readings(field, tuple(numbers)+tuple(original_numbers), tuple(units)+tuple(original_units), True)
    if value is None:
        return None
    return FieldObservation(field,"clear", "\n".join(retained),value[0],value[1])


def merge_recoveries(photo, recoveries, *, layout=None):
    """Clear and absent native fields remain final; only unresolved fields change."""
    accepted = {o.field_id: o for o in recoveries if o.field_id in _FIELDS and o.status == "clear"}
    original = {o.field_id: o for o in photo.observations}
    observations = tuple(original[field] if field in original and original[field].status in ("clear","absent")
                         else accepted.get(field,original.get(field,FieldObservation(field,"unclear"))) for field in _FIELDS)
    anchors = {o.field_id for o in observations if o.status == "clear"}
    promoted = (photo.layout=="unresolved" and layout in _TITLES
                and {"trip_distance","trip_duration"} <= anchors)
    duration_recovered = ('trip_duration' in accepted
                          and original.get('trip_duration', FieldObservation('trip_duration', 'unclear')).status != 'clear')
    issues = tuple(i for i in photo.issues if not (duration_recovered
                   and i.reason == 'Trip Time unreadable, disagreeing or malformed'))
    return replace(photo, observations=observations, layout=layout if promoted else photo.layout, issues=issues)
