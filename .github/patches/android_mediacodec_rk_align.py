#!/usr/bin/env python3
"""
rdgen Android ffmpeg patch: stop aligning the frame size of the Rockchip
MediaCodec encoder.

Problem
-------
With 0013 applied the Rockchip encoder configures fine, RustDesk creates
`HWRAM(h264_mediacodec, OMX.rk.video_encoder.avc, 1366x768)` and
`check_change_scale()` reports `hardware: true` - so the full resolution is
kept and the picture should be sharp. It is not, because every frame fails a
moment later:

    ERROR log2_max_pic_order_cnt_lsb_minus4 out of range: 13, but must be in [0,12].
    ERROR Failed to read unit 0 (type 7).
    ERROR Failed to read access unit from packet.
    ERROR [FFMPEG_RAM_ENC] avcodec_send_frame failed, ret = Invalid data found

RustDesk then retries with VP8 (`new encoder: VPX(... codec: VP8)`),
`is_hardware()` becomes false, `half_scale` turns true and the capture drops to
683x384 - the blurry picture the user sees.

Root cause
----------
The screen is 1366x768. `res/vcpkg/ffmpeg/patch/0011-android-mediacodec-encode-align-64.patch`
aligns the frame size to 64, so ffmpeg configures MediaCodec with 1408x768:

    s->width  = FFALIGN(1366, 64) = 1408
    s->height = FFALIGN(768,  64) = 768

`mediacodec_init_bsf()` then sees a non zero crop and installs the
`h264_metadata` bitstream filter to crop the picture back to 1366:

    int crop_right  = s->width  - avctx->width;   // 1408 - 1366 = 42
    int crop_bottom = s->height - avctx->height;  // 0
    if (!crop_right && !crop_bottom && !s->extract_extradata)
        return 0;                                  // no filter at all
    ...
    "h264_metadata=crop_right=42:crop_bottom=0"

That filter has to *parse and rewrite* the SPS. The SPS the Rockchip encoder
emits carries `log2_max_pic_order_cnt_lsb_minus4 = 13`, while the H.264
specification and the ffmpeg parser only accept 0..12, so
`ff_h264_decode_seq_parameter_set()` aborts the parse, the filter drops every
packet and `avcodec_send_frame()` returns AVERROR_INVALIDDATA.

Note that `hwcodec` sets `AV_CODEC_FLAG2_LOCAL_HEADER`, not
`AV_CODEC_FLAG_GLOBAL_HEADER`, so `s->extract_extradata` is always false. If the
crop is zero, `mediacodec_init_bsf()` returns before building any filter, the
SPS is never parsed by ffmpeg and the encoder output is passed through
untouched.

What it changes
---------------
The Rockchip encoder accepts the exact frame size (a MediaCodec probe encoded
1366x768 successfully), so the alignment is pointless for it. The patch keeps
the 64 alignment for every other encoder and uses 2 (the YUV420 minimum) for
`OMX.rk.*` / `c2.rk.*`, which makes crop_right and crop_bottom zero:

    int align = 64;
    if (s->name && (av_strstart(s->name, "OMX.rk.", NULL) ||
                    av_strstart(s->name, "c2.rk.", NULL)))
        align = 2;

This script copies

    0014-android-mediacodec-rk-skip-align.patch

into the RustDesk source tree at

    res/vcpkg/ffmpeg/patch/0014-android-mediacodec-rk-skip-align.patch

and registers it in the PATCHES list of `res/vcpkg/ffmpeg/portfile.cmake`
right after 0013, so the patches are applied in the right order. The patch is
a pure increment on top of 0011 and 0013.

Both the registration and the copy are validated before anything is written,
so a source tree with an unexpected layout is left untouched.
"""

import os
import shutil
import subprocess
import sys

FFMPEG_DIR = os.path.join('res', 'vcpkg', 'ffmpeg')
PORTFILE = os.path.join(FFMPEG_DIR, 'portfile.cmake')
PATCH_DIR = os.path.join(FFMPEG_DIR, 'patch')
PATCH_NAME = '0014-android-mediacodec-rk-skip-align.patch'
PATCH_PATH = os.path.join(PATCH_DIR, PATCH_NAME)

# 0014 is a pure increment on top of 0013, so it has to be applied after it.
PREVIOUS_PATCH_NAME = '0013-android-mediacodec-skip-profile.patch'
PORTFILE_ANCHOR = '    patch/' + PREVIOUS_PATCH_NAME + '\n'
PORTFILE_NEW = '    patch/' + PATCH_NAME + '\n'

# Fallback when 0013 is not registered (the option that installs 0013 also
# installs this patch, so this should not happen, but a clear failure is
# better than a wrong order).
FALLBACK_ANCHOR = '    patch/0012-fix-macos-big-sur-CVBufferCopyAttachments.patch\n'


def find_source_patch():
    """Locate the ffmpeg patch next to this script."""
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(here, PATCH_NAME),
        os.path.join(here, 'ffmpeg', PATCH_NAME),
    ]
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    return None


def read_text(path):
    with open(path, 'r', encoding='utf-8', newline='') as f:
        return f.read()


def write_text(path, text):
    with open(path, 'w', encoding='utf-8', newline='') as f:
        f.write(text)


def try_git_apply_check(root, patch_file):
    """Best effort check that the patch applies to the source tree.

    The RustDesk tree only contains the ffmpeg *port*, not the ffmpeg sources,
    so the check is only run when the sources happen to be available.
    """
    src = os.path.join(root, 'libavcodec', 'mediacodecenc.c')
    if not os.path.isfile(src):
        return None
    try:
        proc = subprocess.run(
            ['git', 'apply', '--check', patch_file],
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
    except OSError:
        return None
    return proc.returncode == 0


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else '.'

    portfile_path = os.path.join(root, PORTFILE)
    patch_dir_path = os.path.join(root, PATCH_DIR)
    patch_path = os.path.join(root, PATCH_PATH)

    if not os.path.isfile(portfile_path):
        print('ERROR: %s not found (looked in %s)' % (PORTFILE, portfile_path))
        print('       Run this script from the RustDesk source root, or pass')
        print('       the source root as the first argument.')
        return 2

    if not os.path.isdir(patch_dir_path):
        print('ERROR: %s not found (looked in %s)' % (PATCH_DIR, patch_dir_path))
        return 2

    source_patch = find_source_patch()
    if source_patch is None:
        print('ERROR: the ffmpeg patch %s was not found next to this script.'
              % PATCH_NAME)
        print('       It has to be shipped together with')
        print('       android_mediacodec_rk_align.py.')
        return 2

    applied = 0
    already = 0
    failed = []

    # The registration is validated before anything is written, so an
    # unexpected layout leaves the tree completely untouched.
    portfile = read_text(portfile_path)
    need_registration = PORTFILE_NEW not in portfile
    anchor = PORTFILE_ANCHOR
    if not need_registration:
        print('SKIP    %-55s already registered' % 'portfile.cmake')
        already += 1
    else:
        if anchor not in portfile:
            print('WARN    %-55s 0013 is not registered, using the 0012 anchor'
                  % 'portfile.cmake')
            anchor = FALLBACK_ANCHOR
        if anchor not in portfile:
            print('FAIL    %-55s the expected anchor line is missing'
                  % 'portfile.cmake')
            failed.append('portfile.cmake')
        elif portfile.count(anchor) != 1:
            print('FAIL    %-55s the anchor line is not unique (%d matches)'
                  % ('portfile.cmake', portfile.count(anchor)))
            failed.append('portfile.cmake')

    if failed:
        print('')
        print('%d change(s) applied, %d already present, %d failed.'
              % (applied, already, len(failed)))
        print('The RustDesk source does not match the expected layout, so the')
        print('ffmpeg Rockchip alignment fix was NOT installed. The Rockchip')
        print('encoder would keep failing on the crop filter and the remote')
        print('picture would stay blurry.')
        return 1

    # 1) the ffmpeg patch file itself
    if os.path.isfile(patch_path):
        existing = read_text(patch_path)
        wanted = read_text(source_patch)
        if existing == wanted:
            print('SKIP    %-55s already present' % PATCH_NAME)
            already += 1
        else:
            print('FAIL    %-55s the file exists with a different content'
                  % PATCH_NAME)
            failed.append(PATCH_NAME)
    else:
        shutil.copyfile(source_patch, patch_path)
        print('OK      %-55s copied from %s'
              % (PATCH_NAME, os.path.basename(source_patch)))
        applied += 1

    # 2) its registration in the portfile, after 0013
    if need_registration:
        portfile = portfile.replace(anchor, anchor + PORTFILE_NEW, 1)
        write_text(portfile_path, portfile)
        print('OK      %-55s registered after %s'
              % ('portfile.cmake', os.path.basename(anchor).strip()))
        applied += 1

    # 3) optional sanity check when the ffmpeg sources are at hand
    check = try_git_apply_check(root, source_patch)
    if check is True:
        print('OK      %-55s git apply --check passed'
              % 'ffmpeg patch sanity check')
    elif check is False:
        print('FAIL    %-55s git apply --check failed'
              % 'ffmpeg patch sanity check')
        failed.append('ffmpeg patch sanity check')

    print('')
    print('%d change(s) applied, %d already present, %d failed.'
          % (applied, already, len(failed)))
    if failed:
        print('The RustDesk source does not match the expected layout, so the')
        print('ffmpeg Rockchip alignment fix was NOT installed.')
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
