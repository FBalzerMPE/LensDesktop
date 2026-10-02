# Lens Desktop implementation plan

Date: 2026-10-02

## Goal and scope

Improve the existing Qt interface, allow selecting a webcam, load a custom sky
image, and lens a greenscreen-removed subject over that static image. Prepare
for a printable explanatory A4 page, but defer its content and layout until
further instructions.

This is an incremental feature plan, not a framework migration or a rewrite.
Only this document is being added now; the tasks below describe future work.
The user's request and layering clarification are the requirements for this plan.
No separate feature spec, constitution, or architecture artifacts were supplied.

### Confirmed compositing behavior

The sky image is a static display layer. It must **not** pass through the lensing
transformation. The source subject, after greenscreen removal, is transformed
and placed over the sky:

```text
Desktop or selected webcam
    -> crop / mirror / input adjustments
    -> greenscreen removal: foreground color + alpha mask
    -> lens foreground color AND alpha
    -> composite over unchanged sky
    -> optional lens light and explanatory overlays
    -> display / image export

Custom sky image -> resize for display -> composition only
```

Changing lens parameters must not distort or move the sky. Resizing the canvas
may change its displayed crop, but not its lensing. The illustrative lens mass
remains represented by the existing SIE model and optional lens-light overlay;
loading a sky photograph does not derive a mass distribution from that image.

## Current implementation and constraints

- [LensDesktop.py](LensDesktop.py) contains the Qt window, capture logic,
  transformations, controls, and export functions.
- The four corner checkboxes use fixed geometry, bold fonts scaled from image
  size, and separate light-gray backgrounds. Sliders also use fixed geometry.
- `camera_recording()` toggles desktop capture and `cv2.VideoCapture(0)`.
  There is no camera selector, explicit capture release on switching, or useful
  camera-open error notification.
- `capture_cam_rect()` accesses the frame before checking whether capture
  succeeded. Its square crop is unsuitable for some aspect ratios.
- The four rendering paths repeat capture and color conversion. Desktop capture
  returns BGRA, while OpenCV cameras normally return BGR. Normalize these at
  the input boundary rather than assuming all sources have the same channels.
- Forward lensing uses `cv2.remap`. `inverse_remap_image()` currently requires
  three channels and fills unsampled pixels with a mean color. That behavior
  cannot be reused unchanged for transparent foregrounds.
- Screenshot and sequence exports use the displayed image pixmap. Keep those
  workflows, but have them consume the same composed scene as the live display.
- The current timer targets approximately 30 updates per second. This is a
  target, not a measured performance guarantee.
- The user has successfully run Python 3.12 with PyQt5 on Windows. Use that
  combination as the first supported development target. The loader also tries
  other bindings, but that does not establish compatibility with them.
- `mss.MSS()` is already in the current code; no constructor fix is needed.
- The window geometry warning and broader multi-monitor behavior are not
  standalone tasks here. Only adjust geometry where the new UI requires it.
- Preserve the SIE equations, parameter meanings, desktop-under-window capture,
  single/dual view, inverse view, lens light, critical/caustic curves, marker
  interactions, and existing shortcuts.

Use existing NumPy, OpenCV, SciPy, mss, and PyQt5 facilities. Do not introduce a
new UI framework or an AI segmentation dependency. Add dependencies only if a
later implementation requirement demonstrates a need.

## Requirements

| ID | Requirement |
|---|---|
| REQ-001 | Replace the awkward checkbox presentation with readable, consistent controls without losing existing toggles or shortcuts. |
| REQ-002 | Select desktop or a specific available webcam, with explicit capture errors and reliable resource cleanup. |
| REQ-003 | Load, replace, and clear a local custom sky image that remains unaffected by lensing. |
| REQ-004 | Provide input manipulation for a greenscreen setup: crop/fit, mirroring, chroma-key controls, mask preview, and reset. |
| REQ-005 | Lens the transparent foreground and composite it over the static sky consistently across supported views and image exports. |
| REQ-006 | Prepare a reusable scene snapshot for a later explanatory A4 export; defer the actual page implementation until instructions arrive. |
| REQ-007 | Preserve existing desktop functionality and document the new Windows workflow and feature behavior. |

## Proposed file boundaries

Keep the current entry point and extract only functionality needed by these
features. These are proposed future files, not existing modules:

```text
LensDesktop.py      Qt application integration, existing lens math and markers
controls.py        Layout-managed settings panel and control signals
qt_compat.py       Shared binding loader so application and panel use the same Qt
sources.py         Desktop/webcam acquisition, camera selection and cleanup
processing.py      Input normalization, framing, chroma key and composition
scene.py           Scene result and detached export snapshot
tests/test_ui.py   Focused panel, canvas, controls and image-export checks
README.md          Setup, controls, layering and troubleshooting documentation
LensDesktop.spec   Packaging adjustments only when needed
```

Do not extract all lens mathematics merely to reorganize the project. Keep pure
processing helpers independent of Qt widgets so they can be exercised on sample
arrays and reused for export.

## Implementation phases and tasks

Each phase should be usable before moving to the next. Task IDs are execution
order; dependencies are stated explicitly.

### Phase 1: Readable UI first

**Plan 1.1 / REQ-001, REQ-007:** Propose a compact, hideable settings panel with
grouped View and Lens controls. Use Qt layouts, native checkbox indicators,
consistent spacing, palette-aware colors, and normal readable fonts. Prefer a
panel outside the image over separate opaque labels scattered over it. Confirm
this presentation with the user before doing visual polish.

**Plan 1.2 / REQ-001, REQ-007:** Wire the panel to existing application state.
The canvas, not the entire window including the panel, defines image geometry.
Update mouse-coordinate mapping and desktop capture coordinates accordingly.
Retain Ctrl+V presentation mode, including its existing frame toggle, and
inverse-only mask controls. This is not a general resize-warning cleanup.

- [x] T001 [Plan:1.1] Implement the layout-managed View and Lens groups in `controls.py`, reusing the current control labels and parameter ranges.
- [x] T002 [Plan:1.2] Integrate the panel in `LensDesktop.py`; replace the corresponding absolute-position controls and adapt `HideGUI()` and `set_Geometry_sliders_and_labels()`.
- [x] T003 [Plan:1.2] Adapt canvas sizing, `_content_capture_rect_px()`, and marker/drag event coordinates in `LensDesktop.py` so controls do not alter capture or marker placement.

**Acceptance:** Checkbox labels and indicators are fully visible at Windows
100%, 125%, and 150% display scaling, keyboard focus is visible, controls do not
cover the canvas, and all existing view toggles and shortcuts still work.

**Implementation status (2026-10-02):** The user approved the side panel.
T001-T003 are implemented. Eleven focused regression checks pass at each
offscreen scale factor 1.0, 1.25, and 1.5, covering layout, mode switching,
slider settings, capture origin, marker/drag interactions, presentation mode,
shortcut registration/signals, scrolling, and image-only screenshot export.
A native Windows launch with live desktop capture also passes, with capture
exclusion enabled. Python compilation and whitespace checks pass.
Visual approval, native keyboard-focus appearance, and actual desktop alignment
at each Windows display-scaling setting still need hands-on verification.
The Qt loader was extracted to `qt_compat.py` without changing binding preference
so both application and panel use the same binding. Rendering no longer resizes
the window on every tick, as required to keep the panel outside the canvas.
`README.md` documents this batch; T022 remains open for later feature docs.

### Phase 2: Reliable input sources and webcam selection

Depends on Phase 1 for the selector UI.

**Plan 2.1 / REQ-002, REQ-007:** Create one source-acquisition boundary returning
a documented contiguous BGR `uint8` frame. Separate native capture size from
the render canvas size and make framing an explicit later step. Check camera
read success before touching frame dimensions.

**Plan 2.2 / REQ-002:** Add Source, Camera, and Refresh controls. Desktop remains
the startup default. Use a bounded, user-triggered OpenCV device-index probe
with cancellation and a manual index option; label indices honestly rather than
inventing device names. Do not probe cameras every render tick. Probing and
opening must not freeze the UI; keep camera ownership/thread access consistent.
Evaluate the Windows capture backend on actual hardware before selecting one.

Switch sources only after the new camera opens and yields a valid frame. On
failure, keep the previous source and show an actionable message. On disconnect,
show a persistent status and allow retry or an explicit return to desktop;
never silently switch sources or present a fabricated black frame as success.
Release captures on switching, failed probes, and application close. Ctrl+F
toggles desktop and the selected camera, and uses the selector when no camera
has been selected.

- [ ] T004 [Plan:2.1] Implement source acquisition and capture lifecycle in `sources.py`, including BGRA-to-BGR desktop normalization and checked webcam reads.
- [ ] T005 [Plan:2.2] Implement bounded camera discovery, manual index selection, refresh/cancel behavior, and resource release in `sources.py`.
- [ ] T006 [Plan:2.2] Add source controls in `controls.py` and wire source transitions, notifications, Ctrl+F, and shutdown cleanup in `LensDesktop.py`.
- [ ] T007 [Plan:2.1,2.2] Replace repeated capture branches in all four `LensDesktop.py` rendering methods with the common source boundary, preserving opaque rendering behavior.

**Acceptance:** Desktop, an integrated webcam, and an external webcam can be
selected where present. Busy/missing cameras and unplugging are reported without
crashing or freezing the UI. Repeated switches and shutdown release the device.
Portrait, landscape, and square frames work without invalid crops or color swaps.

### Phase 3: Static sky image

Depends on Phases 1 and 2.

**Plan 3.1 / REQ-003:** Add Load sky, Clear sky, and aspect-preserving fit/fill
controls. Initially support local PNG/JPEG files, including Windows paths with
non-ASCII characters. Decode once, keep the original, and cache the fitted
background until the canvas size or fitting settings change. Failed loading
keeps the last valid image and produces a visible error. Cancel is a no-op.

Do not bundle or download a Euclid image automatically. Let the user provide an
image they may use; retain optional attribution text for a future printed page.
Scientific FITS images are outside the initial scope.

- [ ] T008 [Plan:3.1] Implement image loading, normalized color data, and aspect-preserving background fitting/cache in `processing.py`.
- [ ] T009 [Plan:3.1] Add sky-image controls in `controls.py` and integrate the selected background state and error messages in `LensDesktop.py`.

**Acceptance:** A selected sky loads once, remains unchanged as lens parameters
vary, and can be replaced or cleared. Transparent input pixels reveal the sky;
without a sky they reveal a documented neutral backdrop. Opaque input still
covers it, so Phase 4 is necessary to see it behind a webcam subject.

### Phase 4: Greenscreen and input manipulation

Depends on Phase 2 for normalized frames and Phase 1 for controls.

**Plan 4.1 / REQ-004:** Add aspect-preserving crop/fit controls, a mirror toggle,
key-color selection, tolerance, edge softness, basic green-spill suppression,
mask preview, and Reset input settings. Preserve the current mirrored webcam
default, while making it explicit; leave desktop unmirrored. Extra effects,
AI background removal, and extensive photo editing are not initial scope.

**Plan 4.2 / REQ-004, REQ-005:** Implement chroma keying with existing OpenCV/NumPy
operations. Keep foreground color and a floating-point alpha mask in [0, 1].
Apply framing identically to color and mask; do not key the sky or infer
transparency from black pixel values. With keying disabled, use an opaque mask.
Preview must distinguish the source, mask, and final composition without
changing the lens parameters.

- [ ] T010 [Plan:4.1,4.2] Implement framing, mirroring, configurable chroma keying, edge softness, and spill suppression in `processing.py`.
- [ ] T011 [Plan:4.1] Add grouped input/key controls, preview selection, and Reset in `controls.py`; hide or disable irrelevant controls with an explanation.
- [ ] T012 [Plan:4.2] Integrate input settings and preview handling in `LensDesktop.py`, keeping unmodified source frames separate from processed buffers.

**Acceptance:** A webcam subject retains visible colors, green areas become
transparent, soft edges blend cleanly, and legitimate dark/black subject pixels
remain visible. Disabling keying restores opaque input, and Reset restores
documented defaults. The pipeline accepts synthetic sample frames without a
physical webcam, but final tuning must be checked with the actual greenscreen.

### Phase 5: Transparent lensing and consistent output

Depends on Phases 2, 3, and 4.

**Plan 5.1 / REQ-005, REQ-007:** Introduce a shared scene-rendering boundary.
Premultiply foreground color by alpha before forward interpolation; remap color
and alpha with identical coordinates, transparent out-of-bounds pixels, and
bounded alpha values. Composite only after transformation:

```text
output = transformed_premultiplied_color + sky * (1 - transformed_alpha)
```

Preserve existing opaque interpolation unless changing it is demonstrably
necessary. Choose and validate mask interpolation to avoid ringing, dark halos,
or opaque rectangles. Do not remap a foreground already flattened onto the sky.

**Plan 5.2 / REQ-005, REQ-007:** Wire the shared pipeline into forward/inverse and
single/dual modes. In forward dual view, show the untransformed keyed subject
over the sky beside the transformed subject over the same sky. In inverse view,
apply inverse reconstruction to foreground data only; it remains the existing
illustrative inverse operation, not a guaranteed recovery of an original image.

For keyed inverse rendering, reconstruct premultiplied color and alpha using
the same accumulation/count/mask rules. Unsampled or excluded pixels are
transparent, not mean-color fills. Preserve the existing opaque inverse
behavior separately. Draw critical/caustic curves, markers, and lens light at
their intended stage and coordinates without treating the sky as source data.

**Plan 5.3 / REQ-005, REQ-006:** Store explicit source/transformed/composed images
and parameter metadata in a scene result. Screenshot and sequence exports use
that result without control widgets. Snapshot arrays must be detached copies,
not buffers that the next timer tick will mutate. Report file-write failures.
Sequence capture restores parameters and render state even if export fails.

- [ ] T013 [Plan:5.1] Implement transparent forward transformation/composition helpers in `processing.py`, reusing existing lens maps from `LensDesktop.py`.
- [ ] T014 [Plan:5.2] Add an alpha-aware inverse reconstruction path alongside `inverse_remap_image()` in `LensDesktop.py`, preserving its legacy opaque path.
- [ ] T015 [Plan:5.3] Define the scene result and detached snapshot structures in `scene.py`, including lens/input settings and optional sky attribution.
- [ ] T016 [Plan:5.1,5.2] Wire the shared scene pipeline into the four rendering paths and overlays in `LensDesktop.py`, using one acquired frame per displayed scene.
- [ ] T017 [Plan:5.3] Update `save_screenshot()` and `recording()` in `LensDesktop.py` to export the composed scene consistently and handle cancellation/write errors/state restoration.

**Acceptance:** At fixed canvas dimensions, changing lens parameters leaves
background-only pixels identical to the fitted sky. Fully transparent
foreground reproduces the sky; opaque black foreground remains black.
Forward/inverse, single/dual, overlays, screenshots, and image sequences all use
the selected source and documented layering. No green/black rectangles or edge
halos appear where the foreground is transparent.

### Phase 6: A4 export preparation; actual export deferred

Preparation depends on Phase 5. Actual page implementation is blocked until
the user supplies the remaining instructions.

**Plan 6.1 / REQ-006:** Reuse the detached scene snapshot as the future print
input: images, lens settings, source description, and sky attribution. Do not
capture a screenshot of the UI or open a misleading unfinished export dialog.

**Plan 6.2 / REQ-006:** Later confirm page language, explanatory text, audience,
portrait/landscape orientation, diagram/image arrangement, caption requirements,
credits, and whether PDF, direct printing, or both are required. Prefer existing
Qt PDF/printing facilities if suitable. Use physical A4 dimensions (210 x
297 mm), explicit margins, and print-quality scene rendering rather than
stretching a low-resolution preview. Exact resolution and page design remain
undecided.

- [ ] T018 [Plan:6.1] Confirm that `scene.py` snapshots provide independent images, settings, and attribution suitable for later high-resolution rendering.
- [ ] T019 [Plan:6.2] After receiving page instructions, refine the export tasks in `PLAN.md`; only then implement the page renderer and any required Qt print integration.

**Acceptance now:** Snapshot contents are usable independently of the live
camera and Qt controls. **Acceptance later:** A4 PDF/page dimensions, content,
image clarity, attribution, and a physical print are checked against the user's
instructions. Do not claim A4 export is delivered before this gate is met.

### Phase 7: Validation and documentation

Validate at the end of each earlier phase, not only at the end of the project.
Final documentation depends on the corresponding implemented feature.

**Plan 7.1 / REQ-001 through REQ-007:** Run the phase acceptance checks on Windows.
Compare desktop output against the current baseline using fixed input and
parameters; preserve existing opaque behavior. Exercise no-camera, bad-image,
camera-disconnect, cancelled-dialog, unwritable-output, and repeated-switch
paths. Existing desktop geometry warnings are not a completion blocker unless
new work introduces a regression.

Measure capture/processing/render timings on the target laptop before and after
the new pipeline, at the same canvas size. Avoid per-frame image decoding,
camera probing, or lens-map rebuilding. If frames cannot meet the current
roughly 30 Hz target, report measured performance and tune processing resolution
or frame scheduling without silently reducing image quality.

**Plan 7.2 / REQ-007:** Document the working Windows Python 3.12/PyQt5 setup,
source selection, keying workflow, static-sky semantics, shortcuts, attribution,
and limitations. Verify packaging if the new modules affect the executable;
do not claim untested Qt bindings or platforms are supported.

- [ ] T020 [Plan:7.1] Perform the phase acceptance checks and final desktop/webcam/sky/keying/output matrix against `LensDesktop.py` and the extracted modules.
- [ ] T021 [Plan:7.1] Measure and compare pipeline timings on Windows and resolve regressions caused by the changes in `sources.py`, `processing.py`, and `LensDesktop.py`.
- [ ] T022 [Plan:7.2] Update `README.md` with verified setup and feature instructions.
- [ ] T023 [Plan:7.2] Check `LensDesktop.spec` module/resource inclusion and smoke-test a packaged Windows build when packaging dependencies are available.

No new automated-test tooling is prescribed in this plan. Phase 1 adds focused
checks using standard-library `unittest`, without another dependency. Extend
existing checks where appropriate; the measurable acceptance checks above
are mandatory. Any unavailable camera, greenscreen, display-scaling setting, or
printer validation must be reported as an explicit verification gap.

## Requirement mapping

Implementation evidence below names expected future outputs, not completed work.

| Requirement | Plan items | Tasks | Implementation evidence |
|---|---|---|---|
| REQ-001 | 1.1, 1.2, 7.1 | T001-T003, T020 | `controls.py`; `LensDesktop.py` UI, visibility, canvas interaction |
| REQ-002 | 2.1, 2.2, 7.1 | T004-T007, T020 | `sources.py`; source controls and capture lifecycle integration |
| REQ-003 | 3.1, 7.1 | T008-T009, T020 | `processing.py` image loading/cache; sky controls |
| REQ-004 | 4.1, 4.2, 7.1 | T010-T012, T020 | `processing.py` framing/keying; input controls and previews |
| REQ-005 | 4.2, 5.1, 5.2, 5.3, 7.1 | T010, T012-T017, T020-T021 | Shared transparent scene pipeline; all view and image-export paths |
| REQ-006 | 5.3, 6.1, 6.2, 7.1 | T015, T017-T020 | `scene.py` snapshots; later user-approved A4 export implementation |
| REQ-007 | 1.1, 1.2, 2.1, 5.1, 5.2, 7.1, 7.2 | T001-T004, T007, T013-T014, T016, T020-T023 | Preserved opaque desktop behavior; `README.md`; verified packaging |

## Suggested delivery order

1. Deliver the UI cleanup on its own and review its appearance.
2. Deliver reliable webcam selection without changing lensing.
3. Add sky loading and a usable greenscreen preview.
4. Deliver the transparent lensing/composition pipeline and consistent exports.
5. Complete regression checks and usage documentation.
6. Implement the A4 page only after its instructions are supplied.
