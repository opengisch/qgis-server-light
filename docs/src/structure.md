QGIS-Server-Light is made of three subparts.

| name          | description                                                               | depends on pyqgis |
|---------------|---------------------------------------------------------------------------|-------------------|
| **exporter** | export necesary data from a qgis project to a simple json                 | ✅|
| **interface**     | defines all entities shipped around and may be used in 3rd party software |❌|
| **worker**      | the actual rendering system which you can spawn                           |✅|
