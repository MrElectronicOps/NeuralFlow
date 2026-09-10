"""Validate the exact portable archive, including hashes and dependency boundaries."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys
import zipfile

archive = Path(sys.argv[1]).resolve()
with zipfile.ZipFile(archive) as payload:
    offline = '--offline' in sys.argv
    prefix = "NeuralFlow/" if offline else "NeuralFlow-Public/"
    names = set(payload.namelist())
    required = ("NeuralFlow.exe", "NeuralFlow.dll", "engine/service.py",
                "capture/NeuralFlow.Capture.exe", "python/python.exe",
                "licenses/SOURCES.md", "licenses/dotnet-runtime-10.0.11-LICENSE.txt")
    for name in required:
        assert prefix + name in names, name
    for name in names:
        path = PurePosixPath(name)
        assert not path.is_absolute() and ".." not in path.parts
        if not offline:
            assert not path.name.lower().startswith(("nvngx", "_nvngx", "nvcuda")) or not name.endswith(".dll")
            assert path.name != "ffmpeg.exe"
    if offline:
        for component in ('engine/bundled-runtime/nvngx_dlssnr.dll', 'engine/bundled-runtime/caller/nvngx.dll_comfy.dll', 'engine/tools/ffmpeg.exe', 'engine/vendor/av/__init__.py'):
            assert prefix + component in names, component
    checked = 0
    manifest = payload.read(prefix + "SHA256SUMS.txt").decode("ascii")
    for line in manifest.splitlines():
        expected, name = line.split("  ", 1)
        digest = hashlib.sha256(payload.read(prefix + name)).hexdigest()
        assert digest == expected, name
        checked += 1
    # The build directory must still match the app that was checked interactively.
    for name in ("NeuralFlow.exe", "NeuralFlow.dll", "engine/service.py"):
        assert payload.read(prefix + name) == (archive.parent / prefix.rstrip('/') / name).read_bytes()
result = {"passed": True, "hashed_files": checked, "archive_bytes": archive.stat().st_size,
          "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest()}
archive.with_name("portable-validation.json").write_text(json.dumps(result, indent=2))
print(json.dumps(result))
