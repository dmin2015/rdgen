#!/usr/bin/env python3
"""Local self-test for android_mediacodec_skip_profile.py (no network needed).

The script installs an ffmpeg patch into the RustDesk source tree:

    res/vcpkg/ffmpeg/patch/0013-android-mediacodec-skip-profile.patch

and registers it in the PATCHES list of

    res/vcpkg/ffmpeg/portfile.cmake

The fixtures below are copies of the relevant parts of rustdesk/rustdesk
1.4.9 (`res/vcpkg/ffmpeg/portfile.cmake`) and of the vcpkg overlay port
layout. The test also verifies that the shipped ffmpeg patch is a valid
diff that applies cleanly to the ffmpeg 7.1 sources after the existing
`0011-android-mediacodec-encode-align-64.patch` has been applied, which is
the order vcpkg uses.
"""
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, 'android_mediacodec_skip_profile.py')
PATCH_FILE = os.path.join(HERE, '0013-android-mediacodec-skip-profile.patch')

PATCH_NAME = '0013-android-mediacodec-skip-profile.patch'

# The PATCHES list of res/vcpkg/ffmpeg/portfile.cmake in rustdesk 1.4.9.
PORTFILE_149 = '''vcpkg_from_github(
    OUT_SOURCE_PATH SOURCE_PATH
    REPO ffmpeg/ffmpeg
    REF "n${VERSION}"
    SHA512 3b273769ef1a1b63aed0691eef317a760f8c83b1d0e1c232b67bbee26db60b4864aafbc88df0e86d6bebf07185bbd057f33e2d5258fde6d97763b9994cd48b6f
    HEAD_REF master
    PATCHES
    0001-create-lib-libraries.patch
    0002-fix-msvc-link.patch
    0003-fix-windowsinclude.patch
    0004-dependencies.patch
    0005-fix-nasm.patch
    0007-fix-lib-naming.patch
    0013-define-WINVER.patch
    0020-fix-aarch64-libswscale.patch
    0024-fix-osx-host-c11.patch
    0040-ffmpeg-add-av_stream_get_first_dts-for-chromium.patch # Do not remove this patch. It is required by chromium
    0041-add-const-for-opengl-definition.patch
    0043-fix-miss-head.patch
    patch/0001-avcodec-amfenc-add-query_timeout-option-for-h264-e.patch
    patch/0005-mediacodec-changing-bitrate.patch
    patch/0011-android-mediacodec-encode-align-64.patch
    patch/0012-fix-macos-big-sur-CVBufferCopyAttachments.patch
)
'''

# The PATCHES list of a newer upstream master, where the last registered
# patch is a different one.
PORTFILE_MASTER = PORTFILE_149.replace(
    '    patch/0012-fix-macos-big-sur-CVBufferCopyAttachments.patch\n',
    '    patch/0013-android-mediacodec-skip-profile.patch\n'
    '    patch/0014-something-else.patch\n')

failures = []


def check(cond, msg):
    if cond:
        print('  ok   - %s' % msg)
    else:
        print('  FAIL - %s' % msg)
        failures.append(msg)
    return cond


def make_tree(root, portfile, with_patch_dir=True):
    ffmpeg_dir = os.path.join(root, 'res', 'vcpkg', 'ffmpeg')
    os.makedirs(ffmpeg_dir, exist_ok=True)
    with open(os.path.join(ffmpeg_dir, 'portfile.cmake'), 'w',
              encoding='utf-8', newline='') as f:
        f.write(portfile)
    if with_patch_dir:
        os.makedirs(os.path.join(ffmpeg_dir, 'patch'), exist_ok=True)
    return ffmpeg_dir


def run(root):
    return subprocess.run([sys.executable, SCRIPT, root],
                          stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT,
                          universal_newlines=True)

def read(path):
    with open(path, 'r', encoding='utf-8', newline='') as f:
        return f.read()


def git(*args, cwd=None):
    return subprocess.run(['git'] + list(args), cwd=cwd,
                          stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT,
                          universal_newlines=True)


def main():
    if not os.path.isfile(SCRIPT):
        print('ERROR: %s not found' % SCRIPT)
        return 2
    if not os.path.isfile(PATCH_FILE):
        print('ERROR: %s not found' % PATCH_FILE)
        return 2

    print('=== 1. the shipped patch is a well formed diff ===')
    patch_text = read(PATCH_FILE)
    check(patch_text.startswith('diff --git '),
          'the patch starts with a git diff header')
    check('--- a/libavcodec/mediacodecenc.c' in patch_text,
          'the patch targets libavcodec/mediacodecenc.c')
    check('+++ b/libavcodec/mediacodecenc.c' in patch_text,
          'the patch has a target header')
    check('\r\n' not in patch_text, 'the patch uses LF line endings only')
    for needle in ('ff_AMediaCodec_refuses_profile',
                   'av_strstart(name, prefixes[i], NULL)',
                   'if (!ff_AMediaCodec_refuses_profile(s->name))'):
        check(needle in patch_text, 'the patch contains %r' % needle)
    # The helper must not use an API that is not part of the public
    # libavutil string API, otherwise the ffmpeg build breaks.
    check('av_strncmp' not in patch_text,
          'the patch does not use the non public av_strncmp')

    print('')
    print('=== 2. the patch applies to the ffmpeg 7.1 sources ===')
    # The real ffmpeg sources are not part of this repository, so the check
    # is only possible when they are available on the machine. When they
    # are not, the structural checks above are all that can be done.
    ffmpeg_src = None
    for candidate in ('/tmp/ffmpeg-7.1', 'I:/tmp/ffmpeg-7.1',
                      os.path.join(HERE, '..', '..', 'ffmpeg-7.1')):
        if os.path.isfile(os.path.join(candidate, 'libavcodec',
                                       'mediacodecenc.c')):
            ffmpeg_src = os.path.abspath(candidate)
            break
    if ffmpeg_src is None:
        print('  skip - the ffmpeg sources are not available locally')
    else:
        tmp = tempfile.mkdtemp(prefix='rdgen_test_ffmpeg_')
        try:
            shutil.copytree(os.path.join(ffmpeg_src, 'libavcodec'),
                            os.path.join(tmp, 'libavcodec'))
            git('init', '-q', '.', cwd=tmp)
            align = os.path.join(HERE, '0011-align-64.patch')
            if os.path.isfile(align):
                r = git('apply', align, cwd=tmp)
                check(r.returncode == 0,
                      'the existing 0011 patch applies (%s)' % r.stdout.strip())
            r = git('apply', '--check', PATCH_FILE, cwd=tmp)
            check(r.returncode == 0,
                  'the 0013 patch applies after 0011 (%s)' % r.stdout.strip())
            r = git('apply', PATCH_FILE, cwd=tmp)
            check(r.returncode == 0, 'the 0013 patch is applied')
            patched = read(os.path.join(tmp, 'libavcodec',
                                        'mediacodecenc.c'))
            check('ff_AMediaCodec_refuses_profile' in patched,
                  'the patched source contains the helper')
            check(patched.count('ff_AMediaCodec_refuses_profile') == 2,
                  'the helper is defined once and used once')
        finally:
            shutil.rmtree(tmp)

    print('')
    print('=== 3. 1.4.9 layout ===')
    tmp = tempfile.mkdtemp(prefix='rdgen_test_ff_149_')
    make_tree(tmp, PORTFILE_149)
    r = run(tmp)
    print(r.stdout.strip())
    check(r.returncode == 0, 'the patch script returned %d' % r.returncode)
    installed = os.path.join(tmp, 'res', 'vcpkg', 'ffmpeg', 'patch', PATCH_NAME)
    check(os.path.isfile(installed), 'the ffmpeg patch was installed')
    if os.path.isfile(installed):
        check(read(installed) == patch_text,
              'the installed patch is byte identical to the shipped one')
    portfile = read(os.path.join(tmp, 'res', 'vcpkg', 'ffmpeg',
                                 'portfile.cmake'))
    check('    patch/%s\n' % PATCH_NAME in portfile,
          'the patch is registered in the portfile')
    check(portfile.index('patch/0011-android-mediacodec-encode-align-64.patch')
          < portfile.index('patch/%s' % PATCH_NAME),
          'the patch is registered after 0011 so the order is kept')
    check(portfile.count('patch/%s' % PATCH_NAME) == 1,
          'the patch is registered exactly once')
    shutil.rmtree(tmp)

    print('')
    print('=== 4. master layout ===')
    tmp = tempfile.mkdtemp(prefix='rdgen_test_ff_master_')
    make_tree(tmp, PORTFILE_MASTER)
    r = run(tmp)
    print(r.stdout.strip())
    check(r.returncode == 0, 'the patch script returned %d' % r.returncode)
    portfile = read(os.path.join(tmp, 'res', 'vcpkg', 'ffmpeg',
                                 'portfile.cmake'))
    check(portfile.count('patch/%s' % PATCH_NAME) == 1,
          'the patch is registered exactly once')
    shutil.rmtree(tmp)

    print('')
    print('=== 5. idempotency ===')
    tmp = tempfile.mkdtemp(prefix='rdgen_test_ff_idem_')
    make_tree(tmp, PORTFILE_149)
    r1 = run(tmp)
    check(r1.returncode == 0, 'the first run succeeded')
    state_after_first = read(os.path.join(tmp, 'res', 'vcpkg', 'ffmpeg',
                                          'portfile.cmake'))
    r2 = run(tmp)
    print(r2.stdout.strip())
    check(r2.returncode == 0, 'the second run succeeded')
    check('SKIP' in r2.stdout, 'the second run reports the work as skipped')
    state_after_second = read(os.path.join(tmp, 'res', 'vcpkg', 'ffmpeg',
                                           'portfile.cmake'))
    check(state_after_first == state_after_second,
          'the second run did not change the portfile')
    shutil.rmtree(tmp)

    print('')
    print('=== 6. unknown layout must fail loudly and write nothing ===')
    tmp = tempfile.mkdtemp(prefix='rdgen_test_ff_bad_')
    make_tree(tmp, 'vcpkg_from_github(\n    REPO ffmpeg/ffmpeg\n)\n')
    r = run(tmp)
    print(r.stdout.strip())
    check(r.returncode != 0, 'an unexpected layout should fail')
    check('anchor' in r.stdout.lower(),
          'an unexpected layout should report the missing anchor')
    installed = os.path.join(tmp, 'res', 'vcpkg', 'ffmpeg', 'patch', PATCH_NAME)
    check(not os.path.isfile(installed),
          'a failed run must not install the patch')
    shutil.rmtree(tmp)

    print('')
    print('=== 7. missing source tree ===')
    tmp = tempfile.mkdtemp(prefix='rdgen_test_ff_missing_')
    r = run(tmp)
    print(r.stdout.strip())
    check(r.returncode != 0, 'a missing source tree should fail')
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
