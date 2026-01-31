"""Varta Battery MQTT Service for Home Assistant."""

__version__ = "1.0.0"
__author__ = "Marius"
__description__ = "MQTT service for Varta battery integration with Home Assistant"

from .service import main

__all__ = ['main']

if __name__ == "__main__":
    main()
