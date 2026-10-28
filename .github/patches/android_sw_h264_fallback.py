#!/usr/bin/env python3
"""
rdgen Android software H.26x MediaCodec encoder fallback patch.

Applied by .github/workflows/generator-android.yml when the "Android encoder
fallback" option is set to "Software H.264 (MediaCodec)".

Problem
-------
On Android, RustDesk encodes the screen of the *controlled* device (the
"server" side) with a MediaCodec encoder, wrapped by ffmpeg
(`h264_mediacodec` / `hevc_mediacodec`). The list of usable encoders is
collected in two places:

  1. flutter/android/app/src/main/kotlin/com/carriez/flutter_hbb/MainActivity.kt
     `setCodecInfo()` drops every codec that is not a *hardware* codec
     (`if (hw != true) return@forEach`).
  2. libs/scrap/src/common/hwcodec.rs `HwCodecConfig::get()` keeps only the
     codecs flagged as hardware (`c.hw == Some(true) //only use hardware codec`).

On a device without a hardware H.264/H.265 encoder both filters remove every
candidate, so `ram_encode` ends up empty, `h264_useable` / `h265_useable` are
false and `scrap::codec` silently falls back to the bundled *software* VP8
encoder (libvpx). Encoding 1080p VP8 in software on a 32 bit ARM CPU is very
expensive, so the encoder cannot keep up, the frame rate drops and the
picture the user sees is blurry. The same device is perfectly capable of
encoding H.264 with the software MediaCodec codec `OMX.google.h264.encoder`
(that is exactly what scrcpy uses on such boxes).

Note that `hw` is only reported by the platform since API 29. On older
releases (e.g. Android 9 / API 28) RustDesk guesses from the codec name and
marks every `OMX.google.*` / `OMX.SEC.*` / `c2.android.*` codec as software,
so those devices never get a hardware encoder listed at all.

What it changes
---------------
  1. MainActivity.kt keeps the software codecs in the codec info and reports
     them with `hw=false` instead of dropping them.
  2. MainActivity.kt also tests the unaligned screen size when it checks
     whether an encoder can handle the capture resolution. The aligned size
     (1920x1088) can be slightly larger than what a codec advertises
     (1920x1080), which would reject an otherwise usable encoder.
  3. libs/scrap/src/common/hwcodec.rs prefers a hardware MediaCodec encoder
     exactly like upstream, but falls back to a software one when the device
     has no hardware H.26x encoder at all. The software fallback is limited
     to H.264: software H.265 encoding is far too slow for the low end
     devices this fallback targets.

When a hardware H.26x encoder exists, the selected encoder is exactly the
same as upstream, so the patch is a no-op for those devices.

The script performs targeted text replacements on the RustDesk sources so that
it keeps working across patch releases (1.4.x and master share the same code
shape for the touched blocks). It is idempotent: running it twice is a
no-op, and it exits non-zero with a clear message when a target block cannot be
found, so a build never silently ships the wrong encoder behaviour.

Usage: python3 android_sw_h264_fallback.py [rustdesk_source_root]
"""

import os
import sys

FILES = {
    'main_activity': os.path.join(
        'flutter', 'android', 'app', 'src', 'main', 'kotlin', 'com', 'carriez',
        'flutter_hbb', 'MainActivity.kt'),
    'hwcodec': os.path.join('libs', 'scrap', 'src', 'common', 'hwcodec.rs'),
}

# (file key, description, original block, patched block)
PATCHES = [
    # ------------------------------------------- Kotlin: keep software codecs
    (
        'main_activity',
        'MainActivity.kt -> report software MediaCodec encoders instead of dropping them',
        """            if (hw != true) {
                return@forEach
            }
            codecObject.put("hw", hw)
""",
        """            // rdgen: keep software MediaCodec encoders (e.g.
            // OMX.google.h264.encoder) in the codec info and report them with
            // hw=false instead of dropping them here. The Rust side prefers a
            // hardware encoder but falls back to a software one when the
            // device has no hardware H.26x encoder at all. Upstream drops
            // them, so RustDesk silently falls back to the much heavier
            // software VP8 encoder and the remote picture turns blurry.
            codecObject.put("hw", hw ?: false)
""",
    ),
    # ------------------------------------------ Kotlin: keep the raw screen size
    (
        'main_activity',
        'MainActivity.kt -> keep the unaligned screen size for the codec check',
        """        var w = wh.first
        var h = wh.second
        val align = 64
        w = (w + align - 1) / align * align
        h = (h + align - 1) / align * align
""",
        """        var w = wh.first
        var h = wh.second
        // rdgen: keep the unaligned screen size. It is used below to test the
        // encoder capabilities: the aligned size (e.g. 1920x1088) can be
        // slightly larger than what a codec advertises (1920x1080), which
        // would wrongly reject an otherwise usable encoder.
        val rawW = w
        val rawH = h
        val align = 64
        w = (w + align - 1) / align * align
        h = (h + align - 1) / align * align
""",
    ),
    # ------------------------------------- Kotlin: encoder size capability test
    (
        'main_activity',
        'MainActivity.kt -> also test the unaligned size for the encoder',
        """                if (codec.isEncoder) {
                    // Encoder's max_height and max_width are interchangeable
                    if (!caps.videoCapabilities.isSizeSupported(w,h) && !caps.videoCapabilities.isSizeSupported(h,w)) {
                        return@forEach
                    }
                }
""",
        """                if (codec.isEncoder) {
                    // Encoder's max_height and max_width are interchangeable
                    // rdgen: also test the unaligned screen size, see rawW/rawH
                    // above.
                    if (!caps.videoCapabilities.isSizeSupported(w,h) && !caps.videoCapabilities.isSizeSupported(h,w)
                        && !caps.videoCapabilities.isSizeSupported(rawW,rawH) && !caps.videoCapabilities.isSizeSupported(rawH,rawW)) {
                        return@forEach
                    }
                }
""",
    ),
    # ------------------------------------------- Rust: software H.264 fallback
    (
        'hwcodec',
        'hwcodec.rs -> fall back to a software H.264 MediaCodec encoder',
        """                ts.iter().for_each(|t| {
                    let codecs: Vec<_> = info
                        .codecs
                        .iter()
                        .filter(|c| {
                            c.is_encoder
                                && c.mime_type.as_str() == get_mime_type(t.data_format)
                                && c.nv12
                                && c.hw == Some(true) //only use hardware codec
                        })
                        .collect();
""",
        """                ts.iter().for_each(|t| {
                    // rdgen: prefer a hardware MediaCodec encoder, but fall back
                    // to a software one (e.g. OMX.google.h264.encoder) when the
                    // device does not have any hardware H.26x encoder at all.
                    // Upstream drops the software encoders, so on such devices
                    // RustDesk silently falls back to the much heavier software
                    // VP8 encoder and the remote picture turns blurry.
                    // The software fallback is limited to H.264: software H.265
                    // encoding is far too slow for the low end devices this
                    // fallback targets.
                    let matching: Vec<_> = info
                        .codecs
                        .iter()
                        .filter(|c| {
                            c.is_encoder
                                && c.mime_type.as_str() == get_mime_type(t.data_format)
                                && c.nv12
                        })
                        .collect();
                    let hardware: Vec<_> = matching
                        .iter()
                        .filter(|c| c.hw == Some(true))
                        .copied()
                        .collect();
                    let codecs: Vec<_> = if hardware.is_empty() && t.name_prefix == "h264" {
                        matching
                    } else {
                        hardware
                    };
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

    applied = 0
    already = 0
    failed = []

    for key, desc, old, new in PATCHES:
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
