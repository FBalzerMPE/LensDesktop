# Remaining Feature Work

This plan covers follow-up work for the current Lens Desktop application. It
does not propose changes to the A4 montage's curve behavior: the final montage
intentionally omits the critical curve, even when it is enabled in the GUI.

## 1. Use scene snapshots for screenshots and sequences

Update `save_screenshot()` and `recording()` in `LensDesktop/app.py` to use the
detached scene data in `LensDesktop/scene.py` instead of copying the displayed
pixmap. Preserve the intended preview behavior, report save failures, and
restore lens and render state after sequence export, including on errors.

## 2. Finish regression checks

- Resolve the outstanding `test_zoom_is_applied_to_opaque_live_input_before_lensing`
  test error.
- Run the full test suite and confirm it passes.
- Exercise the desktop, webcam, and static-image paths, including camera
  failure/disconnect, greenscreen, single/dual view, forward/inverse modes, and
  PDF export.

## 3. Check performance on Windows

Measure live capture and rendering on the target Windows machine at
representative canvas sizes. Record the results and address significant
regressions; if the 30 Hz target is not practical, document the observed limits.

## 4. Validate the Windows package

Build with `LensDesktop.spec` and smoke-test the packaged app, including its
bundled defaults and image resources.

## 5. Complete hands-on checks

- Verify webcam selection, freeze/resume, disconnect handling, and greenscreen
  tuning with the actual camera and subject.
- Print a PDF on A4 at 100% and check legibility, color, and margins.
- Check presentation mode and screen capture across monitors and display scales,
  including the known one-pixel work-area overshoot at 125% Windows scaling.
