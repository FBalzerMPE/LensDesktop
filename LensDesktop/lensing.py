import cv2
import numpy as np
from scipy.interpolate import RegularGridInterpolator as interp

from .processing import CausticGeometry, ImageError, caustic_geometry, remap_layer


def heart_shape(x, y):
    z = 0.5 * x**2 + (-1.2 * y + 0.35 - np.sqrt(abs(x * 0.75))) ** 2
    return 1 / (1 + np.exp(5 * (z - 0.3)))


def SIE_defl(xx, yy, t, s, heart, q, b):
    ct, st = np.cos(t), np.sin(t)
    xv, yv = ct * xx - st * yy, st * xx + ct * yy
    r = np.sqrt(q * q * (xv * xv + s * s) + yv * yv)
    if b == 0:
        return np.zeros_like(xx), np.zeros_like(yy), r
    fac = heart_shape(xv, yv) if heart else 1.0
    A = b * q / np.sqrt(1 - q * q)
    deflx = A * np.arctan(np.sqrt(1 - q * q) * xv / (r + s)) * fac
    defly = A * np.arctanh(np.sqrt(1 - q * q) * yv / (r + q * q * s)) * fac
    return ct * deflx + st * defly, -st * deflx + ct * defly, r


def source_configuration_geometry(q, core, angle, heart=False):
    if not np.isfinite((q, core, angle)).all() or not 0 < q < 1 or not 0 <= core <= 1:
        raise ImageError("Source configurations require finite, valid lens parameters.")
    if heart:
        raise ImageError("Cross/Cusp/Fold presets require the standard lens, not heart mode.")
    if q >= 0.97:
        raise ImageError("The lens is nearly circular. Lower the axis ratio below 0.97 for distinct presets.")
    axis = np.linspace(-2.5, 2.5, 768)
    xx, yy = np.meshgrid(axis, axis)
    alpha_x, alpha_y, _ = SIE_defl(xx, yy, 0, core, False, q, 1 / np.sqrt(q))
    geometry = caustic_geometry(xx - alpha_x, yy - alpha_y, axis[1] - axis[0])
    rotation = np.array([[np.cos(angle), np.sin(angle)], [-np.sin(angle), np.cos(angle)]])
    curve = geometry.curve @ rotation.T
    curve.setflags(write=False)
    cusp, fold = rotation @ geometry.cusp, rotation @ geometry.fold
    return CausticGeometry(curve, (float(cusp[0]), float(cusp[1])), (float(fold[0]), float(fold[1])))


def create_SIE_map(width, height, b=0.75, q=0.79, s=0.0001, t=0.0, heart=False):
    Lx = 2 * width / max(width, height)
    Ly = 2 * height / max(width, height)
    xx, yy = np.meshgrid(
        np.linspace(-1, 1, width) * Lx / 2, np.linspace(-1, 1, height) * Ly / 2,
    )
    deflxv, deflyv, r = SIE_defl(xx, yy, t, s, heart, q, b)
    map_x = ((xx - deflxv + Lx / 2) * (width - 1)).astype(np.float32)
    map_y = ((yy - deflyv + Ly / 2) * (height - 1)).astype(np.float32)
    kappa = 0.5 * b / (1e-30 + r * r / q / q)
    return map_x, map_y, deflxv, deflyv, xx.astype(np.float32), yy.astype(np.float32), kappa


def lensing_curves(map_x, map_y, deflx, defly):
    height, width = map_x.shape
    Lx, Ly = 2 * width / max(width, height), 2 * height / max(width, height)
    dx, dy = 2.0 / (width - 1), 2.0 / (height - 1)
    determinant = (
        (np.gradient(map_x, axis=1) / dx) * (np.gradient(map_y, axis=0) / dy)
        - (np.gradient(map_x, axis=0) / dy) * (np.gradient(map_y, axis=1) / dx)
    )
    contours, _ = cv2.findContours(
        (determinant < 0).astype(np.uint8), cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE,
    )
    caustics = []
    for contour in contours:
        if len(contour) < 2:
            continue
        mapped = contour.astype(np.float32, copy=True)
        for point in mapped[:, 0]:
            x, y = point
            ix, iy = np.clip(int(round(x)), 0, width - 1), np.clip(int(round(y)), 0, height - 1)
            point[0] = (-Lx / 2 + Lx * x / (width - 1) - deflx[iy, ix] + Lx / 2) / Lx * (width - 1)
            point[1] = (-Ly / 2 + Ly * y / (height - 1) - defly[iy, ix] + Ly / 2) / Ly * (height - 1)
        caustics.append(mapped.astype(np.int32, copy=False))
    return contours, caustics


def draw_lens_light(b, kappa, image, base_w, base_h):
    if b > 0:
        alpha = np.clip(np.log10(1 + kappa), 0, 1)
        for channel, value in enumerate((255, 200, 130)):
            image[:, :, channel] = image[:, :, channel] * (1 - alpha) + value * alpha
    return image


def forward_layer(
    rgb, alpha, map_x, map_y, *, opaque, sky_present, lens_radius, kappa, lens_light,
):
    if opaque:
        transformed = cv2.remap(
            np.clip(np.rint(rgb), 0, 255).astype(np.uint8), map_x, map_y,
            cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT,
        )
        coverage = (
            np.clip(cv2.remap(alpha, map_x, map_y, cv2.INTER_CUBIC), 0, 1)
            if sky_present else np.ones(map_x.shape, np.float32)
        )
    else:
        transformed, coverage = remap_layer(rgb, alpha, map_x, map_y)
    if lens_light and lens_radius > 0:
        height, width = map_x.shape
        transformed = draw_lens_light(lens_radius, kappa, transformed, width, height)
        light = np.clip(np.log10(1 + kappa), 0, 1)
        coverage = coverage * (1 - light) + light
    return transformed, coverage


def draw_forward_markers(image_bgr, alpha, map_x, map_y, image_points, source_points, radius):
    if not image_points and not source_points:
        return
    height, width = map_x.shape
    if image_points:
        point = np.array([image_points[0]])
        axes = (np.arange(width), np.arange(height))
        x_source = int(interp(axes, map_x.T, bounds_error=False, fill_value=None)(point)[0])
        y_source = int(interp(axes, map_y.T, bounds_error=False, fill_value=None)(point)[0])
    if source_points:
        x_source, y_source = (int(2 * value) for value in source_points[0])
    for channel in range(3):
        color = tuple(255 if index == channel else 0 for index in range(3))
        cv2.ellipse(
            image_bgr, (x_source, y_source), (radius, radius), 0,
            channel * 120, (channel + 1) * 120, color, -1,
        )
    if alpha is not None:
        cv2.ellipse(alpha, (x_source, y_source), (radius, radius), 0, 0, 360, 1.0, -1)
