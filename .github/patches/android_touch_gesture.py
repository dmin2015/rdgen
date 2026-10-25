#!/usr/bin/env python3
"""
rdgen Android touch-mode gesture patch.

Applied by .github/workflows/generator-android.yml when the "Android touch mode
gestures" option is set to "One-finger canvas pan / hold gestures / two-finger
vertical wheel".

What it changes (only the mobile client, only in "Touch mode"):

  1. One-finger move  -> moves the canvas (pan) instead of dragging the remote
     mouse with the left button held down.
  2. One-finger hold  -> holding the finger still for 200 ms arms mouse-drag
     mode: the left button is pressed on the next movement and released when
     the finger is lifted. Holding still for 600 ms sends a right click at the
     finger position instead (no left button is pressed in that case).
  3. Two-finger vertical swipe -> mouse wheel (scroll).
     Two-finger horizontal swipe -> canvas pan (unchanged behaviour).
     Pinch -> canvas zoom (unchanged behaviour).
  4. The upstream long-press handling is neutralised while the rdgen hold
     gesture is armed, so the right click is not sent twice and the left
     button is not pressed twice.
  5. The gesture help panel is updated so the labels match the new behaviour.

Desktop / web-desktop touch input and mouse mode keep the upstream behaviour.

The script performs targeted text replacements on the RustDesk flutter sources
so that it keeps working across patch releases (1.4.x and master share the same
code shape for the touched blocks). It is idempotent: running it twice is a
no-op, and it exits non-zero with a clear message when a target block cannot be
found, so a build never silently ships the wrong gesture behaviour.

Usage: python3 android_touch_gesture.py [rustdesk_source_root]
"""

import os
import sys

FILES = {
    'remote_input': os.path.join('flutter', 'lib', 'common', 'widgets',
                                 'remote_input.dart'),
    'gesture_help': os.path.join('flutter', 'lib', 'mobile', 'widgets',
                                 'gesture_help.dart'),
}

IMPORT_DESC = 'import dart:async for the hold timers'

# (file key, description, original block, patched block)
PATCHES = [
    # --------------------------------------------------------------- imports
    (
        'remote_input',
        IMPORT_DESC,
        """import 'dart:math';
""",
        """import 'dart:async';
import 'dart:math';
""",
    ),
    # ----------------------------------------------------------------- state
    (
        'remote_input',
        'hold gesture state fields',
        """  bool _touchModePanStarted = false;
  Offset _doubleFinerTapPosition = Offset.zero;
""",
        """  bool _touchModePanStarted = false;
  // rdgen: one-finger hold gestures in touch mode (mobile only).
  Timer? _rdgenHoldDragTimer;
  Timer? _rdgenHoldRightTimer;
  bool _rdgenHoldDragging = false;
  bool _rdgenHoldRightSent = false;
  bool _rdgenHoldLeftDown = false;
  Offset _rdgenHoldPosition = Offset.zero;
  Offset _doubleFinerTapPosition = Offset.zero;
""",
    ),
    # ------------------------------------------------------------- onTapDown
    (
        'remote_input',
        'onTapDown -> arm the hold timers',
        """    if (handleTouch) {
      _lastPosOfDoubleTapDown = d.localPosition;
      // Desktop or mobile "Touch mode"
      _lastTapDownDetails = d;
    } else {
""",
        """    if (handleTouch) {
      _lastPosOfDoubleTapDown = d.localPosition;
      // Desktop or mobile "Touch mode"
      _lastTapDownDetails = d;
      // rdgen: arm the one-finger hold timers. Holding the finger still for
      // 200 ms arms mouse-drag mode, 600 ms sends a right click.
      _rdgenArmHold(d.localPosition);
    } else {
""",
    ),
    # --------------------------------------------------------------- onTapUp
    (
        'remote_input',
        'onTapUp -> end the hold gesture',
        """    if (handleTouch) {
      final isMoved =
          await ffi.cursorModel.move(d.localPosition.dx, d.localPosition.dy);
""",
        """    if (handleTouch) {
      // rdgen: the finger was lifted, so the hold gesture is over. If a
      // hold-drag had pressed the left button, only release it here; the
      // click below must not fire a second time.
      _rdgenCancelHoldTimers();
      if (_rdgenHoldLeftDown) {
        await _rdgenReleaseHoldButton();
        _rdgenHoldReset();
        return;
      }
      _rdgenHoldReset();
      final isMoved =
          await ffi.cursorModel.move(d.localPosition.dx, d.localPosition.dy);
""",
    ),
    # --------------------------------------------------- onOneFingerPanStart
    (
        'remote_input',
        'one-finger pan start -> canvas pan',
        """      _touchModePanStarted = true;
      if (isDesktop || isWebDesktop) {
        ffi.cursorModel.trySetRemoteWindowCoords();
      }
""",
        """      _touchModePanStarted = true;
      // rdgen: one-finger movement pans the canvas on mobile. Holding the
      // finger still for 200 ms switches to mouse-drag mode and 600 ms sends
      // a right click (see the _rdgenHold* helpers below), so the left
      // button is pressed lazily by onOneFingerPanUpdate instead of here.
      if (!(isDesktop || isWebDesktop)) {
        _rdgenCancelHoldTimers();
        return;
      }
      if (isDesktop || isWebDesktop) {
        ffi.cursorModel.trySetRemoteWindowCoords();
      }
""",
    ),
    # --------------------------------------------------- onOneFingerPanUpdate
    (
        'remote_input',
        'one-finger pan update -> canvas pan or hold-drag',
        """    if (handleTouch && !_touchModePanStarted) {
      return;
    }
    // In relative mouse mode, send delta directly without position tracking.
    if (inputModel.relativeMouseMode.value) {
      await inputModel.sendMobileRelativeMouseMove(d.delta.dx, d.delta.dy);
    } else {
      await ffi.cursorModel.updatePan(d.delta, d.localPosition, handleTouch);
    }
""",
        """    if (handleTouch && !_touchModePanStarted) {
      return;
    }
    // rdgen: mobile touch mode. Movement pans the canvas, unless the 200 ms
    // hold timer already armed mouse-drag mode, in which case the normal
    // drag handling below runs with the left button held. After the 600 ms
    // right click the rest of the gesture is ignored.
    if (handleTouch && !(isDesktop || isWebDesktop)) {
      // Moving the finger ends the "held still" condition.
      _rdgenCancelHoldTimers();
      if (_rdgenHoldRightSent) {
        return;
      }
      if (_rdgenHoldDragging) {
        if (!_rdgenHoldLeftDown) {
          // Warp the cursor to the finger and hold the left button, like a
          // normal drag start.
          await ffi.cursorModel.move(d.localPosition.dx, d.localPosition.dy);
          await inputModel.sendMouse('down', MouseButtons.left);
          _rdgenHoldLeftDown = true;
        }
        // fall through to the drag handling below
      } else {
        if (inputModel.relativeMouseMode.value) {
          await inputModel.sendMobileRelativeMouseMove(d.delta.dx, d.delta.dy);
        } else {
          ffi.canvasModel.panX(d.delta.dx);
          ffi.canvasModel.panY(d.delta.dy);
        }
        return;
      }
    }
    // In relative mouse mode, send delta directly without position tracking.
    if (inputModel.relativeMouseMode.value) {
      await inputModel.sendMobileRelativeMouseMove(d.delta.dx, d.delta.dy);
    } else {
      await ffi.cursorModel.updatePan(d.delta, d.localPosition, handleTouch);
    }
""",
    ),
    # ----------------------------------------------------- onOneFingerPanEnd
    (
        'remote_input',
        'one-finger pan end -> release the hold-drag button',
        """    if (handleTouch) {
      // In relative mouse mode, skip mouse up - matches the skipped mouse down in onOneFingerPanStart
      if (!inputModel.relativeMouseMode.value) {
        await inputModel.sendMouse('up', MouseButtons.left);
      }
    }
""",
        """    if (handleTouch) {
      // rdgen: a one-finger canvas pan never pressed a mouse button; only a
      // hold-drag did, and that button must be released here.
      if (!(isDesktop || isWebDesktop)) {
        _rdgenCancelHoldTimers();
        await _rdgenReleaseHoldButton();
        _rdgenHoldReset();
        return;
      }
      // In relative mouse mode, skip mouse up - matches the skipped mouse down in onOneFingerPanStart
      if (!inputModel.relativeMouseMode.value) {
        await inputModel.sendMouse('up', MouseButtons.left);
      }
    }
""",
    ),
    # -------------------------------------------------- onOneFingerPanCancel
    (
        'remote_input',
        'one-finger pan cancel -> drop the hold gesture',
        """  onOneFingerPanCancel() {
    _touchModePanStarted = false;
  }
""",
        """  onOneFingerPanCancel() {
    _touchModePanStarted = false;
    // rdgen: the gesture was rejected, so drop the hold state. Release the
    // button in case a hold-drag was in progress (fire and forget, this
    // callback is synchronous).
    _rdgenCancelHoldTimers();
    _rdgenReleaseHoldButton();
    _rdgenHoldReset();
  }
""",
    ),
    # -------------------------------------------------- onTwoFingerScaleStart
    (
        'remote_input',
        'two-finger scale start -> cancel the hold gesture',
        """  onTwoFingerScaleStart(ScaleStartDetails d) {
    _lastTapDownDetails = null;
    if (isNotTouchBasedDevice()) {
      return;
    }
""",
        """  onTwoFingerScaleStart(ScaleStartDetails d) {
    _lastTapDownDetails = null;
    // rdgen: a second finger cancels the one-finger hold gesture. Release
    // the button in case a hold-drag was in progress (fire and forget).
    _rdgenCancelHoldTimers();
    _rdgenReleaseHoldButton();
    _rdgenHoldReset();
    if (isNotTouchBasedDevice()) {
      return;
    }
""",
    ),
    # -------------------------------------------------- onTwoFingerScaleUpdate
    (
        'remote_input',
        'two-finger gesture -> vertical swipe is the mouse wheel',
        """    } else {
      // mobile
      ffi.canvasModel.updateScale(d.scale / _scale, d.focalPoint);
      _scale = d.scale;
      ffi.canvasModel.panX(d.focalPointDelta.dx);
      ffi.canvasModel.panY(d.focalPointDelta.dy);
    }
""",
        """    } else {
      // mobile
      // rdgen: two-finger vertical swipe = mouse wheel, two-finger horizontal
      // swipe = canvas pan, pinch = canvas zoom.
      final rdgenScaleRatio = d.scale / _scale;
      final rdgenPanDelta = d.focalPointDelta;
      _scale = d.scale;
      final rdgenIsPinch =
          rdgenScaleRatio > 1.06 || rdgenScaleRatio < 0.94;
      if (!rdgenIsPinch && rdgenPanDelta.dy.abs() > rdgenPanDelta.dx.abs()) {
        _mouseScrollIntegral += rdgenPanDelta.dy / 6.0;
        if (_mouseScrollIntegral >= 1) {
          inputModel.scroll(1);
          _mouseScrollIntegral = 0;
        } else if (_mouseScrollIntegral <= -1) {
          inputModel.scroll(-1);
          _mouseScrollIntegral = 0;
        }
      } else {
        ffi.canvasModel.updateScale(rdgenScaleRatio, d.focalPoint);
        ffi.canvasModel.panX(rdgenPanDelta.dx);
        ffi.canvasModel.panY(rdgenPanDelta.dy);
      }
    }
""",
    ),
    # --------------------------------------------------------- onLongPressDown
    (
        'remote_input',
        'onLongPressDown -> do not press the left button twice',
        """      if (ffiModel.isPeerMobile) {
        await ffi.cursorModel
            .move(_cacheLongPressPosition.dx, _cacheLongPressPosition.dy);
        await inputModel.tapDown(MouseButtons.left);
      }
""",
        """      if (ffiModel.isPeerMobile) {
        await ffi.cursorModel
            .move(_cacheLongPressPosition.dx, _cacheLongPressPosition.dy);
        // rdgen: the one-finger hold gesture owns the left button while it is
        // armed, so don't press it again here.
        if (!_rdgenHoldDragging) {
          await inputModel.tapDown(MouseButtons.left);
        }
      }
""",
    ),
    # ------------------------------------------------------------- onLongPress
    (
        'remote_input',
        'onLongPress -> the 600 ms timer owns the right click',
        """  onLongPress() async {
    if (isNotTouchBasedDevice()) {
      return;
    }
    if (!ffi.ffiModel.isPeerMobile) {
""",
        """  onLongPress() async {
    if (isNotTouchBasedDevice()) {
      return;
    }
    // rdgen: while the one-finger hold gesture is armed, the right click is
    // sent by the 600 ms hold timer instead, to avoid a double right click.
    if (handleTouch && _rdgenHoldDragging) {
      return;
    }
    if (!ffi.ffiModel.isPeerMobile) {
""",
    ),
    # ------------------------------------------------------- helper methods
    (
        'remote_input',
        'hold gesture helpers',
        """        };

  makeGestures(BuildContext context) {
""",
        """        };

  // rdgen: one-finger hold gestures for touch mode (mobile only).
  //
  // Quick tap = left click (onTapUp/onTap), moving finger = canvas pan
  // (onOneFingerPanUpdate). Holding the finger still for 200 ms arms
  // mouse-drag mode: the left button is pressed by the first movement after
  // that and released when the finger is lifted. Holding it still for 600 ms
  // sends a right click at the finger position instead.
  void _rdgenArmHold(Offset position) {
    _rdgenCancelHoldTimers();
    _rdgenHoldReset();
    _rdgenHoldPosition = position;
    _rdgenHoldDragTimer =
        Timer(const Duration(milliseconds: 200), _rdgenHoldDragFire);
    _rdgenHoldRightTimer =
        Timer(const Duration(milliseconds: 600), _rdgenHoldRightFire);
  }

  void _rdgenCancelHoldTimers() {
    _rdgenHoldDragTimer?.cancel();
    _rdgenHoldDragTimer = null;
    _rdgenHoldRightTimer?.cancel();
    _rdgenHoldRightTimer = null;
  }

  void _rdgenHoldReset() {
    _rdgenHoldDragging = false;
    _rdgenHoldRightSent = false;
    _rdgenHoldLeftDown = false;
  }

  Future<void> _rdgenReleaseHoldButton() async {
    if (_rdgenHoldLeftDown) {
      _rdgenHoldLeftDown = false;
      await inputModel.sendMouse('up', MouseButtons.left);
    }
  }

  Future<void> _rdgenHoldDragFire() async {
    if (!mounted) {
      return;
    }
    _rdgenHoldDragTimer = null;
    // Drag mode armed. The left button is pressed by the first pan update,
    // so that a hold followed by a plain lift stays a single click.
    _rdgenHoldDragging = true;
  }

  Future<void> _rdgenHoldRightFire() async {
    if (!mounted) {
      return;
    }
    _rdgenHoldRightTimer = null;
    _rdgenHoldRightSent = true;
    // Release a pressed drag button first so no button stays stuck down.
    await _rdgenReleaseHoldButton();
    // Right click at the finger position, like the upstream long press.
    await ffi.cursorModel.move(_rdgenHoldPosition.dx, _rdgenHoldPosition.dy);
    await inputModel.tap(MouseButtons.right);
  }

  makeGestures(BuildContext context) {
""",
    ),
    # ---------------------------------------------------------- gesture_help
    (
        'gesture_help',
        'gesture help labels',
        """                          GestureInfo(
                              width,
                              GestureIcons.iconGesturePressHold,
                              translate("One-Long Tap"),
                              translate("Right Mouse")),
                          GestureInfo(
                              width,
                              GestureIcons.iconGestureFSwipeRight,
                              translate("One-Finger Move"),
                              translate("Mouse Drag")),
                          GestureInfo(
                              width,
                              GestureIcons.iconGestureFThreeFingers,
                              translate("Three-Finger vertically"),
                              translate("Mouse Wheel")),
""",
        """                          GestureInfo(
                              width,
                              GestureIcons.iconGestureFSwipeRight,
                              translate("One-Finger Move"),
                              translate("Canvas Move")),
                          GestureInfo(
                              width,
                              GestureIcons.iconGesturePressHold,
                              translate("Hold 0.2s"),
                              translate("Mouse Drag")),
                          GestureInfo(
                              width,
                              GestureIcons.iconGesturePressHold,
                              translate("Hold 0.6s"),
                              translate("Right Mouse")),
                          GestureInfo(
                              width,
                              GestureIcons.iconGestureFThreeFingers,
                              translate("Three-Finger vertically"),
                              translate("Mouse Wheel")),
""",
    ),
]


def read_text(path):
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


def write_text(path, text):
    with open(path, 'w', encoding='utf-8', newline='') as f:
        f.write(text)


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else '.'
    contents = {}
    for key, rel in FILES.items():
        path = os.path.join(root, rel)
        if not os.path.isfile(path):
            print('ERROR: %s not found (looked in %s)' % (rel, path))
            print('       Run this script from the RustDesk source root, or pass')
            print('       the source root as the first argument.')
            return 2
        contents[key] = read_text(path)

    patches = list(PATCHES)
    # A newer upstream file may already import dart:async somewhere else;
    # adding it again would only produce a duplicate-import warning.
    if "import 'dart:async';" in contents['remote_input']:
        patches = [p for p in patches if p[1] != IMPORT_DESC]

    applied = 0
    already = 0
    failed = []

    for key, desc, old, new in patches:
        text = contents[key]
        if new in text:
            print('SKIP    %-55s already patched' % desc)
            already += 1
            continue
        if old not in text:
            failed.append(desc)
            print('FAIL    %-55s target block not found' % desc)
            continue
        if text.count(old) != 1:
            failed.append(desc)
            print('FAIL    %-55s target block is not unique (%d matches)'
                  % (desc, text.count(old)))
            continue
        contents[key] = text.replace(old, new, 1)
        applied += 1
        print('OK      %s' % desc)

    for key, rel in FILES.items():
        if contents[key] != read_text(os.path.join(root, rel)):
            if not failed:
                write_text(os.path.join(root, rel), contents[key])
                print('WROTE   %s' % rel)

    print('')
    print('%d patch(es) applied, %d already present, %d failed.'
          % (applied, already, len(failed)))
    if failed:
        print('No file was modified. The RustDesk source does not match any')
        print('known layout for:')
        for key, desc, old, new in PATCHES:
            if desc in failed:
                print('  - %s (%s)' % (desc, FILES[key]))
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
