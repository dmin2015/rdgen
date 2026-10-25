#!/usr/bin/env python3
"""Local self-test for android_touch_gesture.py (no network needed).

The Dart fixtures below are verbatim copies of the relevant parts of
rustdesk/rustdesk (flutter/lib/common/widgets/remote_input.dart and
flutter/lib/mobile/widgets/gesture_help.dart):

  REMOTE_INPUT_149   tag 1.4.9   (SHA 5871033dbb61a10076dab57a06876fdcb3cf422a)
  REMOTE_INPUT_MASTER head master (SHA 1e2daac5db0359dbb54432f8a333ae95050b5582)
  GESTURE_HELP       tag 1.4.9 and master are identical
                               (SHA 8e86681b4b6de494f16e691a6107458da5711d97)

Only the parts of the files that the patch anchors on are included; every
anchor block in android_touch_gesture.py must appear verbatim here, so a green
run means the anchors exist in the real upstream sources.
"""
import os
import shutil
import subprocess
import sys
import tempfile

PATCH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..',
                     '.github', 'patches', 'android_touch_gesture.py')
PATCH = os.path.abspath(PATCH)

REMOTE_INPUT_149 = '''import 'dart:convert';
import 'dart:math';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter/gestures.dart';

import 'package:flutter_hbb/models/platform_model.dart';
import 'package:flutter_hbb/common.dart';
import 'package:flutter_hbb/consts.dart';
import 'package:flutter_hbb/models/model.dart';
import 'package:flutter_hbb/models/input_model.dart';

import './gestures.dart';

// For virtual mouse when using the mouse mode on mobile.
// Special hold-drag mode: one finger holds a button (left/right button), another finger pans.
// This flag is to override the scale gesture to a pan gesture.
bool isSpecialHoldDragActive = false;
// Cache the last focal point to calculate deltas in special hold-drag mode.
Offset _lastSpecialHoldDragFocalPoint = Offset.zero;

class RawTouchGestureDetectorRegion extends StatefulWidget {
  final Widget child;
  final FFI ffi;
  final bool isCamera;
  late final InputModel inputModel = ffi.inputModel;
  late final FfiModel ffiModel = ffi.ffiModel;

  RawTouchGestureDetectorRegion({
    required this.child,
    required this.ffi,
    this.isCamera = false,
  });

  @override
  State<RawTouchGestureDetectorRegion> createState() =>
      _RawTouchGestureDetectorRegionState();
}

/// touchMode only:
///   LongPress -> right click
///   OneFingerPan -> start/end -> left down start/end
///   onDoubleTapDown -> move to
///   onLongPressDown => move to
///
/// mouseMode only:
///   DoubleFiner -> right click
///   HoldDrag -> left drag
class _RawTouchGestureDetectorRegionState
    extends State<RawTouchGestureDetectorRegion> {
  Offset _cacheLongPressPosition = Offset(0, 0);
  // Timestamp of the last long press event.
  int _cacheLongPressPositionTs = 0;
  double _mouseScrollIntegral = 0; // mouse scroll speed controller
  double _scale = 1;

  // Workaround tap down event when two fingers are used to scale(mobile)
  TapDownDetails? _lastTapDownDetails;

  PointerDeviceKind? lastDeviceKind;

  // For touch mode, onDoubleTap
  // `onDoubleTap()` does not provide the position of the tap event.
  Offset _lastPosOfDoubleTapDown = Offset.zero;
  bool _touchModePanStarted = false;
  Offset _doubleFinerTapPosition = Offset.zero;

  // For mouse mode, we need to block the events when the cursor is in a blocked area.
  // So we need to cache the last tap down position.
  Offset? _lastTapDownPositionForMouseMode;
  // Cache global position for onTap (which lacks position info).
  Offset? _lastTapDownGlobalPosition;

  FFI get ffi => widget.ffi;
  FfiModel get ffiModel => widget.ffiModel;
  InputModel get inputModel => widget.inputModel;
  bool get handleTouch => (isDesktop || isWebDesktop) || ffiModel.touchMode;
  SessionID get sessionId => ffi.sessionId;

  @override
  Widget build(BuildContext context) {
    return RawGestureDetector(
      child: widget.child,
      gestures: makeGestures(context),
    );
  }

  bool isNotTouchBasedDevice() {
    return !kTouchBasedDeviceKinds.contains(lastDeviceKind);
  }

  // Mobile, mouse mode.
  // Check if should block the mouse tap event (`_lastTapDownPositionForMouseMode`).
  bool shouldBlockMouseModeEvent() {
    return _lastTapDownPositionForMouseMode != null &&
        ffi.cursorModel.shouldBlock(_lastTapDownPositionForMouseMode!.dx,
            _lastTapDownPositionForMouseMode!.dy);
  }

  onTapDown(TapDownDetails d) async {
    lastDeviceKind = d.kind;
    _lastTapDownGlobalPosition = d.globalPosition;
    if (isNotTouchBasedDevice()) {
      return;
    }
    if (handleTouch) {
      _lastPosOfDoubleTapDown = d.localPosition;
      // Desktop or mobile "Touch mode"
      _lastTapDownDetails = d;
    } else {
      _lastTapDownPositionForMouseMode = d.localPosition;
    }
  }

  onTapUp(TapUpDetails d) async {
    final TapDownDetails? lastTapDownDetails = _lastTapDownDetails;
    _lastTapDownDetails = null;
    if (isNotTouchBasedDevice()) {
      return;
    }
    // Filter duplicate touch tap events on iOS (Magic Mouse issue).
    if (inputModel.shouldIgnoreTouchTap(d.globalPosition)) {
      return;
    }
    if (handleTouch) {
      final isMoved =
          await ffi.cursorModel.move(d.localPosition.dx, d.localPosition.dy);
      if (isMoved) {
        // If pan already handled 'down', don't send it again.
        if (lastTapDownDetails != null && !_touchModePanStarted) {
          await inputModel.tapDown(MouseButtons.left);
        }
        await inputModel.tapUp(MouseButtons.left);
      }
    }
  }

  onTap() async {
    if (isNotTouchBasedDevice()) {
      return;
    }
    // Filter duplicate touch tap events on iOS (Magic Mouse issue).
    final lastPos = _lastTapDownGlobalPosition;
    if (lastPos != null && inputModel.shouldIgnoreTouchTap(lastPos)) {
      return;
    }
    if (!handleTouch) {
      // Cannot use `_lastTapDownDetails` because Flutter calls `onTapUp` before `onTap`, clearing the cached details.
      // Using `_lastTapDownPositionForMouseMode` instead.
      if (shouldBlockMouseModeEvent()) {
        return;
      }
      // Mobile, "Mouse mode"
      await inputModel.tap(MouseButtons.left);
    }
  }

  onDoubleTapDown(TapDownDetails d) async {
    lastDeviceKind = d.kind;
    if (isNotTouchBasedDevice()) {
      return;
    }
    if (handleTouch) {
      _lastPosOfDoubleTapDown = d.localPosition;
      await ffi.cursorModel.move(d.localPosition.dx, d.localPosition.dy);
    } else {
      _lastTapDownPositionForMouseMode = d.localPosition;
    }
  }

  onDoubleTap() async {
    if (isNotTouchBasedDevice()) {
      return;
    }
    if (ffiModel.touchMode && ffi.cursorModel.lastIsBlocked) {
      return;
    }
    if (handleTouch &&
        !ffi.cursorModel.isInRemoteRect(_lastPosOfDoubleTapDown)) {
      return;
    }
    // Check if the position is in a blocked area when using the mouse mode.
    if (!handleTouch) {
      if (shouldBlockMouseModeEvent()) {
        return;
      }
    }
    await inputModel.tap(MouseButtons.left);
    await inputModel.tap(MouseButtons.left);
  }

  onLongPressDown(LongPressDownDetails d) async {
    lastDeviceKind = d.kind;
    if (isNotTouchBasedDevice()) {
      return;
    }
    if (handleTouch) {
      _lastPosOfDoubleTapDown = d.localPosition;
      _cacheLongPressPosition = d.localPosition;
      if (!ffi.cursorModel.isInRemoteRect(d.localPosition)) {
        return;
      }
      _cacheLongPressPositionTs = DateTime.now().millisecondsSinceEpoch;
      if (ffiModel.isPeerMobile) {
        await ffi.cursorModel
            .move(_cacheLongPressPosition.dx, _cacheLongPressPosition.dy);
        await inputModel.tapDown(MouseButtons.left);
      }
    } else {
      _lastTapDownPositionForMouseMode = d.localPosition;
    }
  }

  onLongPressUp() async {
    if (isNotTouchBasedDevice()) {
      return;
    }
    if (handleTouch) {
      await inputModel.tapUp(MouseButtons.left);
    }
  }

  // for mobiles
  onLongPress() async {
    if (isNotTouchBasedDevice()) {
      return;
    }
    if (!ffi.ffiModel.isPeerMobile) {
      if (handleTouch) {
        final isMoved = await ffi.cursorModel
            .move(_cacheLongPressPosition.dx, _cacheLongPressPosition.dy);
        if (!isMoved) {
          return;
        }
      } else {
        if (shouldBlockMouseModeEvent()) {
          return;
        }
      }
      await inputModel.tap(MouseButtons.right);
    } else {
      // It's better to send a message to tell the controlled device that the long press event is triggered.
      // We're now using a `TimerTask` in `InputService.kt` to decide whether to trigger the long press event.
      // It's not accurate and it's better to use the same detection logic in the controlling side.
    }
  }

  onLongPressMoveUpdate(LongPressMoveUpdateDetails d) async {
    if (!ffiModel.isPeerMobile || isNotTouchBasedDevice()) {
      return;
    }
    if (handleTouch) {
      if (!ffi.cursorModel.isInRemoteRect(d.localPosition)) {
        return;
      }
      await ffi.cursorModel.move(d.localPosition.dx, d.localPosition.dy);
    }
  }

  onDoubleFinerTapDown(TapDownDetails d) async {
    lastDeviceKind = d.kind;
    if (isNotTouchBasedDevice()) {
      return;
    }
    _doubleFinerTapPosition = d.localPosition;
    // ignore for desktop and mobile
  }

  onDoubleFinerTap(TapDownDetails d) async {
    lastDeviceKind = d.kind;
    if (isNotTouchBasedDevice()) {
      return;
    }

    // mobile mouse mode or desktop touch screen
    final isMobileMouseMode = isMobile && !ffiModel.touchMode;
    // We can't use `d.localPosition` here because it's always (0, 0) on desktop.
    final isDesktopInRemoteRect = (isDesktop || isWebDesktop) &&
        ffi.cursorModel.isInRemoteRect(_doubleFinerTapPosition);
    if (isMobileMouseMode || isDesktopInRemoteRect) {
      await inputModel.tap(MouseButtons.right);
    }
  }

  onHoldDragStart(DragStartDetails d) async {
    lastDeviceKind = d.kind;
    if (isNotTouchBasedDevice()) {
      return;
    }
    if (!handleTouch) {
      if (isSpecialHoldDragActive) return;
      await inputModel.sendMouse('down', MouseButtons.left);
    }
  }

  onHoldDragUpdate(DragUpdateDetails d) async {
    if (isNotTouchBasedDevice()) {
      return;
    }
    if (!handleTouch) {
      if (isSpecialHoldDragActive) return;
      await ffi.cursorModel.updatePan(d.delta, d.localPosition, handleTouch);
    }
  }

  onHoldDragEnd(DragEndDetails d) async {
    if (isNotTouchBasedDevice()) {
      return;
    }
    if (!handleTouch) {
      await inputModel.sendMouse('up', MouseButtons.left);
    }
  }

  onOneFingerPanStart(BuildContext context, DragStartDetails d) async {
    final TapDownDetails? lastTapDownDetails = _lastTapDownDetails;
    _lastTapDownDetails = null;
    lastDeviceKind = d.kind ?? lastDeviceKind;
    if (isNotTouchBasedDevice()) {
      return;
    }
    if (handleTouch) {
      if (lastTapDownDetails != null) {
        await ffi.cursorModel.move(lastTapDownDetails.localPosition.dx,
            lastTapDownDetails.localPosition.dy);
      }
      if (ffi.cursorModel.shouldBlock(d.localPosition.dx, d.localPosition.dy)) {
        return;
      }
      if (!ffi.cursorModel.isInRemoteRect(d.localPosition)) {
        return;
      }

      _touchModePanStarted = true;
      if (isDesktop || isWebDesktop) {
        ffi.cursorModel.trySetRemoteWindowCoords();
      }

      // Workaround for the issue that the first pan event is sent a long time after the start event.
      // If the time interval between the start event and the first pan event is less than 500ms,
      // we consider to use the long press position as the start position.
      //
      // TODO: We should find a better way to send the first pan event as soon as possible.
      if (DateTime.now().millisecondsSinceEpoch - _cacheLongPressPositionTs <
          500) {
        await ffi.cursorModel
            .move(_cacheLongPressPosition.dx, _cacheLongPressPosition.dy);
      }
      // In relative mouse mode, skip mouse down - only send movement via sendMobileRelativeMouseMove
      if (!inputModel.relativeMouseMode.value) {
        await inputModel.sendMouse('down', MouseButtons.left);
      }
      await ffi.cursorModel.move(d.localPosition.dx, d.localPosition.dy);
    } else {
      final offset = ffi.cursorModel.offset;
      final cursorX = offset.dx;
      final cursorY = offset.dy;
      final visible =
          ffi.cursorModel.getVisibleRect().inflate(1); // extend edges
      final size = MediaQueryData.fromView(View.of(context)).size;
      if (!visible.contains(Offset(cursorX, cursorY))) {
        await ffi.cursorModel.move(size.width / 2, size.height / 2);
      }
    }
  }

  onOneFingerPanUpdate(DragUpdateDetails d) async {
    if (isNotTouchBasedDevice()) {
      return;
    }
    if (ffi.cursorModel.shouldBlock(d.localPosition.dx, d.localPosition.dy)) {
      return;
    }
    if (handleTouch && !_touchModePanStarted) {
      return;
    }
    // In relative mouse mode, send delta directly without position tracking.
    if (inputModel.relativeMouseMode.value) {
      await inputModel.sendMobileRelativeMouseMove(d.delta.dx, d.delta.dy);
    } else {
      await ffi.cursorModel.updatePan(d.delta, d.localPosition, handleTouch);
    }
  }

  onOneFingerPanEnd(DragEndDetails d) async {
    _touchModePanStarted = false;
    if (isNotTouchBasedDevice()) {
      return;
    }
    if (isDesktop || isWebDesktop) {
      ffi.cursorModel.clearRemoteWindowCoords();
    }
    if (handleTouch) {
      // In relative mouse mode, skip mouse up - matches the skipped mouse down in onOneFingerPanStart
      if (!inputModel.relativeMouseMode.value) {
        await inputModel.sendMouse('up', MouseButtons.left);
      }
    }
  }

  // Reset `_touchModePanStarted` if the one-finger pan gesture is cancelled
  // or rejected by the gesture arena. Without this, the flag can remain
  // stuck in the "started" state and cause issues such as the Magic Mouse
  // double-click problem on iPad with magic mouse.
  onOneFingerPanCancel() {
    _touchModePanStarted = false;
  }

  // scale + pan event
  onTwoFingerScaleStart(ScaleStartDetails d) {
    _lastTapDownDetails = null;
    if (isNotTouchBasedDevice()) {
      return;
    }
    if (isSpecialHoldDragActive) {
      // Initialize the last focal point to calculate deltas manually.
      _lastSpecialHoldDragFocalPoint = d.focalPoint;
    }
  }

  onTwoFingerScaleUpdate(ScaleUpdateDetails d) async {
    if (isNotTouchBasedDevice()) {
      return;
    }

    // If in special drag mode, perform a pan instead of a scale.
    if (isSpecialHoldDragActive) {
      // Calculate delta manually to avoid the jumpy behavior.
      final delta = d.focalPoint - _lastSpecialHoldDragFocalPoint;
      _lastSpecialHoldDragFocalPoint = d.focalPoint;
      await ffi.cursorModel.updatePan(delta * 2.0, d.focalPoint, handleTouch);
      return;
    }

    if ((isDesktop || isWebDesktop)) {
      final scale = ((d.scale - _scale) * 1000).toInt();
      _scale = d.scale;

      if (scale != 0) {
        if (widget.isCamera) return;
        await bind.sessionSendPointer(
            sessionId: sessionId,
            msg: json.encode(
                PointerEventToRust(kPointerEventKindTouch, 'scale', scale)
                    .toJson()));
      }
    } else {
      // mobile
      ffi.canvasModel.updateScale(d.scale / _scale, d.focalPoint);
      _scale = d.scale;
      ffi.canvasModel.panX(d.focalPointDelta.dx);
      ffi.canvasModel.panY(d.focalPointDelta.dy);
    }
  }

  onTwoFingerScaleEnd(ScaleEndDetails d) async {
    if (isNotTouchBasedDevice()) {
      return;
    }
    if ((isDesktop || isWebDesktop)) {
      if (widget.isCamera) return;
      await bind.sessionSendPointer(
          sessionId: sessionId,
          msg: json.encode(
              PointerEventToRust(kPointerEventKindTouch, 'scale', 0)
                  .toJson()));
    } else {
      // mobile
      _scale = 1;
      // No idea why we need to set the view style to "" here.
      // bind.sessionSetViewStyle(sessionId: sessionId, value: "");
    }
    if (!isSpecialHoldDragActive) {
      await inputModel.sendMouse('up', MouseButtons.left);
    }
  }

  get onHoldDragCancel => null;
  get onThreeFingerVerticalDragUpdate => ffi.ffiModel.isPeerAndroid
      ? null
      : (d) {
          _mouseScrollIntegral += d.delta.dy / 4;
          if (_mouseScrollIntegral > 1) {
            inputModel.scroll(1);
            _mouseScrollIntegral = 0;
          } else if (_mouseScrollIntegral < -1) {
            inputModel.scroll(-1);
            _mouseScrollIntegral = 0;
          }
        };

  makeGestures(BuildContext context) {
    return <Type, GestureRecognizerFactory>{
      // Official
      TapGestureRecognizer:
          GestureRecognizerFactoryWithHandlers<TapGestureRecognizer>(
              () => TapGestureRecognizer(), (instance) {
        instance
          ..onTapDown = onTapDown
          ..onTapUp = onTapUp
          ..onTap = onTap;
      }),
      DoubleTapGestureRecognizer:
          GestureRecognizerFactoryWithHandlers<DoubleTapGestureRecognizer>(
              () => DoubleTapGestureRecognizer(), (instance) {
        instance
          ..onDoubleTapDown = onDoubleTapDown
          ..onDoubleTap = onDoubleTap;
      }),
      LongPressGestureRecognizer:
          GestureRecognizerFactoryWithHandlers<LongPressGestureRecognizer>(
              () => LongPressGestureRecognizer(), (instance) {
        instance
          ..onLongPressDown = onLongPressDown
          ..onLongPressUp = onLongPressUp
          ..onLongPress = onLongPress
          ..onLongPressMoveUpdate = onLongPressMoveUpdate;
      }),
      // Customized
      HoldTapMoveGestureRecognizer:
          GestureRecognizerFactoryWithHandlers<HoldTapMoveGestureRecognizer>(
              () => HoldTapMoveGestureRecognizer(),
              (instance) => instance
                ..onHoldDragStart = onHoldDragStart
                ..onHoldDragUpdate = onHoldDragUpdate
                ..onHoldDragCancel = onHoldDragCancel
                ..onHoldDragEnd = onHoldDragEnd),
      DoubleFinerTapGestureRecognizer:
          GestureRecognizerFactoryWithHandlers<DoubleFinerTapGestureRecognizer>(
              () => DoubleFinerTapGestureRecognizer(), (instance) {
        instance
          ..onDoubleFinerTap = onDoubleFinerTap
          ..onDoubleFinerTapDown = onDoubleFinerTapDown;
      }),
      CustomTouchGestureRecognizer:
          GestureRecognizerFactoryWithHandlers<CustomTouchGestureRecognizer>(
              () => CustomTouchGestureRecognizer(), (instance) {
        instance.onOneFingerPanStart =
            (DragStartDetails d) => onOneFingerPanStart(context, d);
        instance
          ..onOneFingerPanUpdate = onOneFingerPanUpdate
          ..onOneFingerPanEnd = onOneFingerPanEnd
          ..onOneFingerPanCancel = onOneFingerPanCancel
          ..onTwoFingerScaleStart = onTwoFingerScaleStart
          ..onTwoFingerScaleUpdate = onTwoFingerScaleUpdate
          ..onTwoFingerScaleEnd = onTwoFingerScaleEnd
          ..onThreeFingerVerticalDragUpdate = onThreeFingerVerticalDragUpdate;
      }),
    };
  }
}
'''

# master adds the canvasLocked getter and one guard line in the scale update.
REMOTE_INPUT_MASTER = REMOTE_INPUT_149.replace(
    """  SessionID get sessionId => ffi.sessionId;
""",
    """  SessionID get sessionId => ffi.sessionId;
  bool get canvasLocked => isMobile && ffi.canvasModel.locked;
""").replace(
    """      return;
    }

    if ((isDesktop || isWebDesktop)) {
""",
    """      return;
    }

    if (canvasLocked) return;

    if ((isDesktop || isWebDesktop)) {
""")

GESTURE_HELP = '''class _GestureHelpState extends State<GestureHelp> {
  @override
  Widget build(BuildContext context) {
    return Container(
        child: Wrap(
      spacing: space,
      runSpacing: 2 * space,
      children: _touchMode
          ? [
                          GestureInfo(
                              width,
                              GestureIcons.iconMobileTouch,
                              translate("One-Finger Tap"),
                              translate("Left Mouse")),
                          GestureInfo(
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
                          GestureInfo(
                              width,
                              GestureIcons.iconGestureFDrag,
                              translate("Two-Finger Move"),
                              translate("Canvas Move")),
                          GestureInfo(
                              width,
                              GestureIcons.iconGesturePinch,
                              translate("Pinch to Zoom"),
                              translate("Canvas Zoom")),
            ]
          : [
                          GestureInfo(
                              width,
                              GestureIcons.iconMobileTouch,
                              translate("One-Finger Tap"),
                              translate("Left Mouse")),
                          GestureInfo(
                              width,
                              GestureIcons.iconGesturePressHold,
                              translate("One-Long Tap"),
                              translate("Right Mouse")),
                          GestureInfo(
                              width,
                              GestureIcons.iconGestureFSwipeRight,
                              translate("Double Tap & Move"),
                              translate("Mouse Drag")),
                          GestureInfo(
                              width,
                              GestureIcons.iconGestureFThreeFingers,
                              translate("Three-Finger vertically"),
                              translate("Mouse Wheel")),
                          GestureInfo(
                              width,
                              GestureIcons.iconGestureFDrag,
                              translate("Two-Finger Move"),
                              translate("Canvas Move")),
                          GestureInfo(
                              width,
                              GestureIcons.iconGesturePinch,
                              translate("Pinch to Zoom"),
                              translate("Canvas Zoom")),
            ],
    ));
  }
}
'''

NEEDLES_149 = [
    "import 'dart:async';",
    'Timer? _rdgenHoldDragTimer;',
    '_rdgenArmHold(d.localPosition);',
    'Timer(const Duration(milliseconds: 200), _rdgenHoldDragFire);',
    'Timer(const Duration(milliseconds: 600), _rdgenHoldRightFire);',
    '_rdgenHoldDragging = true;',
    'await inputModel.tap(MouseButtons.right);',
    'ffi.canvasModel.panX(d.delta.dx);',
    'rdgenIsPinch',
    'translate("Hold 0.2s")',
    'translate("Hold 0.6s")',
    'translate("Canvas Move")',
]


def remote_input_path(root):
    return os.path.join(root, 'flutter', 'lib', 'common', 'widgets',
                        'remote_input.dart')


def gesture_help_path(root):
    return os.path.join(root, 'flutter', 'lib', 'mobile', 'widgets',
                        'gesture_help.dart')


def make_tree(root, remote_input, gesture_help):
    d = os.path.join(root, 'flutter', 'lib', 'common', 'widgets')
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, 'remote_input.dart'), 'w',
              encoding='utf-8') as f:
        f.write(remote_input)
    d = os.path.join(root, 'flutter', 'lib', 'mobile', 'widgets')
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, 'gesture_help.dart'), 'w',
              encoding='utf-8') as f:
        f.write(gesture_help)


def run(root):
    return subprocess.run([sys.executable, PATCH, root],
                          capture_output=True, text=True)


def read(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


def main():
    failures = []

    def check(cond, message):
        if not cond:
            failures.append(message)

    # 1. 1.4.9 layout
    tmp = tempfile.mkdtemp(prefix='rdgen_test_149_')
    make_tree(tmp, REMOTE_INPUT_149, GESTURE_HELP)
    r = run(tmp)
    print('--- 1.4.9 layout ---')
    print(r.stdout.strip())
    check(r.returncode == 0, '1.4.9 patch returned %d' % r.returncode)
    out = read(remote_input_path(tmp))
    gh = read(gesture_help_path(tmp))
    for needle in NEEDLES_149:
        check(needle in out or needle in gh,
              '1.4.9 output missing %r' % needle)
    # the mouse-mode branch and the upstream mouse-mode long press stay intact
    check('translate("Double Tap & Move")' in gh,
          '1.4.9 mouse-mode help row was modified')
    check('translate("One-Long Tap")' in gh,
          '1.4.9 mouse-mode long-tap row was modified')
    check('translate("One-Long Tap")' not in out,
          '1.4.9 touch-mode long-tap row should be replaced')
    # relative mouse mode keeps its own movement path (2 new + 1 upstream)
    check(out.count('sendMobileRelativeMouseMove') == 3,
          'relative mouse mode path count changed: %d'
          % out.count('sendMobileRelativeMouseMove'))
    # desktop touch input is untouched
    check('ffi.cursorModel.trySetRemoteWindowCoords();' in out,
          'desktop pan start was modified')
    check(out.count("await inputModel.sendMouse('up', MouseButtons.left);")
          >= 2, 'hold release paths missing')
    # 2. idempotency
    r2 = run(tmp)
    check(r2.returncode == 0 and 'already patched' in r2.stdout,
          'idempotency broken: rc=%d out=%s' % (r2.returncode, r2.stdout))
    check(read(remote_input_path(tmp)) == out,
          'second run changed remote_input.dart')
    shutil.rmtree(tmp)

    # 3. master layout
    tmp = tempfile.mkdtemp(prefix='rdgen_test_master_')
    make_tree(tmp, REMOTE_INPUT_MASTER, GESTURE_HELP)
    r = run(tmp)
    print('--- master layout ---')
    print(r.stdout.strip())
    check(r.returncode == 0, 'master patch returned %d' % r.returncode)
    out = read(remote_input_path(tmp))
    check('canvasLocked' in out and '_rdgenArmHold' in out,
          'master layout did not get both changes')
    shutil.rmtree(tmp)

    # 4. dart:async already imported somewhere else
    tmp = tempfile.mkdtemp(prefix='rdgen_test_async_')
    make_tree(tmp, "import 'dart:async';\n" + REMOTE_INPUT_149,
              GESTURE_HELP)
    r = run(tmp)
    print('--- dart:async already imported ---')
    print(r.stdout.strip())
    check(r.returncode == 0, 'pre-imported dart:async run returned %d'
          % r.returncode)
    out = read(remote_input_path(tmp))
    check(out.count("import 'dart:async';") == 1,
          'duplicate dart:async import: %d' % out.count(
              "import 'dart:async';"))
    check('_rdgenArmHold' in out, 'other patches skipped unexpectedly')
    shutil.rmtree(tmp)

    # 5. unknown layout must fail loudly and write nothing
    tmp = tempfile.mkdtemp(prefix='rdgen_test_bad_')
    broken_input = REMOTE_INPUT_149.replace(
        'ffi.canvasModel.updateScale(d.scale / _scale, d.focalPoint);',
        'canvasModel.updateScale(d.scale / _scale, d.focalPoint);')
    broken_help = GESTURE_HELP.replace('translate("One-Finger Move")',
                                       'translate("Move")')
    make_tree(tmp, broken_input, broken_help)
    before_input = read(remote_input_path(tmp))
    r = run(tmp)
    print('--- unknown layout ---')
    print(r.stdout.strip())
    check(r.returncode != 0, 'unknown layout should fail')
    check('target block not found' in r.stdout,
          'unknown layout should report the missing block')
    check(read(remote_input_path(tmp)) == before_input,
          'failed run modified remote_input.dart')
    shutil.rmtree(tmp)

    # 6. missing file
    tmp = tempfile.mkdtemp(prefix='rdgen_test_missing_')
    r = run(tmp)
    print('--- missing source ---')
    print((r.stdout + r.stderr).strip())
    check(r.returncode != 0, 'missing file should fail')
    shutil.rmtree(tmp)

    print('')
    if failures:
        print('FAILED:')
        for f in failures:
            print('  - %s' % f)
        return 1
    print('ALL CHECKS PASSED')
    return 0


if __name__ == '__main__':
    sys.exit(main())
