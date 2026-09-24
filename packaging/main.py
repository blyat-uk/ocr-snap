"""The bundle's entry script: <root>/src/main.py.

The launchers run `python -s -E -B -X utf8 <root>/src/main.py`; running a
script puts its folder (<root>/src) first on sys.path, so the `ocr_snap`
package next to it is what imports. (`-m ocr_snap` would need the cwd
there, and a launcher cannot choose the user's cwd.)
"""
import sys

from ocr_snap.app import main

if __name__ == "__main__":
    sys.exit(main())
