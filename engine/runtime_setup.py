"""Explicit upstream component setup. Never executes a downloaded installer."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import urllib.request
import zipfile

from backend import PROFILE, Cancelled, file_hash, import_runtime, validate_runtime

ASSETS = (
    {"name": "DLSS5-Swapper-2.2.1-portable.exe", "size": 241904124,
     "url": "https://github.com/rakanki911/DLSS5-Swapper/releases/download/v2.2.1/DLSS5-Swapper-2.2.1-portable.exe",
     "sha256": "10c2e7877039ab5227cca3502dd85fcf561f3cdcaf2c311a7b3c6a768e99db13"},
    {"name": "ComfyUI-DLSS5-NR-v0.3.0-windows-x64.zip", "size": 176746,
     "url": "https://github.com/lisitskyaa/ComfyUI-DLSS5-NR/releases/download/v0.3.0/ComfyUI-DLSS5-NR-v0.3.0-windows-x64.zip",
     "sha256": "3b7d52507a5548d10c3f60f9a5ea4cc5eb2fd9bd715b536533df55887a1d907f"},
)


def check(cancel):
    if cancel.is_set():
        raise Cancelled("Setup cancelled. Verified components already installed are preserved.")


def download(asset, destination, cancel, progress):
    """A pinned release digest and size must match before any file is used."""
    check(cancel)
    digest = hashlib.sha256()
    received = 0
    request = urllib.request.Request(asset["url"], headers={"User-Agent": "NeuralFlow explicit component setup"})
    with urllib.request.urlopen(request, timeout=30) as source, destination.open("xb") as output:
        if not source.geturl().startswith("https://"):
            raise RuntimeError("Component download did not use HTTPS.")
        while True:
            check(cancel)
            block = source.read(1024 * 1024)
            if not block:
                break
            received += len(block)
            if received > asset["size"]:
                raise RuntimeError("Upstream component exceeded its pinned size.")
            output.write(block)
            digest.update(block)
            progress({"message": f"Downloading neural components · {received // 1048576} / {asset['size'] // 1048576} MB"})
    if received != asset["size"] or digest.hexdigest() != asset["sha256"]:
        raise RuntimeError("Upstream component failed its pinned SHA-256 check. Nothing was loaded.")


def extract_runtime(archive, destination, cancel):
    check(cancel)
    # Use our pinned extractor, independently of the Windows tar version.
    tar = Path(__file__).resolve().parent / "tools/archive/7zr.exe"
    if not tar.is_file():
        raise RuntimeError("The bundled archive extractor is missing. Reinstall NeuralFlow.")
    if file_hash(tar) != "ad4c82fadcbdf93c03b4fc440f300509c7d60c5c2f4d183e35d9d70d6957037d":
        raise RuntimeError("The bundled archive extractor failed verification. Reinstall NeuralFlow.")
    with destination.open("xb") as output, tempfile.TemporaryFile() as errors:
        process = subprocess.Popen([str(tar), "x", "-so", "-y", str(archive),
                                    "resources/payload/streamline/nvngx_dlssnr.dll"],
                                   stdout=output, stderr=errors, creationflags=subprocess.CREATE_NO_WINDOW)
        deadline = time.monotonic() + 120
        try:
            while process.poll() is None:
                check(cancel)
                if time.monotonic() > deadline:
                    raise RuntimeError("Runtime extraction timed out. Retry Complete setup.")
                time.sleep(.05)
            if process.returncode:
                errors.seek(0)
                detail = errors.read(4096).decode("utf-8", errors="replace").strip()
                raise RuntimeError(f"Neural component extraction failed (7-Zip exit {process.returncode}): {detail}")
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
    if file_hash(destination) != PROFILE["files"]["nvngx_dlssnr.dll"]:
        raise RuntimeError("Extracted neural runtime did not match the tested profile.")


def install(data_dir, cancel, progress):
    data = Path(data_dir).resolve()
    check(cancel)
    if (data / "runtime").exists():
        return validate_runtime(data / "runtime")
    data.mkdir(parents=True, exist_ok=True)
    bundled = Path(__file__).resolve().parent / "bundled-runtime"
    if bundled.exists():
        progress({"message": "Verifying bundled neural components (no download)…"})
        validate_runtime(bundled)
        check(cancel)
        result = import_runtime(bundled, data)
        (data / "runtime/setup-sources.json").write_text(json.dumps({
            "assets": ASSETS, "profile": PROFILE["id"], "method": "bundled-offline",
            "official_nvidia_support": False,
        }, indent=2), encoding="utf-8")
        return result
    if shutil.disk_usage(data).free < 1024 ** 3:
        raise RuntimeError('Complete setup needs at least 1 GB of free disk space.')
    with tempfile.TemporaryDirectory(prefix="component-setup-", dir=data) as temporary:
        temporary = Path(temporary)
        stage = temporary / "runtime"
        (stage / "caller").mkdir(parents=True)
        for asset in ASSETS:
            download(asset, temporary / asset["name"], cancel, progress)
        progress({"message": "Verifying and installing neural components…"})
        extract_runtime(temporary / ASSETS[0]["name"], stage / "nvngx_dlssnr.dll", cancel)
        with zipfile.ZipFile(temporary / ASSETS[1]["name"]) as archive:
            members = [m for m in archive.infolist() if m.filename.endswith("/runtime/caller/nvngx.dll_comfy.dll")]
            if len(members) != 1 or members[0].file_size != 103936:
                raise RuntimeError("Caller package does not contain the expected component.")
            with archive.open(members[0]) as source, (stage / "caller/nvngx.dll_comfy.dll").open("xb") as output:
                shutil.copyfileobj(source, output)
        validate_runtime(stage)
        check(cancel)
        result = import_runtime(stage, data)
        (data / "runtime/setup-sources.json").write_text(json.dumps({
            "assets": ASSETS, "profile": PROFILE["id"],
            "method": "Downloaded from community upstream releases on explicit user request; archive and DLL hashes verified. No third-party installer executed.",
            "official_nvidia_support": False,
        }, indent=2), encoding="utf-8")
        return result
