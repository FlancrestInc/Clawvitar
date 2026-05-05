import json
from pathlib import Path

from PIL import Image


class AssetManifestError(ValueError):
    pass


def load_manifest(path):
    return json.loads(Path(path).read_text())


def _required(mapping, key, context):
    if key not in mapping:
        raise AssetManifestError(f"Missing {key} in {context}")
    return mapping[key]


def _canvas_size(manifest):
    canvas = _required(manifest, "canvas", "manifest")
    width = int(_required(canvas, "width", "canvas"))
    height = int(_required(canvas, "height", "canvas"))
    if width <= 0 or height <= 0:
        raise AssetManifestError("Canvas width and height must be positive")
    return width, height


def _position(spec):
    position = spec.get("position", {})
    return int(position.get("x", 0)), int(position.get("y", 0))


def _scale(spec):
    scale = float(spec.get("scale", 1))
    if scale <= 0:
        raise AssetManifestError("Frame scale must be positive")
    return scale


def _validate_rect(rect, sheet, context):
    x = int(_required(rect, "x", context))
    y = int(_required(rect, "y", context))
    w = int(_required(rect, "w", context))
    h = int(_required(rect, "h", context))

    if w <= 0 or h <= 0:
        raise AssetManifestError(f"{context} width and height must be positive")

    if x < 0 or y < 0 or x + w > sheet.width or y + h > sheet.height:
        raise AssetManifestError(f"{context} is outside the spritesheet")

    return x, y, w, h


def _grid_rects(spec, sheet):
    frame_width = int(_required(spec, "frame_width", "grid state"))
    frame_height = int(_required(spec, "frame_height", "grid state"))
    columns = int(_required(spec, "columns", "grid state"))
    frame_count = int(_required(spec, "frame_count", "grid state"))

    if frame_width <= 0 or frame_height <= 0 or columns <= 0 or frame_count <= 0:
        raise AssetManifestError("Grid dimensions must be positive")

    rects = []
    for index in range(frame_count):
        column = index % columns
        row = index // columns
        rect = {
            "x": column * frame_width,
            "y": row * frame_height,
            "w": frame_width,
            "h": frame_height,
        }
        rects.append(_validate_rect(rect, sheet, f"grid frame {index}"))
    return rects


def _explicit_rects(spec, sheet):
    frames = _required(spec, "frames", "frames state")
    if not frames:
        raise AssetManifestError("frames state must include at least one frame")
    return [_validate_rect(frame, sheet, f"frame {index}") for index, frame in enumerate(frames)]


def _resize_if_needed(frame, scale):
    if scale == 1:
        return frame

    width = max(1, int(round(frame.width * scale)))
    height = max(1, int(round(frame.height * scale)))
    return frame.resize((width, height), Image.Resampling.NEAREST)


def process_manifest(manifest, source_dir, output_dir):
    source_dir = Path(source_dir)
    output_dir = Path(output_dir)
    canvas_width, canvas_height = _canvas_size(manifest)

    background_path = source_dir / _required(manifest, "background", "manifest")
    if not background_path.exists():
        raise AssetManifestError(f"Missing background: {background_path}")

    background = Image.open(background_path).convert("RGBA").resize((canvas_width, canvas_height))
    states = _required(manifest, "states", "manifest")

    for state, spec in states.items():
        sheet_path = source_dir / _required(spec, "sheet", f"state {state}")
        if not sheet_path.exists():
            raise AssetManifestError(f"Missing spritesheet for {state}: {sheet_path}")

        sheet = Image.open(sheet_path).convert("RGBA")
        mode = spec.get("mode", "grid")
        if mode == "grid":
            rects = _grid_rects(spec, sheet)
        elif mode == "frames":
            rects = _explicit_rects(spec, sheet)
        else:
            raise AssetManifestError(f"Unsupported frame mode for {state}: {mode}")

        state_dir = output_dir / state
        state_dir.mkdir(parents=True, exist_ok=True)
        x, y = _position(spec)
        scale = _scale(spec)

        for index, (left, top, width, height) in enumerate(rects):
            frame = sheet.crop((left, top, left + width, top + height))
            frame = _resize_if_needed(frame, scale)
            canvas = background.copy()
            canvas.alpha_composite(frame, (x, y))
            canvas.convert("RGB").save(state_dir / f"{index:02d}.png")
