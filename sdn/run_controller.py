"""Start the controller with Eventlet initialized before OS-Ken imports."""

import eventlet

eventlet.monkey_patch()

from os_ken.cmd.manager import main

if __name__ == "__main__":
    main()
