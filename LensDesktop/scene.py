from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from .lensing import apply_lens_light, create_SIE_map, draw_forward_markers, forward_layer, lensing_curves, source_configuration_geometry
from .processing import ChromaKeySettings, ImageError, fit_background, fit_layer, foreground_bounds, place_layer, place_source, prepare_input


@dataclass(frozen=True)
class LensSettings:
    radius: float = 0.5
    axis_ratio: float = 0.65
    core: float = 1 / 59
    angle: float = 0
    heart: bool = False

    def __post_init__(self):
        if (
            not np.isfinite((self.radius, self.axis_ratio, self.core, self.angle)).all()
            or not 0 <= self.radius <= 1 or not 0 < self.axis_ratio < 1 or not 0 <= self.core <= 1
        ):
            raise ImageError("Invalid lens settings for the print snapshot.")


@dataclass(frozen=True)
class InputSettings:
    key: ChromaKeySettings = ChromaKeySettings()
    framing: str = "fit"
    mirror: bool = False
    zoom: float = 100
    configuration: str | None = None
    size_percent: float = 10

    def __post_init__(self):
        if (
            self.framing not in ("fit", "fill", "stretch")
            or self.configuration not in (None, "cross", "cusp", "fold")
            or not np.isfinite((self.zoom, self.size_percent)).all()
            or not 100 <= self.zoom <= 400 or not 1 <= self.size_percent <= 100
        ):
            raise ImageError("Invalid input settings for the print snapshot.")


@dataclass(frozen=True)
class DisplaySettings:
    scale: float = 0.25
    offset_x: float = 0
    offset_y: float = 0
    sky_mode: str = "fill"
    lens_light: bool = False
    curves: bool = False
    image_markers: tuple[tuple[float, float], ...] = ()
    source_markers: tuple[tuple[float, float], ...] = ()
    marker_radius: float = 0.05

    def __post_init__(self):
        if (
            not np.isfinite((self.scale, self.offset_x, self.offset_y, self.marker_radius)).all()
            or not 0.1 <= self.scale <= 2 or not -1 <= self.offset_x <= 1 or not -1 <= self.offset_y <= 1
            or self.marker_radius <= 0 or self.sky_mode not in ("fit", "fill")
        ):
            raise ImageError("Invalid display settings for the print snapshot.")


@dataclass(frozen=True)
class SkyAttribution:
    title: str = "Ohne Himmelsbild"
    credit: str = "Schwarzer Hintergrund."
    source_url: str = ""
    license: str = ""


def sky_attribution(path: Path | None) -> SkyAttribution:
    if path is None:
        return SkyAttribution()
    data = Path(__file__).resolve().parent.parent / "data"
    if path.resolve() == (data / "euclid_abell_2764_example.jpeg").resolve():
        return SkyAttribution(
            "Euclid: Abell 2764",
            "ESA/Euclid/Euclid Consortium/NASA; Bildverarbeitung: J.-C. Cuillandre (CEA Paris-Saclay), G. Anselmi",
            "https://www.esa.int/ESA_Multimedia/Images/2024/05/Euclid_s_new_view_of_galaxy_cluster_Abell_2764",
            "CC BY-SA 3.0 IGO",
        )
    if path.resolve() == (data / "euclid_patch_example.jpg").resolve():
        return SkyAttribution(
            "Euclid: Himmelsmosaik",
            "ESA/Euclid/Euclid Consortium/NASA, CEA Paris-Saclay; J.-C. Cuillandre, E. Bertin, G. Anselmi; ESA/Gaia/DPAC; ESA/Planck Collaboration",
            "https://www.euclid-ec.org/euclids-first-large-piece-of-the-sky/",
            "CC BY-SA 3.0 IGO",
        )
    return SkyAttribution(
        path.name, f"Eigener Hintergrund: {path.name}. Bildrechte und Lizenz vor Weitergabe prüfen.",
    )


def _detached_image(image: np.ndarray) -> np.ndarray:
    if image.dtype != np.uint8 or image.ndim != 3 or image.shape[2] != 3 or not image.size:
        raise ImageError("Print snapshots require nonempty uint8 three-channel images.")
    detached = np.ascontiguousarray(image).copy()
    detached.setflags(write=False)
    return detached


@dataclass(frozen=True)
class SceneSnapshot:
    raw_bgr: np.ndarray
    sky_rgb: np.ndarray | None
    lens: LensSettings = LensSettings()
    input: InputSettings = InputSettings()
    display: DisplaySettings = DisplaySettings()
    source_description: str = "Statische Aufnahme"
    attribution: SkyAttribution = SkyAttribution()

    def __post_init__(self):
        object.__setattr__(self, "raw_bgr", _detached_image(self.raw_bgr))
        if self.sky_rgb is not None:
            object.__setattr__(self, "sky_rgb", _detached_image(self.sky_rgb))


@dataclass(frozen=True)
class ImageLayer:
    rgb: np.ndarray
    alpha: np.ndarray


def _layer(rgb: np.ndarray, alpha: np.ndarray) -> ImageLayer:
    alpha = np.clip(alpha.astype(np.float32, copy=False), 0, 1)
    rgb = np.clip(rgb.astype(np.float32, copy=False), 0, alpha[..., None] * 255)
    rgb.setflags(write=False)
    alpha.setflags(write=False)
    return ImageLayer(rgb, alpha)


@dataclass(frozen=True)
class RenderedScene:
    raw_rgb: np.ndarray
    cleaned: ImageLayer
    source: ImageLayer
    lensed: ImageLayer
    montage: np.ndarray
    critical_curves: tuple[np.ndarray, ...]
    caustic_curves: tuple[np.ndarray, ...]
    source_center: tuple[float, float]
    warnings: tuple[str, ...]
    snapshot: SceneSnapshot


def render_snapshot(
    snapshot: SceneSnapshot,
    *,
    side: int = 734,
    montage_size: tuple[int, int] = (2197, 733),
    include_montage_critical_curve: bool = True,
) -> RenderedScene:
    if not isinstance(side, int) or not 32 <= side <= 2048 or side % 2:
        raise ImageError("Print field resolution must be even and between 32 and 2048 pixels.")
    width, height = montage_size
    if any(not isinstance(value, int) or not 32 <= value <= 4096 for value in montage_size):
        raise ImageError("Invalid print montage dimensions.")
    lens, settings, display = snapshot.lens, snapshot.input, snapshot.display
    raw = cv2.cvtColor(snapshot.raw_bgr, cv2.COLOR_BGR2RGB)
    raw.setflags(write=False)
    rgb, alpha = prepare_input(
        snapshot.raw_bgr, settings.key, side * 2, side * 2, settings.framing,
        mirror=settings.mirror, zoom=settings.zoom,
    )
    top, bottom, left, right = foreground_bounds(alpha)
    cleaned = _layer(*fit_layer(rgb, alpha, side, side, "stretch"))
    warnings = []
    center = (
        ((left + right - 1) / 2) / (side - 1) - 1,
        ((top + bottom - 1) / 2) / (side - 1) - 1,
    )
    if settings.configuration is not None:
        if lens.radius <= 0:
            raise ImageError("Source configurations require positive Einstein radius.")
        geometry = source_configuration_geometry(lens.axis_ratio, lens.core, lens.angle, lens.heart)
        position = geometry.position(settings.configuration) * lens.radius
        center = (float(position[0]), float(position[1]))
        rgb, alpha, diameter = place_source(rgb, alpha, lens.radius, settings.size_percent, center)
        if settings.size_percent / 200 >= geometry.clearance(settings.configuration):
            warnings.append("Die ausgedehnte Quelle kann die Kaustik überschreiten; Einzelbilder können zu Bögen verschmelzen.")
        if diameter < 2:
            warnings.append("Die Quelle ist kleiner als zwei Eingangsbildpunkte; Details sind nicht zuverlässig aufgelöst.")
    opaque = not settings.key.enabled and settings.configuration is None
    if opaque:
        alpha = np.ones_like(alpha)
    map_x, map_y, dx, dy, _, _, kappa = create_SIE_map(
        side, side, lens.radius / np.sqrt(lens.axis_ratio), lens.axis_ratio,
        lens.core * lens.radius, lens.angle, lens.heart,
    )
    if display.image_markers or display.source_markers:
        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        alpha = alpha.copy()
        draw_forward_markers(
            bgr, alpha, map_x, map_y,
            tuple((x * side, y * side) for x, y in display.image_markers),
            tuple((x * side, y * side) for x, y in display.source_markers),
            max(1, round(display.marker_radius * side)),
        )
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    source = _layer(*fit_layer(rgb, alpha, side, side, "stretch"))
    transformed, coverage = forward_layer(
        rgb, alpha, map_x, map_y, opaque=opaque, sky_present=snapshot.sky_rgb is not None,
        lens_radius=lens.radius, kappa=kappa, lens_light=display.lens_light,
    )
    lensed = _layer(transformed, coverage)
    critical, caustics = lensing_curves(map_x, map_y, dx, dy)
    for contour in (*critical, *caustics):
        contour.setflags(write=False)
    color, coverage = lensed.rgb.copy(), lensed.alpha.copy()
    if not display.lens_light:
        color, coverage = apply_lens_light(lens.radius, kappa, color, coverage)
    if display.curves and include_montage_critical_curve:
        cv2.drawContours(color, critical, -1, (255, 255, 255), 5)
        cv2.drawContours(color, critical, -1, (0, 0, 0), 2)
        cv2.drawContours(coverage, critical, -1, 1.0, 5)
    short_side = min(width, height)
    color, coverage = fit_layer(color, coverage, short_side, short_side, "stretch")
    top, left = (height - short_side) // 2, (width - short_side) // 2
    color = np.pad(color, ((top, height - short_side - top), (left, width - short_side - left), (0, 0)))
    coverage = np.pad(coverage, ((top, height - short_side - top), (left, width - short_side - left)))
    background = (
        np.zeros((height, width, 3), np.uint8) if snapshot.sky_rgb is None
        else fit_background(snapshot.sky_rgb, width, height, display.sky_mode)
    )
    montage = place_layer(
        color, coverage, background, scale=display.scale, x=display.offset_x, y=display.offset_y,
    )
    montage.setflags(write=False)
    return RenderedScene(
        raw, cleaned, source, lensed, montage, tuple(critical), tuple(caustics), center, tuple(warnings), snapshot,
    )
