import ctypes
import platform

import epicscorelibs.path

# ctypes needs a different version of LoadLibrary for each platform
system = platform.system()
if system == "Windows":
    load_library = ctypes.windll.LoadLibrary
else:
    load_library = ctypes.cdll.LoadLibrary

# Load the library provided by epicscorelibs
libca = load_library(epicscorelibs.path.get_lib("ca"))
