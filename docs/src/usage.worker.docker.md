The following sections explain how to use QGIS-Server-Light within a docker container for development purpose.

### Spin up a redis instance

```shell
docker run --rm -d -p 1234:6379 --name qsl-redis redis
```

This redis instance will be available with url: `redis://localhost:1234`

### Build QGIS-Server-Light image

In order to use QGIS-Server-Light locally as a docker container we need to build the image first:

```shell
docker build -t opengisch/qgis-server-light-dev:latest --target dev .
```

!!! note
    If you are developing this project, and you use the docker approach: This step has to be executed
    anytime you do changes on the pip dependencies.


### Spin up QGIS-Server-Light worker

So we can spin up our QGIS-Server-Light worker instance and let it connect to the redis.

!!! info
    Either one of the following sections are meant to be executed.

#### Run the worker

This section tells you how to simply start QGIS-Server-Light as built before in a container.

```shell
docker run --rm -ti --net host --name qsl opengisch/qgis-server-light-dev:latest
```

This works because QGIS-Server-Light has a default value for the connection to redis which fits redis
instance we started with the command before.

!!! note
    You can configure QGIS-Server-Light differently inside you container by setting environment variables
    with `-e <ENV_VAR>=<ENV_VALUE>` in the docker run command. See
    [instructions for local usage](usage.worker.local.md#environment-variables-available-with-make) for details.

We see several [parameters](https://docs.docker.com/reference/cli/docker/container/run/#options) here:

- `--rm` since QGIS-Server-Light does not have any persistance layer we can remove stopped containers to
  save diskspace on the longterm
- `-e` we pass the URL where QGIS-Server-Light can reach redis, this works only in conjunction with next parameter
- `--net` we tell docker to run this container on the hosts network, which gives us access to localhost and
  therefore to your running redis instance.

!!! danger
    :exclamation:  Don't use `--net host` in production or in untrusted network environment!

#### Run the worker for development

This section tells you how to start QGIS-Server-Light for development. It assumes, you are in the root of the
project directory when calling the `docker` command.

```shell
docker run --rm -ti --net host -v $(pwd):/app --name qsl opengisch/qgis-server-light-dev:latest run-reload
```

This mounts the source code directory into the container so that you can change source code locally, and it
is reflected transparently inside the container.

In addition, it starts the worker in reload mode. This means the worker process is restarted automatically
everytime you apply changes to the source code.
