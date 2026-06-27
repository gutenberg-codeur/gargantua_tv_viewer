#!/usr/bin/env python3
"""
Gargantua — DVB-T viewer + EPG program guide

Keyboard shortcuts:
  f / Enter : show/hide the channel panel
  m         : mute / unmute
  q         : close the active window or quit
  p / n     : previous / next channel
  ↑ / ↓     : move selection in the channel list
  ← / →     : timeshift (rewind / fast-forward in buffer)
  d         : DVB signal debug window
  e         : program guide (EPG)
"""

import sys

from PyQt6.QtWidgets import QApplication

from zapper_window import ZapperWindow


def main():
    app = QApplication(sys.argv)
    win = ZapperWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
