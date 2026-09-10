"""Read-only Windows adapter and installed NVIDIA runtime discovery."""
from __future__ import annotations

import ctypes as C
import os
from pathlib import Path
import re
import uuid


class GUID(C.Structure):
    _fields_ = [('data', C.c_ubyte * 16)]


def guid(value):
    return GUID((C.c_ubyte * 16).from_buffer_copy(uuid.UUID(value).bytes_le))


def com(obj, index, restype, args, *values):
    table = C.cast(obj, C.POINTER(C.POINTER(C.c_void_p))).contents
    return C.WINFUNCTYPE(restype, C.c_void_p, *args)(table[index])(obj, *values)


def release(obj):
    if obj:
        com(obj, 2, C.c_ulong, [])


class LUID(C.Structure):
    _fields_ = [('LowPart', C.c_uint32), ('HighPart', C.c_int32)]


class AdapterDesc(C.Structure):
    _fields_ = [('Description', C.c_wchar * 128), ('VendorId', C.c_uint),
                ('DeviceId', C.c_uint), ('SubSysId', C.c_uint), ('Revision', C.c_uint),
                ('DedicatedVideoMemory', C.c_size_t), ('DedicatedSystemMemory', C.c_size_t),
                ('SharedSystemMemory', C.c_size_t), ('AdapterLuid', LUID), ('Flags', C.c_uint)]


class MemoryInfo(C.Structure):
    _fields_ = [('Budget', C.c_uint64), ('CurrentUsage', C.c_uint64),
                ('AvailableForReservation', C.c_uint64), ('CurrentReservation', C.c_uint64)]


def luid_string(value):
    return f'{value.HighPart & 0xffffffff:08x}:{value.LowPart:08x}'


def factory():
    if os.name != 'nt':
        raise RuntimeError('Neural processing requires Windows 11 x64.')
    dxgi = C.WinDLL('dxgi.dll')
    fn = dxgi.CreateDXGIFactory1
    fn.argtypes = [C.POINTER(GUID), C.POINTER(C.c_void_p)]
    fn.restype = C.c_long
    result = C.c_void_p()
    hr = fn(C.byref(guid('770aae78-f26f-4dba-a829-253c83d1b387')), C.byref(result))
    if hr:
        raise RuntimeError(f'DXGI factory failed: 0x{hr & 0xffffffff:08x}')
    return result


def adapter_description(adapter):
    desc = AdapterDesc()
    hr = com(adapter, 10, C.c_long, [C.POINTER(AdapterDesc)], C.byref(desc))
    if hr:
        raise RuntimeError(f'DXGI adapter description failed: 0x{hr & 0xffffffff:08x}')
    driver = C.c_int64()
    hr = com(adapter, 9, C.c_long, [C.POINTER(GUID), C.POINTER(C.c_int64)],
             C.byref(guid('db6f6ddb-ac77-4e88-8253-819df9bbf140')), C.byref(driver))
    version = '.'.join(str((driver.value >> shift) & 0xffff) for shift in (48, 32, 16, 0)) if not hr else 'unknown'
    return {'name': desc.Description, 'luid': luid_string(desc.AdapterLuid),
            'vendor_id': desc.VendorId, 'device_id': desc.DeviceId,
            'dedicated_memory_bytes': desc.DedicatedVideoMemory,
            'shared_memory_bytes': desc.SharedSystemMemory,
            'software': bool(desc.Flags & 2), 'driver_version': version}


def enumerate_adapters():
    fac = factory()
    result = []
    try:
        index = 0
        while True:
            adapter = C.c_void_p()
            hr = com(fac, 12, C.c_long, [C.c_uint, C.POINTER(C.c_void_p)], index, C.byref(adapter))
            if hr & 0xffffffff == 0x887a0002:
                break
            if hr:
                raise RuntimeError(f'DXGI enumeration failed: 0x{hr & 0xffffffff:08x}')
            try:
                result.append(adapter_description(adapter))
            finally:
                release(adapter)
            index += 1
        return result
    finally:
        release(fac)


def open_adapter(luid):
    fac = factory()
    try:
        index = 0
        while True:
            adapter = C.c_void_p()
            hr = com(fac, 12, C.c_long, [C.c_uint, C.POINTER(C.c_void_p)], index, C.byref(adapter))
            if hr:
                break
            if adapter_description(adapter)['luid'] == luid:
                return adapter
            release(adapter)
            index += 1
    finally:
        release(fac)
    raise RuntimeError('The selected GPU is no longer available.')


def memory_info(adapter):
    a3 = C.c_void_p()
    hr = com(adapter, 0, C.c_long, [C.POINTER(GUID), C.POINTER(C.c_void_p)],
             C.byref(guid('645967a4-1392-4310-a798-8053ce3e93fd')), C.byref(a3))
    if hr:
        return None
    try:
        info = MemoryInfo()
        hr = com(a3, 14, C.c_long, [C.c_uint, C.c_int, C.POINTER(MemoryInfo)], 0, 0, C.byref(info))
        if hr:
            return None
        return {'budget_bytes': info.Budget, 'usage_bytes': info.CurrentUsage,
                'available_for_reservation_bytes': info.AvailableForReservation}
    finally:
        release(a3)


def file_version(path):
    class Fixed(C.Structure):
        _fields_ = [('value', C.c_uint32 * 13)]
    v = C.WinDLL('version.dll')
    v.GetFileVersionInfoSizeW.argtypes = [C.c_wchar_p, C.POINTER(C.c_uint)]
    v.GetFileVersionInfoSizeW.restype = C.c_uint
    v.GetFileVersionInfoW.argtypes = [C.c_wchar_p, C.c_uint, C.c_uint, C.c_void_p]
    v.VerQueryValueW.argtypes = [C.c_void_p, C.c_wchar_p, C.POINTER(C.c_void_p), C.POINTER(C.c_uint)]
    dummy = C.c_uint()
    size = v.GetFileVersionInfoSizeW(str(path), C.byref(dummy))
    if not size:
        return 'unknown'
    data = C.create_string_buffer(size)
    if not v.GetFileVersionInfoW(str(path), 0, size, data):
        return 'unknown'
    pointer, length = C.c_void_p(), C.c_uint()
    if not v.VerQueryValueW(data, '\\', C.byref(pointer), C.byref(length)):
        return 'unknown'
    values = C.cast(pointer, C.POINTER(Fixed)).contents.value
    return '.'.join(map(str, (values[2] >> 16, values[2] & 0xffff, values[3] >> 16, values[3] & 0xffff)))


def discover_core():
    """Prefer the active NVIDIA display driver's package before DriverStore fallback."""
    import winreg
    candidates = []
    class_key = r'SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}'
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, class_key) as root:
            for i in range(winreg.QueryInfoKey(root)[0]):
                child = winreg.EnumKey(root, i)
                if not child.isdigit():
                    continue
                with winreg.OpenKey(root, child) as key:
                    values = {}
                    for j in range(winreg.QueryInfoKey(key)[1]):
                        name, value, _ = winreg.EnumValue(key, j)
                        values[name.lower()] = value
                    identity = str(values.get('providername', '')) + str(values.get('matchingdeviceid', ''))
                    if 'nvidia' not in identity.lower() and 'ven_10de' not in identity.lower():
                        continue
                    for name in ('user modedrivername', 'usermodedrivername', 'installeddisplaydrivers'):
                        value = values.get(name, '')
                        items = value if isinstance(value, list) else str(value).split(',')
                        for item in items:
                            path = Path(os.path.expandvars(str(item).strip()))
                            if path.is_absolute():
                                candidates.append(path.parent / '_nvngx.dll')
    except OSError:
        pass
    system = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32'
    candidates.append(system / '_nvngx.dll')
    store = system / 'DriverStore' / 'FileRepository'
    try:
        fallback = list(store.glob('nv*.inf_amd64*/_nvngx.dll'))
        fallback.sort(key=lambda p: tuple(int(x) for x in re.findall(r'\d+', file_version(p))), reverse=True)
        candidates.extend(fallback)
    except OSError:
        pass
    for candidate in candidates:
        if candidate.is_file():
            return {'path': str(candidate.resolve()), 'version': file_version(candidate)}
    raise RuntimeError('Installed NVIDIA NGX core was not found. Install a compatible NVIDIA display driver using its normal installer.')
