"""Run actual local hardware validation; runtime path is supplied explicitly."""
import argparse
import json
from pathlib import Path
import threading
import time

from backend import Backend, Cancelled, benchmark_image, import_runtime, validate_runtime


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime', required=True)
    parser.add_argument('--data', required=True)
    parser.add_argument('--reuse-cache', action='store_true')
    args = parser.parse_args()
    backend = Backend(args.data, args.runtime)
    print(json.dumps(backend.status()), flush=True)
    if not backend.status()['available']:
        raise RuntimeError(backend.status()['error'])
    try:
        def progress(value):
            result = value.get('result', {})
            print(json.dumps({key: val for key, val in dict(value, result={
                k: result.get(k) for k in ('passed', 'gpu_ms_median', 'roundtrip_ms_median', 'error')
            }).items() if key != 'message'}), flush=True)
        report = backend.cache if args.reuse_cache and backend.cache else backend.benchmark(progress)
        assert report['complete']
        assert report['supported_sizes'], 'No neural size passed.'
        small = min(report['supported_sizes'])
        source = benchmark_image(small)
        output, metrics = backend.render(source)
        assert output.size == source.size and metrics['finite']
        process = backend.process
        process.kill()
        process.wait(timeout=5)
        recovered, recovery = backend.render(source)
        assert recovery['finite'] and recovered.size == source.size
        cancel = threading.Event()
        cancel.set()
        try:
            backend.render(source, cancel=cancel)
            raise AssertionError('Cancelled evaluation completed unexpectedly.')
        except Cancelled:
            pass
        try:
            backend.benchmark(cancel=cancel)
            raise AssertionError('Cancelled benchmark completed unexpectedly.')
        except Cancelled:
            pass
        try:
            backend.render(source.resize((129, 129)))
            raise AssertionError('Unsupported dimensions accepted.')
        except (ValueError, RuntimeError):
            pass
        reloaded = Backend(args.data, args.runtime)
        assert reloaded.status()['supported_sizes'] == report['supported_sizes']
        imported = import_runtime(args.runtime, Path(args.data) / 'import-case')
        assert imported['files'] == backend.runtime['files']
        from hardware import enumerate_adapters
        other = next((a for a in enumerate_adapters() if a['vendor_id'] != 0x10de), None)
        if other:
            unsupported = Backend(Path(args.data) / 'unsupported-adapter', args.runtime, other['luid'])
            assert not unsupported.status()['available']
            unsupported.close()
        checks = {'worker_crash_recovery': True, 'cancelled_check': True, 'cancelled_evaluation': True, 'reject_invalid_size': True,
                  'cache_reload': True, 'verified_local_import': True, 'reject_non_nvidia': bool(other),
                  'auto_smooth': reloaded.auto_size('Smooth'),
                  'auto_balanced': reloaded.auto_size('Balanced'), 'auto_detail': reloaded.auto_size('Detail'),
                  'supported_sizes': report['supported_sizes']}
        reloaded.close()
        Path(args.data, 'checks.json').write_text(json.dumps(checks, indent=2), encoding='utf-8')
        print(json.dumps({'checks': checks}), flush=True)
    finally:
        backend.close()


if __name__ == '__main__':
    main()
