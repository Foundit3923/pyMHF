from ctypes import windll, create_unicode_buffer, byref, c_ulong
from configparser import ConfigParser
from typing import Optional
import pywinctl as pwc
import win32gui
import win32process
import pymem
import pprint
import logging
import pymhf.core._internal as _internal
from pymhf.core._internal import PID, EXE_NAME
import ctypes
 

def getWindowByHandle(pid, handle):
    windows = {x.getHandle(): x for x in pwc.getAllWindows()}
    if windows[handle]:
        return windows[handle]
    else:
        return None
        

def set_main_window_focus():
    #logging.info(f'{_internal.EXE_NAME}')
    pm_process = pymem.Pymem( _internal.EXE_NAME)
    main_window = getWindowByHandle(pm_process.process_id, _internal.MAIN_HWND) #Window class methods and properties detailed at https://github.com/Kalmat/PyWinCtl?tab=readme-ov-file 
    if main_window:
        main_window.activate()
    else:
        logging.info("noKey")


# def dump_resource(res, fname):
#     with open(op.join(_internal.CWD, fname), "w") as f:
#         f.write(json.dumps(res, indent=2))


def safe_assign_enum(enum, index: int):
    """ Safely try and get the enum with the associated integer value.
    If the index isn't one in the enum return the original index."""
    try:
        return enum(index)
    except ValueError:
        return index


def get_foreground_window_title() -> Optional[str]:
    hWnd = windll.user32.GetForegroundWindow()
    length = windll.user32.GetWindowTextLengthW(hWnd)
    buf = create_unicode_buffer(length + 1)
    windll.user32.GetWindowTextW(hWnd, buf, length + 1)
    
    # 1-liner alternative: return buf.value if buf.value else None
    if buf.value:
        return buf.value
    else:
        return None


def get_foreground_pid():
    handle = windll.user32.GetForegroundWindow()
    pid = c_ulong()
    windll.user32.GetWindowThreadProcessId(handle, byref(pid))
    return pid.value


def does_pid_have_focus(pid: int) -> bool:
    return pid == get_foreground_pid()


class AutosavingConfig(ConfigParser):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._filename: str
        self._encoding: Optional[str]

    def read(self, filenames, encoding=None):
        super().read(filenames, encoding)
        self._filename = filenames
        self._encoding = encoding

    def set(self, section: str, option: str, value=None):
        if value is not None:
            val = str(value)
        else:
            val = value
        try:
            super().set(section, option, val)
            with open(self._filename, "w", encoding=self._encoding) as f:
                self.write(f, space_around_delimiters=True)
        except Exception as e:
            import logging
            logging.exception(e)
