# NeuralFlow Preview

Experimental DLSS 5 Screen Lab — Windows 11 x64, NVIDIA-first beta.

**[Download the complete Windows installer](https://github.com/MrElectronicOps/NeuralFlow/releases/download/v0.6.0-preview.4/NeuralFlowPreviewSetup.exe)** · [Portable ZIP](https://github.com/MrElectronicOps/NeuralFlow/releases/download/v0.6.0-preview.4/NeuralFlow-Preview.zip)

Install → open **System → Complete setup** → choose a window or display.
Neural components and video tools are included. No separate component downloads.

NeuralFlow enhances a selected window or display using a local, experimental NVIDIA neural runtime and motion-stabilized residual composition. It also prepares local videos for consistent playback. It does not install native DLSS support into games, and it is not an NVIDIA product.

## Start

1. Install **NeuralFlow Preview**, or extract the complete portable ZIP and open **NeuralFlow.exe**. Keep the entire folder together.
2. Open **System → Complete setup**. One button verifies components and checks your NVIDIA GPU. The offline package includes neural components and video tools and needs no setup downloads. The standard package downloads missing components (approximately 300 MB). Allow at least 1 GB of free space. No separate DLL search or manual copying is required.
3. Wait for **Setup complete**. Only sizes that pass actual neural evaluation become selectable. Already verified components are reused when setup is repeated. **Cancel setup** stops preparation; completed components are retained so a retry can reuse them.
4. Open **Live**, choose **Application window** or **Entire display**, select the source, then enable effects. Return to the selected application. Floating controls remain accessible.
5. **F8** toggles effects. **F9** restores the original. All effects start OFF.

If the runtime is unavailable, zero neural strength allows the separate clarity and color controls to work. Protected content and HDR capture are not supported by this preview.

## Components and advanced runtime import

The standard package fetches neural files on your explicit Complete setup action from recorded community releases. The offline test package includes the exact same verified DLL pair. This uses a community-modified runtime, not an official NVIDIA release. It does not establish official GPU support or grant redistribution rights. When downloading, the upstream executable is treated only as an archive and is never executed. Archive hashes and DLL hashes must match pinned values before loading; offline imports also verify the DLL hashes.

Manual **Import neural runtime** remains available for an existing compatible local folder. The installed NVIDIA driver core is discovered locally; setup never downloads or replaces a graphics driver.

This initial backend supports one tested ABI and hash pair:

| File | SHA-256 |
| --- | --- |
| nvngx_dlssnr.dll | 8270b350cd82de5ce89806872cdd6b6a9249b80836b91bbeb3573470744cc206 |
| caller/nvngx.dll_comfy.dll | 62f38c26846c355ff2f122a1a077aa8ea3e56cac344b8d0b1724f594aeb99b9d |

Unknown files are rejected before loading. A normal official DLL with a different hash is not automatically interchangeable with this experimental build. Runtime provenance and the MIT caller-shim attribution are documented in `engine/BACKEND-NOTICES.md`. No NVIDIA license or redistribution rights are granted by NeuralFlow.

## Controls

- Neural strength controls the amount of generated detail. Lower strength does not reduce the cost of one model evaluation.
- Stability smooths the enhancement across matching motion. Higher values settle more slowly; uncertain detail fades out.
- Auto processing size selects from the sizes that passed on your GPU. Smooth uses a tighter time budget; Detail uses the largest validated size. Sizes describe the square neural input, not display resolution.
- Neural updates per second is a maximum target. Capture and GPU display update independently of slower neural inference.
- Clarity, saturation, contrast, brightness, warmth, and tone are separate finishing effects.

Moving or newly revealed details can lose the neural effect temporarily. Text and faces can change; compare with the original. No universal flicker-free or zero-latency claim is made.

## Video Studio

**Complete setup** includes Video Studio dependencies. The separate **System → Download video tools** button also remains available. Both routes download pinned, hash-verified packages from their original PyPI publishers into your application data. Nothing downloads merely by opening the app.

Choose an SDR video and a new output filename. MP4 uses high-quality H.264 and AAC audio; MKV uses lossless FFV1 video and copied audio where supported. Source frame timestamps are preserved, including variable frame rate. Every neural tile is evaluated locally. Temporal stabilization is applied to the residual, preserving the original frame geometry.

Playback preparation completes before viewing. The original and enhanced videos share playback position; only the enhanced player's audio is heard to avoid doubled sound. Fullscreen: Escape or double-click exits, Space plays/pauses, Tab switches original/enhanced. The original file is never overwritten. Cancel removes partial export data. A completed export is retained even if subsequent playback-proxy preparation fails.

Playback proxies and imported runtimes are stored under `%LOCALAPPDATA%\NeuralFlow`. These can consume disk space. Uninstalling preserves them and your rendered files. Diagnostic reports contain device/runtime details; they do not include captured pictures by default. Inspect a report before sharing it.

## Compatibility and limitations

See `COMPATIBILITY.md` for actual tests. The only physically verified neural GPU is currently the GTX 1650. Other NVIDIA cards are eligible for the local compatibility check; passing initialization alone is insufficient. AMD neural processing is unavailable.

This release is unsigned. Windows may identify it as an unrecognized app. It does not modify drivers, disable protection, inject into games, or alter game files. NeuralFlow uses capture overlays, so exclusive fullscreen and protected surfaces may not work. Capture/display and inference can use different adapters on hybrid systems; their actual selected adapters are available in diagnostics.

## Building

Requires .NET 10 SDK and the pinned dependencies in `packaging`. Run `packaging/stage-dependencies.ps1`, then `packaging/build.ps1 -Public`. The public package is self-contained for desktop app, capture host, and Python engine. Neural runtime import and video-tool download remain separate. Build the public installer with `-Public -BuildInstaller`. Existing archives are preserved, so produce a new versioned release instead of silently replacing a published ZIP.

NeuralFlow is an independent experimental project. NVIDIA and DLSS are trademarks of NVIDIA Corporation. NeuralFlow is not endorsed by or affiliated with NVIDIA.
