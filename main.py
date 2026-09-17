"""MyAudio entry point — v1.1

Tcl/Tk has to be pointed at the copy inside the bundle BEFORE anything imports
tkinter. py2app relinks the tcl and tk dylibs into Contents/Frameworks, but it
does not bring their script libraries, and the path compiled into those dylibs
is the one on the build machine -- /opt/homebrew/Cellar/tcl-tk/... . On any
other Mac that directory does not exist and the app dies at the first Tk call
with "Cannot find a usable init.tcl". build.sh copies the two library
directories in; this tells Tcl where they went.
"""

import os
import sys

if getattr(sys, "frozen", None):
    _res = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(sys.executable))), "Resources")
    for _var, _dir in (("TCL_LIBRARY", "tcl9.0"), ("TK_LIBRARY", "tk9.0")):
        _path = os.path.join(_res, "lib", _dir)
        if os.path.isdir(_path):
            os.environ[_var] = _path

from myaudio.app import main

if __name__ == "__main__":
    main()
