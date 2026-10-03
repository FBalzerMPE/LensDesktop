# Lens Desktop

![A tool to lens what is shown on your Desktop!](example.png)

# Important Disclaimer

This tool uses screen / camera recording to map images in (almost) real time to a lensed/delensed image.

In order for the tool to apply to other windows you will need to give it the rights for screen / camera recording.
I, therefore, recommend to use pyinstaller to create an ".app" file first. 
Once you have that you can give these rights to the app rather than the terminal (the latter might being a security concern).
Your computer might close the app before you can give permission for those recordings, but you usually just have to restart it when that happens.

I only used this Code on my Macbook where it ran in almost real time. I have not yet confirmed if it is supported by other platforms.
If it does not work for those, but you found a fix, please let me know so that we can include it in upcoming versions!

# Installation

First download the code into a folder of your choice:
```
git clone https://github.com/WolfgangEnzi/LensDesktop.git
cd LensDesktop
```

I also recommend to create a new environment either with conda or venv:

```
conda create -n lens_desktop python=3.11
conda activate lens_desktop
```

or

```
python -m venv lens_desktop
source lens_desktop/Scripts/activate
```

The following commands should create an executable (.exe or .app) in a newly created dist folder. You can grant the executable the rights for screen / camera recording without having to give these rights to the terminal.

You can then install the required packages. 
For Macbooks users this should be:

```
python -m pip install pyobjc mss pyinstaller pyobjc-framework-Quartz numpy scipy opencv-python PyQt5
```

Alternatively for Windows users:

```
pip install numpy scipy opencv-python pyqt5 mss pyinstaller 
```

Using pyinstaller you can then create the executable in a new folder:

```
pyinstaller --noconfirm LensDesktop.spec
```

The first start after creating the app usually takes a bit longer.

### GUI defaults

User-facing startup and reset values are stored in [data/defaults.ini](data/defaults.ini),
grouped by the settings-panel sections. Edit the file before starting Lens Desktop
to change these defaults. A missing or invalid file is reported at startup rather
than silently falling back to hard-coded values.

## Running on Windows for development

Use Python 3.12 and a dedicated environment containing PyQt5. From PowerShell
in the repository folder:

```powershell
& "C:\Python312\python.exe" -m venv .venv-qt5
.\.venv-qt5\Scripts\python.exe -m pip install numpy scipy opencv-python PyQt5 mss
.\.venv-qt5\Scripts\python.exe -m LensDesktop
```

Replace the first executable path with your installed Python 3.12 path if
different. Using that path directly avoids Conda environments shadowing the
Windows `py` launcher. Do not install another Qt binding in this environment:
the application's loader prefers PySide6, but the current application uses
Qt5-specific APIs.

The application modules live in the `LensDesktop` package. Run the command from
the repository folder, not from inside the package. `LensDesktop/__main__.py`
starts the application implemented in `LensDesktop/app.py`.
The PyInstaller specification and icons remain at the repository root.

## Controls

View toggles and lens sliders are grouped in a settings panel beside the image.
Related controls are grouped in keyboard-accessible expanders, with a restrained
teal accent and rounded panels. Sections appear in the order Source, Input /
greenscreen, Sky background, Source placement, Source relative to lens, Lens,
View, and Print / export. Expansion defaults are configured in
`data/defaults.ini`. Click a section header to expand/collapse it; values and
enabled states are retained. The reset icon at the right of a settings section
restores that section's configured defaults; Sky background restores its bundled
image and Source restores the configured default input (currently the Hand
example). Print / export has no reset icon.
Ctrl+F opens the required camera sections when selection is needed. The panel
scrolls vertically when the window is short.
Mask Radius is shown only in De-lensing mode.

Window height is capped to the current screen's available height, including
title bar/borders and excluding the taskbar. The cap updates when the window
changes screens, available screen geometry changes, maximize/restore changes the
frame margins, or Ctrl+V toggles the frame. Native maximization is retained.
This is a maximum, not a fixed window height; shorter windows remain supported.

**Known display-scaling limitation:** On Windows at 125% scaling, maximized
frameless/presentation mode can extend one physical pixel into the taskbar work
area. Normal-scale maximize/restore and presentation checks passed. Physical
mixed-DPI monitor movement still needs verification; this minor fractional-scale
edge case is deferred rather than changing otherwise satisfactory window behavior.

The image remains square (two squares in Dual view) and fits in the available
canvas area. Extra space is left around it instead of stretching the image.
Drag the image to move the window; right-click the image to add or remove a
marker. Clicking the settings panel does not place markers.

Ctrl+V hides or restores the panel and toggles the window frame for presentation.
Settings are retained. Screenshots export the image, not the settings panel.
Greenscreen controls and A4 PDF export are described below. Remaining work is
tracked in [PLAN.md](PLAN.md).

### Sky background and source placement

The bundled [Euclid image of Abell 2764](data/euclid_abell_2764_example.jpeg)
loads by default. The earlier [sky mosaic](data/euclid_patch_example.jpg) remains
available through **Load...**.
Its source, credits, and license are in [data/README.md](data/README.md); retain
the required attribution/license when sharing images that use it.

In **Sky background**:

- **Load...** selects a local PNG/JPEG, including non-ASCII Windows filenames.
  A failed load leaves the last valid sky in place; cancelling does nothing.
- **Clear** removes the sky and uses a black backdrop. **Default** restores the
  bundled Abell 2764 image.
- **Fill** preserves aspect ratio and crops the center to fill the canvas.
  **Fit** preserves the whole sky image and adds black margins.
- In **Source placement**, the **Source size** slider scales the rendered source
  from 10% to 200% of a panel, with a percentage readout. Its default is set in
  `data/defaults.ini` (currently **50%**).
  **Horizontal offset** and **Vertical offset** shift it by a percentage of the
  panel width/height (positive values move right/down).
- The **Source placement reset icon** restores the configured size and offsets.

Placement is applied **after lensing**, including the source's curves/markers
and optional lens-light overlay. It does not move the lens relative to the input,
recompute the lens maps, or lens the sky. In Dual view, the same placement and
unchanged sky are used in both panels. Screenshots and sequences export the
composed scene, without controls.

The sky is decoded once and its fitted version is cached. The configured source
size leaves room to see the surrounding sky; increase the slider for a larger subject.
The webcam's own background remains opaque unless **Remove greenscreen** is
enabled. Black subject pixels are not treated as transparency.

### Cross, Cusp, and Fold configurations

Open **Source relative to lens** and enable **Place input before lensing**.
Leaving it off preserves the existing rendering. Its initial enabled state and
size are configured in `data/defaults.ini`.

- **Input size** sets the longest visible source extent to 1-100% of the
  Einstein radius. Its default is set in `data/defaults.ini` (currently **50%**).
  The visible-alpha bounding box is
  trimmed and centered; without greenscreen removal, the whole image rectangle
  is the subject. Black pixels remain opaque.
- **Cross** centers the subject inside the tangential caustic.
- **Cusp** places it just inside a pointed caustic end, bringing three dominant
  images together on one side.
- **Fold** places it just inside a smooth caustic edge, bringing two images
  close together.
- Preset positions follow axis ratio, core radius, position angle, and lens
  mass. The **Source relative to lens reset icon** restores its configured
  enabled state, size, and preset.

These controls change the input **before lensing**. Input zoom still crops the
original subject first; **Source placement** still scales/moves the resulting
lensed image afterwards. Neither operation lenses the sky or modifies saved
native calibration pixels.

For testing, load **Hand example**, enable **Remove greenscreen**, and select
**Composed scene**. Start with Cross; for Cusp/Fold, try a smaller Input size
(1-3%) and increase the post-lens Source size to inspect the result. **Dual view**
shows the positioned source and its lensed counterpart.

An extended photograph may cross a caustic or merge into arcs rather than show
four separate copies. The status warns about excessive source extent, low
source sampling resolution, and clipping. High lens mass can also push images
outside the displayed field; reduce mass if necessary. Nearly circular lenses,
cores without a usable tangential caustic, zero mass, and heart mode are
reported explicitly; the last image stays visible but cannot be exported as a
new configured scene.

Presets apply only to forward lensing: De-lensing disables them while retaining
the selection. Source/mask calibration previews remain unplaced. Ctrl+S
validates and redraws an active configuration before saving. Configuration
sequences omit the undefined zero-mass sample (159 positive-mass frames instead
of the usual 160) and restore the selected lens settings afterwards.

### Selecting a webcam

The application starts with the supplied **Hand example** as a static input.
The input-source menu lists **Static image**, **Webcam**, then **Desktop**; it
does not open or probe a camera until you request one.

1. In the **Source** group, click **Refresh** to check camera indices 0 through 4.
2. Choose a discovered **Camera N**, then choose **Webcam** as the input source.
3. Alternatively, enter an index (0-99) and click **Use index / retry** to open it
   directly. Index 0 commonly refers to the integrated webcam; external cameras
   may use another index. These indices are not stable device names.
4. Choose **Desktop** to return to screen capture. **Ctrl+F** toggles between
   Desktop and the selected webcam; without a selection, it reveals the camera
   controls rather than guessing a device.

Webcam frames are center-cropped to a square and mirrored. Portrait, landscape,
and square inputs are supported. The source is used in forward/inverse and
single/dual views, as well as the existing image export workflows.

Opening and reading cameras, refreshing the list, and releasing devices happen
on a worker thread. A failed open keeps the previous source. If an active camera
stops producing frames, the last displayed image is explicitly marked as frozen
in the status text; click **Use index / retry**, or select **Desktop**.

**Cancel** stops a refresh between driver operations. Selecting Desktop (or
Ctrl+F while opening) cancels a pending camera switch. A blocking OpenCV driver
call cannot be forcibly interrupted: cancellation and shutdown finish when that
call returns. The window remains responsive and reports when shutdown is
waiting for the driver. A scan may temporarily retain the active camera's last
frame while probing other indices.

If a camera cannot be opened, check Windows **Settings > Privacy & security >
Camera**, enable camera access for desktop apps, and close other programs using
the camera. OpenCV's automatic capture backend is used; actual backend/device
compatibility still needs verification on your laptop.

### Static input and greenscreen preparation

In the **Source** group:

- **Hand example** loads the supplied [greenscreen photo](data/example_gs_pic.jpeg)
  as the input, not the sky. **Load image...** selects another local PNG/JPEG.
  Images are decoded once, stay unmirrored, and initially use **Fit** to show the
  whole photograph. **Fill** center-crops to fill the source canvas.
- **Freeze webcam** is a prominent two-state toggle outside the camera setup
  controls. It captures the current webcam frame and releases the camera; click
  **Resume webcam** to reopen that camera. It is disabled until a webcam is
  connected, and the frozen frame keeps its mirrored preview while storing the
  original unmirrored pixels.
- Static mode stops live acquisition, not rendering: lens parameters, view
  modes, sky selection, and source size/position remain adjustable.
- Select **Desktop** or **Webcam** in the input-source menu to change the live
  source. Selecting **Static image** restores the last loaded image; if none
  exists, a file picker opens.
- **Save input...** saves the original input at its captured/loaded resolution,
  before framing, mirroring, lensing, sky composition, or overlays. PNG is the
  default and preserves calibration pixels exactly; JPEG is also available but
  is lossy. A save snapshots the current frame before the file dialog opens.
  This differs from **Ctrl+S**, which saves the composed, rendered scene.

Cancelled dialogs and failed loads retain the previous source. Freeze/Save are
disabled for a disconnected webcam; retry or choose another source first.
This static workflow provides reproducible input for greenscreen calibration.

### Greenscreen removal

1. Load **Hand example**, freeze a live frame, or select your webcam.
2. Expand **Input / greenscreen** and enable **Remove greenscreen**. It is off by
   default, so existing opaque desktop/webcam behavior remains unchanged.
3. Select **Alpha mask** under **Preview** to calibrate: white is retained,
   black is removed, and gray is a partially transparent edge. **Original source**
   shows the framed/mirrored/zoomed image without keying, lensing, sky, or overlays.
4. Return to **Composed scene** to see the keyed subject over the sky. Dual view
   shows the keyed original on the left and the lensed result on the right.

The default key color is green-cyan (`#00ff80`), suitable for the supplied cloth:
**Hue tolerance** 30 degrees, **Edge softness** 12 degrees,
**Minimum saturation** 20%, and **Spill suppression** 50%.
Click **Key color** to choose a different saturated color. Keying matches hue,
including darker/lighter versions of the cloth; black, gray, and low-saturation
pixels are protected. This is chroma keying, not semantic subject segmentation:
subject colors matching the selected screen can also be removed.

- Increase **Hue tolerance** to remove more color variation; decrease it if
  subject colors disappear. **Edge softness** blends the next hue band rather
  than blurring the image spatially.
- Raise **Minimum saturation** to protect more neutral/skin pixels; lower it if
  washed-out cloth remains. **Spill suppression** reduces excess key-channel
  color near the selected hue without changing the mask.
- **Input framing** offers Fit/Fill for all sources. **Source default** retains
  the static Fit/Fill choice, center-crops webcams, and leaves desktop framing
  unchanged. With keying enabled, Fit margins are transparent.
- **Mirror** can override source defaults. Loaded photos/desktop are unmirrored;
  live or frozen webcam input is mirrored by default. Color and mask always use
  identical framing and mirroring.
- **Input zoom** center-crops the input **before lensing**, independently of
  Source size. **100%** is unchanged, **200%** keeps the central half of each
  input axis, and **400%** keeps the central quarter. It ranges from 100-400%,
  keeps the canvas dimensions unchanged, and applies when the slider is released.
  The sky and lens maps do not zoom. Color and alpha use the same crop.
- The **Input / greenscreen reset icon** restores keying, framing/mirroring,
  zoom, and preview settings from `data/defaults.ini`, without changing the
  source or lens/sky settings.

Only foreground color and alpha pass through lensing; the sky stays unchanged.
Forward keyed interpolation uses premultiplied color and linear sampling to
avoid colored/dark halos. Inverse reconstruction averages premultiplied color
and alpha with the same sample counts; unsampled/masked areas reveal the sky.
Clearing the sky gives a black backdrop. Lens light, curves, and markers remain
visible over removed areas. Marker placement is available in Composed scene,
not the calibration previews.

**Ctrl+S** exports the displayed scene or selected diagnostic preview.
Sequences likewise export the selected view; use Composed scene for lensed
sequences. **Save input...** always preserves unprocessed native pixels.
Static keying/framing is cached until input/settings/canvas dimensions change.
Live frames are keyed at native resolution; high-resolution webcams and large
canvases can be CPU-heavy, and the timer's 30 Hz target is not a guaranteed rate.
Actual camera lighting, shadows, hair edges, and spill should be tuned using
the mask preview on your setup.

### Printable A4 PDF

1. Use the default **Hand example**, load a static image, or click **Freeze webcam**
   when a webcam is connected. Lens and greenscreen controls remain adjustable;
   a frozen input does not lock the UI.
2. Configure the foreground, input zoom/mirroring, lens, optional Cross/Cusp/Fold
   placement, sky and post-lens source placement as desired.
3. Turn off **De-lensing**. Open **Print / export** and select **Export A4 PDF...**
   or press **Ctrl+P** to save a PDF, or select **Print A4...** to choose a printer
   and print directly.

The exporter creates one **portrait A4 page**, with German headings and
explanations, the MPE and Minerva logos beside the title, and a compact
bottom-right box containing the model and montage settings. Sky credits and
licensing information remain in the bottom-left footer. It follows the
five-panel layout of the earlier composition:

1. Original native photograph, without cropping, mirroring or greenscreen removal.
2. Foreground after the current keying, input crop/framing and mirroring.
   A checkerboard indicates transparency; disabled keying is explicitly noted.
3. Positioned source with the **caustic in the source plane**.
4. Lensed foreground with the **critical curve in the image plane**.
5. Foreground montage over the **currently selected sky**, defaulting to Abell 2764.

The two curve types are deliberately shown in their respective planes rather
than treated as the same physical coordinates. Diagnostic panels always include
the curves; the montage follows the GUI's curve and marker settings, and always
includes the softened lens-light glow regardless of the GUI toggle. That toggle
continues to control the lensed diagnostic panel. Dual view and Source/Mask
preview selection do not determine the PDF layout.

Export captures detached copies of the frozen pixels, sky and current settings
before opening the save dialog. It re-renders the model at print resolution
(300 dpi page layout), rather than enlarging the displayed pixmap. Text and
diagnostic curves are vector elements. The original image retains its native
pixels; export cannot recover detail absent from a low-resolution input.

The montage is a wide panel. **Fit/Fill** applies to that panel's aspect ratio,
so its sky crop can differ from the square live preview. The lens field remains
square and undistorted within it. Source size still scales the rendered layer;
offsets remain percentages of the destination panel width/height.
The model lens is illustrative and is not inferred from the galaxy-cluster
photograph. The sky never passes through lensing.

Small source settings can produce very small printed copies; increase Input size
and/or post-lens Source size in the GUI if desired. Larger sources can instead
merge into arcs; relevant source-size warnings appear on the page.
Invalid or fully removed foregrounds report an error instead of exporting a
stale scene. Cancellation leaves the existing output alone, and successful PDFs
replace the target atomically. Controls pause briefly while rendering and recover
after success or failure; the timer's previous running/stopped state is retained.

Bundled Euclid images include their source, credits and **CC BY-SA 3.0 IGO**
license on the page. Retain these when distributing a montage. For a custom sky,
the exporter identifies the filename and reminds you to check its rights; it
cannot infer the owner's credit or license automatically.

For a saved PDF, print on A4 at **actual size / 100%** in your PDF viewer. The
**Print A4...** button opens the system printer dialog and sends the same page
directly to the selected printer.

### Regression checks

The focused checks use the existing environment and Python's standard-library
test runner; no additional test dependency is needed:

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
.\.venv-qt5\Scripts\python.exe -m unittest discover -s tests -v
Remove-Item Env:QT_QPA_PLATFORM
```

These checks use synthetic desktop frames and simulated cameras, including
failed opens, disconnects, slow drivers, cancellation, and resource cleanup.
Actual webcams, Windows permissions, native keyboard focus appearance, and
display scaling should also be checked on the target laptop.

**Current A4 verification:** 21 targeted checks passed, including snapshot
ownership, export guards, atomic failures, packaged resources and a keyed
GUI-versus-print comparison. A native Windows hand-image PDF was generated and
inspected for its single A4 page, German text/credits, seven embedded images
(including both header logos), print-resolution raster sizes and page bounds.

**Open verification:** The latest full run executed 157 tests: 155 passed and
two failed because the keying mock still targeted its former location and the
shortcut expectation omitted the new Ctrl+P action. Those expectations have
been updated, but the full suite has not been rerun. An additional frozen-webcam
print-snapshot test also awaits execution. Further testing was stopped at the
user's request; no final all-green claim is made.

Remaining work includes a physical print check, packaged Windows executable
smoke test, final live-camera/performance checks, and the already deferred
125% presentation-mode one-pixel edge case. Screenshots/sequences still export
detached pixmap copies rather than the new formal print-scene snapshot.

# Lens Desktop

This Python Tool is a Desktop Lens. When executed it will record the screen below it 
and either lens it or de-lens it according to an softened SIE model.

The slider parameters are:

Mask Radius : Radius of a mask for the inverse mode (to cut away lens light that is close to the center).
Position Angle : Position angle that allows to change the orientation of the lens mass profile.
Core Radius : Softening scale / core radius of the power law mass profile.
Axis Ratio : Minor-to-Major axis ratio of the mass profile.
Einstein Radius : Einstein Radius of the mass profile.

You can use the following shortcuts:

- Ctrl+S : To Save the currently shown screen (without the GUI printed on top of it).
- Ctrl+P : To export a German five-panel A4 PDF from a frozen/static input in forward mode.
- Ctrl+F : To switch between desktop capture and the selected webcam, or reveal camera controls if none is selected.
- Ctrl+R : To Save a sequence of images in which the Einstein radius increases up
         to its current value (this allows to create nice gifs, e.g. using ffmpeg to postprocess the images).
- Ctrl+V : To turn some of the GUI elements on/off.

Use Rightclick to add / remove an RBG circle. This can be used to show Parity of images, magnification and sheer, and conjugate points.
Notice that it matters on which side of the dual view you click when creating this RBG circle, since this will decide the where the circle is anchored to.

I used ChatGPT o4/o3 to deal with the GUI elements of this Code and to help me figure out how to include the Camera recording and minor things.
If you have any suggestions for how to improve anything or if you want new features to be added, just drop me a message!

The Code in its current form shows some unexpected behaviour for multiple screens when you are not in the main screen.
I plan on fixing this in future versions!

Copyright (c) 2025, Wolfgang Enzi
