QGIS-Server-Light is made of three subparts.

- **exporter** => export necesary data from a qgis project to a simple json (has deps to pyqgis)
- **interface** => defines all entities shipped around and may be used in 3rd party software (no deps to pyqgis)
- **worker** => the actual rendering system which you can spawn
