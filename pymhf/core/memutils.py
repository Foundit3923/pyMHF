import ctypes
import configparser
from gc import get_referents
import logging
import sys
from types import ModuleType, FunctionType
from typing import Type, TypeVar, Optional, Iterable, Union

import pymhf.core._internal as _internal

import pymem
import pymem.pattern
import pymem.process


# Custom objects know their class.
# Function objects seem to know way too much, including modules.
# Exclude modules as well.
BLACKLIST = type, ModuleType, FunctionType


mem_logger = logging.getLogger("MemUtils")

MEM_ACCESS_R = 0x100   # Read only.
MEM_ACCESS_RW = 0x200  # Read and Write access.

BLOB_SIZE = 0x1_000_000  # 16Mb


ctypes.pythonapi.PyMemoryView_FromMemory.argtypes = (
    ctypes.c_char_p,
    ctypes.c_ssize_t,
    ctypes.c_int,
)
ctypes.pythonapi.PyMemoryView_FromMemory.restype = ctypes.py_object


# TypeVar for the map_struct so that we can correctly get the returned type to
# be the same as the input type.
CTYPES = Union[ctypes._SimpleCData, ctypes.Structure, ctypes._Pointer]
Struct = TypeVar("Struct", bound=CTYPES)

hm_cache = {}
config = configparser.ConfigParser()


def getsize(obj):
    """sum size of object & members."""
    if isinstance(obj, BLACKLIST):
        raise TypeError('getsize() does not take argument of type: ' + str(type(obj)))
    seen_ids = set()
    size = 0
    objects = [obj]
    while objects:
        need_referents = []
        for _obj in objects:
            if not isinstance(_obj, BLACKLIST) and id(_obj) not in seen_ids:
                seen_ids.add(id(_obj))
                size += sys.getsizeof(_obj)
                need_referents.append(_obj)
        objects = get_referents(*need_referents)
    try:
        _len = len(obj)
    except TypeError:
        _len = None
    return size, _len



def chunks(lst: Iterable, n: int):
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


def match(patt: bytes, input: bytes):
    """ Check whether or not the pattern matches the provided bytes. """
    for i, char in enumerate(patt):
        if not (char == b'.' or char == input[i]):
            return False
    return True


def pprint_mem(offset: int, size: int, stride: Optional[int] = None) -> str:
    # TODO: Make this print a much nicer output... It sucks right now...
    if not offset:
        # If we are passed in an offset of 0, don't even try.
        return ""
    _data = (ctypes.c_char * size).from_address(offset)
    if stride:
        result = " ".join([f"{x:02X}".upper() for x in range(stride)]) + "\n"
        for chunk in chunks(_data, stride):
            result += " ".join([f"{k:02X}".upper() for k in chunk]) + "\n"
        return "\n" + result
    else:
        return "\n" + " ".join([k.hex().upper() for k in _data])


def _hex_repr(val: int, as_hex: bool) -> str:
    if as_hex:
        return hex(val)
    else:
        return str(val)


def get_field_info(obj, logger=None, indent: int = 0, as_hex: bool = True, max_depth: int = -1):
    if indent == max_depth:
        return
    if isinstance(obj, ctypes.Structure):
        # Need to get the actual class object to iterate over its' fields:
        cls_obj = obj.__class__
        has_values = True
    elif isinstance(obj, ctypes.Array):
        cls_obj = obj[0]
        has_values = True
    else:
        try:
            if issubclass(obj, ctypes.Structure):
                cls_obj = obj
                has_values = False
            elif issubclass(obj, ctypes.Array):
                cls_obj = obj._type_
                has_values = False
            else:
                raise TypeError(f"obj {obj} must be an instance of a ctypes.Structure or a subclass.")
        except TypeError as e:
            yield obj.__mro__
            raise TypeError(f"!!! obj {obj} must be an instance of a ctypes.Structure or a subclass.") from e
    for field, field_type in cls_obj._fields_:
        if has_values:
            val = getattr(obj, field)
            # if isinstance(val, ctypes.Array):
            #     val = [x for x in val]
        field_data: ctypes._CField = getattr(cls_obj, field)
        offset = _hex_repr(field_data.offset, as_hex)
        size = _hex_repr(field_data.size, as_hex)
        if has_values and not isinstance(val, ctypes.Structure):
            msg = f"{field} ({field_type.__name__}): size: {size} offset: {offset} value: {val}"
        else:
            msg = f"{field} ({field_type.__name__}): size: {size} offset: {offset}"
        msg = indent * "  " + msg
        yield msg
        if not issubclass(field_type, (ctypes._SimpleCData, ctypes.Array, ctypes._Pointer)):
            if has_values:
                for _msg in get_field_info(val, logger, indent + 1, as_hex, max_depth):
                    yield _msg
            else:
                for _msg in get_field_info(field_type, logger, indent + 1, as_hex, max_depth):
                    yield _msg


def get_addressof(obj) -> int:
    try:
        # If it's a pointer, this is the branch that is used.
        return ctypes.cast(obj, ctypes.c_void_p).value
    except:
        # TODO: Get correct error type.
        # Otherwise fallback to the usual method.
        return ctypes.addressof(obj)


def _get_memview(offset: int, type_: Type[ctypes.Structure]) -> memoryview:
    """ Return a memoryview which covers the region of memory specified by the
    struct provided.

    Parameters
    ----------
    offset:
        The memory address to start reading the struct from.
    type_:
        The type of the ctypes.Structure to be loaded at this location.
    """
    return ctypes.pythonapi.PyMemoryView_FromMemory(
        ctypes.cast(offset, ctypes.c_char_p),
        ctypes.sizeof(type_),
        MEM_ACCESS_RW,
    )


def _get_memview_with_size(offset: int, size: int) -> Optional[memoryview]:
    """ Return a memoryview which covers the region of memory specified by the
    struct provided.

    Parameters
    ----------
    offset:
        The memory address to start reading the struct from.
    type_:
        The type of the ctypes.Structure to be loaded at this location.
    """
    if not offset:
        return None
    return ctypes.pythonapi.PyMemoryView_FromMemory(
        ctypes.cast(offset, ctypes.c_char_p),
        size,
        MEM_ACCESS_RW,
    )


def map_struct(offset: int, type_: Type[Struct]) -> Struct:
    """ Return an instance of the `type_` struct provided which shares memory
    with the provided offset.
    Note that the amount of memory to read is automatically determined by the
    size of the struct provided.

    Parameters
    ----------
    offset:
        The memory address to start reading the struct from.
    type_:
        The type of the ctypes.Structure to be loaded at this location.

    Returns
    -------
    An instance of the input type.
    """
    if not offset:
        raise ValueError("Offset is 0. This would result in a segfault or similar")
    instance = ctypes.cast(offset, ctypes.POINTER(type_))
    return instance.contents


def pattern_to_bytes(patt: str) -> bytes:
    """ Take a pattern that looks like `8C 14 23 56 ?? 12` (etc) and convert it to a bytes object which can
    be searched with pymem.
    The format is what is provided by the IDA plugin `SigMakerEx` and the `??` values indicate a wildcard.
    """
    split = patt.split(" ")
    return b"".join([f"\\x{x}".encode() if x != "??" else b"." for x in split])


def find_pattern_in_binary(
    pattern: str,
    return_multiple: bool = False,
    binary: Optional[str] = None
) -> Union[int, list[int], None]:
    if binary is None:
        binary = _internal.EXE_NAME
    if binary not in hm_cache:
        try:
            pm_process = pymem.Pymem(binary)
            handle = pm_process.process_handle
            module = pymem.process.module_from_name(handle, binary)
            hm_cache[binary] = (handle, module)
        except TypeError:
            return None
    handle, module = hm_cache[binary]
    patt = pattern_to_bytes(pattern)
    return pymem.pattern.pattern_scan_module(handle, module, patt, return_multiple=return_multiple)
