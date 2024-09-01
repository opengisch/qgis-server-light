Driving many instances of QGIS-Server for rendering WMS maps gave us many insights of the actual needs.
Especially when it comes to deployment strategies fitting environments other than a metal server
driving your QGIS-Server, there are a bit of pitfalls here and there which are difficult to handle.

In bigger environments we deal with zero downtime requirements for PROD instances. Varying datasource
definitions dependent on the layer (not only database). Massive amount of QGIS project files
which need to be tracked for validity and content over time. We often need rollback mechanisms of deployments.
In short: Small to big environments utilizing QGIS-Server ending up often in the classic pattern of
administer => integrate => publish.

We can state, that we are perfectly able to implement this with QGIS-Server. However, it lacks several simple
patterns of automatisation and scalability.

QGIS-Server-Light tries to overcome this issues with the following main concepts:

- separate QGIS project from QGIS-Server runtime
- isolate rendering into a minuscule python process
- provide ephemeral runtime
