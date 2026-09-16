# NeuralFlow Preview 0.6.0-preview.7

Stability hardening for floating controls used while the main window is minimized:

- Only one settings request is in flight; subsequent slider changes collapse to
  the latest values instead of accumulating pending requests.
- Floating-panel drawing uses software rendering, reducing UI competition with
  GPU neural work. Neural rendering and capture continue to use the GPU.
- Engine protocol JSON documents are disposed after parsing.
- The 15-second request deadline covers waiting, writing and receiving. An
  unresponsive engine and its overlay are stopped; the main app reports that it
  needs restarting instead of indefinitely retaining the request.

The reported user freeze was not reproduced in the baseline 90-second test.
This release addresses identified stability risks and is not proof that every
freeze cause is fixed. Tests include a stalled-engine timeout, physical GTX 1650
compatibility checks, minimized floating-control stress testing, and package
integrity verification.
