from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


class ImageError(RuntimeError):
    pass


@dataclass(frozen=True)
class CausticGeometry:
    curve: np.ndarray
    cusp: tuple[float, float]
    fold: tuple[float, float]

    def position(self, name: str) -> np.ndarray:
        if name not in ("cross", "cusp", "fold"):
            raise ImageError("Select Cross, Cusp, or Fold.")
        return np.array((0, 0) if name == "cross" else getattr(self, name), np.float64)

    def clearance(self, name: str) -> float:
        return cv2.pointPolygonTest(self.curve.astype(np.float32), tuple(self.position(name)), True)


def caustic_geometry(beta_x: np.ndarray, beta_y: np.ndarray, step: float) -> CausticGeometry:
    dx_x, dx_y = np.gradient(beta_x, step, axis=1), np.gradient(beta_x, step, axis=0)
    dy_x, dy_y = np.gradient(beta_y, step, axis=1), np.gradient(beta_y, step, axis=0)
    determinant = dx_x * dy_y - dx_y * dy_x
    contours, _ = cv2.findContours(
        (determinant < 0).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE,
    )
    if not contours:
        raise ImageError("No tangential caustic: reduce the lens core radius.")
    critical = max(contours, key=cv2.contourArea).reshape(-1, 2)
    height, width = beta_x.shape
    if np.any(critical <= 0) or np.any(critical[:, 0] >= width - 1) or np.any(critical[:, 1] >= height - 1):
        raise ImageError("The tangential critical curve is outside the preset sampling region.")
    # Select the outer image-plane critical curve, not the larger radial source-plane caustic.
    curve = np.column_stack((beta_x[critical[:, 1], critical[:, 0]], beta_y[critical[:, 1], critical[:, 0]]))
    a, b = np.max(curve[:, 0]), np.max(curve[:, 1])
    if min(a, b) < 0.01 or cv2.pointPolygonTest(curve.astype(np.float32), (0, 0), True) <= 0:
        raise ImageError("The tangential caustic is too small or degenerate for distinct presets.")
    following = np.roll(curve, -1, axis=0)
    difference = curve[:, 0] / a - curve[:, 1] / b
    next_difference = following[:, 0] / a - following[:, 1] / b
    candidates = np.flatnonzero(
        (curve[:, 0] > 0) & (curve[:, 1] > 0) & (difference * next_difference <= 0)
        & (difference != next_difference)
    )
    if not candidates.size:
        raise ImageError("Cannot identify a smooth fold segment on this caustic.")
    index = int(candidates[0])
    fraction = difference[index] / (difference[index] - next_difference[index])
    fold = 0.85 * (curve[index] + fraction * (following[index] - curve[index]))
    curve.setflags(write=False)
    result = CausticGeometry(curve, (float(a * 0.85), 0), (float(fold[0]), float(fold[1])))
    if result.clearance("cusp") <= 0 or result.clearance("fold") <= 0:
        raise ImageError("Cannot place the selected presets inside the tangential caustic.")
    return result


def foreground_bounds(alpha: np.ndarray) -> tuple[int, int, int, int]:
    visible = alpha > 1 / 255
    rows, columns = np.flatnonzero(np.any(visible, axis=1)), np.flatnonzero(np.any(visible, axis=0))
    if not rows.size or not columns.size:
        raise ImageError("No visible source remains. Adjust the greenscreen settings or bring the subject into view.")
    return int(rows[0]), int(rows[-1] + 1), int(columns[0]), int(columns[-1] + 1)


def place_source(
    color: np.ndarray, alpha: np.ndarray, einstein_radius: float,
    size_percent: float, position: tuple[float, float],
) -> tuple[np.ndarray, np.ndarray, float]:
    if (
        not np.isfinite((einstein_radius, size_percent, *position)).all()
        or einstein_radius <= 0 or not 1 <= size_percent <= 100
    ):
        raise ImageError("Source placement requires positive lens mass and a size from 1% to 100%.")
    height, width = alpha.shape
    if height != width or width < 4 or color.shape != (height, width, 3):
        raise ImageError("Source placement requires matching square color and alpha canvases.")
    top, bottom, left, right = foreground_bounds(alpha)
    color, alpha = color[top:bottom, left:right], alpha[top:bottom, left:right]
    pixels_per_unit = width / 2 - 1
    diameter = einstein_radius * size_percent / 100 * pixels_per_unit
    factor = diameter / max(color.shape[:2])
    resized_size = (max(1, round(color.shape[1] * factor)), max(1, round(color.shape[0] * factor)))
    interpolation = cv2.INTER_AREA if factor < 1 else cv2.INTER_LINEAR
    color = cv2.resize(color, resized_size, interpolation=interpolation)
    alpha = cv2.resize(alpha, resized_size, interpolation=interpolation)
    matrix = np.array(
        [[1, 0, (position[0] + 1) * pixels_per_unit - (resized_size[0] - 1) / 2],
         [0, 1, (position[1] + 1) * pixels_per_unit - (resized_size[1] - 1) / 2]],
        np.float32,
    )
    return (
        cv2.warpAffine(color, matrix, (width, height), flags=cv2.INTER_LINEAR),
        cv2.warpAffine(alpha, matrix, (width, height), flags=cv2.INTER_LINEAR),
        diameter,
    )


@dataclass(frozen=True)
class ChromaKeySettings:
    enabled: bool = False
    color: tuple[int, int, int] = (0, 255, 128)
    tolerance: float = 30
    softness: float = 12
    saturation: float = 0.2
    spill: float = 0.5

    def __post_init__(self):
        if len(self.color) != 3 or any(
            not isinstance(value, int) or not 0 <= value <= 255 for value in self.color
        ):
            raise ImageError("Key color must contain three RGB values from 0 to 255.")
        for value, maximum in (
            (self.tolerance, 180), (self.softness, 90),
            (self.saturation, 1), (self.spill, 1),
        ):
            if not np.isfinite(value) or not 0 <= value <= maximum:
                raise ImageError("Chroma-key settings are outside their supported range.")


def chroma_key(frame: np.ndarray, settings: ChromaKeySettings) -> tuple[np.ndarray, np.ndarray]:
    if frame.dtype != np.uint8 or frame.ndim != 3 or frame.shape[2] != 3 or frame.size == 0:
        raise ImageError("Chroma keying requires a nonempty uint8 BGR image.")
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB).astype(np.float32)
    alpha = np.ones(frame.shape[:2], np.float32)
    if not settings.enabled:
        return rgb, alpha
    key = cv2.cvtColor(np.array([[settings.color]], np.uint8), cv2.COLOR_RGB2HSV)[0, 0]
    if key[1] < 16:
        raise ImageError("Choose a saturated key color, not black, white, or gray.")
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    distance = np.abs(hsv[..., 0].astype(np.float32) * 2 - float(key[0]) * 2)
    distance = np.minimum(distance, 360 - distance)
    if settings.softness:
        alpha = np.clip((distance - settings.tolerance) / settings.softness, 0, 1)
        alpha = alpha * alpha * (3 - 2 * alpha)
    else:
        alpha = (distance > settings.tolerance).astype(np.float32)
    chromatic = (hsv[..., 1] >= settings.saturation * 255) & (hsv[..., 1] > 0)
    alpha[~chromatic] = 1
    if settings.spill:
        channel = int(np.argmax(settings.color))
        others = [index for index in range(3) if index != channel]
        excess = np.maximum(
            rgb[..., channel] - np.maximum(rgb[..., others[0]], rgb[..., others[1]]), 0
        )
        proximity = np.clip(
            1 - distance / (settings.tolerance + settings.softness + 30), 0, 1
        )
        rgb[..., channel] -= excess * proximity * chromatic * settings.spill
    return rgb * alpha[..., None], alpha


def fit_layer(
    color: np.ndarray, alpha: np.ndarray, width: int, height: int, mode: str,
    *, mirror: bool = False, zoom: float = 100,
) -> tuple[np.ndarray, np.ndarray]:
    if width <= 0 or height <= 0 or mode not in ("fit", "fill", "stretch"):
        raise ImageError("Input framing requires positive dimensions and fit/fill/stretch mode.")
    if alpha.ndim != 2 or alpha.size == 0 or color.shape != (*alpha.shape, 3):
        raise ImageError("Input color and alpha dimensions must agree.")
    if not np.isfinite(zoom) or not 100 <= zoom <= 400:
        raise ImageError("Input zoom must be between 100% and 400%.")
    if zoom != 100:
        source_h, source_w = alpha.shape
        crop_w, crop_h = max(1, round(source_w * 100 / zoom)), max(1, round(source_h * 100 / zoom))
        left, top = (source_w - crop_w) // 2, (source_h - crop_h) // 2
        color = color[top:top + crop_h, left:left + crop_w]
        alpha = alpha[top:top + crop_h, left:left + crop_w]
    source_h, source_w = alpha.shape
    if mode == "stretch":
        resized_w, resized_h = width, height
    else:
        ratios = (width / source_w, height / source_h)
        factor = min(ratios) if mode == "fit" else max(ratios)
        resized_w, resized_h = max(1, round(source_w * factor)), max(1, round(source_h * factor))
    interpolation = (
        cv2.INTER_AREA if resized_w <= source_w and resized_h <= source_h else cv2.INTER_LINEAR
    )
    color = cv2.resize(color, (resized_w, resized_h), interpolation=interpolation)
    alpha = cv2.resize(alpha, (resized_w, resized_h), interpolation=interpolation)
    if mode == "fit":
        result = np.zeros((height, width, 3), color.dtype)
        coverage = np.zeros((height, width), np.float32)
        left, top = (width - resized_w) // 2, (height - resized_h) // 2
        result[top:top + resized_h, left:left + resized_w] = color
        coverage[top:top + resized_h, left:left + resized_w] = alpha
        color, alpha = result, coverage
    elif mode == "fill":
        left, top = (resized_w - width) // 2, (resized_h - height) // 2
        color = color[top:top + height, left:left + width]
        alpha = alpha[top:top + height, left:left + width]
    if mirror:
        color, alpha = cv2.flip(color, 1), cv2.flip(alpha, 1)
    return np.ascontiguousarray(color), np.ascontiguousarray(alpha)


def remap_layer(
    color: np.ndarray, alpha: np.ndarray, map_x: np.ndarray, map_y: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    color = cv2.remap(
        color, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT,
    )
    alpha = cv2.remap(
        alpha, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT,
    )
    alpha = np.clip(alpha, 0, 1)
    return np.clip(color, 0, alpha[..., None] * 255), alpha


def default_background_path(filename: str | None = None) -> Path:
    if filename is None:
        from .defaults import load_gui_defaults

        filename = load_gui_defaults().background.image
    return Path(__file__).resolve().parent.parent / "data" / filename


def prepare_input(
    frame: np.ndarray, settings: ChromaKeySettings, width: int, height: int,
    mode: str, *, mirror: bool = False, zoom: float = 100,
) -> tuple[np.ndarray, np.ndarray]:
    return fit_layer(*chroma_key(frame, settings), width, height, mode, mirror=mirror, zoom=zoom)


def example_source_path() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "example_gs_pic.jpeg"


def read_image_bgr(path: str | Path) -> np.ndarray:
    path = Path(path)
    try:
        encoded = np.frombuffer(path.read_bytes(), dtype=np.uint8)
        image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    except (OSError, cv2.error) as error:
        raise ImageError(f"Cannot load image {path.name}: {error}") from error
    if image is None:
        raise ImageError(f"Cannot decode image {path.name}. Select a valid PNG or JPEG.")
    return image


def write_image_bgr(path: str | Path, frame: np.ndarray):
    path = Path(path)
    extension = path.suffix.lower()
    if extension not in (".png", ".jpg", ".jpeg"):
        raise ImageError("Save the input image as PNG (lossless) or JPEG.")
    try:
        ok, encoded = cv2.imencode(extension, frame)
        if not ok:
            raise ImageError(f"Cannot encode input image as {extension}.")
        path.write_bytes(encoded.tobytes())
    except (OSError, cv2.error) as error:
        raise ImageError(f"Cannot save input image to {path}: {error}") from error


def _validate_fit(width: int, height: int, mode: str):
    if width <= 0 or height <= 0 or mode not in ("fit", "fill"):
        raise ImageError("Background fitting requires a positive canvas size and fit/fill mode.")


def fit_background(image: np.ndarray, width: int, height: int, mode: str) -> np.ndarray:
    _validate_fit(width, height, mode)
    fitted, _ = fit_layer(image, np.ones(image.shape[:2], np.float32), width, height, mode)
    return fitted


class SkyBackground:
    def __init__(self):
        self.path: Path | None = None
        self.image: np.ndarray | None = None
        self._cache_key: tuple[int, int, str] | None = None
        self._cache: np.ndarray | None = None

    def load(self, path: str | Path):
        path = Path(path)
        image_bgr = read_image_bgr(path)
        image = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        image.setflags(write=False)
        self.path = path
        self.image = image
        self._cache_key = None
        self._cache = None

    def clear(self):
        self.path = None
        self.image = None
        self._cache_key = None
        self._cache = None

    def fitted(self, width: int, height: int, mode: str) -> np.ndarray:
        _validate_fit(width, height, mode)
        key = (width, height, mode)
        if key != self._cache_key:
            if self.image is None:
                image = np.zeros((height, width, 3), np.uint8)
            else:
                image = fit_background(self.image, width, height, mode)
            image.setflags(write=False)
            self._cache = image
            self._cache_key = key
        assert self._cache is not None
        return self._cache


def placement_matrix(width: int, height: int, scale: float, x: float, y: float) -> np.ndarray:
    if not np.isfinite((scale, x, y)).all() or scale <= 0:
        raise ValueError("Source placement requires a positive scale and finite offsets.")
    return np.array(
        [[scale, 0, width * ((1 - scale) / 2 + x)],
         [0, scale, height * ((1 - scale) / 2 + y)]],
        dtype=np.float32,
    )


def place_layer(
    rgb: np.ndarray, alpha: np.ndarray, background: np.ndarray,
    *, scale: float = 1, x: float = 0, y: float = 0,
) -> np.ndarray:
    # Color is premultiplied before interpolation so transparent edges stay clean.
    height, width = background.shape[:2]
    matrix = placement_matrix(width, height, scale, x, y)
    alpha = np.clip(alpha.astype(np.float32, copy=False), 0, 1)
    color = np.clip(rgb.astype(np.float32, copy=False), 0, alpha[..., None] * 255)
    if scale != 1 or x != 0 or y != 0:
        color = cv2.warpAffine(
            color, matrix, (width, height), flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
        )
        alpha = cv2.warpAffine(
            alpha, matrix, (width, height), flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
        )
    output = color + background.astype(np.float32) * (1 - alpha[..., None])
    return np.ascontiguousarray(np.clip(np.rint(output), 0, 255).astype(np.uint8))


def unplace_point(
    x: float, y: float, width: int, height: int,
    scale: float, offset_x: float, offset_y: float,
) -> tuple[float, float] | None:
    matrix = placement_matrix(width, height, scale, offset_x, offset_y)
    source_x = (x - float(matrix[0, 2])) / scale
    source_y = (y - float(matrix[1, 2])) / scale
    if 0 <= source_x < width and 0 <= source_y < height:
        return source_x, source_y
    return None
