import logging
import os
import runpy

import debugpy

if os.environ.get("DEBUGPY") == "1":
    # starting the debugpy server
    debugpy.listen(("0.0.0.0", 5678))
    if os.environ.get("DEBUGPY_WAIT") == "1":
        logging.debug("debugpy: waiting for client on 5678", flush=True)
        debugpy.wait_for_client()

runpy.run_module("qgis_server_light.worker.redis", run_name="__main__", alter_sys=True)
