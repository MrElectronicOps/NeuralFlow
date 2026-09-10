# NeuralFlow experimental NVIDIA backend

`Backend(data_dir, runtime_dir=None, adapter_luid=None)` discovers hardware and the
installed NVIDIA NGX core. Omit runtime_dir in production to use an explicit user
import in `data_dir/runtime`. `status()` is read-only after initialization and
does not launch inference. Missing runtime/core, software adapters and non-NVIDIA
hardware produce an unavailable status with a clear explanation.

`import_runtime(source_dir, data_dir)` inspects x64 PE headers and verifies both
known hashes before copying a local import. It never downloads DLLs or loads
unrecognized code. Construct a fresh Backend after importing. The application
must stop existing live/video work before changing the import or GPU.

`benchmark(progress=None, cancel=None)` evaluates all nine candidate sizes. Each
size receives an exact disabled identity control and four enabled evaluations;
the median excludes the first enabled evaluation. Success requires feature 18
creation, evaluation return 0x1, a completed GPU fence, finite output and changed
RGB pixels. These checks establish execution and basic compatibility, not the
absence of artifacts on every image or native game integration.

`render(PIL_RGB_square)` returns `(PIL_RGB_output, metrics)`. The image dimension
selects the worker size. The API serializes its calls and keeps only one worker
alive. New sizes restart the worker. Do not call it once per UI-slider movement;
commit size changes on release. The API takes full-strength neural output so the
compositor can blend only the correction over the original at the requested
strength. Zero-effect presentation must bypass the overlay entirely.

`auto_size(preset)` chooses the largest validated size within 225 ms roundtrip for
Smooth or 250 ms for Balanced. Detail chooses the largest validated size. If no
size meets a time goal, the fastest measured size is selected. This controls
inference size, not source playback rate; the live scheduler independently limits
inference updates and fades stale corrections.

`close()` interrupts the isolated process. Initialization has a 45-second parent
deadline; evaluation has a 25-second parent deadline and a 20-second GPU-fence
deadline. Failed processes are killed and can be recreated on the next render.
Closing the parent stdin also lets an idle worker exit. GUI OFF must remove the
overlay immediately without waiting for this method or an evaluation to finish.

## Packaging

Bundle the same tested x64 Python 3.12 runtime and pinned numpy/Pillow dependencies
used by the rest of NeuralFlow. Include hardware.py, worker.py, backend.py and
BACKEND-NOTICES.md alongside the engine. Include product.json one level above the
engine; its version participates in the benchmark cache identity. Python must
permit imports from engine and engine/vendor in its embedded path configuration.
The backend itself uses only Python's standard library plus numpy/Pillow.

Do not include tests/backend-local, an imported runtime directory, old driver DLLs,
sample captures or this laptop's cached compatibility data in public packages.
The caller source has the MIT notice recorded separately; NVIDIA binary rights
have not been established. Public installs therefore use guided local import.

On a clean Windows 11 x64 machine the app must first detect a hardware NVIDIA
adapter, a working D3D12 device and an installed NGX core, then receive a recognized
local runtime import and complete its own benchmark. This backend makes no claim
that GTX1650 success proves compatibility on another GTX/RTX model. AMD/iGPU
adapters are explicitly unavailable for this backend.

## Measured limits

The benchmark reports Windows process-local DXGI memory usage after each GPU
completion. It is not a transient peak or total-machine VRAM measurement. Before
initialization it requires at least a 512 MiB budget and 256 MiB of headroom below
85% of the budget. It stops an evaluation stream if observed usage crosses 85%.
These are protective limits, not a guarantee against all driver failures.

The installed core is used only to allocate the NGX parameter object. Core NGX
initialization is intentionally absent, matching the previously verified direct
snippet experiment. Runtime neural history resets every frame; all temporal
stabilization is implemented by NeuralFlow around that output.
