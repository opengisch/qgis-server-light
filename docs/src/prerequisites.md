QGIS-Server-light is nothing but a renderer. It does not know what a WMS request is nor
does it know which layer it can render. All information is delivered at runtime by a
3rd party application which is not part of this stack. The current implementation chose
Redis as an intermediate broker/store where the 3rd party application can push its
requests, and they will be picked and processed by QGIS-Server-Light.

So to further proceed you need a running instance of Redis. If you want to feed QGIS-Server-Light
with actual rendering jobs you will need an application which puts jobs in the redis queue.
