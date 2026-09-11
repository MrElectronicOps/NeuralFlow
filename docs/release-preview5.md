# NeuralFlow Preview 0.6.0-preview.5

Failed neural compatibility checks no longer block setup of the rest of the app.
Setup clearly reports non-neural mode, keeps effects OFF, and leaves clarity and
color controls available. Neural strength is disabled until evaluation passes;
presets and floating controls preserve that restriction. Video neural strength
requires a successful 512-size test.

Completed failed tests are labeled Unavailable rather than Not tested. The first
size failure is displayed in System and all size errors remain in saved diagnostics.
Repeated setup reuses a completed check instead of retrying every failing size.
Use Check my hardware to retry explicitly; driver changes invalidate cached tests.

Validation: simulated rejected, cached-rejected, missing-NVIDIA and successful
setup paths. Physical GTX 1650 offline setup and neural size tests.

GTX 1050 neural evaluation failure has been reported by a tester. Its cause is
not confirmed without diagnostics; this release does not claim to fix Pascal
neural compatibility. AMD/Intel neural processing is unavailable. Non-neural
capture still depends on Windows and driver support and is not verified on every GPU.
