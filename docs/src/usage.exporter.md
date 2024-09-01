## Generate QGIS Project config

By separating QGIS project information from the servers runtime we save a lot of headaches and be sure to
have the server know only what it should know. With that we minimize the amount of potential bugs drastically.
There is another idea embedded here. Thinking of a big amount of QGIS projects with a ton of layer in each
served by 4 instances of QGIS-Server (in a classical setup) for load balancing reasons as WMS. This means each
server has to solve several tasks (Capabilities, Rendering, LayerTree knowledge etc.). Not only that rendering
a WMS request does not need any knowledge of a tree structure but a one dimensional ordered stacking list
of layers. Serving the capabilities with lets say a permission system is not being implemented easily.

However, this comes with a downside:

* We need to extract this information from a QGIS-Project to feed the server with it at runtime to empower it
  for rendering our requested layers.

QGIS-Server-Light gives you a typed way
([python lib](src/qgis_server_light/interface)) to store extracted information of a QGIS project. This is
what you can use programmatically in your 3rd party application. In addition, it offers a
[CLI](src/qgis_server_light/exporter/cli.py) to just do a command line call to extract the information.

### Using the CLI

You can extract information of a QGIS-Project like this:

```shell
.venv/bin/python3 -m qgis_server_light.exporter.cli --project [path-to-your-project]
```

This uses the default output format `json` and does not `unify layer names` in the project.

| :exclamation:  This command writes to stdout! |
|-----------------------------------------------|

If you want to save the output to a file, you can do by:

```shell
.venv/bin/python3 -m qgis_server_light.exporter.cli --project [path-to-your-project] > project_config.json
```

#### Supported QGIS project extensions

- `qgs`
- `qgz`

#### Supported output formats

`--output_format`

- `json` (default)
- `xml`

#### Unify layer names

`--unify_layer_names_by_group`

- `False` (default)
- `True`

There is an option `unify_layer_names_by_group`. It allows you to reflect the structure of your tree in the
layer names.

Let's say you have a tree structure like that:
```
environment
├── ground_coverage
│   ├── forest
│   ├── field
│   └── lake
└── forest
```

And presume it is the layer names we see. So the short name which is the name used for exposition to WMS.
This would end up in forest being not addressable in a WMS request easily unless we would use the layer id
of QGIS project layer. But this is not so nicely read in the capabilities in the end.

So enabling this option, will produce the following names for the layers:

- `environment.forest`
- `environment.ground_coverage.forest`
- `environment.ground_coverage.field`
- `environment.ground_coverage.lake`
