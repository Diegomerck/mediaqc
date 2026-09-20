"""PyInstaller entry point with absolute package imports."""

from multiprocessing import freeze_support

from mediaqc_engine.__main__ import main

if __name__ == "__main__":
    freeze_support()
    main()
