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
Camera selection, sky backgrounds, greenscreen processing, and A4 export are
future phases described in [PLAN.md](PLAN.md); this UI update does not add them.

### UI regression checks

The focused checks use the existing environment and Python's standard-library
test runner; no additional test dependency is needed:

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
.\.venv-qt5\Scripts\python.exe -m unittest discover -s tests -v
Remove-Item Env:QT_QPA_PLATFORM
```

These checks use synthetic desktop frames. Actual desktop capture, native
keyboard focus appearance, and display scaling should also be checked on the
target laptop.

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
- Ctrl+F : To turn the device camera on/off for recording.
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
