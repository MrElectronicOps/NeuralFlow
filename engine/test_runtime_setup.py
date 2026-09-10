import hashlib
import io
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import runtime_setup as setup


class Response(io.BytesIO):
    def geturl(self):
        return 'https://release-assets.githubusercontent.com/test'


class SetupTests(unittest.TestCase):
    def test_pre_cancel_does_not_create_data(self):
        with tempfile.TemporaryDirectory() as folder:
            data=Path(folder)/'data';cancel=threading.Event();cancel.set()
            with self.assertRaises(setup.Cancelled):setup.install(data,cancel,lambda _:None)
            self.assertFalse(data.exists())

    def test_hash_mismatch_rejected(self):
        asset={'url':'https://github.com/test','size':3,'sha256':'0'*64}
        with tempfile.TemporaryDirectory() as folder, patch.object(setup.urllib.request,'urlopen',return_value=Response(b'bad')):
            with self.assertRaisesRegex(RuntimeError,'SHA-256'):
                setup.download(asset,Path(folder)/'part',threading.Event(),lambda _:None)

    def test_oversized_download_rejected(self):
        asset={'url':'https://github.com/test','size':2,'sha256':'0'*64}
        with tempfile.TemporaryDirectory() as folder, patch.object(setup.urllib.request,'urlopen',return_value=Response(b'bad')):
            with self.assertRaisesRegex(RuntimeError,'size'):
                setup.download(asset,Path(folder)/'part',threading.Event(),lambda _:None)

    def test_download_cancel(self):
        body=b'a'*(2*1024*1024);cancel=threading.Event()
        asset={'url':'https://github.com/test','size':len(body),'sha256':hashlib.sha256(body).hexdigest()}
        with tempfile.TemporaryDirectory() as folder, patch.object(setup.urllib.request,'urlopen',return_value=Response(body)):
            with self.assertRaises(setup.Cancelled):
                setup.download(asset,Path(folder)/'part',cancel,lambda _:cancel.set())

    def test_failed_install_cleans_temporary_download(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(setup,'download',side_effect=RuntimeError('offline')):
            with self.assertRaisesRegex(RuntimeError,'offline'):
                setup.install(folder,threading.Event(),lambda _:None)
            self.assertEqual(list(Path(folder).iterdir()),[])


if __name__=='__main__':unittest.main()
