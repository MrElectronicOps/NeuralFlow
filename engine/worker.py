"""Isolated D3D12 feature-18 worker. Never auto-load unrecognized user DLLs.

ABI/parameter layout adapted from ComfyUI-DLSS5-NR (MIT, 2026 contributors).
See BACKEND-NOTICES.md. All runtime paths and adapter LUID are explicit arguments.
"""
import argparse
import base64
import ctypes as C
import io
import json
import os
from pathlib import Path
import sys
import time

from hardware import guid, GUID, com, open_adapter, adapter_description, memory_info, file_version

if (Path(__file__).resolve().parent / 'vendor').is_dir():
    sys.path.insert(0, str(Path(__file__).resolve().parent / 'vendor'))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime', required=True)
    parser.add_argument('--core', required=True)
    parser.add_argument('--luid', required=True)
    parser.add_argument('--size', type=int, required=True)
    parser.add_argument('--log-dir', required=True)
    args = parser.parse_args()
    size = args.size
    if size not in (128, 160, 192, 224, 256, 320, 384, 448, 512):
        raise ValueError('Processing size is not a candidate size.')
    rt = Path(args.runtime).resolve()
    outdir = Path(args.log_dir).resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    protocol = sys.stdout
    sys.stdout = (outdir / 'worker.log').open('w', encoding='utf-8', buffering=1)
    os.chdir(rt)
    dll_dirs = [os.add_dll_directory(str(rt)), os.add_dll_directory(str(rt / 'caller')),
                os.add_dll_directory(str(Path(args.core).parent))]
    from PIL import Image
    import numpy as np

    def checked(hr, layer):
        if hr:
            raise RuntimeError(f'{layer}: 0x{hr & 0xffffffff:08x}')

    adapter = open_adapter(args.luid)
    info = adapter_description(adapter)
    if info['driver_version'] == 'unknown':
        info['driver_version'] = file_version(args.core)
    if info['vendor_id'] != 0x10de or info['software']:
        raise RuntimeError('Selected adapter is not a hardware NVIDIA adapter.')
    available = memory_info(adapter)
    if available and available['budget_bytes'] and (
        available['budget_bytes'] < 512 * 1024 * 1024 or
        available['usage_bytes'] + 256 * 1024 * 1024 > .85 * available['budget_bytes']
    ):
        raise RuntimeError('The current GPU memory budget is too small to initialize neural processing safely.')
    d3d = C.WinDLL('d3d12.dll')
    d3d.D3D12CreateDevice.argtypes = [C.c_void_p, C.c_uint, C.POINTER(GUID), C.POINTER(C.c_void_p)]
    d3d.D3D12CreateDevice.restype = C.c_long
    dev = C.c_void_p()
    hr = d3d.D3D12CreateDevice(adapter, 0xb000, C.byref(guid('189819f1-1db6-4b57-be54-1821339b85f7')), C.byref(dev))
    checked(hr, 'D3D12CreateDevice')
    nr = C.CDLL(str(rt / 'nvngx_dlssnr.dll'))
    shim = C.CDLL(str(rt / 'caller' / 'nvngx.dll_comfy.dll'))

    class Paths(C.Structure):
        _fields_ = [('Path', C.POINTER(C.c_wchar_p)), ('Length', C.c_uint)]
    class Log(C.Structure):
        _fields_ = [('Callback', C.c_void_p), ('Level', C.c_int), ('Disable', C.c_bool)]
    class FCI(C.Structure):
        _fields_ = [('Paths', Paths), ('Internal', C.c_void_p), ('Log', Log)]

    runtime_log = (outdir / 'runtime.log').open('w', encoding='utf-8', buffering=1)
    @C.CFUNCTYPE(None, C.c_char_p, C.c_int, C.c_int)
    def logger(msg, level, feature):
        runtime_log.write(f'{level} feature={feature} ' + (msg or b'').decode(errors='replace') + '\n')
    paths = (C.c_wchar_p * 1)(str(rt))
    fci = FCI(Paths(paths, 1), None, Log(C.cast(logger, C.c_void_p), 2, True))
    shim.DLSSNR_CallInit.argtypes = [C.c_void_p, C.c_ulonglong, C.c_wchar_p, C.c_void_p, C.c_int, C.c_void_p]
    shim.DLSSNR_CallInit.restype = C.c_uint
    r = shim.DLSSNR_CallInit(C.cast(nr.NVSDK_NGX_D3D12_Init_Ext, C.c_void_p), 141959980, str(rt), dev, 0x15, C.byref(fci))
    if r != 1:
        raise RuntimeError(f'Neural snippet initialization: 0x{r:08x}')
    core = C.CDLL(args.core)
    params = C.c_void_p()
    core.NVSDK_NGX_D3D12_AllocateParameters.argtypes = [C.POINTER(C.c_void_p)]
    core.NVSDK_NGX_D3D12_AllocateParameters.restype = C.c_uint
    ar = core.NVSDK_NGX_D3D12_AllocateParameters(C.byref(params))
    if ar != 1 or not params:
        raise RuntimeError(f'NGX parameter allocation: 0x{ar:08x}')

    alloc, cmd = C.c_void_p(), C.c_void_p()
    checked(com(dev, 9, C.c_long, [C.c_int, C.POINTER(GUID), C.POINTER(C.c_void_p)], 0,
                C.byref(guid('6102dee4-af59-4b09-b999-b44d73f09b24')), C.byref(alloc)), 'Command allocator')
    checked(com(dev, 12, C.c_long, [C.c_uint, C.c_int, C.c_void_p, C.c_void_p, C.POINTER(GUID), C.POINTER(C.c_void_p)],
                0, 0, alloc, None, C.byref(guid('5b160d0f-ac1b-4185-8ba8-b3ae42a5a455')), C.byref(cmd)), 'Command list')

    class Heap(C.Structure):
        _fields_ = [('Type', C.c_int), ('CPU', C.c_int), ('Pool', C.c_int), ('CreateMask', C.c_uint), ('VisibleMask', C.c_uint)]
    class Sample(C.Structure):
        _fields_ = [('Count', C.c_uint), ('Quality', C.c_uint)]
    class Desc(C.Structure):
        _fields_ = [('Dimension', C.c_int), ('Alignment', C.c_ulonglong), ('Width', C.c_ulonglong),
                    ('Height', C.c_uint), ('Depth', C.c_ushort), ('Mips', C.c_ushort), ('Format', C.c_int),
                    ('Sample', Sample), ('Layout', C.c_int), ('Flags', C.c_int)]

    def resource(desc, heap_type, state):
        hp, result = Heap(heap_type, 0, 0, 1, 1), C.c_void_p()
        checked(com(dev, 27, C.c_long, [C.POINTER(Heap), C.c_int, C.POINTER(Desc), C.c_int, C.c_void_p, C.POINTER(GUID), C.POINTER(C.c_void_p)],
                    C.byref(hp), 0, C.byref(desc), state, None, C.byref(guid('696442be-a72e-4059-bc79-5b5c98040fad')), C.byref(result)), 'GPU resource')
        return result

    textures = [resource(Desc(3, 0, size, size, 1, 1, 10, Sample(1, 0), 0, flags), 1, state)
                for state, flags in ((64, 0), (8, 4))]
    def setp(name, val, kind=C.c_int, idx=4):
        # MSVC overload order in the imported NGX parameter ABI.
        com(params, 7 - idx, None, [C.c_char_p, kind], name.encode(), val)

    for key in ('Width', 'Height', 'ColorSubrectWidth', 'ColorSubrectHeight', 'OutputSubrectWidth', 'OutputSubrectHeight'):
        setp('DLSSNR.' + key, size, C.c_uint, 3)
    for key, val in {'Enabled': 1, 'Reset': 1, 'Style': 0, 'Hint.Render.Preset': 0, 'UseAutoMask': 0,
                     'UICorrection': 0, 'DepthInverted': 1, 'ColorSubrectBaseX': 0, 'ColorSubrectBaseY': 0,
                     'OutputSubrectBaseX': 0, 'OutputSubrectBaseY': 0}.items():
        setp('DLSSNR.' + key, val)
    for key in ('Intensity', 'LocalToneStrength', 'LocalStructureStrength', 'SkinStructureStrength', 'ScalingRatio', 'MVecScaleX', 'MVecScaleY'):
        setp('DLSSNR.' + key, 1., C.c_float, 1)
    for key, texture in (('Color', textures[0]), ('Output', textures[1]), ('Backbuffer', textures[1]), ('MVec', None)):
        setp('DLSSNR.' + key, texture, C.c_void_p, 6)
    feature = C.c_void_p()
    shim.DLSSNR_CallCreate.argtypes = [C.c_void_p, C.c_void_p, C.c_int, C.c_void_p, C.POINTER(C.c_void_p)]
    shim.DLSSNR_CallCreate.restype = C.c_uint
    cr = shim.DLSSNR_CallCreate(C.cast(nr.NVSDK_NGX_D3D12_CreateFeature, C.c_void_p), cmd, 18, params, C.byref(feature))
    if cr != 1 or not feature:
        raise RuntimeError(f'Neural feature 18 creation: 0x{cr:08x}')
    runtime_log.write('NeuralFlow host: feature 18 created, non-null handle; runtime result=0x1\n')
    upload = resource(Desc(1, 0, size * size * 8, 1, 1, 1, 0, Sample(1, 0), 1, 0), 2, 0xac3)
    readback = resource(Desc(1, 0, size * size * 8, 1, 1, 1, 0, Sample(1, 0), 1, 0), 3, 0x400)

    class Transition(C.Structure):
        _fields_ = [('Resource', C.c_void_p), ('Subresource', C.c_uint), ('Before', C.c_int), ('After', C.c_int)]
    class Barrier(C.Structure):
        _fields_ = [('Type', C.c_int), ('Flags', C.c_int), ('Transition', Transition)]
    def barrier(res, before, after):
        b = Barrier(0, 0, Transition(res, 0xffffffff, before, after))
        com(cmd, 26, None, [C.c_uint, C.POINTER(Barrier)], 1, C.byref(b))
    class Footprint(C.Structure):
        _fields_ = [('Format', C.c_int), ('Width', C.c_uint), ('Height', C.c_uint), ('Depth', C.c_uint), ('Pitch', C.c_uint)]
    class Placed(C.Structure):
        _fields_ = [('Offset', C.c_ulonglong), ('Footprint', Footprint)]
    class LocUnion(C.Union):
        _fields_ = [('Placed', Placed), ('Index', C.c_uint)]
    class Location(C.Structure):
        _fields_ = [('Resource', C.c_void_p), ('Type', C.c_int), ('Data', LocUnion)]
    def loc(res, buffer=False):
        result = Location()
        result.Resource, result.Type = res, 1 if buffer else 0
        if buffer:
            result.Data.Placed = Placed(0, Footprint(10, size, size, 1, size * 8))
        return result
    def copy(dst, src):
        com(cmd, 16, None, [C.POINTER(Location), C.c_uint, C.c_uint, C.c_uint, C.POINTER(Location), C.c_void_p],
            C.byref(dst), 0, 0, 0, C.byref(src), None)
    class QueueDesc(C.Structure):
        _fields_ = [('Type', C.c_int), ('Priority', C.c_int), ('Flags', C.c_int), ('Node', C.c_uint)]
    queue, qd = C.c_void_p(), QueueDesc()
    checked(com(dev, 8, C.c_long, [C.POINTER(QueueDesc), C.POINTER(GUID), C.POINTER(C.c_void_p)],
                C.byref(qd), C.byref(guid('0ec870a6-5d7e-4c22-8cfc-5baaE07616ed')), C.byref(queue)), 'Command queue')
    fence = C.c_void_p()
    checked(com(dev, 36, C.c_long, [C.c_ulonglong, C.c_int, C.POINTER(GUID), C.POINTER(C.c_void_p)],
                0, 0, C.byref(guid('0a753dcf-c4d8-4b91-adf6-be5a60d95a76')), C.byref(fence)), 'GPU fence')
    fence_value = 0
    proof = {'adapter': info, 'core_initialized': False, 'direct_snippet_init': hex(r),
             'allocate_parameters': hex(ar), 'create_feature_18': hex(cr), 'feature_handle_nonnull': bool(feature), 'size': size}
    print(json.dumps({'ready': True, 'proof': proof}), file=protocol, flush=True)
    shim.DLSSNR_CallEvaluate.argtypes = [C.c_void_p, C.c_void_p, C.c_void_p, C.c_void_p, C.c_void_p]
    shim.DLSSNR_CallEvaluate.restype = C.c_uint
    for line in sys.stdin:
        request = json.loads(line)
        if request.get('quit'):
            break
        image = Image.open(io.BytesIO(base64.b64decode(request['image'], validate=True))).convert('RGB')
        if image.size != (size, size):
            raise ValueError('Neural input dimensions do not match the initialized size.')
        rgba = np.ones((size, size, 4), dtype=np.float16)
        rgba[:, :, :3] = np.asarray(image, dtype=np.float32) / 255
        pixels = rgba.tobytes()
        pointer = C.c_void_p()
        checked(com(upload, 8, C.c_long, [C.c_uint, C.c_void_p, C.POINTER(C.c_void_p)], 0, None, C.byref(pointer)), 'Upload map')
        C.memmove(pointer, pixels, len(pixels))
        com(upload, 9, None, [C.c_uint, C.c_void_p], 0, None)
        setp('DLSSNR.Enabled', int(request.get('enabled', True)))
        setp('DLSSNR.Reset', 1)
        barrier(textures[0], 64, 0x400)
        copy(loc(textures[0]), loc(upload, True))
        barrier(textures[0], 0x400, 64)
        barrier(textures[1], 8, 0x400)
        copy(loc(textures[1]), loc(upload, True))
        barrier(textures[1], 0x400, 8)
        start = time.perf_counter()
        er = shim.DLSSNR_CallEvaluate(C.cast(nr.NVSDK_NGX_D3D12_EvaluateFeature, C.c_void_p), cmd, feature, params, None)
        if er != 1:
            raise RuntimeError(f'Neural feature 18 evaluation: 0x{er:08x}')
        barrier(textures[1], 8, 0x800)
        copy(loc(readback, True), loc(textures[1]))
        barrier(textures[1], 0x800, 8)
        checked(com(cmd, 9, C.c_long, []), 'Close command list')
        lists = (C.c_void_p * 1)(cmd)
        com(queue, 10, None, [C.c_uint, C.POINTER(C.c_void_p)], 1, lists)
        fence_value += 1
        checked(com(queue, 14, C.c_long, [C.c_void_p, C.c_ulonglong], fence, fence_value), 'Signal GPU fence')
        deadline = time.monotonic() + 20
        while True:
            completed = com(fence, 8, C.c_ulonglong, [])
            if completed == 0xffffffffffffffff:
                raise RuntimeError('D3D12 device removed')
            if completed >= fence_value:
                break
            if time.monotonic() > deadline:
                raise TimeoutError('Neural GPU fence exceeded 20 seconds.')
            time.sleep(.002)
        elapsed = time.perf_counter() - start
        checked(com(readback, 8, C.c_long, [C.c_uint, C.c_void_p, C.POINTER(C.c_void_p)], 0, None, C.byref(pointer)), 'Readback map')
        data = C.string_at(pointer, len(pixels))
        arr = np.frombuffer(data, dtype=np.float16).reshape(size, size, 4)
        finite = bool(np.isfinite(arr).all())
        if not finite:
            raise RuntimeError('Neural output contains non-finite pixels.')
        output = Image.fromarray((np.clip(arr[:, :, :3].astype(np.float32), 0, 1) * 255).round().astype(np.uint8))
        encoded = io.BytesIO()
        output.save(encoded, format='PNG', compress_level=1)
        metrics = dict(proof, evaluate_feature_18=hex(er), readback_completed=True, finite=finite,
                       gpu_ms=elapsed * 1000, output_equals_input=data == pixels,
                       mean_absolute_rgb_difference=float(np.abs(arr[:, :, :3].astype(np.float32) - rgba[:, :, :3]).mean()),
                       memory=memory_info(adapter))
        runtime_log.write(f'NeuralFlow host: feature 18 evaluation=0x1, GPU fence={fence_value} completed, finite output; enabled={bool(request.get("enabled", True))}\n')
        com(readback, 9, None, [C.c_uint, C.c_void_p], 0, None)
        checked(com(alloc, 8, C.c_long, []), 'Reset allocator')
        checked(com(cmd, 10, C.c_long, [C.c_void_p, C.c_void_p], alloc, None), 'Reset command list')
        print(json.dumps({'ok': True, 'result': metrics, 'image': base64.b64encode(encoded.getvalue()).decode()}), file=protocol, flush=True)


if __name__ == '__main__':
    try:
        main()
    except BaseException as error:
        # stdout may have been redirected to the diagnostic log; the parent also sees process exit.
        import traceback
        traceback.print_exc(file=sys.stderr)
        raise SystemExit(1)
