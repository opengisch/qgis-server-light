## Structure

The [QGIS-Server-Light project](https://github.com/opengisch/qgis-server-light) is made of three subparts.

| name          | description                                                               | independent from pyqgis |
|---------------|---------------------------------------------------------------------------|-------------------------|
| **exporter** | exports necesary data from a qgis project to a simple json                | ❌                       |
| **interface**     | defines all entities shipped around and may be used in 3rd party software | ✅                       |
| **worker**      | the actual rendering system which you can spawn                           | ❌                       |

!!! important
    QGIS-Server-Ligth is also a [pypi package](https://pypi.org/project/qgis-server-light/).
    This package contains only the **interface**! This way, we ensure the isolation/separation of
    the dependency to QGIS (pyqgis).

### Interface

The interface is a pure python library which is only used to define the entities which are shared between
QGIS-Server-Light and the 3rd party application through the redis queue. If you want to use QGIS-Server-Light
with your python application you can install it with `pip install qgis-server-light` and have than all items
available to talk to a QGIS-Server-Light Worker.

Consult [Usage of Interface](usage.interface.md) for details.

### Worker

The QGIS-Server-Light Worker is nothing but a renderer. It does not know what a WMS request is nor
does it know which layer it can render. All information is delivered at runtime by a
3rd party application which is not part of this stack. The current implementation chose
Redis as an intermediate broker/store where the 3rd party application can push its
requests, and they will be picked and processed by QGIS-Server-Light.

!!! important
    So to further proceed you need:

    - a QGIS installation on the same system as you want to run the QGIS-Server-Light Worker
    - a running instance of Redis
    - 3rd party application which feeds the queue (we recommend [Georama](https://docs.georama.io))

### Exporter

The Exporter is a cli tool which lets you export a QGIS Project to a handy JSON representation.

Consult [Usage of Exporter](usage.exporter.md) for details.
