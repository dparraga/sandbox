"""Private serial worker; OS containment is established before native imports."""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import signal
from statistics import median
import subprocess
import sys
import tempfile
import threading
import time

from .interpretation import (InterpretationAssets, SharedAssetError, _validate_assets,
    _parse_field, _FIELDS, _MODEL_SHA256, _MEMORY_BYTES, _DECODE_SECONDS, _OCR_SECONDS,
    _PHOTO_SECONDS, _PRIMARY_PIXELS, _CROP_PIXELS, _SCALED_PIXELS, _diagnostic_trace)


class _WindowsJob:
    def __init__(self, process):
        from ctypes import wintypes as w
        class Basic(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                        ("LimitFlags", w.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", w.DWORD),
                        ("Affinity", ctypes.c_size_t), ("PriorityClass", w.DWORD), ("SchedulingClass", w.DWORD)]
        class IO(ctypes.Structure):
            _fields_ = [(name, ctypes.c_uint64) for name in ("ReadOperationCount", "WriteOperationCount",
                "OtherOperationCount", "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]
        class Extended(ctypes.Structure):
            _fields_ = [("BasicLimitInformation", Basic), ("IoInfo", IO),
                        ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                        ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]
        class Accounting(ctypes.Structure):
            _fields_ = [(name, ctypes.c_int64) for name in ("TotalUserTime", "TotalKernelTime",
                        "ThisPeriodTotalUserTime", "ThisPeriodTotalKernelTime")] + [
                        (name, w.DWORD) for name in ("TotalPageFaultCount", "TotalProcesses",
                        "ActiveProcesses", "TotalTerminatedProcesses")]
        self.accounting_type = Accounting
        self.api = ctypes.WinDLL("kernel32", use_last_error=True)
        self.api.CreateJobObjectW.restype = w.HANDLE
        self.api.CreateJobObjectW.argtypes = [ctypes.c_void_p, w.LPCWSTR]
        self.api.SetInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD]
        self.api.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
        self.api.TerminateJobObject.argtypes = [w.HANDLE, w.UINT]
        self.api.QueryInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                                       w.DWORD, ctypes.c_void_p]
        self.api.CloseHandle.argtypes = [w.HANDLE]
        self.handle = self.api.CreateJobObjectW(None, None)
        limits = Extended()
        limits.BasicLimitInformation.LimitFlags = 0x2000 | 0x200  # kill-on-close + aggregate memory
        limits.JobMemoryLimit = _MEMORY_BYTES
        if not self.handle or not self.api.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            self.close()
            raise RuntimeError("Windows job memory enforcement unavailable")
        if not self.api.AssignProcessToJobObject(self.handle, w.HANDLE(int(process._handle))):
            self.close()
            raise RuntimeError("Windows worker containment unavailable")

    def close(self):
        if getattr(self, "handle", None):
            try:
                if not self.api.TerminateJobObject(self.handle, 1):
                    raise RuntimeError("Windows worker job termination failed")
                deadline = time.monotonic() + 5
                while True:
                    accounting = self.accounting_type()
                    if not self.api.QueryInformationJobObject(self.handle, 1, ctypes.byref(accounting),
                                                              ctypes.sizeof(accounting), None):
                        raise RuntimeError("Windows worker termination status unavailable")
                    if accounting.ActiveProcesses == 0:
                        break
                    if time.monotonic() >= deadline:
                        raise RuntimeError("Windows worker job termination deadline exceeded")
                    time.sleep(.01)
            finally:
                # Retain kill-on-close as a fallback even when explicit draining fails.
                self.api.CloseHandle(self.handle)
                self.handle = None


def _environment():
    env = {key: value for key, value in os.environ.items()
           if not key.upper().startswith(("TESS", "OMP", "PYTHON"))}
    env["OMP_THREAD_LIMIT"] = "1"
    return env


def run_bounded(path, assets, *, diagnostics=False):
    """Launch one worker and always reap its entire native process group/job."""
    # The parent owns derivatives so killing a crashed or timed-out worker
    # cannot bypass cleanup of pixels or the private model copy.
    temporary = tempfile.TemporaryDirectory(prefix="flex-photo-")
    try:
        return (_run_worker(path, assets, Path(temporary.name), diagnostics=True) if diagnostics
                else _run_worker(path, assets, Path(temporary.name)))
    finally:
        # Windows may briefly retain file references after a drained job exits.
        # Retry only that observed sharing/locking failure; every other cleanup
        # failure, or one lasting beyond the deadline, must remain visible.
        deadline = time.monotonic() + 5
        while True:
            try:
                temporary.cleanup()
                break
            except OSError as error:
                if (os.name != "nt" or getattr(error, "winerror", None) not in (32, 33)
                        or time.monotonic() >= deadline):
                    raise
                time.sleep(.01)


def _run_worker(path, assets, workspace, *, diagnostics=False):
    started = time.monotonic()
    process = subprocess.Popen([sys.executable, "-m", __name__], stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
        start_new_session=os.name != "nt", env=_environment(),
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        encoding="utf-8")
    job = None
    messages = queue.Queue()
    def read():
        try:
            while line := process.stdout.readline(65_537):
                if len(line) > 65_536:
                    messages.put({"error": "worker output limit exceeded"})
                    return
                messages.put(json.loads(line))
        except (ValueError, OSError):
            pass
        finally:
            messages.put({"error": "native worker exited without a result"})
    try:
        if os.name == "nt":
            job = _WindowsJob(process)
        thread = threading.Thread(target=read, daemon=True)
        thread.start()
        process.stdin.write(json.dumps({"path": str(path.resolve()) if path is not None else None,
            "exe": str(assets.tesseract_executable.resolve()),
            "models": str(assets.tessdata_directory.resolve()), "sha": assets.executable_sha256,
            "workspace": str(workspace), "diagnostics": diagnostics}) + "\n")
        process.stdin.flush()
        process.stdin.close()
        first = messages.get(timeout=_DECODE_SECONDS)
        if first.get("stage") != "decoded":
            return first
        remaining = _PHOTO_SECONDS - (time.monotonic() - started)
        return messages.get(timeout=max(0.01, remaining))
    except queue.Empty:
        raise RuntimeError("photo decode or total deadline exceeded") from None
    finally:
        try:
            if job:
                job.close()
            elif os.name != "nt":
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()
            if process.stdout:
                process.stdout.close()


def _load_decoder():
    try:
        from PIL import Image
        import pillow_heif
    except (ImportError, OSError) as error:
        raise SharedAssetError("shared decoder runtime unavailable") from error
    return Image, pillow_heif


def _decode(path):
    import warnings
    Image, pillow_heif = _load_decoder()
    Image.MAX_IMAGE_PIXELS = _PRIMARY_PIXELS
    warnings.simplefilter("error", Image.DecompressionBombWarning)
    pillow_heif.options.DISABLE_SECURITY_LIMITS = False
    pillow_heif.options.THUMBNAILS = False
    pillow_heif.options.DEPTH_IMAGES = False
    pillow_heif.options.AUX_IMAGES = False
    pillow_heif.options.DECODE_THREADS = 1
    decoded = pillow_heif.open_heif(path, convert_hdr_to_8bit=True)
    primary = decoded[decoded.primary_index]
    if primary.size[0] * primary.size[1] > _PRIMARY_PIXELS:
        raise ValueError("primary pixel limit exceeded")
    # libheif has applied HEIF rotation/mirroring during decode. Do not transpose again.
    return primary.to_pillow().convert("RGB")


def _crosses_reading_edge(image, bounds, component):
    """A selected glyph continuing outside its reading crop is incomplete."""
    x0, y0, x1, y1 = bounds
    left, top, right, bottom = component
    strips = []
    if left == 0:
        if x0 == 0:
            return True
        strips.append(((x0 - 1, y0 + top, x0 + 1, y0 + bottom), True))
    if right == x1 - x0:
        if x1 == image.width:
            return True
        strips.append(((x1 - 1, y0 + top, x1 + 1, y0 + bottom), True))
    if top == 0:
        if y0 == 0:
            return True
        strips.append(((x0 + left, y0 - 1, x0 + right, y0 + 1), False))
    if bottom == y1 - y0:
        if y1 == image.height:
            return True
        strips.append(((x0 + left, y1 - 1, x0 + right, y1 + 1), False))
    for box, vertical in strips:
        strip = image.crop(box).convert("L")
        pixels = strip.load()
        if vertical:
            if any(pixels[0, y] > 190 and pixels[1, y] > 190 for y in range(strip.height)):
                return True
        elif any(pixels[x, 0] > 190 and pixels[x, 1] > 190 for x in range(strip.width)):
            return True
    return False


def _segment_reading(image, bounds):
    """Separate numeric and smaller unit glyphs within one requested reading."""
    crop = image.crop(bounds)
    if crop.width * crop.height > _CROP_PIXELS:
        raise ValueError("crop pixel limit exceeded")
    gray = crop.convert("L")
    data = bytearray(gray.point(lambda value: 255 if value > 190 else 0).tobytes())
    components, marks = [], []
    width, height = crop.size
    for start in range(len(data)):
        if not data[start]:
            continue
        data[start] = 0
        stack, xs, ys = [start], [], []
        while stack:
            point = stack.pop()
            x, y = point % width, point // width
            xs.append(x)
            ys.append(y)
            for xx, yy in ((x, y - 1), (x, y + 1), (x - 1, y), (x + 1, y)):
                if 0 <= xx < width and 0 <= yy < height:
                    neighbor = yy * width + xx
                    if data[neighbor]:
                        data[neighbor] = 0
                        stack.append(neighbor)
        if len(xs) >= 15 and max(xs) - min(xs) >= 3:
            box = (min(xs), min(ys), max(xs) + 1, max(ys) + 1)
            if max(ys) - min(ys) >= 5:
                components.append(box)
            elif box[2] - box[0] >= 2 * (box[3] - box[1]):
                marks.append(box)
    candidates = [c for c in components if 8 <= c[3] - c[1] < height * .8
                  and .12 <= (c[2] - c[0]) / (c[3] - c[1]) <= 1.3]
    clusters = []
    for component in candidates:
        glyph_height = component[3] - component[1]
        cluster = [c for c in candidates if .9 * glyph_height <= c[3] - c[1] <= 1.1 * glyph_height
                   and abs((c[1] + c[3]) - (component[1] + component[3])) <= glyph_height * .6]
        if len(cluster) >= 2:
            clusters.append(cluster)
    numeric = max(clusters, key=lambda group: (len(group), sum(c[3] - c[1] for c in group) / len(group))) if clusters else candidates
    if not numeric:
        return None
    glyph_height = median(c[3] - c[1] for c in numeric)
    left = min(c[0] for c in numeric)
    edge = max(c[2] for c in numeric)
    top, bottom = min(c[1] for c in numeric), max(c[3] for c in numeric)
    # A height/cluster filter must never silently remove a leading digit or sign.
    for component in components + marks:
        c0, c1, c2, c3 = component
        if c2 <= left and left - c2 <= glyph_height:
            overlap = min(c3, bottom) - max(c1, top)
            if (c3 - c1 >= glyph_height * .5
                    and overlap >= min(c3 - c1, glyph_height) * .5):
                return None
            if (c2 - c0 >= 2 * (c3 - c1)
                    and top + glyph_height * .25 <= (c1 + c3) / 2 <= bottom - glyph_height * .25):
                return None
    if any(_crosses_reading_edge(image, bounds, component) for component in numeric):
        return None
    units = [c for c in components if edge <= c[0] < edge + glyph_height * 3
             and glyph_height * .15 <= c[3] - c[1] <= glyph_height * 1.2
             and c[2] - c[0] < glyph_height * 1.3
             and c[1] >= top - glyph_height * .2 and c[3] <= bottom + glyph_height * .2]
    if not units:
        return None
    x0, y0, x1, y1 = bounds
    margin = 16
    # Keep antialiased stroke margins, capped at the inter-token whitespace.
    split = x0 + (edge + min(c[0] for c in units)) // 2
    number_bounds = (max(x0, x0 + min(c[0] for c in numeric) - margin),
                     max(y0, y0 + top - margin), min(x1, x0 + edge + margin, split),
                     min(y1, y0 + bottom + margin))
    unit_bounds = (max(x0, x0 + min(c[0] for c in units) - margin, split),
                   max(y0, y0 + min(c[1] for c in units) - margin),
                   min(x1, x0 + max(c[2] for c in units) + margin),
                   min(y1, y0 + max(c[3] for c in units) + margin))
    return number_bounds, unit_bounds


def _red_unit_view(crop, threshold):
    """Remove boundary glare from one fixed red-channel unit view."""
    from PIL import Image, ImageOps
    mask = crop.getchannel("R").point(lambda value: 255 if value > threshold else 0)
    width, height = mask.size
    data = bytearray(mask.tobytes())
    stack = [y * width + x for y in range(height) for x in (0, width - 1) if data[y * width + x]]
    stack += [y * width + x for x in range(width) for y in (0, height - 1) if data[y * width + x]]
    while stack:
        point = stack.pop()
        if not data[point]:
            continue
        data[point] = 0
        x, y = point % width, point // width
        for xx, yy in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 0 <= xx < width and 0 <= yy < height and data[yy * width + xx]:
                stack.append(yy * width + xx)
    remaining = data[:]
    components = []
    for start in range(width * height):
        if not remaining[start]:
            continue
        remaining[start] = 0
        stack, points = [start], []
        while stack:
            point = stack.pop()
            points.append(point)
            x, y = point % width, point // width
            for xx, yy in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if 0 <= xx < width and 0 <= yy < height and remaining[yy * width + xx]:
                    remaining[yy * width + xx] = 0
                    stack.append(yy * width + xx)
        xs, ys = [point % width for point in points], [point // width for point in points]
        if len(points) >= 4:
            components.append((min(xs), min(ys), max(xs) + 1, max(ys) + 1, points))
    candidates = [c for c in components if c[3] - c[1] >= 8
                  and .1 <= (c[2] - c[0]) / (c[3] - c[1]) <= 3.0]
    clusters = []
    for component in candidates:
        glyph_height = component[3] - component[1]
        cluster = [c for c in candidates if .7 * glyph_height <= c[3] - c[1] <= 1.4 * glyph_height
                   and abs((c[1] + c[3]) - (component[1] + component[3])) <= glyph_height * .6]
        if len(cluster) >= 2:
            clusters.append(cluster)
    if clusters:
        chosen = max(clusters, key=lambda group: (sum(len(c[4]) for c in group), len(group)))
        left, right = min(c[0] for c in chosen), max(c[2] for c in chosen)
        for point in range(width * height):
            if not left - 8 <= point % width <= right + 8:
                data[point] = 0
    mask = Image.frombytes("L", (width, height), bytes(data))
    bounds = mask.getbbox()
    if bounds:
        mask = mask.crop(bounds)
    mask = ImageOps.invert(mask)
    mask = mask.resize((max(1, round(mask.width * 48 / mask.height)), 48), Image.Resampling.LANCZOS)
    return ImageOps.expand(mask.convert("RGB"), border=24, fill="white")


def _ocr_views(crop, kind):
    """The fixed reviewed view order supplies stable per-crop view IDs."""
    from PIL import Image, ImageOps
    gray = crop.convert("L")
    bounds = gray.point(lambda value: 255 if value > 190 else 0).getbbox()
    if bounds:
        gray = gray.crop((max(0, bounds[0] - 16), max(0, bounds[1] - 16),
                          min(gray.width, bounds[2] + 16), min(gray.height, bounds[3] + 16)))
    views = []
    if kind == "unit":
        ordinary = ImageOps.autocontrast(ImageOps.invert(gray))
        # Same pixels with Otsu/Sauvola settings, each at native and 2x sizes.
        for _method in (0, 2):
            for scale in (1, 2):
                view = ordinary.resize((ordinary.width * scale, ordinary.height * scale), Image.Resampling.LANCZOS)
                views.append(ImageOps.expand(view.convert("RGB"), border=24, fill="white"))
        views.extend(_red_unit_view(crop, threshold) for threshold in (225, 230))
    elif kind in ("anchor", "numeric"):
        for threshold in (200, 220):
            mask = gray.point(lambda value: 255 if value > threshold else 0)
            bounds = mask.getbbox()
            if bounds:
                mask = mask.crop(bounds)
            views.append(ImageOps.expand(ImageOps.invert(mask).convert("RGB"), border=24, fill="white"))
        if kind == "numeric":
            ordinary = ImageOps.autocontrast(ImageOps.invert(gray))
            # Keep the reviewed native Sauvola view; no additional numeric 2x view.
            ordinary = ordinary.resize(ordinary.size, Image.Resampling.LANCZOS)
            views.append(ImageOps.expand(ordinary.convert("RGB"), border=24, fill="white"))
    else:
        raise ValueError("unsupported OCR view kind")
    return tuple(views)


def _ocr(image, bounds, assets, folder, psm="7", kind="anchor"):
    _validate_assets(assets)
    crop = image.crop(bounds)
    if crop.width * crop.height > _CROP_PIXELS:
        raise ValueError("crop pixel limit exceeded")
    results = []
    for index, view in enumerate(_ocr_views(crop, kind)):
        _validate_assets(assets)
        if view.width * view.height > _SCALED_PIXELS:
            raise ValueError("scaled crop pixel limit exceeded")
        if hashlib.sha256((folder / "models" / "eng.traineddata").read_bytes()).hexdigest() != _MODEL_SHA256:
            raise SharedAssetError("shared English model copy identity changed")
        ppm = folder / "reading.ppm"
        view.save(ppm, format="PPM")
        extra = []
        if kind in ("numeric", "unit"):
            extra = ["-c", "load_system_dawg=0", "-c", "load_freq_dawg=0"]
        if kind == "numeric":
            extra += ["-c", "tessedit_char_whitelist=0123456789.:-"]
        if (kind == "numeric" and index >= 2) or (kind == "unit" and 2 <= index < 4):
            extra += ["-c", "thresholding_method=2"]
        mode = "8" if kind == "unit" and index >= 4 else ("7" if kind in ("unit", "numeric") else psm)
        result = subprocess.run([str(assets.tesseract_executable), str(ppm), "stdout",
            "--tessdata-dir", str(folder / "models"), "-l", "eng", "--oem", "1", "--psm", mode] + extra,
            cwd=folder, env=_environment(), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8", timeout=_OCR_SECONDS)
        if result.returncode:
            _validate_assets(assets)
            raise RuntimeError("individual OCR execution failed")
        if result.stdout is None:
            raise RuntimeError("OCR output stream unavailable")
        if len(result.stdout) > 16_384:
            raise RuntimeError("OCR output limit exceeded")
        results.append(" ".join(result.stdout.split()))
    return tuple(results)


def _title_glyph_count(small, bounds):
    """Reject short glyph groups before any title OCR, using undilated ink."""
    pixels = small.load()
    left, top, right, bottom = bounds
    points = {(x, y) for y in range(max(0, top), min(small.height, bottom))
              for x in range(max(0, left), min(small.width, right))
              if min(pixels[x, y]) > 155 and max(pixels[x, y]) - min(pixels[x, y]) < 80}
    heights = []
    while points:
        point = points.pop()
        stack = [point]
        low = high = point[1]
        area = 0
        while stack:
            x, y = stack.pop()
            area += 1
            low, high = min(low, y), max(high, y)
            for neighbor in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if neighbor in points:
                    points.remove(neighbor)
                    stack.append(neighbor)
        if area >= 2:
            heights.append(high - low + 1)
    # Detached dots must not make a four-digit clock look like a title.
    threshold = median(heights) * .5 if heights else 0
    return sum(height >= threshold for height in heights)


def _title_components(image):
    """Locate white title-shaped glyph groups geometrically, without panel OCR."""
    small = image.resize((800, 600))
    pixels = small.load()
    mask = bytearray(800 * 600)
    for y in range(90, 340):
        for x in range(340, 700):
            r, g, b = pixels[x, y]
            if min(r, g, b) > 155 and max(r, g, b) - min(r, g, b) < 80:
                mask[y * 800 + x] = 255
    from PIL import Image
    # Join adjacent title glyphs horizontally, preserving separate text rows.
    data = bytearray(len(mask))
    for y in range(90, 340):
        row = y * 800
        count = sum(bool(v) for v in mask[row:row + 8])
        for x in range(800):
            if x > 0:
                if x + 7 < 800:
                    count += bool(mask[row + x + 7])
                if x - 8 >= 0:
                    count -= bool(mask[row + x - 8])
            if count:
                data[row + x] = 255
    boxes = []
    for start in range(90 * 800, 340 * 800):
        if not data[start]:
            continue
        data[start] = 0
        stack = [start]
        left = right = start % 800
        top = bottom = start // 800
        while stack:
            point = stack.pop()
            x, y = point % 800, point // 800
            left, right, top, bottom = min(left, x), max(right, x), min(top, y), max(bottom, y)
            for neighbor in (point - 800, point + 800, point - 1, point + 1):
                if 0 <= neighbor < len(data) and data[neighbor]:
                    data[neighbor] = 0
                    stack.append(neighbor)
        width, height = right - left - 14, bottom - top
        if 10 <= height <= 40 and ((65 <= width <= 110 and 3 <= width / height <= 8)
                                  or (140 <= width <= 220 and 4 <= width / height <= 10)):
            bounds = (left + 5, top - 3, right - 4, bottom + 4)
            if _title_glyph_count(small, bounds) >= 8:
                boxes.append(bounds)
    return boxes


_LABELS = {"trip_distance": "Trip Distance", "trip_duration": "Trip Time",
           "trip_average_mpg": "Trip Average", "odometer": ""}


def _complete_readings(field, numeric_views, unit_views, associated):
    if not associated:
        return ()
    # Each crop must supply its own component. Pairing must never borrow a
    # missing number from a full reading misrecognized inside the unit crop.
    pattern = r"[0-9]+:[0-5][0-9]" if field == "trip_duration" else r"-?[0-9]+(?:\.[0-9]+)?"
    numbers = [(index, text) for index, text in enumerate(numeric_views) if re.fullmatch(pattern, text)]
    prefix = _LABELS[field] + " " if _LABELS[field] else ""
    literal_unit = "MPG" if field == "trip_average_mpg" else "mi"
    units = [(index, text) for index, text in enumerate(unit_views) if text == literal_unit]
    combinations = ((ni, None, prefix + number) for ni, number in numbers) if field == "trip_duration" else (
        (ni, ui, prefix + number + " " + unit)
        for ni, number in numbers for ui, unit in units)
    complete = []
    for ni, ui, text in combinations:
        value = _parse_field(field, text)
        if value is not None:
            complete.append((ni, ui, text, value))
    return tuple(complete)


def _agree_readings(field, numeric_views, unit_views=(), associated=True):
    """Require distinct supporting views and veto every complete conflict."""
    complete = _complete_readings(field, numeric_views, unit_views, associated)
    values = {reading[3] for reading in complete}
    numeric_ids = {reading[0] for reading in complete}
    unit_ids = {reading[1] for reading in complete}
    clear = (len(values) == 1 and len(numeric_ids) >= 2
             and (field == "trip_duration" or len(unit_ids) >= 2))
    return (next(iter(values)) if clear else None,
            tuple(reading[2] for reading in complete))


def _reading_evidence(field, numbers, units, associated, numeric_bounds, unit_bounds):
    complete = _complete_readings(field, numbers, units, associated)
    numeric_ids = sorted({reading[0] for reading in complete})
    unit_ids = sorted({reading[1] for reading in complete if reading[1] is not None})
    evidence = [{"bounds": numeric_bounds, "views": [numbers[index] for index in numeric_ids],
                 "view_ids": numeric_ids}]
    if unit_bounds is not None:
        evidence.append({"bounds": unit_bounds, "views": [units[index] for index in unit_ids],
                         "view_ids": unit_ids})
    return evidence


def _drive_label_bottom(image, bounds, nominal):
    """Keep label descenders above a measured gap without changing numeric crops."""
    x0, y0, x1, y1 = bounds
    if (x1 - x0) * (y1 - y0) > _CROP_PIXELS:
        raise ValueError("crop pixel limit exceeded")
    gray = image.crop(bounds).convert("L")
    pixels = gray.load()
    row = nominal - y0
    stop = min(gray.height, int(gray.height * .60))
    while row < stop and any(pixels[x, row] > 190 for x in range(gray.width)):
        row += 1
    if row == stop:
        return nominal
    end = row
    while end < stop and not any(pixels[x, end] > 190 for x in range(gray.width)):
        end += 1
    return y0 + (row + end) // 2


def _interpret(image, assets, folder):
    import math
    if all(low == high for low, high in image.getextrema()):
        return {"layout": "nonmatch", "issues": []}
    sx, sy = image.width / 800, image.height / 600
    def native(box):
        return (max(0, math.floor(box[0] * sx)), max(0, math.floor(box[1] * sy)),
                min(image.width, math.ceil(box[2] * sx)), min(image.height, math.ceil(box[3] * sy)))
    matches = []
    candidates = _title_components(image)
    if len(candidates) > 1 and abs(candidates[1][1] - candidates[0][1]) <= 10:
        return {"layout": "unresolved", "issues": ["ambiguous layout anchor geometry"]}
    # Only the upper title-shaped row is an anchor candidate. A failed title
    # must not cause OCR to search lower dashboard readings for another title.
    for candidate in candidates[:1]:
        texts = _ocr(image, native(candidate), assets, folder, "7")
        for title, layout in (("Drive Info", "drive_info"), ("Trip Summary", "trip_summary")):
            if texts == (title, title):
                matches.append((layout, candidate))
    if len(matches) != 1:
        # No real negative dashboard rule has been validated. Unknown content stays unresolved.
        return {"layout": "unresolved", "issues": ["unsupported or ambiguous layout anchors"]}
    layout, (left, top, right, bottom) = matches[0]
    width, height = right - left, bottom - top
    if layout == "drive_info":
        boxes = {"trip_distance": (left - .6 * width, top + .31 * width, right + .6 * width, top + .88 * width),
                 "trip_duration": (left - .6 * width, top + .98 * width, right + .6 * width, top + 1.54 * width)}
    else:
        boxes = {"trip_distance": (left - .62 * width, top + .25 * width, right + .57 * width, top + .49 * width),
                 "trip_duration": (left - .62 * width, top + .52 * width, right + .44 * width, top + .76 * width),
                 "trip_average_mpg": (left - .62 * width, top + 1.07 * width, right + .7 * width, top + 1.34 * width),
                 "odometer": (max(0, left - 2.2 * width), top + 1.80 * width,
                              left - 1.1 * width, top + 2.12 * width)}
    observations, issues = [], []
    label_ok = set()
    for field in _FIELDS:
        if field not in boxes:
            observations.append({"field_id": field, "status": "absent"})
            continue
        bounds = native(boxes[field])
        if bounds[0] >= bounds[2] or bounds[1] >= bounds[3]:
            observations.append({"field_id": field, "status": "unclear"})
            continue
        label = ("", "")
        numeric_bounds = bounds
        if layout == "drive_info":
            x0, y0, x1, y1 = bounds
            cut = y0 + int((y1 - y0) * .46)
            label = _ocr(image, (x0, y0, x1, _drive_label_bottom(image, bounds, cut)), assets, folder, "7")
            numeric_bounds = (x0 + int((x1 - x0) * .30), cut, x1, y1)
        elif field != "odometer":
            x0, y0, x1, y1 = bounds
            cut = x0 + int((x1 - x0) * .60)
            label = _ocr(image, (x0, y0, cut, y1), assets, folder, "7")
            numeric_bounds = (cut, y0, x1, y1)
        expected_label = _LABELS[field]
        associated = not expected_label or all(text == expected_label or text.startswith(expected_label + " ")
                                              or text.startswith(expected_label + ".")
                                              or re.fullmatch(re.escape(expected_label) + r"[^\w\s]+", text) is not None
                                              for text in label)
        if expected_label and associated:
            label_ok.add(field)
        unit_bounds = None
        if field == "trip_duration":
            numbers = _ocr(image, numeric_bounds, assets, folder, "7", kind="numeric")
            units = ()
        else:
            parts = _segment_reading(image, numeric_bounds)
            if parts is None:
                numbers, units = (), ()
            else:
                numeric_bounds, unit_bounds = parts
                numbers = _ocr(image, numeric_bounds, assets, folder, "7", kind="numeric")
                units = _ocr(image, unit_bounds, assets, folder, "7", kind="unit")
        value, retained = _agree_readings(field, numbers, units, associated)
        observations.append({"field_id": field, "status": "clear" if value is not None else "unclear",
            "raw_text": "\n".join(retained) or None, "value": value[0] if value is not None else None,
            "unit": value[1] if value is not None else None,
            "evidence": _reading_evidence(field, numbers, units, associated, numeric_bounds, unit_bounds)})
        if field == "trip_duration" and value is None:
            issues.append("Trip Time unreadable, disagreeing or malformed")
    if not {"trip_distance", "trip_duration"} <= label_ok:
        return {"layout": "unresolved", "issues": ["incomplete requested label/geometry anchors"]}
    return {"layout": layout, "observations": observations, "issues": issues}


def main():
    # Blocking input is the parent handshake: Windows assigns the job before releasing it.
    request = json.loads(sys.stdin.readline(16_384))
    try:
        if os.name != "nt":
            import resource
            resource.setrlimit(resource.RLIMIT_AS, (_MEMORY_BYTES, _MEMORY_BYTES))
        assets = InterpretationAssets(Path(request["exe"]), Path(request["models"]), request["sha"])
        _validate_assets(assets)
        try:
            version = subprocess.run([str(assets.tesseract_executable), "--version"],
                cwd=assets.tesseract_executable.parent, env=_environment(), stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, text=True, timeout=_OCR_SECONDS)
        except (OSError, subprocess.SubprocessError) as error:
            raise SharedAssetError("shared executable unavailable") from error
        expected = "tesseract v5.5.3.20260724" if os.name == "nt" else "tesseract 5.3.0"
        if version.returncode or not version.stdout.splitlines() or version.stdout.splitlines()[0] != expected:
            raise SharedAssetError("shared executable version unsupported")
        if request["path"] is None:
            _load_decoder()
            print(json.dumps({"validated": True}), flush=True)
            return
        image = _decode(Path(request["path"]))
        print(json.dumps({"stage": "decoded"}), flush=True)
        folder = Path(request["workspace"])
        (folder / "models").mkdir()
        (folder / "models" / "eng.traineddata").write_bytes((assets.tessdata_directory / "eng.traineddata").read_bytes())
        result = _interpret(image, assets, folder)
        print(json.dumps(result), flush=True)
    except SharedAssetError as error:
        print(json.dumps({"shared_error": str(error)}), flush=True)
    except Exception as error:
        # Fixed messages disclose the failing stage without OCR text or paths.
        reason = "individual decode/OCR/resource failure: " + type(error).__name__
        if isinstance(error, ValueError) and str(error) in (
                "primary pixel limit exceeded", "crop pixel limit exceeded", "scaled crop pixel limit exceeded"):
            reason = str(error)
        result = {"error": reason}
        if request.get("diagnostics") is True:
            result["diagnostic_trace"] = _diagnostic_trace(error)
        print(json.dumps(result), flush=True)

if __name__ == "__main__":
    main()
