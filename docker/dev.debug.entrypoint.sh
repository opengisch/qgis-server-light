set -e
[ "${DEV_AUTOSTART:-1}" = "0" ] && exec sleep infinity

if [ "${DEV_SYNC:-1}" = "1" ] && [ -f uv.lock ] && command -v uv >/dev/null; then
  uv sync
fi
exec "$@"