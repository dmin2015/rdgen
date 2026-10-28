#!/usr/bin/env python3
"""
rdgen Android ffmpeg patch: stop the MediaCodec encoders that refuse an
explicit profile from failing configure().

Problem
-------
RustDesk encodes the screen of the *controlled* device (the "server" side)
with a MediaCodec encoder wrapped by ffmpeg (`h264_mediacodec`).

The `hwcodec` crate hardcodes the H.264 profile in
`cpp/common/util.cpp`:

    if (name.find("h264") != std::string::npos) {
        c->profile = FF_PROFILE_H264_HIGH;
    }

ffmpeg turns that into a "profile" key in the MediaFormat
(`libavcodec/mediacodecenc.c`):

    ret = ff_AMediaCodecProfile_getProfileFromAVCodecContext(avctx);
    if (ret > 0) {
        ff_AMediaFormat_setInt32(format, "profile", ret);
    }

Some MediaCodec encoders refuse to be configured when the format carries an
explicit profile. The Rockchip AVC encoder (`OMX.rk.video_encoder.avc`) used
by the very common RK3566 boxes rejects *every* profile value and fails the
whole configure() call with `OMX_ErrorBadParameter` (-38), which surfaces as
`MediaCodec$CodecException: Error 0x80001001`.

Measured on such a device with a MediaCodec probe:

    OMX.rk.video_encoder.avc  1366x768  color=21  flags=1  profile unset   -> configure OK, encodes
    OMX.rk.video_encoder.avc  1366x768  color=21  flags=1  profile=1/2/4/8/16/4096 -> configure FAIL
    c2.android.avc.encoder    1366x768  color=21  flags=1  any profile     -> configure OK

When the hardware encoder cannot be created RustDesk gives up on H.26x
completely: `Encoder::new()` clears the hardware codec config, the negotiated
format falls back to VP8/VP9, and because the VPx encoder reports
`is_hardware() == false` the capture resolution is halved
(`check_change_scale()` -> `half_scale = true`). The user then sees a blurry
picture encoded with VP8.

The profile and the level are only *hints* for the encoder: when they are
absent, the encoder picks its own defaults. The probe above confirms that the
Rockchip encoder produces real H.264 frames (SPS/PPS included) at 1366x768 and
at the 64-aligned 1408x768 when no profile is set.

What it changes
---------------
This script copies the ffmpeg patch

    0013-android-mediacodec-skip-profile.patch

from this script's own directory into the RustDesk source tree at

    res/vcpkg/ffmpeg/patch/0013-android-mediacodec-skip-profile.patch

and registers it in

    res/vcpkg/ffmpeg/portfile.cmake

The patch makes ffmpeg skip the "profile" and "level" keys for the MediaCodec
encoders that are known to refuse them (the Rockchip ones). Every other
encoder keeps the current behaviour, so the change is a no-op on the devices
that already work.

RustDesk builds ffmpeg from source for Android through vcpkg
(`flutter/build_android_deps.sh` -> `vcpkg install`, with `./res/vcpkg` as an
overlay port), so the patch is really applied to the ffmpeg that ends up in
the APK.

The patch is kept as a separate file instead of being embedded in this
script so that its bytes are exactly the ones that were verified with
`git apply --check`; embedding it in a Python string literal would risk
mangling the diff format and break the ffmpeg build.

The script is idempotent: running it twice is a no-op. It exits non-zero with
a clear message when the expected files cannot be found or when the portfile
does not have the expected layout, so a build never silently ships a client
without the fix.

Usage: python3 android_mediacodec_skip_profile.py [rustdesk_source_root]
"""

import os
import shutil
import subprocess
import sys

FFMPEG_DIR = os.path.join('res', 'vcpkg', 'ffmpeg')
PORTFILE = os.path.join(FFMPEG_DIR, 'portfile.cmake')
PATCH_DIR = os.path.join(FFMPEG_DIR, 'patch')
PATCH_NAME = '0013-android-mediacodec-skip-profile.patch'
PATCH_PATH = os.path.join(PATCH_DIR, PATCH_NAME)

# The line that registers the previous patch in the PATCHES list of the
# portfile. The new patch has to be added right after it so that the patches
# are applied in the order they are listed.
PORTFILE_ANCHOR = '    patch/0012-fix-macos-big-sur-CVBufferCopyAttachments.patch\n'
PORTFILE_NEW = '    patch/' + PATCH_NAME + '\n'


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
    """Best effort check that the patch still applies to the source tree.

    The RustDesk tree only contains the ffmpeg *port*, not the ffmpeg sources
    themselves, so the patch cannot really be applied here. The check is only
    run when the ffmpeg sources happen to be available next to the port.
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
        print('ERROR: the ffmpeg patch %s was not found next to this script.' % PATCH_NAME)
        print('       It has to be shipped together with')
        print('       android_mediacodec_skip_profile.py.')
        return 2

    applied = 0
    already = 0
    failed = []

    # 2) its registration in the portfile
    #
    # The portfile is checked *before* anything is written, so a source tree
    # with an unexpected layout is left completely untouched.
    portfile = read_text(portfile_path)
    need_registration = PORTFILE_NEW not in portfile
    if not need_registration:
        print('SKIP    %-55s already registered' % ('portfile.cmake'))
        already += 1
    else:
        if PORTFILE_ANCHOR not in portfile:
            print('FAIL    %-55s the expected anchor line is missing' % ('portfile.cmake'))
            failed.append('portfile.cmake')
        elif portfile.count(PORTFILE_ANCHOR) != 1:
            print('FAIL    %-55s the anchor line is not unique (%d matches)'
                  % ('portfile.cmake', portfile.count(PORTFILE_ANCHOR)))
            failed.append('portfile.cmake')

    if failed:
        # Nothing has been written yet, the source tree is still pristine.
        print('')
        print('%d change(s) applied, %d already present, %d failed.'
              % (applied, already, len(failed)))
        print('The RustDesk source does not match the expected layout, so the')
        print('ffmpeg MediaCodec profile fix was NOT installed. The build would')
        print('still work, but the Rockchip hardware encoder would keep failing')
        print('to configure and the remote picture would stay blurry.')
        return 1

    # 1) the ffmpeg patch file itself
    if os.path.isfile(patch_path):
        existing = read_text(patch_path)
        wanted = read_text(source_patch)
        if existing == wanted:
            print('SKIP    %-55s already present' % PATCH_NAME)
            already += 1
        else:
            print('FAIL    %-55s the file exists with a different content' % PATCH_NAME)
            failed.append(PATCH_NAME)
    else:
        shutil.copyfile(source_patch, patch_path)
        print('OK      %-55s copied from %s'
              % (PATCH_NAME, os.path.basename(source_patch)))
        applied += 1

    # 2b) write the registration
    if need_registration:
        portfile = portfile.replace(PORTFILE_ANCHOR, PORTFILE_ANCHOR + PORTFILE_NEW, 1)
        write_text(portfile_path, portfile)
        print('OK      %-55s registered' % ('portfile.cmake'))
        applied += 1

    # 3) optional sanity check when the ffmpeg sources are at hand
    check = try_git_apply_check(root, source_patch)
    if check is True:
        print('OK      %-55s git apply --check passed' % ('ffmpeg patch sanity check'))
    elif check is False:
        print('FAIL    %-55s git apply --check failed' % ('ffmpeg patch sanity check'))
        failed.append('ffmpeg patch sanity check')

    print('')
    print('%d change(s) applied, %d already present, %d failed.'
          % (applied, already, len(failed)))
    if failed:
        print('The RustDesk source does not match the expected layout, so the')
        print('ffmpeg MediaCodec profile fix was NOT installed. The build would')
        print('still work, but the Rockchip hardware encoder would keep failing')
        print('to configure and the remote picture would stay blurry.')
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
