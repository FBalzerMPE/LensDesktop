# Lens Desktop

![A tool to lens what is shown on your Desktop!](example.png)

# Important Disclaimer

This tool uses screen / camera recording to map images in (almost) real time to a lensed/delensed image.

In order for the tool to apply to other windows you will need to give it the rights for screen / camera recording. I, therefore, recommend to use pyinstaller to create an ".app" file first. Once you have that you can give these rights to the app rather than the terminal (the latter might being a security concern). Your computer might close the app before you can give permission for those recordings, but you usually just have to restart it when that happens.

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
The panel uses native Qt controls and scrolls when the window is short.
Mask Radius is shown only in De-lensing mode.

The image remains square (two squares in Dual view) and fits in the available
canvas area. Extra space is left around it instead of stretching the image.
Drag the image to move the window; right-click the image to add or remove a
marker. Clicking the settings panel does not place markers.

Ctrl+V hides or restores the panel and toggles the window frame for presentation.
Settings are retained. Screenshots export the image, not the settings panel.
Greenscreen controls are described below. A4 export remains a future phase
described in [PLAN.md](PLAN.md).

### Sky background and source placement

The bundled [Euclid example](data/euclid_patch_example.jpg) loads by default.
Its source, credits, and license are in [data/README.md](data/README.md); retain
the required attribution/license when sharing images that use it.

In **Sky background**:

- **Load...** selects a local PNG/JPEG, including non-ASCII Windows filenames.
  A failed load leaves the last valid sky in place; cancelling does nothing.
- **Clear** removes the sky and uses a black backdrop. **Default** restores the
  bundled Euclid image.
- **Fill** preserves aspect ratio and crops the center to fill the canvas.
  **Fit** preserves the whole sky image and adds black margins.
- **Source size** scales the rendered source from 10% to 200% of a panel.
  **Horizontal offset** and **Vertical offset** shift it by a percentage of the
  panel width/height (positive values move right/down).
- **Reset source placement** restores size 100% and zero offsets.

Placement is applied **after lensing**, including the source's curves/markers
and optional lens-light overlay. It does not move the lens relative to the input,
recompute the lens maps, or lens the sky. In Dual view, the same placement and
unchanged sky are used in both panels. Screenshots and sequences export the
composed scene, without controls.

The sky is decoded once and its fitted version is cached. At the default 100%
source size, an opaque webcam/desktop image may cover most of it; try 50-60% to
see the sky around the source. The webcam's own background remains opaque unless **Remove greenscreen** is
enabled. Black subject pixels are not treated as transparency.

### Selecting a webcam

The application starts with **Desktop** capture and does not open or probe any
camera until you request it.

1. In the **Source** group, click **Refresh** to check camera indices 0 through 4.
2. Choose a discovered **Camera N**, then choose **Webcam** as the input source.
3. Alternatively, enter an index (0-99) and click **Use index / retry** to open it
   directly. Index 0 commonly refers to the integrated webcam; external cameras
   may use another index. These indices are not stable device names.
4. Choose **Desktop** to return to screen capture. **Ctrl+F** toggles between the
   desktop and the selected webcam; without a selection, it reveals the camera
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
- **Freeze input** captures the current desktop region or webcam frame and
  switches to **Static image**. Webcam freezing releases the camera and retains
  its mirrored, center-cropped preview. The stored pixels remain unmirrored.
- Static mode stops live acquisition, not rendering: lens parameters, view
  modes, sky selection, and source size/position remain adjustable.
- Select **Desktop** or **Webcam** to resume live input. Selecting **Static image**
  again restores the last loaded/frozen input; if none exists, a file picker opens.
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
2. In **Greenscreen / input**, enable **Remove greenscreen**. It is off by
   default, so existing opaque desktop/webcam behavior remains unchanged.
3. Select **Alpha mask** under **Preview** to calibrate: white is retained,
   black is removed, and gray is a partially transparent edge. **Original source**
   shows the framed/mirrored image without keying, lensing, sky, or overlays.
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
- **Reset input settings** disables keying, restores the above key defaults,
  source-default framing/mirroring and Composed scene preview. It retains the
  source and lens/sky settings, restoring Fit for loaded photos and Fill for
  frozen input.

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
