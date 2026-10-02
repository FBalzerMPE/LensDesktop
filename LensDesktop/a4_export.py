from pathlib import Path

import numpy as np

from .processing import ImageError, place_layer
from .qt_compat import QtCore, QtGui
from .scene import ImageLayer, RenderedScene, SceneSnapshot, render_snapshot

PAGE_SIZE_MM = (210, 297)
PRINT_DPI = 300
PRINT_SIDE = 734
MONTAGE_SIZE = (2197, 733)


def _checkerboard(layer: ImageLayer) -> np.ndarray:
    height, width = layer.alpha.shape
    yy, xx = np.indices((height, width))
    tiles = (xx // max(8, width // 24) + yy // max(8, height // 24)) % 2
    background = np.repeat(np.where(tiles, 232, 248)[..., None], 3, axis=2).astype(
        np.uint8
    )
    return place_layer(layer.rgb, layer.alpha, background)


def paint_a4_page(
    painter: QtGui.QPainter, snapshot: SceneSnapshot, scene: RenderedScene, dpi: int
):
    unit = dpi / 25.4

    def rect(x, y, width, height):
        return QtCore.QRectF(x * unit, y * unit, width * unit, height * unit)

    def text(box, content, size=8, *, bold=False, color="#243336", centered=False):
        flags = QtCore.Qt.TextWordWrap | QtCore.Qt.AlignVCenter
        flags |= QtCore.Qt.AlignHCenter if centered else QtCore.Qt.AlignLeft
        font = QtGui.QFont("Segoe UI")
        font.setBold(bold)
        while True:
            font.setPointSizeF(size)
            painter.setFont(font)
            if painter.boundingRect(box, flags, content).height() <= box.height() + 1:
                break
            size -= 0.5
            if size < 6:
                raise ImageError("The explanatory text does not fit the A4 page.")
        painter.setPen(QtGui.QColor(color))
        painter.drawText(box, flags, content)

    def image(rgb, box):
        rgb = np.ascontiguousarray(rgb)
        height, width = rgb.shape[:2]
        ratio = min(box.width() / width, box.height() / height)
        target = QtCore.QRectF(
            box.center().x() - width * ratio / 2,
            box.center().y() - height * ratio / 2,
            width * ratio,
            height * ratio,
        )
        qimage = QtGui.QImage(
            rgb.data,
            width,
            height,
            width * 3,
            QtGui.QImage.Format_RGB888,
        ).copy()
        painter.drawImage(target, qimage)
        painter.setPen(QtGui.QPen(QtGui.QColor("#a5b4b5"), 0.15 * unit))
        painter.setBrush(QtCore.Qt.NoBrush)
        painter.drawRect(target)
        return target

    def logo(filename, box):
        path = Path(__file__).resolve().parent.parent / "data" / filename
        logo_image = QtGui.QImage(str(path))
        if logo_image.isNull():
            raise ImageError(f"Cannot load A4 header logo: {path}")
        ratio = min(
            box.width() / logo_image.width(), box.height() / logo_image.height()
        )
        target = QtCore.QRectF(
            box.center().x() - logo_image.width() * ratio / 2,
            box.center().y() - logo_image.height() * ratio / 2,
            logo_image.width() * ratio,
            logo_image.height() * ratio,
        )
        painter.drawImage(target, logo_image)

    def curves(target, contours, color, dashed=False):
        painter.save()
        painter.setClipRect(target)
        pen = QtGui.QPen(QtGui.QColor(color), 0.3 * unit)
        if dashed:
            pen.setStyle(QtCore.Qt.DashLine)
        painter.setPen(pen)
        side = scene.source.alpha.shape[0]
        for contour in contours:
            points = [
                QtCore.QPointF(
                    target.left() + x / (side - 1) * target.width(),
                    target.top() + y / (side - 1) * target.height(),
                )
                for x, y in contour.reshape(-1, 2)
            ]
            if len(points) >= 2:
                painter.drawPolyline(QtGui.QPolygonF(points + [points[0]]))
        painter.restore()

    painter.setRenderHint(QtGui.QPainter.Antialiasing)
    painter.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)
    painter.fillRect(rect(0, 0, *PAGE_SIZE_MM), QtCore.Qt.white)
    logo("mpe_logo.png", rect(13, 8, 15, 15))
    text(
        rect(31, 12, 148, 8),
        "Der Gravitationslinseneffekt – Die Schwerkraft als Lupe",
        15,
        bold=True,
        centered=True,
    )
    logo("mpe_minerva.png", rect(182, 8, 15, 15))
    text(
        rect(30, 21, 150, 9),
        "Wie sähe dein Licht aus, wenn es auf seinem Weg zu uns durch die Schwerkraft "
        "einer Galaxie abgelenkt würde?\nEine visuelle Demonstration.",
        9,
        centered=True,
    )
    lens, settings, display = snapshot.lens, snapshot.input, snapshot.display
    configuration = (
        settings.configuration.title() if settings.configuration else "Originalrahmung"
    )
    metadata = (
        f"Normierte Modellwerte: {'SIE (Herzmodifikation)' if lens.heart else 'SIE+Core'} | Einsteinradius b = {lens.radius:.3f}, "
        f"Achsenverhältnis q = {lens.axis_ratio:.2f}, Kernradius/b = {lens.core:.3f}, "
        f"Winkel = {np.degrees(lens.angle):.1f}° | Quelle: {configuration}"
        + (
            f", Ausdehnung {settings.size_percent:g}% von b"
            if settings.configuration
            else ""
        )
        + f"\nMontage: Größe {display.scale * 100:g}%, Versatz ({display.offset_x * 100:g}%, "
        f"{display.offset_y * 100:g}%), Himmel {display.sky_mode}; "
        f"GUI-Linsenlicht {'an' if display.lens_light else 'aus'}, Montage-Linsenlicht an, "
        f"Kurven {'an' if display.curves else 'aus'}."
    )
    text(rect(12, 35, 88, 6), "1. Deine Originalaufnahme", 10, bold=True, centered=True)
    text(
        rect(110, 35, 88, 6),
        "2. Freigestelltes Eingangsbild",
        10,
        bold=True,
        centered=True,
    )
    image(scene.raw_rgb, rect(12, 42, 88, 58))
    image(_checkerboard(scene.cleaned), rect(110, 42, 88, 58))
    text(
        rect(12, 101, 88, 9),
        f"Originalbild ({scene.raw_rgb.shape[1]} × {scene.raw_rgb.shape[0]} pixel).",
        7,
    )
    key = settings.key
    color = "#{:02x}{:02x}{:02x}".format(*key.color)
    text(
        rect(110, 101, 88, 9),
        f"Farbe {color}, Zoom {settings.zoom:g}%, Spiegelung {'an' if settings.mirror else 'aus'}, "
        f"Rahmung {settings.framing}.\nSchachbrett = transparent.",
        6.8,
    )
    text(rect(12, 113, 88, 6), "3. Quelle und Kaustik", 10, bold=True, centered=True)
    text(
        rect(110, 113, 88, 6),
        "4. Linsenbild und kritische Kurve",
        10,
        bold=True,
        centered=True,
    )
    source_rect = image(_checkerboard(scene.source), rect(12, 120, 88, 58))
    lensed_rect = image(_checkerboard(scene.lensed), rect(110, 120, 88, 58))
    curves(source_rect, scene.caustic_curves, "#a02f47")
    curves(lensed_rect, scene.critical_curves, "#237679", dashed=True)
    x, y = scene.source_center
    center = QtCore.QPointF(
        source_rect.left() + (x + 1) / 2 * source_rect.width(),
        source_rect.top() + (y + 1) / 2 * source_rect.height(),
    )
    painter.save()
    painter.setClipRect(source_rect)
    painter.setPen(QtGui.QPen(QtGui.QColor("#17252a"), 0.15 * unit))
    for direction in (-1, 1):
        painter.drawLine(
            QtCore.QPointF(
                center.x() - 0.35 * unit, center.y() - direction * 0.35 * unit
            ),
            QtCore.QPointF(
                center.x() + 0.35 * unit, center.y() + direction * 0.35 * unit
            ),
        )
    painter.restore()
    source_caption = (
        "Quellenebene: Die Markierung zeigt das Quellenzentrum, die rote Kaustik ist die mathematische Beschreibung der kritischen Kurve. "
        + " ".join(scene.warnings)
    )
    if not scene.caustic_curves:
        source_caption += " Keine Kaustik im dargestellten Feld."
    text(rect(12, 179, 88, 10), source_caption, 7)
    text(
        rect(110, 179, 88, 10),
        (
            "Bildebene: Die kritische Kurve ist blau gestrichelt. Hier entstehen stark vergrößerte Bilder."
            if scene.critical_curves
            else "Keine kritische Kurve im dargestellten Feld."
        ),
        7,
    )
    text(
        rect(12, 192, 186, 6),
        "5. Montage vor dem ausgewählten Himmel",
        10,
        bold=True,
        centered=True,
    )
    image(scene.montage, rect(12, 200, 186, 61))
    attribution = snapshot.attribution
    footer = (
        f"{attribution.title} | Illustration: Die Modelllinse ist nicht aus diesem Himmelsbild abgeleitet. "
        "Der Himmel bleibt unverzerrt.\n"
        f"{attribution.credit}\n"
        + (f"{attribution.source_url}\n" if attribution.source_url else "")
        + (
            f"{attribution.license}: https://creativecommons.org/licenses/by-sa/3.0/igo/ | Montage verändert."
            if attribution.license
            else ""
        )
    )
    text(rect(12, 264, 109, 29), footer, 6)
    metadata_box = rect(125, 264, 73, 29)
    painter.setPen(QtGui.QPen(QtGui.QColor("#a5b4b5"), 0.2 * unit))
    painter.setBrush(QtGui.QColor("#f3f6f5"))
    painter.drawRoundedRect(metadata_box, 1.2 * unit, 1.2 * unit)
    text(rect(128, 266, 67, 25), metadata, 6.2)


def write_a4_pdf(snapshot: SceneSnapshot, path: str | Path) -> RenderedScene:
    if QtGui.QGuiApplication.instance() is None:
        raise ImageError("A running Qt application is required for A4 PDF export.")
    scene = render_snapshot(snapshot, side=PRINT_SIDE, montage_size=MONTAGE_SIZE)
    output = QtCore.QSaveFile(str(path))
    if not output.open(QtCore.QIODevice.WriteOnly):
        raise ImageError(f"Cannot open A4 PDF output: {output.errorString()}")
    writer = QtGui.QPdfWriter(output)
    writer.setResolution(PRINT_DPI)
    writer.setTitle("Der Gravitationslinseneffekt")
    writer.setCreator("Lens Desktop")
    layout = QtGui.QPageLayout(
        QtGui.QPageSize(QtGui.QPageSize.A4),
        QtGui.QPageLayout.Portrait,
        QtCore.QMarginsF(0, 0, 0, 0),
    )
    if not writer.setPageLayout(layout):
        del writer
        output.cancelWriting()
        output.commit()
        raise ImageError("Cannot configure the PDF as portrait A4.")
    painter = QtGui.QPainter()
    if not painter.begin(writer):
        del painter, writer
        output.cancelWriting()
        output.commit()
        raise ImageError("Cannot start the A4 PDF painter.")
    complete = False
    try:
        paint_a4_page(painter, snapshot, scene, PRINT_DPI)
        complete = True
    finally:
        ended = painter.end()
        del painter, writer
        if not complete or not ended:
            output.cancelWriting()
            output.commit()
    if not ended:
        raise ImageError("Cannot finish writing the A4 PDF.")
    if not output.commit():
        raise ImageError(f"Cannot save A4 PDF: {output.errorString()}")
    return scene


def print_a4_snapshot(snapshot: SceneSnapshot, printer) -> RenderedScene:
    if QtGui.QGuiApplication.instance() is None:
        raise ImageError("A running Qt application is required for A4 printing.")
    scene = render_snapshot(snapshot, side=PRINT_SIDE, montage_size=MONTAGE_SIZE)
    painter = QtGui.QPainter()
    if not painter.begin(printer):
        raise ImageError("Cannot start the A4 printer painter.")
    complete = False
    try:
        paint_a4_page(painter, snapshot, scene, printer.resolution())
        complete = True
    finally:
        ended = painter.end()
    if not complete or not ended:
        raise ImageError("Cannot finish printing the A4 page.")
    return scene
