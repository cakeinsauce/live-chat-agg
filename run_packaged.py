"""Entry point for PyInstaller-packaged builds.

Exists only so PyInstaller can bundle the launcher without breaking the
relative imports inside the ``app`` package. The real logic lives in
``app.launcher.main`` and is also runnable in dev via ``python -m app.launcher``.
"""

from app.launcher import main

if __name__ == "__main__":
    main()
