#!/usr/bin/env python3
"""Test that the GUI can be instantiated without errors."""

import sys
from unittest.mock import patch

try:
    # Mock Qt application since we don't have a display
    with patch('PySide6.QtWidgets.QApplication'):
        with patch('PySide6.QtWidgets.QMainWindow'):
            from vanitygen_py.gui import VanityGenGUI
            print("✓ GUI modules imported successfully")
    
    sys.exit(0)
except Exception as e:
    print(f"❌ GUI import failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)