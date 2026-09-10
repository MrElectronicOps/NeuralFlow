"""Optional video dependencies installed directly from their upstream publisher.

Public NeuralFlow packages omit these FFmpeg binaries. Installation is an
explicit UI action; downloads are pinned and checked against PyPI SHA-256.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sys
import tempfile
import urllib.parse
import urllib.request
import zipfile

ENGINE = Path(__file__).resolve().parent
PACKAGES = (
    ("av", "18.1.0", "av-18.1.0-cp311-abi3-win_amd64.whl"),
    ("imageio-ffmpeg", "0.6.0", "imageio_ffmpeg-0.6.0-py3-none-win_amd64.whl"),
)


class MediaInstallCancelled(RuntimeError):
    pass


def _check(cancel):
    if cancel.is_set():
        raise MediaInstallCancelled("Video tool installation cancelled.")


def configure_media_tools(data_dir):
    directory = Path(data_dir).resolve() / "media-tools"
    if (directory / "av").is_dir() and str(directory) not in sys.path:
        sys.path.insert(0, str(directory))
    ffmpeg = directory / "tools" / "ffmpeg.exe"
    if ffmpeg.is_file():
        os.environ["NEURALFLOW_FFMPEG"] = str(ffmpeg)
    return media_tools_status(data_dir)


def media_tools_status(data_dir):
    directory = Path(data_dir).resolve() / "media-tools"
    ffmpeg = (directory / "tools" / "ffmpeg.exe")
    bundled = ENGINE / "tools" / "ffmpeg.exe"
    configured = os.environ.get("NEURALFLOW_FFMPEG")
    have_ffmpeg = ffmpeg.is_file() or bundled.is_file() or bool(configured and Path(configured).is_file()) or bool(shutil.which("ffmpeg"))
    have_av = (directory / "av" / "__init__.py").is_file() or importlib.util.find_spec("av") is not None
    return {"available": bool(have_av and have_ffmpeg), "directory": str(directory),
            "needs_install": not (have_av and have_ffmpeg),
            "source": "PyPI: PyAV 18.1.0 and imageio-ffmpeg 0.6.0",
            "message": "Video tools ready" if have_av and have_ffmpeg else "Install video tools to render and prepare video playback."}


def _request(url):
    request = urllib.request.Request(url, headers={"User-Agent": "NeuralFlow/0.6 (explicit video tools installer)"})
    return urllib.request.urlopen(request, timeout=30)


def _safe_member(name):
    path = PurePosixPath(name)
    return bool(name) and not path.is_absolute() and ".." not in path.parts and "\\" not in name and ":" not in name


def install_video_tools(data_dir, cancel, progress):
    directory = Path(data_dir).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / "media-tools"
    if target.exists():
        status = configure_media_tools(data_dir)
        if status["available"]:
            return status
        raise RuntimeError("A partial video tools folder already exists. Rename it before installing again: " + str(target))
    _check(cancel)
    manifests = []
    with tempfile.TemporaryDirectory(prefix="media-tools-install-", dir=str(directory)) as temporary:
        temporary = Path(temporary)
        stage = temporary / "complete"
        stage.mkdir()
        for index, (project, version, filename) in enumerate(PACKAGES):
            _check(cancel)
            progress({"stage": "downloading", "message": f"Downloading video tools ({index + 1}/{len(PACKAGES)})", "percent": index * 50})
            with _request(f"https://pypi.org/pypi/{project}/{version}/json") as response:
                metadata = json.load(response)
            asset = next((item for item in metadata["urls"] if item["filename"] == filename), None)
            if not asset:
                raise RuntimeError("The pinned upstream video package is unavailable: " + filename)
            url = asset["url"]
            parsed = urllib.parse.urlparse(url)
            if parsed.scheme != "https" or parsed.hostname != "files.pythonhosted.org":
                raise RuntimeError("The upstream package did not use the expected download host.")
            archive = temporary / filename
            digest = hashlib.sha256()
            received = 0
            with _request(url) as response, archive.open("xb") as output:
                while True:
                    _check(cancel)
                    block = response.read(1024 * 1024)
                    if not block:
                        break
                    output.write(block)
                    digest.update(block)
                    received += len(block)
                    if received > 200 * 1024 * 1024:
                        raise RuntimeError("The video package exceeded the allowed download size.")
                    progress({"stage": "downloading", "message": f"Downloading {project} · {received // (1024 * 1024)} MB",
                              "percent": index * 50 + min(48, 48 * received / max(1, asset["size"]))})
            if digest.hexdigest() != asset["digests"]["sha256"] or received != asset["size"]:
                raise RuntimeError("The downloaded video package failed its published SHA-256 or size check.")
            with zipfile.ZipFile(archive) as package:
                members = package.infolist()
                if sum(member.file_size for member in members) > 750 * 1024 * 1024:
                    raise RuntimeError("The video package expands beyond the allowed size.")
                for member in members:
                    _check(cancel)
                    if not _safe_member(member.filename):
                        raise RuntimeError("The video package contained an unsafe file path.")
                    mode = member.external_attr >> 16
                    if mode & 0o170000 == 0o120000:
                        raise RuntimeError("The video package contained a symbolic link.")
                    if member.is_dir():
                        continue
                    parts = PurePosixPath(member.filename).parts
                    relative = None
                    if project == "av" and parts[0] in ("av", "av.libs", "av-18.1.0.dist-info"):
                        relative = Path(*parts)
                    elif project == "imageio-ffmpeg":
                        if member.filename == "imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v7.1.exe":
                            relative = Path("tools/ffmpeg.exe")
                        elif parts[0] == "imageio_ffmpeg-0.6.0.dist-info":
                            relative = Path("notices", *parts)
                    if relative is None:
                        continue
                    destination = stage / relative
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with package.open(member) as source, destination.open("xb") as output:
                        shutil.copyfileobj(source, output)
            manifests.append({"project": project, "version": version, "filename": filename, "url": url,
                              "sha256": digest.hexdigest(), "published_hash_verified": True,
                              "publisher_metadata": f"https://pypi.org/pypi/{project}/{version}/json"})
        if not (stage / "av" / "__init__.py").is_file() or not (stage / "tools" / "ffmpeg.exe").is_file():
            raise RuntimeError("The upstream video packages did not contain the expected files.")
        (stage / "install-manifest.json").write_text(json.dumps(manifests, indent=2), encoding="utf-8")
        _check(cancel)
        stage.rename(target)
    status = configure_media_tools(data_dir)
    progress({"stage": "ready", "message": "Video tools installed", "percent": 100})
    return status


# Short service-facing names.
install = install_video_tools
status = media_tools_status
configure = configure_media_tools
