#!/bin/bash
# Activate virtual environment and install package
source .venv/bin/activate
pip install -e ".[dev]"
echo ""
echo "Installation complete! You can now run:"
echo "  - pytest           (run tests)"
echo "  - varta-mqtt       (run service)"
echo "  - pytest --cov     (tests with coverage)"
