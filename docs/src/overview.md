## What Problems does QGIS-Server-Light solve

Dealing with QGIS based service publishing always is put around the QGIS Project.

This comes in handy when dealing with small to medium size contexts but might get a bit
tedious in the bigger/enterprise context.

1. Project has to be part of the URL in QGIS Server deployments.
2. Management of multiple projects in QGIS Server is not formalized.
3. Federated role based Project handling (Styling,Integrating,Publishing) has no place.
4. For rendering one layer as WMS the whole project has to be known.

QGIS-Server-Light separates the QGIS project structure from its content. It is
not a service itself. It is a stateless worker which gets parameters as inputs.
Depending on the parameters it can process different types jobs:

- Rendering
- Feature
- FeatureInfo
- Legend
- Processing

The interface to configure the job, is designed to be aligned to, but not exactly
copying the OGC Services/API standards on purpose.

## What are the Benefits of using QGIS-Service-Light

It is a light weight and stateless wrapper ontop of pyqgis purely written in python.

This enables it to:

- instantly boot
- combine layers from multiple projects
- stying immutable / stateless
- scale horizontally & natively with orchestration

The beforementioned job types all share the same basic idea, We call it
**Configuration-By-Wire**:

    Instead of reading layers and styles and what else is necessary to process the job
    from a QGIS project, this information is sent to the worker in the job parameters.
