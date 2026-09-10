"""Regression: exact SFX member, cancellation, and invalid archive diagnostics."""
from pathlib import Path
import sys
import tempfile
import threading
sys.path.insert(0, str(Path(sys.argv[1]).resolve() / 'engine'))
import runtime_setup as setup

with tempfile.TemporaryDirectory() as folder:
    root = Path(folder)
    cancel = threading.Event()
    cancel.set()
    try:
        setup.extract_runtime(Path(sys.argv[2]), root / 'cancelled.dll', cancel)
        raise AssertionError('Cancellation ignored')
    except setup.Cancelled:
        assert not (root / 'cancelled.dll').exists()
    cancel.clear()
    setup.extract_runtime(Path(sys.argv[2]).resolve(), root / 'verified.dll', cancel)
    assert setup.file_hash(root / 'verified.dll') == setup.PROFILE['files']['nvngx_dlssnr.dll']
    bad = root / 'bad.exe'
    bad.write_bytes(b'Invalid archive')
    try:
        setup.extract_runtime(bad, root / 'bad.dll', cancel)
        raise AssertionError('Invalid archive accepted')
    except RuntimeError as error:
        assert '7-Zip exit' in str(error), str(error)
print('PASS: pinned extraction, pre-cancel, actionable invalid archive error')
