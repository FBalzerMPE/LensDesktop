# Lens Desktop implementation plan

Date: 2026-10-02

## Goal and scope

Improve the existing Qt interface, allow selecting a webcam, load a custom sky
image, and lens a greenscreen-removed subject over that static image. Prepare
for a printable explanatory A4 page. The user has now supplied the earlier
composition and approved a frozen-input, five-panel German portrait PDF.
Implementation and native PDF inspection are complete; final verification
was paused at the user's request.

This is an incremental feature plan, not a framework migration or a rewrite.
This document tracks completed batches and the remaining implementation work.
The user's request and layering clarification are the requirements for this plan.
No separate feature spec, constitution, or architecture artifacts were supplied.

### Confirmed compositing behavior

The sky image is a static display layer. It must **not** pass through the lensing
transformation. The source subject, after greenscreen removal, is transformed
and placed over the sky:

```text
Desktop, selected webcam, or static image
    -> optional native-resolution greenscreen removal: foreground color + alpha mask
    -> paired input zoom / crop / mirror / framing
    -> optional pre-lens source shrinking and Cross / Cusp / Fold positioning
    -> lens foreground color AND alpha
    -> optional lens light and source-associated explanatory overlays
    -> size / move the rendered source (AFTER lensing)
    -> composite over unchanged sky
    -> display / image export

Custom sky image -> resize for display -> composition only
```

Changing lens parameters must not distort or move the sky. Resizing the canvas
may change its displayed crop, but not its lensing. The illustrative lens mass
remains represented by the existing SIE model and optional lens-light overlay;
loading a sky photograph does not derive a mass distribution from that image.
The user confirmed that size and position controls should manipulate the
already-lensed result, not move the input subject relative to the lens.
The later Cross/Cusp/Fold request adds a separate, opt-in pre-lens transform;
it does not change the meaning of those existing post-lens controls.

## Baseline and constraints

The implementation observations below describe the starting point for this
plan. Completed changes and their verification are recorded under each phase.

- [LensDesktop/app.py](LensDesktop/app.py) contains the Qt window, capture logic,
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
| REQ-008 | Resize and move the rendered source after lensing over an unchanged sky; load the user-supplied Euclid image from `data` by default. |
| REQ-009 | Load a static input image or freeze live input for reproducible greenscreen testing; save original calibration pixels separately from rendered-scene exports. |
| REQ-010 | Compact collapsible controls with restrained styling; cap visible window height to the available screen; use a source-size slider defaulting/resetting to 25%. |
| REQ-011 | Independently zoom/crop the input before lensing by a specified percentage, consistently across framing, masks, previews and exports without modifying native calibration pixels. |
| REQ-012 | Independently shrink the input relative to the Einstein radius and select adaptive Cross/Cusp/Fold source-plane presets, with explicit finite-source/degenerate-lens limitations and safe scene exports. |
| REQ-013 | Export a German five-panel portrait A4 PDF from a frozen/static input using current GUI settings and a detached print-resolution scene. Use Abell 2764 as the application default, but montage the currently selected sky with appropriate attribution. |

## Proposed file boundaries

Keep the current entry point and extract only functionality needed by these
features. Implemented modules and explicitly marked future modules are:

```text
LensDesktop/
    __init__.py    Package marker
    __main__.py    Launcher for python -m LensDesktop
    app.py         Qt application, source controls and export integration
    lensing.py     Shared existing lens math, forward layers, curves and markers
    controls.py    Layout-managed settings panel and control signals
    qt_compat.py   Shared binding loader so application and panel use the same Qt
    sources.py     Desktop/webcam/static normalization, selection, worker and cleanup
    processing.py  Sky loading/cache, fitting, chroma keying, alpha remapping and composition
    scene.py       Detached pixels/settings/attribution and independent print rendering
    a4_export.py   German five-panel A4 PDF layout and atomic Qt PDF writing
tests/
    test_ui.py          Panel, canvas, controls and image-export checks
    test_entrypoint.py  Package and script launcher checks
    test_sources.py     Frame normalization and threaded camera lifecycle checks
    test_camera_ui.py   Source controls, camera rendering and error integration
    test_processing.py Sky, fitting, alpha and placement math
    test_background_ui.py Default sky, all modes, markers and composed exports
    test_resources.py Bundled image/attribution paths and relocated resource layout
    test_static_source.py Native input ownership, cached fitting and calibration export
    test_static_ui.py Static selection, freeze/resume, all views and native input saving
    test_chroma_key.py Key/matte, spill, framing, halo and actual hand-photo checks
    test_chroma_ui.py Keyed views, inverse alpha, previews, webcam transitions and exports
    test_ui_polish.py Expanders, source default/slider, height limits and paired input zoom
data/
    euclid_patch_example.jpg  User-supplied default sky
    example_gs_pic.jpeg       User-supplied greenscreen calibration hand photo
    README.md                Image origin, credits and license
README.md          Setup, controls, layering and troubleshooting documentation
LensDesktop.spec   Root-level packaging specification
```

Do not extract all lens mathematics merely to reorganize the project. Keep pure
processing helpers independent of Qt widgets so they can be exercised on sample
arrays and reused for export.

**Package preparation (2026-10-02):** Before Phase 2, the application modules
were moved into the user-created `LensDesktop` package. The former
`LensDesktop.py` is now `LensDesktop/app.py`; internal imports are relative.
Run from the repository root with `python -m LensDesktop`. Tests and the
PyInstaller specification use the package entry point. Documentation, tests,
build configuration, and icons remain at the repository root.

## Implementation phases and tasks

Each phase should be usable before moving to the next. Task IDs normally follow
execution order; T024-T026 were added later for calibration and UI refinements.
Dependencies are stated explicitly.

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

- [x] T001 [Plan:1.1] Implement the layout-managed View and Lens groups in `LensDesktop/controls.py`, reusing the current control labels and parameter ranges.
- [x] T002 [Plan:1.2] Integrate the panel in `LensDesktop/app.py`; replace the corresponding absolute-position controls and adapt `HideGUI()` and `set_Geometry_sliders_and_labels()`.
- [x] T003 [Plan:1.2] Adapt canvas sizing, `_content_capture_rect_px()`, and marker/drag event coordinates in `LensDesktop/app.py` so controls do not alter capture or marker placement.

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
The Qt loader was extracted to `LensDesktop/qt_compat.py` without changing binding preference
so both application and panel use the same binding. Rendering no longer resizes
the window on every tick, as required to keep the panel outside the canvas.
`README.md` documents this batch; T022 remains open for later feature docs.

### Phase 1 follow-up: Compact controls and bounded window

**Plan 1.3 / REQ-001, REQ-007, REQ-010:** After greenscreen implementation,
refactor the growing controls into reusable keyboard-accessible expanders.
Keep Source, Source placement and View open by default; Camera setup, Input /
greenscreen, Sky background and Lens start closed. Preserve state/enabled controls
when collapsed and automatically reveal camera setup when Ctrl+F needs selection.
Keep the vertical scrollbar and native checkbox indicators. Add palette-derived
panel/input colors, rounded borders, restrained teal accents and focus outlines.

Move post-lens size/offsets into Source placement. Replace the size spin box with
a 10-200% slider/readout, default/reset 25%, zero offsets. Bound window height
using available screen geometry and non-client margins, update on screen/geometry/
window-state/frame changes, and preserve native maximization. Do not make height
fixed or require every section to be expanded.

- [x] T025 [Plan:1.3] Add reusable expanders, compact grouping and styling, source-size slider/default, screen-height limits, camera-section reveal and regression coverage.

**Acceptance/status:** Expansion retains controls and values; short windows scroll
without horizontal clipping. Source size and Reset yield 25%. Normal resize and
presentation respect the height cap. Native maximized Windows frames have invisible
off-screen borders, so their visible DWM bounds, rather than the larger Qt frame
rectangle, were verified against the taskbar-excluded work area at normal scaling.
Maximize, restore and frame toggling preserve window state. A native 125% scaling
check found maximized frameless/presentation mode extending one physical pixel
beyond the work area (1043px versus 1042px). This minor remaining issue is deferred
at the user's request to wrap up; no further window-behavior changes were made.

The actual styled Windows UI was visually checked. All 121 regressions pass at
1.5 offscreen scaling; focused polish tests also pass at 1.25 scaling. Syntax and
whitespace checks pass. Physical mixed-DPI monitor movement remains a manual check.
The user tested the UI, approved its appearance, and requested moving on after
documentation. Remaining validation gaps are physical mixed-DPI movement,
fractional-scale native bounds, and a full packaged executable build.

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

- [x] T004 [Plan:2.1] Implement source acquisition and capture lifecycle in `LensDesktop/sources.py`, including BGRA-to-BGR desktop normalization and checked webcam reads.
- [x] T005 [Plan:2.2] Implement bounded camera discovery, manual index selection, refresh/cancel behavior, and resource release in `LensDesktop/sources.py`.
- [x] T006 [Plan:2.2] Add source controls in `LensDesktop/controls.py` and wire source transitions, notifications, Ctrl+F, and shutdown cleanup in `LensDesktop/app.py`.
- [x] T007 [Plan:2.1,2.2] Replace repeated capture branches in all four `LensDesktop/app.py` rendering methods with the common source boundary, preserving opaque rendering behavior.

**Acceptance:** Desktop, an integrated webcam, and an external webcam can be
selected where present. Busy/missing cameras and unplugging are reported without
crashing or freezing the UI. Repeated switches and shutdown release the device.
Portrait, landscape, and square frames work without invalid crops or color swaps.

**Implementation status (2026-10-02):** T004-T007 are implemented. Camera
ownership stays on one worker thread; rendering polls a copied latest-frame
buffer, avoiding a growing queue of image signals. Opening a replacement
camera is transactional, desktop is the startup default, and no automatic
probing occurs. Refresh probes indices 0-4; manual selection supports 0-99.
Frames are normalized to BGR and webcam framing is center-cropped and mirrored.
All four view modes use one shared acquired frame per displayed update.
Failures are reported in the panel, status bar, and error log without black-frame
fallbacks or silent source switching. Device release occurs on the worker.
Cancel/close cannot interrupt a blocking native driver call, so shutdown remains
responsive while waiting for the call to return and cleanup to finish.

All 40 regression tests pass at the default and 1.5 offscreen scale factors.
Coverage includes colors, frame shapes, switching, discovery, cancellation,
disconnects, stale requests, slow drivers, and shutdown. Native Windows controls,
simulated webcam rendering, and clean release were also smoke-tested; Python
compilation and whitespace checks pass. No physical camera was opened during
validation. Integrated/external webcams, busy devices, unplug/retry behavior,
permissions, and performance still require hardware verification under T020.
The existing automatic OpenCV backend is retained until actual hardware results
justify a different backend. No new dependencies were added.

### Phase 3: Static sky image

Depends on Phases 1 and 2.

**Plan 3.1 / REQ-003, REQ-008:** Add Load sky, Clear sky, and aspect-preserving fit/fill
controls. Initially support local PNG/JPEG files, including Windows paths with
non-ASCII characters. Decode once, keep the original, and cache the fitted
background until the canvas size or fitting settings change. Failed loading
keeps the last valid image and produces a visible error. Cancel is a no-op.

The user has now supplied `data/euclid_patch_example.jpg` and requested it as the
default. Bundle that file and its existing `data/README.md` attribution/license;
do not download other imagery. Resource paths must be independent of the current
working directory and work with the existing PyInstaller layout. Scientific FITS
images are outside the initial scope.

**Plan 3.2 / REQ-008, REQ-005:** Add post-lens source size and horizontal/vertical
offset controls, with reset. Keep lens maps and sky unchanged when placement
changes. Apply the same placement to both Dual view panels, update marker click
coordinates using its inverse, and include the composition in screenshots and
sequences. Use explicit layer alpha/coverage rather than interpreting black
pixels as transparent. Full chroma-keying and scene snapshots remain later work.

- [x] T008 [Plan:3.1] Implement image loading, normalized color data, and aspect-preserving background fitting/cache in `LensDesktop/processing.py`.
- [x] T009 [Plan:3.1,3.2] Add sky-image and post-lens placement controls in `LensDesktop/controls.py`; integrate the default image, error handling, all views, marker coordinates, and composed image exports in `LensDesktop/app.py` and resource inclusion in `LensDesktop.spec`.

**Acceptance:** A selected sky loads once, remains unchanged as lens parameters
vary, and can be replaced or cleared. Transparent input pixels reveal the sky;
without a sky they reveal a documented neutral backdrop. Opaque input still
covers it where present; reducing source size reveals the surrounding sky.
Phase 4 is still needed to remove the webcam's own greenscreen background.

**Implementation status (2026-10-02):** T008-T009 are implemented with default
Euclid loading, PNG/JPEG selection, transactional errors/cancellation, clear/
default actions, fit/fill cache, and source size (10-200%) and offsets (-100 to
100% of a panel). That batch used full-size, centered source placement;
Plan 1.3 now changes the default/reset size to 25%, with centered placement.
The static sky bypasses lensing; placement transforms the rendered layer's
premultiplied color and alpha together. Forward out-of-bounds pixels and inverse
unsampled pixels expose sky, while real black pixels stay opaque. Clearing the
sky preserves the legacy opaque reconstruction behavior. Source-associated
overlays move with the source, and mouse coordinates are mapped back correctly.
Screenshots and sequences contain the composed scene. Sequence handling was
repaired for current inverse-map dimensions, cancelled/failed writes, and radius
restoration; zero lens mass now yields finite zero deflection instead of a
central division by zero.

All 63 regression tests pass at 1.5 offscreen scaling. Default-asset loading,
Unicode filenames, fitting/cache, unchanged background-only pixels across modes,
placement/mapping, alpha coverage, composed exports, and resource paths are
covered. Native Windows preview with the actual Euclid sky and a simulated
camera also passed and was visually checked. PyInstaller includes the image and
attribution file; a relocated bundle layout is tested, but an executable build
has not been run. Greenscreen removal and the full Phase 5 scene/snapshot work
remain open.

### Phase 4: Greenscreen and input manipulation

Depends on Phase 2 for normalized frames and Phase 1 for controls.

**Plan 4.0 / REQ-009, REQ-007:** Before implementing keying, support a static
PNG/JPEG source, the supplied hand example, and freezing the current native
desktop/webcam input. Keep original pixels separate from writable render buffers.
Static mode pauses acquisition while leaving lens, sky, and placement controls
editable. Release a frozen webcam, cancel pending camera switches, and retain
the cached static image when returning to live input. Add a native input export
distinct from the existing rendered-scene screenshot.

- [x] T024 [Plan:4.0] Add immutable static input/cache, load/example/freeze/resume controls, Fit/Fill framing, transactional source changes, and native PNG/JPEG input export; bundle the hand example and test all rendering modes and camera transitions.

**Acceptance:** The hand photograph loads without a camera. Frozen input stays
unchanged while rendering controls vary. Freeze preserves the webcam preview's
mirroring/crop but exports original, unmirrored pixels. PNG calibration exports
round-trip exactly at native dimensions. Failed loads and cancelled dialogs do
not discard input; cancelled camera requests cannot replace a static source.

**Implementation status:** T024 is implemented. Static image fitting is cached;
rendering and markers use detached buffers. Desktop capture now retains native
pixels, with resizing performed at the shared rendering boundary. Camera
freezing releases the device; Desktop/Webcam resume live acquisition. Loaded
images start in Fit without mirroring. This preparation batch preceded the
greenscreen implementation under T010-T012 described below.
All 85 regression tests pass at 1.5 offscreen scaling, including 22 new static
source/UI checks and extended relocated-resource tests. Native Windows preview
with the actual hand photo and Euclid sky passed and was visually checked;
shutdown was clean. Syntax and whitespace checks pass. The sample is included
in the packaging specification, but a full executable build was not run.

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

- [x] T010 [Plan:4.1,4.2] Implement framing, mirroring, configurable chroma keying, edge softness, and spill suppression in `LensDesktop/processing.py`.
- [x] T011 [Plan:4.1] Add grouped input/key controls, preview selection, and Reset in `LensDesktop/controls.py`; hide or disable irrelevant controls with an explanation.
- [x] T012 [Plan:4.2] Integrate input settings and preview handling in `LensDesktop/app.py`, keeping unmodified source frames separate from processed buffers.

**Acceptance:** A webcam subject retains visible colors, green areas become
transparent, soft edges blend cleanly, and legitimate dark/black subject pixels
remain visible. Disabling keying restores opaque input, and Reset restores
documented defaults. The pipeline accepts synthetic sample frames without a
physical webcam, but final tuning must be checked with the actual greenscreen.

**Implementation status:** T010-T012 are implemented. Keying is opt-in and uses
wrapped HSV hue distance, saturation protection, a smooth alpha transition, and
configurable spill suppression. Defaults are green-cyan `#00ff80`, tolerance
30 degrees, softness 12 degrees, minimum saturation 20%, and spill 50%.
Framing/mirror overrides work for desktop, webcam and static input. Original
source and alpha-mask previews bypass lensing and placement; scene preview
restores normal interaction. Reset retains source/lens/sky settings and disables
keying. Source pixels and static cached mattes remain unmodified by overlays
or exports. Static processing is reused across lens/placement changes.

The supplied hand photograph removes 100% of pixels in the tested cloth ROI
and retains 100% in the tested bright-skin and interior shadowed-arm ROIs.
These are regional checks, not a ground-truth full-image segmentation score.
All 108 regression tests pass at 1.5 offscreen scaling, including 23 new
keying/UI checks. Native Windows dual-view preview was visually checked with
the actual photo/Euclid sky and clean shutdown. Webcam checks use simulated
devices; physical lighting, hair edges and spill still need hands-on calibration.

### Phase 4 follow-up: Input zoom

**Plan 4.3 / REQ-004, REQ-007, REQ-011:** The user selected input zoom before
lensing, not zooming the final sky/composition. Add a 100-400% slider/readout:
100% retains all input; 200% keeps the central half of each native input axis;
400% keeps its central quarter. Crop color and alpha identically before fitting/
mirroring, then render at unchanged canvas dimensions. Keep native pixels, sky,
lens parameters/maps and post-lens placement independent. Apply the slider on
release and reset it to 100% with input settings.

- [x] T026 [Plan:4.3] Add paired central crop to shared framing, zoom controls/cache invalidation, opaque/keyed/live/static/preview integrations and regression tests.

**Acceptance/status:** Exact 200% crop bounds and color/alpha correspondence are
tested, including small images and invalid percentages. Zoomed green borders are
cropped in all four view modes with keying on/off. Mask/source previews use zoom;
native calibration exports remain byte-equivalent to the original decoded input.
All 121 regressions pass at 1.5 offscreen scaling. Native hand/Euclid preview with
150% input zoom and 25% post-lens source size was visually checked.

### Phase 4 follow-up: Source relative to lens

**Plan 4.4 / REQ-005, REQ-007, REQ-012:** This user-requested addition is separate
from post-lens display placement. Add opt-in shrinking of the visible-alpha
bounding box to 1-100% of the Einstein radius (default 10%) and exclusive
Cross/Cusp/Fold radio buttons. Center Cross on the tangential caustic, place
Cusp just inside its pointed end, and Fold just inside a smooth edge. Compute
the outer image-plane critical curve using the existing softened SIE map in
dimensionless lens-aligned coordinates, then map it into the source plane.
Cache shape by axis ratio/core/heart mode; rotate and scale positions with lens
angle/mass without repeating native keying. Cache static placed buffers too.

Keep this feature off by default and preserve the old opaque render path.
Placement uses paired premultiplied color/alpha, including when keying is off.
Apply it after input zoom/framing, before forward lensing. The sky, post-lens
placement, and native input/export remain independent. Calibration previews
stay unplaced; inverse mode disables presets without losing the selection.
Report absent/degenerate caustics, nearly circular lenses, zero mass, heart mode,
empty foreground, finite-source caustic crossing, clipping and low sampling
resolution. Invalid configured scenes must not export a stale pixmap.
Configured sequences omit the undefined zero-mass sample with notification
and restore the original radius; feature-off sequences retain their behavior.

- [x] T027 [Plan:4.4] Implement cached caustic-derived presets and foreground placement, grouped opt-in controls/status, forward rendering/export integration, mathematical and Qt regression tests, and usage documentation.

**Acceptance/status:** Six pure tests verify caustic containment, rotational
covariance, shape dependence, explicit unsupported states, alpha/bounding-box
placement and opaque black. Numerical lens-equation roots independently verify
four dominant point-source images, a cusp-side trio and a close fold pair.
Eleven Qt tests verify radio selection/reset, separate sky/post-lens state,
native pixels/calibration export, transparent placement without keying,
shape/static caches including failures, inverse/calibration behavior, warnings,
snapshot validation, and positive-mass sequence output/restoration.
All 138 regression tests pass at 1.5 offscreen scaling. Native Windows controls
and all three presets render with the supplied keyed hand; finite photographs
are not guaranteed to produce four distinct visible copies.

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

- [x] T013 [Plan:5.1] Implement transparent forward transformation/composition helpers in `LensDesktop/processing.py`, reusing existing lens maps from `LensDesktop/app.py`.
- [x] T014 [Plan:5.2] Add an alpha-aware inverse reconstruction path alongside `inverse_remap_image()` in `LensDesktop/app.py`, preserving its legacy opaque path.
- [x] T015 [Plan:5.3] Define the scene result and detached snapshot structures in `LensDesktop/scene.py`, including lens/input settings and optional sky attribution.
- [x] T016 [Plan:5.1,5.2] Wire the shared scene pipeline into the four rendering paths and overlays in `LensDesktop/app.py`, using one acquired frame per displayed scene.
- [ ] T017 [Plan:5.3] Update `save_screenshot()` and `recording()` in `LensDesktop/app.py` to export the composed scene consistently and handle cancellation/write errors/state restoration.

**Partial Phase 5 implementation:** T013, T014 and T016 are complete alongside
greenscreen removal. The keyed path premultiplies color before framing/remapping
and uses linear sampling for bounded, halo-free alpha edges. Opaque input keeps
its existing cubic forward/legacy inverse behavior. Keyed inverse reconstruction
averages color and alpha with identical counts and transparent excluded/unsampled
pixels. Sky composition and post-lens placement remain shared. Curves, markers,
and forward lens light explicitly contribute alpha after keying.

Keyed screenshots and inverse sequences are tested, including radius restoration
and the separate native calibration export. Diagnostic previews export what is
displayed; select Composed scene for lensed sequences. T015 is now implemented
for print export: immutable settings and detached native/sky pixels accompany
raw, cleaned, source, lensed and montage images. T017 remains open for adopting
that formal result boundary in existing screenshot/sequence workflows, which
still use detached displayed-pixmap copies.

Controlled native static dual-view measurements after avoiding redundant color
conversion/copies: 365 pixels per panel, opaque 40.99 ms / keyed 42.46 ms;
730 pixels per panel, opaque 123.50 ms / keyed 131.20 ms. Native 1200x1600 matte
computation was 120.10 ms and is cached for static input. These timings are not
webcam FPS guarantees; the 30 Hz target is not reached at these canvas sizes.
No input resolution or output quality is silently reduced. Live driver and
full pipeline benchmarking under T021 remain pending.

**Acceptance:** At fixed canvas dimensions, changing lens parameters leaves
background-only pixels identical to the fitted sky. Fully transparent
foreground reproduces the sky; opaque black foreground remains black.
Forward/inverse, single/dual, overlays, screenshots, and image sequences all use
the selected source and documented layering. No green/black rectangles or edge
halos appear where the foreground is transparent.

### Phase 6: Frozen-input A4 PDF

**Confirmed decisions:** Frozen means the existing Static / Freeze input mode,
not permanently locking the controls. Abell 2764 becomes the application default;
the PDF uses whichever sky is currently selected. The user approved portrait A4,
German text and the earlier five-panel arrangement. Direct application printing
is outside this first PDF delivery.

**Plan 6.1 / REQ-006, REQ-013:** Capture detached native pixels, sky and frozen
lens/input/display metadata at export invocation. Re-render independently of the
live canvas, source/mask preview and single/dual mode. Reuse the existing SIE
equations, keying/framing, pre-lens placement, forward remapping, lens light,
markers and critical/caustic extraction. Keep the opaque cubic path separate
from premultiplied linear alpha rendering.

**Plan 6.2 / REQ-006, REQ-013:** Use Qt's existing PDF facilities for one A4
portrait page with 12 mm content margins and a 300 dpi layout. Include native
raw photo, cleaned foreground, source/caustic diagram, lensed/critical-curve
diagram, and a wide sky montage. Label the two coordinate planes separately.
Diagnostic curves are always visible; montage overlays follow the GUI.
Fit/Fill and percentage placement operate on the wide montage destination;
the lens field remains undistorted. Include normed model/input settings,
finite-source caveats, and sky source/credits/license. Unknown custom skies
must not receive fabricated attribution. Save atomically and restore timer,
cursor and control states after errors.

- [x] T018 [Plan:6.1] Verify independent snapshot pixels/settings/attribution and print-resolution re-rendering.
- [x] T019 [Plan:6.2] Implement and verify the five-panel A4 PDF renderer and frozen-input GUI export. **Implemented; final verification pending after user-requested stop.**

**Implementation/verification status:** Print / export and Ctrl+P require static
input and forward lensing, without changing the current modes. Native Windows
export of the supplied keyed hand over Abell 2764 took about 1.06 seconds and
produced an approximately 0.82 MB PDF. Independent inspection verified one
standard A4 page, German text and credits, five embedded images (native
1200x1600 photo, three 734x734 panels, 2197x733 montage), in-page text bounds
and successful PDF rasterization. The A4 preview was accepted by the user.
The independent reader was isolated validation tooling, not an application
dependency; Qt PDF writing adds no runtime package requirement.

Twenty-one targeted scene/PDF/GUI/resource checks passed. The latest full run
had 157 tests: 155 passed, two failed from outdated test expectations for the
relocated keying helper and new Ctrl+P shortcut. These expectations were updated,
but not rerun. The subsequent frozen-webcam snapshot test and final small
caption/annotation changes are also unverified. The user explicitly requested
documentation and wrap-up rather than more implementation/testing.
A final regression run and physical A4 print remain open; do not claim a
fully verified final batch.

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

- [ ] T020 [Plan:7.1] Perform the phase acceptance checks and final desktop/webcam/sky/keying/output matrix against `LensDesktop/app.py` and the extracted modules.
- [ ] T021 [Plan:7.1] Measure and compare pipeline timings on Windows and resolve regressions caused by the changes in `LensDesktop/sources.py`, `LensDesktop/processing.py`, and `LensDesktop/app.py`.
- [x] T022 [Plan:7.2] Update `README.md` with setup, feature instructions, A4 workflow, attribution and explicit verification gaps.
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
| REQ-001 | 1.1, 1.2, 7.1 | T001-T003, T020 | `LensDesktop/controls.py`; `LensDesktop/app.py` UI, visibility, canvas interaction |
| REQ-002 | 2.1, 2.2, 7.1 | T004-T007, T020 | `LensDesktop/sources.py`; source controls and capture lifecycle integration |
| REQ-003 | 3.1, 7.1 | T008-T009, T020 | `LensDesktop/processing.py` image loading/cache; sky controls |
| REQ-004 | 4.1, 4.2, 7.1 | T010-T012, T020 | `LensDesktop/processing.py` framing/keying; input controls and previews |
| REQ-005 | 3.2, 4.2, 5.1, 5.2, 5.3, 7.1 | T009-T010, T012-T017, T020-T021 | Layer coverage/composition and placement; later chroma key and scene/snapshot pipeline |
| REQ-006 | 5.3, 6.1, 6.2, 7.1 | T015, T017-T020 | Detached `LensDesktop/scene.py` print snapshots; `LensDesktop/a4_export.py` PDF renderer; frozen-input GUI integration |
| REQ-007 | 1.1, 1.2, 2.1, 5.1, 5.2, 7.1, 7.2 | T001-T004, T007, T013-T014, T016, T020-T023 | Preserved opaque desktop behavior; `README.md`; verified packaging |
| REQ-008 | 3.1, 3.2 | T008-T009 | Post-lens placement helpers and controls; default `data` asset; all view/export integrations |
| REQ-009 | 4.0 | T024 | Static source/cache; load/example/freeze/resume controls; raw input export; hand resource; static source/UI tests |
| REQ-010 | 1.3 | T025 | Reusable expanders/styles; size slider/default; available-screen height/state hooks; polish tests |
| REQ-011 | 4.3 | T026 | Paired zoom crop/framing; slider/cache/preview integration; native export and all-mode tests |
| REQ-012 | 4.4 | T027 | Caustic-derived presets; alpha-aware pre-lens placement; opt-in controls/status; safe screenshots/sequences; point-source and Qt tests |
| REQ-013 | 5.3, 6.1, 6.2, 7.2 | T015, T018-T019, T022 | Shared lens helpers, detached print rendering, five-panel German PDF, static-mode guard, Abell resource/default and attribution |

## Suggested delivery order

1. Deliver the UI cleanup on its own and review its appearance.
2. Deliver reliable webcam selection without changing lensing.
3. Add sky loading, static calibration input, and then a usable greenscreen preview.
4. Deliver the transparent lensing/composition pipeline and consistent exports.
5. Complete regression checks and usage documentation.
6. A4 instructions have been supplied and the PDF implemented; finish its
   regression and physical-print checks when testing resumes.

## Open todos at A4 wrap-up

- **T019 / T020:** Run the final regression suite after the two expectation fixes,
  the new frozen-webcam test, and latest caption/annotation adjustments. The
  present suite is expected to contain 158 tests, but that run has not occurred.
- **T019:** Print the PDF on physical A4 at actual size / 100%; check legibility,
  colors and margins. Small GUI sources remain small on paper by design.
- **T017:** Adopt the formal scene result in existing screenshot/sequence exports;
  their current detached-pixmap behavior is preserved.
- **T020 / T021:** Final live-camera/lighting, mixed-DPI and performance checks.
  Prior live rendering measurements exceeded the 30 Hz target at larger canvases.
- **T023:** Build and smoke-test the Windows executable. The spec includes Abell
  2764 and resource-path tests passed; the full executable was not built.
- **Deferred UI issue:** The known one-physical-pixel Windows 125% maximized
  presentation-mode work-area overshoot remains untouched.

No additional implementation or testing was performed after the user's
request to stop and finish documentation.
