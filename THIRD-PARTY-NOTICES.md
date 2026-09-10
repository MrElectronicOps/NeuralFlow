# NeuralFlow third-party components

NeuralFlow is an independent experimental project. NVIDIA and DLSS are
trademarks of NVIDIA Corporation. NeuralFlow is not endorsed by or affiliated
with NVIDIA. NVIDIA neural runtime files and the community caller shim are
**not included** in either package. Complete setup downloads the pinned compatible
files from their recorded community releases on explicit user request; manual
import is also available. Automatic retrieval does not grant additional rights
to those binaries or imply NVIDIA authorization.
See `engine/BACKEND-NOTICES.md` for their provenance and hash policy.

## Components included in the public preview

- CPython 3.12.10 embeddable x64 — Python Software Foundation license.
  The original `python/LICENSE.txt` is included. The archive SHA-256 is verified
  against the official python.org SPDX manifest, recorded in
  `engine/tools/dependency-manifest.json`.
- NumPy 2.2.6 — BSD-3-Clause and bundled numerical-library notices. Retained in
  `engine/vendor/numpy-2.2.6.dist-info` and the corresponding library folders.
- Pillow 11.3.0 — HPND and bundled third-party notices. Retained in
  `engine/vendor/pillow-11.3.0.dist-info`.
- OpenCV headless 4.12.0.88 — Apache-2.0 plus third-party notices retained in
  `engine/vendor/opencv_python_headless-4.12.0.88.dist-info`. The optional FFmpeg
  video-I/O plugin is excluded from the public package. NeuralFlow uses OpenCV
  for optical flow and image transforms; video decoding is provided separately.
- .NET 10.0.11 runtime and Windows Desktop runtime — MIT licenses and the
  runtime, WPF and Windows Forms third-party notices are retained in `licenses/`.
- Vortice.Direct3D11, Vortice.D3DCompiler, Vortice.DXGI and Vortice.DirectX
  3.8.1, plus Vortice.Mathematics 2.0.0 — MIT. Exact upstream notices from the
  package repository commits are retained in `licenses/`.
- SharpGen.Runtime and SharpGen.Runtime.COM 2.4.2-beta — MIT. The upstream
  license and package copyright declarations are retained in `licenses/`.
- C#/WinRT runtime 2.2.0 — Microsoft MIT license and its upstream notice are
  retained in `licenses/`. The Windows SDK .NET projection package
  10.0.22621.57's linked SDK license is retained in its original RTF format.

`licenses/SOURCES.md` records the source package versions, pinned upstream
commits, download URLs and included filenames. `licenses/SHA256SUMS.txt`
records the staged notice file hashes. These accompany both the portable
application and the application payload embedded in the installer.

## Optional video tools installed by the user

The public preview excludes PyAV, its bundled FFmpeg libraries, the standalone
FFmpeg executable, and OpenCV's optional FFmpeg plugin. The System screen offers
an explicit **Install video tools** action that retrieves these exact packages
directly from their upstream PyPI publishers into the user's application data:

- PyAV 18.1.0, `av-18.1.0-cp311-abi3-win_amd64.whl`:
  https://pypi.org/project/av/18.1.0/
- imageio-ffmpeg 0.6.0, `imageio_ffmpeg-0.6.0-py3-none-win_amd64.whl`:
  https://pypi.org/project/imageio-ffmpeg/0.6.0/

The installer checks each exact filename, size and SHA-256 against the
publisher's PyPI metadata and records a local installation manifest. Package
license files remain with the installation. No video tools are downloaded on
application launch. Installation can be cancelled.

PyAV's wrapper is BSD-3-Clause. Its selected FFmpeg build reports LGPLv3+, but
the upstream build patch changes the configuration classification of x264 and
x265. That banner alone is not treated as proof of redistribution rights for
all codec components. The separate FFmpeg 7.1 Gyan essentials executable reports
GPLv3+. These binaries therefore remain user-installed in the public preview.

Exact build-reference records:
https://github.com/PyAV-Org/pyav-ffmpeg/tree/8.1.2-1 and
https://github.com/GyanD/codexffmpeg/releases/tag/7.1 .

## Local development package

`NeuralFlow-LocalPreview.zip` retains locally installed video dependencies for
development and testing and is marked `LOCAL-ONLY.txt`. It is not the public
distribution. `NeuralFlow-Preview.zip` is built using the public exclusions
above. Complete corresponding source materials for the locally bundled media
codec builds have not been assembled, and no completed redistribution audit is
claimed for that local archive.
