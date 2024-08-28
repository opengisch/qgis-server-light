Documentation of QGIS-Server-light
-----------------------------------


QGIS-Server-light is a python worker process which uses pyqgis
to render a set of layers into an image. It is backed by Redis
as a queue system.
All configuration happens at runtime through a lean interface.



build image locally:

```bash
docker build -t qgis-server-light:3.22-dev --target dev .
```

run image

```bash
docker run --rm -u $(id -u):$(id -g) --name qgis-server-light-dev-server -v $(pwd):/app -v ~/Downloads/project_store/:/io/themes -p 6543:6543 -e OGIS_SERVER_LIGHT_THEMES_DIR="/io/themes" qgis-server-light:3.22-dev
```

In a desktop QGIS configure new WMS source from:

```link
http://localhost:6543/forest_fires
```

Add layers as you want. Be aware some of them are not implemented yet. This should be logged on the server console.

In the moment process cant be killed through `ctrl+c`.

To kill container start a new shell and execute:

```bash
docker kill qgis-server-light-dev-server
```