#!/usr/bin/env python3
"""
rdgen Android encoder fallback patch.

Applied by .github/workflows/generator-android.yml when the "Android encoder
fallback" option is set to "Software H.264 (MediaCodec)".

Problem
-------
On Android, RustDesk encodes the screen of the *controlled* device (the
"server" side) with a MediaCodec encoder wrapped by ffmpeg
(`h264_mediacodec` / `hevc_mediacodec`). The list of usable encoders is
collected in two places:

  1. flutter/android/app/src/main/kotlin/com/carriez/flutter_hbb/MainActivity.kt
     `setCodecInfo()` drops every codec that is not a *hardware* codec
     (`if (hw != true) return@forEach`).
  2. libs/scrap/src/common/hwcodec.rs `HwCodecConfig::get()` keeps only the
     codecs flagged as hardware (`c.hw == Some(true) //only use hardware codec`).

When the hardware MediaCodec encoder cannot be created at runtime, RustDesk
gives up on H.26x completely: `Encoder::new()` clears the hardware codec
config, the negotiated format falls back to VP8/VP9, and because the VPx
encoder reports `is_hardware() == false` the capture resolution is halved
(`check_change_scale()` -> `half_scale = true`). The user then sees a blurry
picture encoded with VP8.

This is not a rare corner case. The very common RK3566 boxes are a perfect
example: their Rockchip encoder `OMX.rk.video_encoder.avc` *exists* and is
reported by the platform as a hardware H.264 encoder, but it refuses to be
configured with the parameters RustDesk uses, and the whole session ends up
on a blurry VP8 stream. Measured on such a device with a MediaCodec probe:

    OMX.rk.video_encoder.avc  1366x768  color=21  flags=1  profile unset -> configure OK
    OMX.rk.video_encoder.avc  1366x768  color=21  flags=1  profile=1/2/4/8/16/4096 -> FAIL
    c2.android.avc.encoder    1366x768  color=21  flags=1  any profile            -> configure OK

The reason is the `hwcodec` crate: `cpp/common/util.cpp` hardcodes
`c->profile = FF_PROFILE_H264_HIGH`, so ffmpeg always writes a "profile" key
into the MediaFormat, and the Rockchip encoder rejects *any* explicit profile.
Meanwhile the AOSP software encoders (`c2.android.avc.encoder`,
`OMX.google.h264.encoder`) accept every profile and encode 1366x768 just fine
even though they advertise a 1280x720 limit.

What it changes
---------------
  1. MainActivity.kt keeps the software MediaCodec encoders in the codec info
     and reports them with `hw=false` instead of dropping them.
  2. MainActivity.kt no longer drops an encoder because the platform
     advertises a maximum size that is smaller than the capture resolution.
     The advertised limit is unreliable (the AOSP software encoders claim
     1280x720 but encode 1366x768 fine), so the size check is relaxed and the
     real limit is enforced later, when the encoder is actually created.
  3. libs/scrap/src/common/hwcodec.rs keeps *every* usable MediaCodec
     encoder as a candidate, hardware ones first, and
     `HwRamEncoder::new()` retries with the next candidate when the encoder
     cannot be created. The software candidates are limited to H.264:
     software H.265 encoding is far too slow for the low end devices this
     fallback targets.

Because the software encoder is used through the very same `HwRamEncoder`
(ffmpeg `h264_mediacodec`) path, `HwRamEncoder::is_hardware()` stays `true`,
so `check_change_scale()` keeps the full capture resolution: the picture is
H.264 *and* sharp.

The script performs targeted text replacements on the RustDesk sources so that
it keeps working across patch releases (1.4.x and master share the same code
shape for the touched blocks). It is idempotent: running it twice is a
no-op, and it exits non-zero with a clear message when a target block cannot
be found, so a build never silently ships the wrong encoder behaviour.

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
            // OMX.google.h264.encoder, c2.android.avc.encoder) in the codec
            // info and report them with hw=false instead of dropping them
            // here. They are used as a fallback when the hardware encoder
            // cannot be created at runtime - see the notes in
            // libs/scrap/src/common/hwcodec.rs. Upstream drops them, so
            // RustDesk silently falls back to the much heavier software VP8
            // encoder and the remote picture turns blurry.
            codecObject.put("hw", hw ?: false)
""",
    ),
    # ------------------------- Kotlin: do not drop encoders by advertised size
    (
        'main_activity',
        'MainActivity.kt -> keep encoders whose advertised max size is too small',
        """                if (codec.isEncoder) {
                    // Encoder's max_height and max_width are interchangeable
                    if (!caps.videoCapabilities.isSizeSupported(w,h) && !caps.videoCapabilities.isSizeSupported(h,w)) {
                        return@forEach
                    }
                }
""",
        """                // rdgen: do not drop an encoder because the platform
                // advertises a maximum size that is smaller than the capture
                // resolution. That limit is unreliable: the AOSP software AVC
                // encoders advertise 1280x720 but encode 1366x768 just fine.
                // The real limit is enforced later, when the encoder is
                // actually created, so an encoder that turns out to be
                // unusable is rejected at that point instead of being
                // removed from the list up front.
""",
    ),
    # ------------------- Rust: keep every candidate, hardware ones first
    (
        'hwcodec',
        'hwcodec.rs -> keep every MediaCodec encoder as a candidate',
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
""",
        """                ts.iter().for_each(|t| {
                    // rdgen: keep every usable MediaCodec encoder as a
                    // candidate, the hardware ones first. Some hardware
                    // encoders cannot be created with the parameters RustDesk
                    // uses - the Rockchip AVC encoder (OMX.rk.video_encoder.avc
                    // on the very common RK3566 boxes) rejects every explicit
                    // H.264 profile, and ffmpeg always writes one. Instead of
                    // giving up on H.26x and falling back to the blurry
                    // software VP8 encoder, the next candidate is tried.
                    // The software fallback is limited to H.264: software H.265
                    // encoding is far too slow for the low end devices this
                    // fallback targets.
                    let mut codecs: Vec<_> = info
                        .codecs
                        .iter()
                        .filter(|c| {
                            c.is_encoder
                                && c.mime_type.as_str() == get_mime_type(t.data_format)
                                && c.nv12
                                && (c.hw == Some(true)
                                    || (t.name_prefix == "h264" && c.hw == Some(false)))
                        })
                        .collect();
                    // hardware encoders first, software ones last
                    codecs.sort_by_key(|c| if c.hw == Some(true) { 0 } else { 1 });
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
                    // rdgen: remember the other candidates so that
                    // HwRamEncoder::new() can retry with them when the
                    // preferred encoder cannot be created.
                    for codec in codecs.iter() {
                        if Some(&codec.name) == best.as_ref() {
                            continue;
                        }
                        e.push(CodecInfo {
                            name: format!("{}_mediacodec", t.name_prefix),
                            mc_name: Some(codec.name.clone()),
                            format: t.data_format,
                            hwdevice: hwcodec::ffmpeg::AVHWDeviceType::AV_HWDEVICE_TYPE_NONE,
                            priority: 1,
                        });
                    }
                });
""",
    ),
    # ------------------- Rust: retry with the next candidate on failure
    (
        'hwcodec',
        'hwcodec.rs -> retry with the next MediaCodec encoder candidate',
        """                match Encoder::new(ctx.clone()) {
                    Ok(encoder) => Ok(HwRamEncoder {
                        encoder,
                        format,
                        pixfmt: ctx.pixfmt,
                        bitrate,
                        config,
                    }),
                    Err(_) => Err(anyhow!(format!("Failed to create encoder"))),
                }
""",
        """                match Encoder::new(ctx.clone()) {
                    Ok(encoder) => Ok(HwRamEncoder {
                        encoder,
                        format,
                        pixfmt: ctx.pixfmt,
                        bitrate,
                        config,
                    }),
                    Err(_) => {
                        // rdgen: the preferred MediaCodec encoder cannot be
                        // created. Try the remaining candidates before giving
                        // up on H.26x. Some hardware encoders refuse the
                        // parameters RustDesk uses - the Rockchip AVC encoder
                        // on the RK3566 boxes rejects every explicit H.264
                        // profile, and ffmpeg always writes one. Upstream
                        // clears the hardware config here, the negotiated
                        // format falls back to VP8/VP9 and, because the VPx
                        // encoder reports is_hardware() == false, the capture
                        // resolution is halved - the remote picture turns
                        // blurry. A software MediaCodec encoder goes through
                        // the same path, so is_hardware() stays true and the
                        // full resolution is kept.
                        let mut last_err = anyhow!(format!("Failed to create encoder"));
                        let candidates: Vec<_> = HwCodecConfig::get()
                            .ram_encode
                            .into_iter()
                            .filter(|c| {
                                c.name == config.name && c.mc_name != config.mc_name
                            })
                            .collect();
                        for candidate in candidates {
                            let mut retry_cfg = config.clone();
                            retry_cfg.mc_name = candidate.mc_name.clone();
                            // clamp the bitrate to the range the candidate
                            // encoder actually supports
                            let retry_bitrate = Self::check_bitrate_range(&retry_cfg, bitrate);
                            let mut retry_ctx = ctx.clone();
                            retry_ctx.mc_name = candidate.mc_name.clone();
                            retry_ctx.kbs = retry_bitrate as i32;
                            log::info!(
                                "retry with MediaCodec encoder: {:?}",
                                candidate.mc_name
                            );
                            match Encoder::new(retry_ctx) {
                                Ok(encoder) => {
                                    log::info!("MediaCodec encoder created: {:?}", candidate.mc_name);
                                    return Ok(HwRamEncoder {
                                        encoder,
                                        format,
                                        pixfmt: ctx.pixfmt,
                                        bitrate: retry_bitrate,
                                        config: retry_cfg,
                                    });
                                }
                                Err(_) => {
                                    last_err = anyhow!(format!("Failed to create encoder"));
                                }
                            }
                        }
                        Err(last_err)
                    }
                }
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
