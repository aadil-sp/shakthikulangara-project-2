"""Entry point used by PyInstaller to build the stand-alone markerpilot binary."""

import multiprocessing

from markerpilot.cli import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
