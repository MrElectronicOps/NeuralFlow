# NeuralFlow compatibility — preview 0.6

## One-button setup, preview 0.6.0-preview.2

An empty application-data folder completed the actual upstream downloads,
archive and DLL hash checks, extraction, video-tool installation and all nine
GTX 1650 neural-size checks in 64.31 seconds on this laptop. Repeating setup
reused the installed components in 0.31 seconds, without downloads. Effects
remained OFF. This is an isolated first-run test on the development laptop,
not a clean Windows installation. Initial setup requires internet and the
pinned community releases to remain available.

| Component / hardware | State | Evidence or limit |
| --- | --- | --- |
| NVIDIA GTX 1650 4GB, driver 592.82 | Verified experiment | All nine sizes passed feature-18 create/evaluate, completed readback, finite changed pixels and disabled exact identity |
| Ryzen 5 5600H / Windows 11 laptop | Verified development machine | App/backend/video and Windows Graphics Capture checks run locally |
| Other GTX cards | Not tested | Per-device check required; no family-wide compatibility claim |
| RTX 20/30/40/50 | Not tested by NeuralFlow | May run the experimental backend; no automatic claim of native DLSS integration |
| AMD / Intel neural processing | Unavailable | No integrated neural backend in this release |
| SDR application windows / monitors | Experimental | Direct3D output, resizing, minimizing and restoration checked on this laptop |
| Native integrated DLSS 5 | Unavailable through this overlay | Requires game integration and supported NVIDIA runtime/hardware |
| HDR, protected media, secure desktops | Unavailable | No HDR pipeline or protected-content bypass |
| Clean Windows machine | Not tested | Self-contained imports checked locally; a separate clean-machine test remains a public release gate |

## Measured neural sizes

All of 128, 160, 192, 224, 256, 320, 384, 448 and 512 passed. In the initial nine-size run, median neural GPU evaluation was approximately 179–279 ms, and worker round trip 186–317 ms. These are neural measurements, not displayed FPS or end-to-end interaction latency. Cached timing from the user's own device determines Auto resolution.

Windows GPU budget usage is sampled after evaluation. Transient peak memory is not measured. Passing the small local test does not establish stability in every workload.

## Offline tests

Synthetic VFR timestamps, audio offsets, final-frame duration, MKV identity, MP4 proxy timing, tile blending, motion alignment, scene cuts and cancellation passed. A six-frame real Vice City clip at 436×326 completed six actual neural evaluations at 512 processing size, with original timestamps preserved. These tests do not establish universal flicker-free rendering.

The actual WPF player opened both 436×326 test clips, advanced playback, switched original/enhanced, muted duplicate audio and sought to 0.25 seconds. The measured player-clock difference was 0.1042 ms at the sampled instant; this is not hardware-measured speaker/display latency.

The packaged interface opened in wide and compact layouts at the laptop's 150% Windows scaling. Keyboard interaction verified quick F8/F9 presses, navigation, and selection of the detected 1920×1080 display. Global shortcuts use Windows hotkey messages; a conflicting registration is reported in the interface. Separate 100% and 200% OS-scaling tests remain outstanding.

An actual packaged-app start/stop test passed with neutral effects on its own capture-excluded window: OFF during pending startup, a second toggle during startup, and OFF after completed startup all left both engine and interface OFF. This verifies control ordering, not visual rendering quality.

## Combined live test

The actual source service, published capture host and GTX 1650 neural worker ran an animated test chart at 720p, 1080p and 1920×1080 monitor capture. Median compositor presentation rate was about 44/s; 720p/1080p window capture produced about 21 unique updated frames/s, and monitor capture about 45/s. These are not 44 unique video or neural frames/s. Neural evaluations took 206–211 ms; ON/OFF, comparison, neutral settings and target closure passed. Browser/VLC/game-specific end-to-end tests and a long-duration soak remain unverified.
