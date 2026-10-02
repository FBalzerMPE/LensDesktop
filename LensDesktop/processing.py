from pathlib import Path

import cv2
import numpy as np


class ImageError(RuntimeError):
    pass


def default_background_path() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "euclid_patch_example.jpg"


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
    source_h, source_w = image.shape[:2]
    ratios = (width / source_w, height / source_h)
    factor = min(ratios) if mode == "fit" else max(ratios)
    resized_w = max(1, round(source_w * factor))
    resized_h = max(1, round(source_h * factor))
    resized = cv2.resize(
        image, (resized_w, resized_h),
        interpolation=cv2.INTER_AREA if factor < 1 else cv2.INTER_LINEAR,
    )
    if mode == "fill":
        left = (resized_w - width) // 2
        top = (resized_h - height) // 2
        return np.ascontiguousarray(resized[top:top + height, left:left + width])
    result = np.zeros((height, width, 3), np.uint8)
    left = (width - resized_w) // 2
    top = (height - resized_h) // 2
    result[top:top + resized_h, left:left + resized_w] = resized
    return result


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
    alpha = np.clip(alpha.astype(np.float32), 0, 1)
    color = np.clip(rgb.astype(np.float32), 0, alpha[..., None] * 255)
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
