import os
import logging
from typing import List, Optional

from qgis.core import Qgis as Qgis_
from qgis.core import QgsApplication, QgsCredentials, QgsProviderRegistry


class CredentialsHelper(QgsCredentials):
    def __init__(self):
        super().__init__()
        self.setInstance(self)

    def request(self, realm, username, password, message):
        logging.warning(message)
        return True, None, None

    def requestMasterPassword(self, password, stored):
        logging.warning("Master password requested")


def Qgis(svg_paths: Optional[List[str]], log_level):
    # TODO: Is this save for rendering? Currently the image ghcr.io/opengisch/qgis-slim:3.34.8
    #   does not support
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    qgs = QgsApplication([], False)
    qgs.initQgis()
    if svg_paths:
        _svg_paths = qgs.svgPaths()
        # we do fast set algebra to always have unique list of paths
        # https://docs.python.org/3/library/stdtypes.html#frozenset.union
        qgs.setSvgPaths(list(set(_svg_paths) | set(svg_paths)))
    providers = QgsProviderRegistry.instance().pluginList().split("\n")
    logging.debug(f"Application Path: {qgs.prefixPath()}")
    logging.info(f"QGIS Version {Qgis_.version()}")
    logging.info("Found Providers:")
    for provider in providers:
        logging.info(f" - {provider}")

    if log_level == logging.DEBUG:
        logging.debug("QGIS Debugging enabled")

        def write_log_message(message, tag, level):
            logging.debug(f"{tag}({level}): {message}")

        QgsApplication.messageLog().messageReceived.connect(write_log_message)

        qgs.credentialsHelper = CredentialsHelper()

    return qgs
