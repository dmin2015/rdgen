#!/usr/bin/env python3
"""Local self-test for android_sw_h264_fallback.py (no network needed).

The fixtures below are verbatim copies of the relevant parts of
rustdesk/rustdesk:

  MAIN_ACTIVITY_149 / HWCODEC_149    tag 1.4.9
                                      (SHA 6c578292e8ebbbec708b76986ba8c4bc7c509747)
  MAIN_ACTIVITY_MASTER / HWCODEC_MASTER  head master

Only the parts of the files that the patch anchors on are included; every
anchor block in android_sw_h264_fallback.py must appear verbatim here, so a
green run means the anchors exist in the real upstream sources.
"""
import os
import shutil
import subprocess
import sys
import tempfile

PATCH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     'android_sw_h264_fallback.py')
PATCH = os.path.abspath(PATCH)

MAIN_ACTIVITY_149 = '''    private fun setCodecInfo() {
        val codecList = MediaCodecList(MediaCodecList.REGULAR_CODECS)
        val codecs = codecList.codecInfos
        val codecArray = JSONArray()

        val windowManager = getSystemService(Context.WINDOW_SERVICE) as WindowManager
        val wh = getScreenSize(windowManager)
        var w = wh.first
        var h = wh.second
        val align = 64
        w = (w + align - 1) / align * align
        h = (h + align - 1) / align * align
        codecs.forEach { codec ->
            val codecObject = JSONObject()
            codecObject.put("name", codec.name)
            codecObject.put("is_encoder", codec.isEncoder)
            var hw: Boolean? = null;
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                hw = codec.isHardwareAccelerated
            } else {
                // https://chromium.googlesource.com/external/webrtc/+/HEAD/sdk/android/src/java/org/webrtc/MediaCodecUtils.java#29
                // https://chromium.googlesource.com/external/webrtc/+/master/sdk/android/api/org/webrtc/HardwareVideoEncoderFactory.java#229
                if (listOf("OMX.google.", "OMX.SEC.", "c2.android").any { codec.name.startsWith(it, true) }) {
                    hw = false
                } else if (listOf("c2.qti", "OMX.qcom.video", "OMX.Exynos", "OMX.hisi", "OMX.MTK", "OMX.Intel", "OMX.Nvidia").any { codec.name.startsWith(it, true) }) {
                    hw = true
                }
            }
            if (hw != true) {
                return@forEach
            }
            codecObject.put("hw", hw)
            var mime_type = ""
            codec.supportedTypes.forEach { type ->
                if (listOf("video/avc", "video/hevc").contains(type)) { // "video/x-vnd.on2.vp8", "video/x-vnd.on2.vp9", "video/av01"
                    mime_type = type;
                }
            }
            if (mime_type.isNotEmpty()) {
                codecObject.put("mime_type", mime_type)
                val caps = codec.getCapabilitiesForType(mime_type)
                if (codec.isEncoder) {
                    // Encoder's max_height and max_width are interchangeable
                    if (!caps.videoCapabilities.isSizeSupported(w,h) && !caps.videoCapabilities.isSizeSupported(h,w)) {
                        return@forEach
                    }
                }
                codecObject.put("min_width", caps.videoCapabilities.supportedWidths.lower)
                codecObject.put("max_width", caps.videoCapabilities.supportedWidths.upper)
                codecObject.put("min_height", caps.videoCapabilities.supportedHeights.lower)
                codecObject.put("max_height", caps.videoCapabilities.supportedHeights.upper)
                val surface = caps.colorFormats.contains(COLOR_FormatSurface);
                codecObject.put("surface", surface)
                val nv12 = caps.colorFormats.contains(COLOR_FormatYUV420SemiPlanar)
                codecObject.put("nv12", nv12)
                if (!(nv12 || surface)) {
                    return@forEach
                }
                codecObject.put("min_bitrate", caps.videoCapabilities.bitrateRange.lower / 1000)
                codecObject.put("max_bitrate", caps.videoCapabilities.bitrateRange.upper / 1000)
                if (!codec.isEncoder) {
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                        codecObject.put("low_latency", caps.isFeatureSupported(MediaCodecInfo.CodecCapabilities.FEATURE_LowLatency))
                    }
                }
                if (!codec.isEncoder) {
                    return@forEach
                }
                codecArray.put(codecObject)
            }
        }
        val result = JSONObject()
        result.put("version", Build.VERSION.SDK_INT)
        result.put("w", w)
        result.put("h", h)
        result.put("codecs", codecArray)
        FFI.setCodecInfo(result.toString())
    }'''

MAIN_ACTIVITY_MASTER = '''    private fun setCodecInfo() {
        val codecList = MediaCodecList(MediaCodecList.REGULAR_CODECS)
        val codecs = codecList.codecInfos
        val codecArray = JSONArray()

        val windowManager = getSystemService(Context.WINDOW_SERVICE) as WindowManager
        val wh = getScreenSize(windowManager)
        var w = wh.first
        var h = wh.second
        val align = 64
        w = (w + align - 1) / align * align
        h = (h + align - 1) / align * align
        codecs.forEach { codec ->
            val codecObject = JSONObject()
            codecObject.put("name", codec.name)
            codecObject.put("is_encoder", codec.isEncoder)
            var hw: Boolean? = null;
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                hw = codec.isHardwareAccelerated
            } else {
                // https://chromium.googlesource.com/external/webrtc/+/HEAD/sdk/android/src/java/org/webrtc/MediaCodecUtils.java#29
                // https://chromium.googlesource.com/external/webrtc/+/master/sdk/android/api/org/webrtc/HardwareVideoEncoderFactory.java#229
                if (listOf("OMX.google.", "OMX.SEC.", "c2.android").any { codec.name.startsWith(it, true) }) {
                    hw = false
                } else if (listOf("c2.qti", "OMX.qcom.video", "OMX.Exynos", "OMX.hisi", "OMX.MTK", "OMX.Intel", "OMX.Nvidia").any { codec.name.startsWith(it, true) }) {
                    hw = true
                }
            }
            if (hw != true) {
                return@forEach
            }
            codecObject.put("hw", hw)
            var mime_type = ""
            codec.supportedTypes.forEach { type ->
                if (listOf("video/avc", "video/hevc").contains(type)) { // "video/x-vnd.on2.vp8", "video/x-vnd.on2.vp9", "video/av01"
                    mime_type = type;
                }
            }
            if (mime_type.isNotEmpty()) {
                codecObject.put("mime_type", mime_type)
                val caps = codec.getCapabilitiesForType(mime_type)
                if (codec.isEncoder) {
                    // Encoder's max_height and max_width are interchangeable
                    if (!caps.videoCapabilities.isSizeSupported(w,h) && !caps.videoCapabilities.isSizeSupported(h,w)) {
                        return@forEach
                    }
                }
                codecObject.put("min_width", caps.videoCapabilities.supportedWidths.lower)
                codecObject.put("max_width", caps.videoCapabilities.supportedWidths.upper)
                codecObject.put("min_height", caps.videoCapabilities.supportedHeights.lower)
                codecObject.put("max_height", caps.videoCapabilities.supportedHeights.upper)
                val surface = caps.colorFormats.contains(COLOR_FormatSurface);
                codecObject.put("surface", surface)
                val nv12 = caps.colorFormats.contains(COLOR_FormatYUV420SemiPlanar)
                codecObject.put("nv12", nv12)
                if (!(nv12 || surface)) {
                    return@forEach
                }
                codecObject.put("min_bitrate", caps.videoCapabilities.bitrateRange.lower / 1000)
                codecObject.put("max_bitrate", caps.videoCapabilities.bitrateRange.upper / 1000)
                if (!codec.isEncoder) {
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                        codecObject.put("low_latency", caps.isFeatureSupported(MediaCodecInfo.CodecCapabilities.FEATURE_LowLatency))
                    }
                }
                if (!codec.isEncoder) {
                    return@forEach
                }
                codecArray.put(codecObject)
            }
        }
        val result = JSONObject()
        result.put("version", Build.VERSION.SDK_INT)
        result.put("w", w)
        result.put("h", h)
        result.put("codecs", codecArray)
        FFI.setCodecInfo(result.toString())
    }'''

HWCODEC_149 = '''    pub fn get() -> HwCodecConfig {
        #[cfg(target_os = "android")]
        {
            let info = crate::android::ffi::get_codec_info();
            log::info!("all codec info: {info:?}");
            struct T {
                name_prefix: &'static str,
                data_format: DataFormat,
            }
            let ts = vec![
                T {
                    name_prefix: "h264",
                    data_format: DataFormat::H264,
                },
                T {
                    name_prefix: "hevc",
                    data_format: DataFormat::H265,
                },
            ];
            let mut e = vec![];
            if let Some(info) = info {
                ts.iter().for_each(|t| {
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
                    let screen_wh = std::cmp::max(info.w, info.h);
                    let mut best = None;
                    if let Some(codec) = codecs
                        .iter()
                        .find(|c| c.max_width >= screen_wh && c.max_height >= screen_wh)
                    {
                        best = Some(codec.name.clone());
                    } else {
                        // find the max resolution
                        let mut max_area = 0;
                        for codec in codecs.iter() {
                            if codec.max_width * codec.max_height > max_area {
                                best = Some(codec.name.clone());
                                max_area = codec.max_width * codec.max_height;
                            }
                        }
                    }
                    if let Some(best) = best {
                        e.push(CodecInfo {
                            name: format!("{}_mediacodec", t.name_prefix),
                            mc_name: Some(best),
                            format: t.data_format,
                            hwdevice: hwcodec::ffmpeg::AVHWDeviceType::AV_HWDEVICE_TYPE_NONE,
                            priority: 0,
                        });
                    }
                });
            }
            log::debug!("e: {e:?}");
            HwCodecConfig {
                ram_encode: e,
                ..Default::default()
            }
        }
                match Encoder::new(ctx.clone()) {
                    Ok(encoder) => Ok(HwRamEncoder {
                        encoder,
                        format,
                        pixfmt: ctx.pixfmt,
                        bitrate,
                        config,
                    }),
                    Err(_) => Err(anyhow!(format!("Failed to create encoder"))),
                }
'''

HWCODEC_MASTER = '''    pub fn get() -> HwCodecConfig {
        #[cfg(target_os = "android")]
        {
            let info = crate::android::ffi::get_codec_info();
            log::info!("all codec info: {info:?}");
            struct T {
                name_prefix: &'static str,
                data_format: DataFormat,
            }
            let ts = vec![
                T {
                    name_prefix: "h264",
                    data_format: DataFormat::H264,
                },
                T {
                    name_prefix: "hevc",
                    data_format: DataFormat::H265,
                },
            ];
            let mut e = vec![];
            if let Some(info) = info {
                ts.iter().for_each(|t| {
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
                    let screen_wh = std::cmp::max(info.w, info.h);
                    let mut best = None;
                    if let Some(codec) = codecs
                        .iter()
                        .find(|c| c.max_width >= screen_wh && c.max_height >= screen_wh)
                    {
                        best = Some(codec.name.clone());
                    } else {
                        // find the max resolution
                        let mut max_area = 0;
                        for codec in codecs.iter() {
                            if codec.max_width * codec.max_height > max_area {
                                best = Some(codec.name.clone());
                                max_area = codec.max_width * codec.max_height;
                            }
                        }
                    }
                    if let Some(best) = best {
                        e.push(CodecInfo {
                            name: format!("{}_mediacodec", t.name_prefix),
                            mc_name: Some(best),
                            format: t.data_format,
                            hwdevice: hwcodec::ffmpeg::AVHWDeviceType::AV_HWDEVICE_TYPE_NONE,
                            priority: 0,
                        });
                    }
                });
            }
            log::debug!("e: {e:?}");
            HwCodecConfig {
                ram_encode: e,
                ..Default::default()
            }
        }
                match Encoder::new(ctx.clone()) {
                    Ok(encoder) => Ok(HwRamEncoder {
                        encoder,
                        format,
                        pixfmt: ctx.pixfmt,
                        bitrate,
                        config,
                    }),
                    Err(_) => Err(anyhow!(format!("Failed to create encoder"))),
                }
'''


NEEDLES_KOTLIN = [
    'codecObject.put("hw", hw ?: false)',
]

NEEDLES_RUST = [
    'c.hw == Some(true)',
    't.name_prefix == "h264" && c.hw == Some(false)',
    'codecs.sort_by_key',
    'retry with MediaCodec encoder',
    'retry_ctx.mc_name = candidate.mc_name.clone()',
]


def main_activity_path(root):
    return os.path.join(root, 'flutter', 'android', 'app', 'src', 'main',
                        'kotlin', 'com', 'carriez', 'flutter_hbb',
                        'MainActivity.kt')


def hwcodec_path(root):
    return os.path.join(root, 'libs', 'scrap', 'src', 'common', 'hwcodec.rs')


def make_tree(root, main_activity, hwcodec):
    d = os.path.join(root, 'flutter', 'android', 'app', 'src', 'main',
                     'kotlin', 'com', 'carriez', 'flutter_hbb')
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, 'MainActivity.kt'), 'w',
              encoding='utf-8', newline='\n') as f:
        f.write(main_activity)
    d = os.path.join(root, 'libs', 'scrap', 'src', 'common')
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, 'hwcodec.rs'), 'w',
              encoding='utf-8', newline='\n') as f:
        f.write(hwcodec)


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
    tmp = tempfile.mkdtemp(prefix='rdgen_test_enc_149_')
    make_tree(tmp, MAIN_ACTIVITY_149, HWCODEC_149)
    r = run(tmp)
    print('--- 1.4.9 layout ---')
    print(r.stdout.strip())
    check(r.returncode == 0, '1.4.9 patch returned %d' % r.returncode)
    kt = read(main_activity_path(tmp))
    rs = read(hwcodec_path(tmp))
    for needle in NEEDLES_KOTLIN:
        check(needle in kt, '1.4.9 kotlin output missing %r' % needle)
    for needle in NEEDLES_RUST:
        check(needle in rs, '1.4.9 rust output missing %r' % needle)
    # the upstream "hardware only" filter must be gone
    check('c.hw == Some(true) //only use hardware codec' not in rs,
          '1.4.9 upstream hardware-only filter is still present')
    check('if (hw != true) {' not in kt,
          '1.4.9 upstream software-codec drop is still present')
    # a hardware encoder must still win over a software one
    check('codecs.sort_by_key(|c| if c.hw == Some(true) { 0 } else { 1 })' in rs,
          '1.4.9 hardware preference was lost')
    # the software fallback must be limited to H.264
    check('t.name_prefix == "h264" && c.hw == Some(false)' in rs,
          '1.4.9 software fallback is not limited to H.264')
    # the retry must happen when the encoder cannot be created
    check('retry with MediaCodec encoder' in rs,
          '1.4.9 the MediaCodec encoder retry is missing')
    # the upstream size check must be gone, otherwise the software encoders
    # (1280x720 limit) never reach the Rust side
    check('isSizeSupported' not in kt,
          '1.4.9 the upstream encoder size check is still present')
    shutil.rmtree(tmp)

    # 2. idempotency
    tmp = tempfile.mkdtemp(prefix='rdgen_test_enc_idem_')
    make_tree(tmp, MAIN_ACTIVITY_149, HWCODEC_149)
    run(tmp)
    kt1 = read(main_activity_path(tmp))
    rs1 = read(hwcodec_path(tmp))
    r2 = run(tmp)
    check(r2.returncode == 0 and 'already patched' in r2.stdout,
          'idempotency broken: rc=%d out=%s' % (r2.returncode, r2.stdout))
    check(read(main_activity_path(tmp)) == kt1,
          'second run changed MainActivity.kt')
    check(read(hwcodec_path(tmp)) == rs1, 'second run changed hwcodec.rs')
    shutil.rmtree(tmp)

    # 3. master layout
    tmp = tempfile.mkdtemp(prefix='rdgen_test_enc_master_')
    make_tree(tmp, MAIN_ACTIVITY_MASTER, HWCODEC_MASTER)
    r = run(tmp)
    print('--- master layout ---')
    print(r.stdout.strip())
    check(r.returncode == 0, 'master patch returned %d' % r.returncode)
    kt = read(main_activity_path(tmp))
    rs = read(hwcodec_path(tmp))
    for needle in NEEDLES_KOTLIN:
        check(needle in kt, 'master kotlin output missing %r' % needle)
    for needle in NEEDLES_RUST:
        check(needle in rs, 'master rust output missing %r' % needle)
    shutil.rmtree(tmp)

    # 4. unknown layout must fail loudly and write nothing
    tmp = tempfile.mkdtemp(prefix='rdgen_test_enc_bad_')
    broken_kt = MAIN_ACTIVITY_149.replace(
        '            if (hw != true) {\n                return@forEach\n            }\n',
        '            // upstream filter removed\n')
    broken_rs = HWCODEC_149.replace(
        '                            && c.hw == Some(true) //only use hardware codec\n',
        '')
    make_tree(tmp, broken_kt, broken_rs)
    before_kt = read(main_activity_path(tmp))
    before_rs = read(hwcodec_path(tmp))
    r = run(tmp)
    print('--- unknown layout ---')
    print(r.stdout.strip())
    check(r.returncode != 0, 'unknown layout should fail')
    check('target block not found' in r.stdout,
          'unknown layout should report the missing block')
    check(read(main_activity_path(tmp)) == before_kt,
          'failed run modified MainActivity.kt')
    check(read(hwcodec_path(tmp)) == before_rs,
          'failed run modified hwcodec.rs')
    shutil.rmtree(tmp)

    # 5. missing source file
    tmp = tempfile.mkdtemp(prefix='rdgen_test_enc_missing_')
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
