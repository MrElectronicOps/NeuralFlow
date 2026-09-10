"""Portable, isolated experimental NVIDIA neural backend and capability cache."""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
from pathlib import Path
import queue
import shutil
import statistics
import struct
import subprocess
import sys
import threading
import time
import uuid

ENGINE = Path(__file__).resolve().parent
if (ENGINE / 'vendor').is_dir():
    sys.path.insert(0, str(ENGINE / 'vendor'))
from PIL import Image, ImageDraw
from hardware import enumerate_adapters, discover_core, file_version

try:
    APP_VERSION = json.loads((ENGINE.parent / 'product.json').read_text(encoding='utf-8'))['version']
except (OSError, ValueError, KeyError):
    APP_VERSION = 'development'
CANDIDATE_SIZES = (128, 160, 192, 224, 256, 320, 384, 448, 512)
PROFILE = {
    'id': 'community-nr-310.8-comfy-0.3.0',
    'files': {
        'nvngx_dlssnr.dll': '8270b350cd82de5ce89806872cdd6b6a9249b80836b91bbeb3573470744cc206',
        'caller/nvngx.dll_comfy.dll': '62f38c26846c355ff2f122a1a077aa8ea3e56cac344b8d0b1724f594aeb99b9d',
    },
    'runtime_source': 'https://github.com/rakanki911/DLSS5-Swapper/releases/tag/v2.2.1',
    'shim_source': 'https://github.com/lisitskyaa/ComfyUI-DLSS5-NR/releases/tag/v0.3.0',
}


class Cancelled(RuntimeError):
    pass


def file_hash(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as file:
        for block in iter(lambda: file.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def validate_runtime(directory):
    """Inspect bytes without loading executable code; this initial backend has one tested ABI."""
    directory = Path(directory).resolve()
    files = {}
    for relative, expected in PROFILE['files'].items():
        path = directory / relative
        if not path.is_file():
            raise RuntimeError(f'Runtime import needs {relative}. Select the folder containing both runtime components.')
        with path.open('rb') as file:
            header = file.read(64)
            if len(header) < 64 or header[:2] != b'MZ':
                raise RuntimeError(f'{relative} is not a Windows DLL.')
            offset = struct.unpack_from('<I', header, 60)[0]
            file.seek(offset)
            if file.read(6) != b'PE\0\0\x64\x86':
                raise RuntimeError(f'{relative} is not an x64 Windows DLL.')
        digest = file_hash(path)
        if digest != expected:
            raise RuntimeError(f'{relative} does not match this beta\'s tested runtime profile. It was not loaded. Expected SHA-256 {expected}.')
        files[relative] = {'sha256': digest, 'bytes': path.stat().st_size, 'version': file_version(path)}
    return {'profile': PROFILE['id'], 'directory': str(directory), 'files': files,
            'modified_runtime': True, 'official_support': False}


def import_runtime(source_dir, data_dir):
    """Copy only the two recognized local files into application data after byte verification."""
    source = Path(source_dir).resolve()
    metadata = validate_runtime(source)
    destination = Path(data_dir).resolve() / 'runtime'
    if source == destination:
        return metadata
    staging = destination.parent / ('runtime-import-' + uuid.uuid4().hex[:8])
    staging.mkdir(parents=True, exist_ok=False)
    try:
        for relative in PROFILE['files']:
            target = staging / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source / relative, target)
        validate_runtime(staging)
        if destination.exists():
            # Preserve an existing import; an identical valid import can simply be reused.
            return validate_runtime(destination)
        staging.rename(destination)
        metadata = validate_runtime(destination)
        manifest = dict(metadata, imported_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                        provenance=PROFILE, redistribution='Component verification does not grant redistribution rights.')
        (destination / 'import-manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        return metadata
    finally:
        if staging.exists():
            # This exact newly-created staging directory contains only the two files above.
            for relative in PROFILE['files']:
                (staging / relative).unlink(missing_ok=True)
            if (staging / 'caller').exists():
                (staging / 'caller').rmdir()
            staging.rmdir()


def benchmark_image(size):
    image = Image.new('RGB', (size, size), '#234760')
    draw = ImageDraw.Draw(image)
    for y in range(size):
        draw.line((0, y, size, y), fill=(24 + y * 90 // size, 40 + y * 70 // size, 85 + y * 60 // size))
    draw.rectangle((size // 8, size // 2, size * 7 // 8, size * 7 // 8), fill='#b68456')
    draw.ellipse((size // 4, size // 8, size * 3 // 4, size * 5 // 8), fill='#c89d82', outline='#3f302a', width=3)
    for i in range(5):
        x = size // 8 + i * size // 7
        draw.line((x, size // 2, x, size * 7 // 8), fill='#493726', width=2)
    return image


class Backend:
    def __init__(self, data_dir, runtime_dir=None, adapter_luid=None):
        self.data_dir = Path(data_dir).resolve()
        self.runtime_dir = Path(runtime_dir).resolve() if runtime_dir else self.data_dir / 'runtime'
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.process = None
        self.messages = None
        self.worker_size = None
        self.worker_log = None
        self.closed = False
        self.initialization_error = None
        self.adapters, self.adapter, self.core, self.runtime = [], None, None, None
        self.cache_key = None
        self.cache = None
        try:
            self.adapters = enumerate_adapters()
            compatible = [a for a in self.adapters if a['vendor_id'] == 0x10de and not a['software']]
            if adapter_luid:
                self.adapter = next((a for a in compatible if a['luid'] == adapter_luid), None)
                if not self.adapter:
                    raise RuntimeError('The selected GPU is not an available NVIDIA hardware adapter.')
            elif compatible:
                self.adapter = max(compatible, key=lambda a: a['dedicated_memory_bytes'])
            else:
                raise RuntimeError('No NVIDIA hardware adapter found. Neural processing is unavailable on this backend.')
            self.core = discover_core()
            if self.adapter['driver_version'] == 'unknown':
                self.adapter['driver_version'] = self.core['version']
            self.runtime = validate_runtime(self.runtime_dir)
            identity = {'app_version': APP_VERSION, 'adapter': self.adapter,
                        'core_version': self.core['version'], 'runtime_files': self.runtime['files']}
            self.cache_key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
            cache_file = self.data_dir / 'compatibility' / (self.cache_key + '.json')
            if cache_file.is_file():
                report = json.loads(cache_file.read_text(encoding='utf-8'))
                if report.get('cache_key') == self.cache_key and report.get('complete'):
                    self.cache = report
        except (OSError, RuntimeError, ValueError) as error:
            self.initialization_error = str(error)

    def status(self):
        return {'available': self.initialization_error is None, 'error': self.initialization_error,
                'adapter': self.adapter, 'adapters': self.adapters, 'core': self.core, 'runtime': self.runtime,
                'cache_key': self.cache_key, 'benchmark': self.cache,
                'supported_sizes': self.cache['supported_sizes'] if self.cache else [],
                'compatibility': ('Unavailable' if self.initialization_error else 'Verified' if self.cache and self.cache['supported_sizes'] else 'Not tested'),
                'backend': 'Experimental NVIDIA feature-18 image enhancement', 'official_native_dlss': False}

    def _receive(self, timeout, cancel=None):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.closed or (cancel and cancel.is_set()):
                self._stop_worker()
                raise Cancelled('Neural operation cancelled.')
            try:
                message = self.messages.get(timeout=.05)
            except queue.Empty:
                if self.process is None or self.process.poll() is not None:
                    detail = ''
                    if self.worker_log:
                        try:
                            detail = (self.worker_log / 'errors.log').read_text(encoding='utf-8', errors='replace')[-2400:]
                        except OSError:
                            pass
                    self._stop_worker()
                    raise RuntimeError('Neural worker exited. ' + detail)
                continue
            if message.get('error'):
                self._stop_worker()
                raise RuntimeError(message['error'])
            return message
        self._stop_worker()
        raise TimeoutError(f'Neural worker did not respond within {timeout:g} seconds.')

    def _start_worker(self, size, cancel=None):
        if self.initialization_error:
            raise RuntimeError(self.initialization_error)
        if self.closed:
            raise RuntimeError('Neural backend is closed.')
        if self.process and self.process.poll() is None and self.worker_size == size:
            return
        self._stop_worker()
        # Re-verify the selected bytes before each new process, including after a runtime import.
        validate_runtime(self.runtime_dir)
        self.worker_log = self.data_dir / 'logs' / (time.strftime('%Y%m%d-%H%M%S') + '-' + str(size) + '-' + uuid.uuid4().hex[:6])
        self.worker_log.mkdir(parents=True, exist_ok=True)
        errors = (self.worker_log / 'errors.log').open('w', encoding='utf-8')
        executable = Path(sys.executable)
        if executable.name.lower() == 'pythonw.exe':
            executable = executable.with_name('python.exe')
        try:
            self.process = subprocess.Popen([str(executable), '-u', str(ENGINE / 'worker.py'), '--runtime', str(self.runtime_dir),
                '--core', self.core['path'], '--luid', self.adapter['luid'], '--size', str(size), '--log-dir', str(self.worker_log)],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors, text=True, encoding='utf-8',
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), cwd=str(ENGINE))
        finally:
            errors.close()
        self.worker_size = size
        messages = self.messages = queue.Queue()
        pipe = self.process.stdout
        def reader():
            try:
                for line in pipe:
                    try:
                        messages.put(json.loads(line))
                    except ValueError:
                        pass
            except (OSError, ValueError):
                pass
        threading.Thread(target=reader, daemon=True, name='NeuralFlow worker messages').start()
        if not self._receive(45, cancel).get('ready'):
            self._stop_worker()
            raise RuntimeError('Neural worker did not return initialization proof.')

    def _evaluate(self, image, enabled=True, cancel=None):
        if image.mode != 'RGB' or image.width != image.height or image.width not in CANDIDATE_SIZES:
            raise ValueError('Neural input must be an RGB square at a supported candidate size.')
        self._start_worker(image.width, cancel)
        encoded = io.BytesIO()
        image.save(encoded, format='PNG', compress_level=1)
        start = time.perf_counter()
        try:
            self.process.stdin.write(json.dumps({'image': base64.b64encode(encoded.getvalue()).decode(), 'enabled': bool(enabled)}) + '\n')
            self.process.stdin.flush()
            response = self._receive(25, cancel)
        except (OSError, AttributeError) as error:
            self._stop_worker()
            raise RuntimeError('The neural worker disconnected.') from error
        if not response.get('ok'):
            self._stop_worker()
            raise RuntimeError('Neural evaluation failed.')
        metrics = response['result']
        required = metrics.get('evaluate_feature_18') == '0x1' and metrics.get('finite') and metrics.get('readback_completed')
        if not required:
            self._stop_worker()
            raise RuntimeError('Neural evaluation proof or finite output is missing.')
        output = Image.open(io.BytesIO(base64.b64decode(response['image'], validate=True))).convert('RGB')
        if output.size != image.size:
            raise RuntimeError('Neural output dimensions are invalid.')
        metrics['roundtrip_ms'] = (time.perf_counter() - start) * 1000
        metrics['log_dir'] = str(self.worker_log)
        memory = metrics.get('memory')
        if memory and memory['budget_bytes'] and memory['usage_bytes'] > .85 * memory['budget_bytes']:
            self._stop_worker()
            raise RuntimeError('Neural GPU memory usage exceeded 85% of the current Windows budget.')
        return output, metrics

    def render(self, image, cancel=None):
        with self.lock:
            # Render can run before a full benchmark, but never at a size already known to fail.
            if self.cache and image.width not in self.cache['supported_sizes']:
                raise RuntimeError('This processing size did not pass the compatibility benchmark.')
            return self._evaluate(image, cancel=cancel)

    def benchmark(self, progress=None, cancel=None):
        cancel = cancel or threading.Event()
        with self.lock:
            if self.initialization_error:
                raise RuntimeError(self.initialization_error)
            report = {'app_version': APP_VERSION, 'cache_key': self.cache_key, 'adapter': self.adapter,
                      'core': self.core, 'runtime': self.runtime, 'results': [], 'supported_sizes': [],
                      'complete': False, 'started_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                      'memory_measurement': 'Windows process-local DXGI usage sampled after completed evaluation; transient peak is not measured.'}
            try:
                for index, size in enumerate(CANDIDATE_SIZES):
                    if cancel.is_set():
                        raise Cancelled('Compatibility check cancelled.')
                    if progress:
                        progress({'phase': 'benchmark', 'size': size, 'index': index, 'total': len(CANDIDATE_SIZES), 'message': f'Testing {size} neural processing…'})
                    entry = {'size': size, 'passed': False}
                    try:
                        source = benchmark_image(size)
                        disabled, disabled_metrics = self._evaluate(source, enabled=False, cancel=cancel)
                        identity = disabled.tobytes() == source.tobytes() and disabled_metrics['output_equals_input']
                        trials = []
                        for _ in range(4):
                            output, metrics = self._evaluate(source, cancel=cancel)
                            trials.append(metrics)
                        changed = output.tobytes() != source.tobytes() and metrics['mean_absolute_rgb_difference'] > 0
                        entry.update(passed=bool(identity and changed), disabled_exact=identity, enabled_changed=changed,
                                     gpu_ms_median=statistics.median(m['gpu_ms'] for m in trials[1:]),
                                     roundtrip_ms_median=statistics.median(m['roundtrip_ms'] for m in trials[1:]),
                                     observed_process_gpu_bytes=max((m.get('memory') or {}).get('usage_bytes', 0) for m in trials),
                                     proof=metrics, trials=trials)
                        if not entry['passed']:
                            entry['error'] = 'Identity or changed-output validation failed.'
                    except Cancelled:
                        raise
                    except Exception as error:
                        entry['error'] = str(error)
                        entry['log_dir'] = str(self.worker_log) if self.worker_log else None
                    finally:
                        self._stop_worker()
                    report['results'].append(entry)
                    if entry['passed']:
                        report['supported_sizes'].append(size)
                    if progress:
                        progress({'phase': 'benchmark-result', 'size': size, 'index': index + 1,
                                  'total': len(CANDIDATE_SIZES), 'passed': entry['passed'], 'result': entry})
                report['complete'] = True
                folder = self.data_dir / 'compatibility'
                folder.mkdir(exist_ok=True)
                destination = folder / (self.cache_key + '.json')
                temporary = folder / (self.cache_key + '.tmp')
                temporary.write_text(json.dumps(report, indent=2), encoding='utf-8')
                temporary.replace(destination)
                self.cache = report
                return report
            finally:
                self._stop_worker()

    def auto_size(self, preset='Balanced'):
        supported = self.cache['supported_sizes'] if self.cache else []
        if not supported:
            raise RuntimeError('Run the hardware compatibility check before selecting Auto.')
        entries = [r for r in self.cache['results'] if r['passed']]
        if str(preset).lower() == 'detail':
            return max(supported)
        target_ms = 225 if str(preset).lower() == 'smooth' else 250
        eligible = [r['size'] for r in entries if r['roundtrip_ms_median'] <= target_ms]
        return max(eligible) if eligible else min(entries, key=lambda r: r['roundtrip_ms_median'])['size']

    def _stop_worker(self):
        process, self.process = self.process, None
        self.worker_size = None
        if not process:
            return
        try:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=3)
        except (OSError, subprocess.TimeoutExpired):
            pass
        for pipe in (process.stdin, process.stdout):
            if pipe:
                try:
                    pipe.close()
                except OSError:
                    pass

    def close(self):
        self.closed = True
        self._stop_worker()
