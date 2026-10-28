# RDGen, a RustDesk client generator to use with your self-hosted RustDesk server

The client generator is currently hosted [here](https://rdgen.crayoneater.org).
If you would like to host the generator yourself, see [here](setup.md)

## Features

- Embed server and key into client
- Custom app name
- Custom icon/logo
- Set default settings for the client
- Support for rustdesk advanced settings (https://rustdesk.com/docs/en/self-host/client-configuration/advanced-settings/)
- Android only: custom touch mode gestures (one-finger drag moves the canvas; hold still 0.2s = mouse drag, 0.6s = right click; two-finger vertical swipe is the mouse wheel)
- Android only: encoder fallback for the controlled device - when the device has no hardware H.264/H.265 MediaCodec encoder (e.g. Android 9 boxes, 32-bit ARM), use the software H.264 MediaCodec encoder (`OMX.google.h264.encoder`) instead of the bundled software VP8 encoder, which is too slow for 1080p and produces a blurry picture

## Generate RustDesk clients from command line instead of using a web browser

Save your configuration from the rdgen web interface, or generate your own, then use that json file with [@AlekseyLapunov's rdgen-cli](https://github.com/AlekseyLapunov/rdgen-cli) to build from the command line on Windows, Linux, or MacOS like this: `python rdgen-cli -f my_config.json --set-version 1.4.5 --set-platform windows -s https://rdgen.crayoneater.org`

## Notes

- Icons should be square (256x256 recommended)
- Avoid special characters or non-English characters in app name and file name
- Build time is currently 30 - 45 minutes

