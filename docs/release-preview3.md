# NeuralFlow Preview 0.6.0-preview.3

The complete Windows installer includes the verified neural runtime, caller shim,
Python runtime, capture helper and video tools. Open System → Complete setup to
verify components and benchmark your GPU; no component downloads are needed.

This fixes the reported “Windows could not extract the verified neural component”
setup failure by bypassing archive extraction in the complete package. The
download-based setup path now uses a pinned standalone extractor and reports
its error details instead of depending on the Windows tar version.

Validated on GTX 1650: fresh setup with Python network requests blocked (23.14 s),
all nine processing sizes, repeated setup (0.33 s), package file hashes, embedded
installer payload and a six-frame video export with full decoding, audio retained
and zero measured timestamp error. Other PCs still need testing.

Installers remain unsigned. Windows 11 x64 and an installed compatible NVIDIA
driver are required. NeuralFlow does not provide native game-integrated DLSS.
Component hash verification is not a redistribution-license clearance; upstream
terms and the included third-party notices still apply.
