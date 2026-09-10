# NVIDIA backend provenance

NeuralFlow's installer does not contain NVIDIA neural runtime or installed driver DLLs.
An explicit Complete setup action downloads the pinned community releases listed
below and extracts only `nvngx_dlssnr.dll` and `caller/nvngx.dll_comfy.dll`.
Manual import remains available. The beta accepts only the byte-identical
runtime profile recorded in `backend.py`; unknown files are inspected but not loaded.
This profile is a community-modified runtime with an invalid original NVIDIA
signature, not an official NVIDIA release or supported native game integration.

Runtime source: https://github.com/rakanki911/DLSS5-Swapper/releases/tag/v2.2.1

Caller shim source: https://github.com/lisitskyaa/ComfyUI-DLSS5-NR/releases/tag/v0.3.0

Archive SHA-256 values and exact URLs are pinned in `runtime_setup.py` and
recorded with each automatic installation. Setup uses Windows tar to read the
Swapper archive without running its executable. It does not modify either DLL,
replace drivers, or grant rights beyond the upstream terms. These are community
download sources, not an assertion of authorization from NVIDIA.

The caller shim source and the ABI/parameter layout adapted in `worker.py` use
the following MIT license. This grants rights for that project code, not for
NVIDIA's separately provided binaries.

MIT License

Copyright (c) 2026 ComfyUI-DLSS5-NR contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
