## Spin up a redis instance

```shell
docker run --rm -d -p 1234:6379 --name georama-redis redis
```

This redis instance will be available with url: `redis://localhost:1234`

So we can spin up our QGIS-Server-Light instance and let it connect to the redis.

```shell
docker run --rm -e QSL_REDIS_URL=redis://localhost:1234 --net host ghcr.io/opengisch/qgis-server-light:latest
```

We see several [parameters](https://docs.docker.com/reference/cli/docker/container/run/#options) here:

- `--rm` since QGIS-Server-Light does not have any persistance layer we can remove stopped containers to
  save diskspace on the longterm
- `-e` we pass the URL where QGIS-Server-Light can reach redis, this works only in conjunction with next parameter
- `--net` we tell docker to run this container on the hosts network, which gives us access to localhost and
  therefore to your running redis instance.

!!! danger
    :exclamation:  Dont use `--net` in production or in untrusted network environment!
