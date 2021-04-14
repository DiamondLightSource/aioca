import ctypes

from epicscorelibs.ca.cadef import libca

caRepeaterThread = libca.caRepeaterThread
caRepeaterThread.argtypes = [ctypes.c_void_p]

epicsThreadCreate = libca.epicsThreadCreate
epicsThreadCreate.argtypes = [
    ctypes.c_char_p,
    ctypes.c_uint,
    ctypes.c_void_p,
    ctypes.c_void_p,
]

epicsThreadGetStackSize = libca.epicsThreadGetStackSize
epicsThreadGetStackSize.argtypes = [ctypes.c_int]
epicsThreadStackMedium = 1
epicsThreadPriorityLow = 10


def carepeater():
    """Start caRepeater in a thread. Call this to silence these messages::

        **** The executable "caRepeater" couldn't be located
        **** because of errno = "No such file or directory".
        **** You may need to modify your PATH environment variable.
        **** Unable to start "CA Repeater" process.
    """
    epicsThreadCreate(
        b"CAC-repeater",
        epicsThreadPriorityLow,
        epicsThreadGetStackSize(epicsThreadStackMedium),
        caRepeaterThread,
        0,
    )
