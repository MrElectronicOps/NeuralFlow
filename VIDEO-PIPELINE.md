# NeuralFlow offline video

`engine/video.py` exposes `export_video(source, destination, strength, stability,
backend, cancel, progress)` and `prepare_playback(source, destination, cancel,
progress)`. Both return a report containing the completed `path`.

Strength and stability are fractions from zero to one. The backend supplies
`render(PIL_RGB_square) -> (PIL_RGB_square, metrics)`. Offline processing uses
512-pixel native-resolution tiles with overlapping feathered edges. The service
must pause live neural work for the entire export. At zero strength the backend
is not called, and RGB pixels are unchanged before encoding.

Temporal stabilization aligns only the neural residual using forward and
backward optical flow, rejects inconsistent or newly visible areas, and resets
at scene cuts. It is postprocessing, not temporal inputs to NVIDIA's model.
It reduces measured synthetic residual flicker; universal flicker-free quality
has not been demonstrated.

Each decoded source frame keeps its presentation timestamp and duration. Video
and audio share the same normalized timeline origin. Frames are not duplicated,
dropped, or converted to a nominal constant frame rate. Lossless MKV uses FFV1
RGB and copies all audio tracks; MP4 uses H.264 CRF 16 and AAC 192 kb/s. MP4 audio
is re-encoded, so codec sample padding may differ by one AAC packet. Rotation,
HDR, interlacing, embedded subtitles, and chapters are not current acceptance
targets; users should supply progressive 8-bit SDR video up to 3840×2160.

Cancellation is checked between tiles, frames, muxing polls and verification
frames. A running neural tile can take up to the backend's timeout to return.
Temporary files are cleaned, and originals/existing outputs are never replaced.
All video/audio streams must completely decode and frame PTS/durations must
pass verification before the completed media is published. Logs are beside the
chosen output, and a JSON report records the measurements.

The Windows comparison player uses high-quality H.264/AAC MP4 proxies when
needed. Proxy preparation uses the same timestamp-preserving path at zero
neural strength. Odd dimensions require MKV export; the proxy helper does not
silently resize these videos.

## Dependencies and provenance

- PyAV 18.1.0: https://pypi.org/project/av/18.1.0/ (bundles FFmpeg libraries).
- OpenCV headless 4.12.0.88: https://pypi.org/project/opencv-python-headless/4.12.0.88/
- NumPy 2.2.6: https://pypi.org/project/numpy/2.2.6/
- Pillow 11.3.0: https://pypi.org/project/pillow/11.3.0/
- Standalone FFmpeg is resolved at `engine/tools/ffmpeg.exe`, via the explicit
  `NEURALFLOW_FFMPEG` environment variable, or from the user's PATH.

The local wheel installation uses CPython 3.12. NumPy and Pillow require matching
CPython 3.12 in the portable distribution. Retain package license files and
FFmpeg license/build notices in the distribution. NVIDIA runtime redistribution
is handled separately by the guided import.

Timestamp implementation references:
https://pyav.org/docs/stable/api/time.html and
https://github.com/PyAV-Org/PyAV/blob/main/examples/numpy/generate_video_with_pts.py

## Validation

`tests/test_video.py` performs deterministic identity-backend container tests
and separate motion/cut/stability checks. These do not prove NVIDIA inference.
`tests/test_video_gpu.py` explicitly runs the selected genuine backend, verifies
changed pixels, and saves actual runtime logs and measurements. A short sample
is not a substitute for human review of faces, captions, pans and long videos.
