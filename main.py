"""MyAudio entry point — v1.2

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
    # Whichever version build.sh copied in (tcl9.0/tk9.0, tcl9.1/tk9.1, ...).
    _lib = os.path.join(_res, "lib")
    for _var, _prefix in (("TCL_LIBRARY", "tcl9."), ("TK_LIBRARY", "tk9.")):
        _found = sorted(d for d in os.listdir(_lib) if d.startswith(_prefix))
        if _found:
            os.environ[_var] = os.path.join(_lib, _found[-1])

from myaudio.app import main

if __name__ == "__main__":
    main()
