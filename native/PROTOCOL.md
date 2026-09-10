# NeuralFlow capture host protocol 1

Build/publish `NeuralFlow.Capture.csproj` as self-contained Windows x64. Start
`NeuralFlow.Capture.exe` with redirected stdin/stdout and no console window.
It emits one ready JSON line. Each request and response occupies exactly one
UTF-8 line. Optional `id` is copied into the corresponding response. One request
at a time; the UI/graphics thread handles commands between frame updates.

| Command | Fields | Response |
|---|---|---|
| `start` | `target`: int64 HWND/HMONITOR, `kind`: `window` or `monitor` | Status |
| `stop` | none | Status; overlay immediately hidden and graphics resources released |
| `grab` | `size`: integer 32–1024 | `ok`, `serial`, `size`, `width`, `height`, `rgb`, `age_ms` |
| `residual` | `size`, `rgb`, optional `reference` | `ok` |
| `parameters` | any of `strength`, `clarity`, `saturation`, `contrast`, `brightness`, `warmth`, `tone` | `ok` |
| `exclude` | `hwnd`: controller HWND | `ok`; registers controller as a foreground exception |
| `status` | none | Status |
| `close` | none | `ok`; shuts down |

`grab.rgb` is base64 of tightly packed row-major RGB8. Aspect ratio is preserved
inside the square, with centered black padding. Only this small texture is
copied to CPU; the full-resolution source remains on the GPU. Map waits at most
30 ms; `GPU readback busy; try the newest frame` is retryable. Capture startup
can return `No fresh captured frame`; retry after a short delay. Do not treat
unchanged `serial` as a new source frame. WGC may send no frames for a static
desktop; `age_ms` is the age of the latest update, not end-to-end latency.

`residual.rgb` is base64 of little-endian float32 RGB differences measured in
8-bit pixel units (neural output minus input, before strength). `reference` is
the square input RGB8 used to create/aligned to the correction. Reference-based
confidence masking rejects mismatched current pixels. The shader converts the
letterbox mapping back to original display coordinates, applies the correction
at native source resolution, and gradually fades corrections older than 200 ms
to zero at 1000 ms. Motion compensation itself belongs in the inference service.

Neutral parameter values are `strength=0`, `clarity=0`, `saturation=1`,
`contrast=1`, `brightness=0`, `warmth=0`, `tone=0`. All neutral values hide the
overlay entirely, so the original screen pixels are restored exactly. Strength
does not disable independent appearance controls.

Status contains `active`, `visible`, `emergency`, `adapter`, `width`, `height`,
`frames`, `displayed_frames` (presentation attempts), `average_fps` (capture
updates since start), `frame_age_ms`, `error`, `pause`, `target`, `foreground`,
and `overlay_hwnd`. Frame counters are diagnostics, not neural evaluations.

The owning WPF process MUST apply `SetWindowDisplayAffinity(hwnd, 0x11)` to its
own controls; Windows does not let this separate process set affinity on foreign
HWNDs. This host enforces its own overlay exclusion before starting capture.
Unrelated foreground applications pause window overlays; monitor mode stays
active. Resizing recreates textures and clears the old correction. Minimized or
closed targets hide the overlay. Capture itself continues behind a focus pause.

F9 restoration also runs on a dedicated watchdog thread. If necessary it exits
the isolated capture process with code 9 so Windows removes the overlay even
if a driver call stalls. A protocol timeout exits with code 10. The service must
report OFF and create a new capture host on the next user-requested enable.

The `--diagnostics` launch option enables `probe`, which briefly inspects one
pixel of this process's visible overlay to verify composition during owned-window
tests. It is disabled for ordinary launches and refuses monitor mode.

Dependencies: .NET Windows Desktop runtime, Windows SDK C#/WinRT projection,
Vortice.Direct3D11/DXGI/D3DCompiler 3.8.1. Upstream Vortice is MIT-licensed:
https://github.com/amerkoleci/Vortice.Windows
