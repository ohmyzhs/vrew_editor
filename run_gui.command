#!/bin/zsh
set -e
cd "${0:A:h}"
exec python3 run_gui.py
