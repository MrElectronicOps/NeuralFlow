"""Explicit local GPU export test; needs a legitimately imported runtime."""
import argparse
import json
import os
from pathlib import Path
import sys
import threading

ROOT = Path(os.environ.get('NEURALFLOW_TEST_PACKAGE', str(Path(__file__).resolve().parents[1])))
sys.path.insert(0, str(ROOT / "engine"))
from video import export_video
from backend import Backend
import av
import numpy as np


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--data", required=True)
    args = parser.parse_args()
    backend = Backend(args.data, runtime_dir=args.runtime)
    try:
        if not backend.status()["available"]:
            raise RuntimeError(backend.status()["error"])
        report = export_video(args.source, args.output, .7, .75, backend, threading.Event(),
                              lambda value: print(json.dumps(value), flush=True))
        differences = []
        with av.open(args.source) as source, av.open(args.output) as output:
            for original, rendered in zip(source.decode(video=0), output.decode(video=0)):
                a = original.to_ndarray(format="rgb24").astype(np.float32)
                b = rendered.to_ndarray(format="rgb24").astype(np.float32)
                differences.append(float(np.mean(np.abs(a - b))))
        assert len(differences) == report["frames"]
        assert max(differences) > 0, "Neural output did not change the test video."
        report["mean_absolute_pixel_changes"] = differences
        report["gpu"] = backend.status()["adapter"]
        report["neural_worker_log"] = str(backend.worker_log)
        report["test_type"] = "actual NVIDIA backend, short local video; visual quality not universally verified"
        result = Path(args.output).with_name(Path(args.output).name + ".gpu-test.json")
        result.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
    finally:
        backend.close()


if __name__ == "__main__":
    main()
