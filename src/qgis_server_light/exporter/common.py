import logging
from pathlib import Path

import pgserviceparser

from qgis_server_light.exporter.extract import Exporter


def create_full_pg_service_conf(pg_service_conf: str | None = None) -> dict:
    full_pg_service_config_env = {}
    try:
        logging.info(
            "Loading pg_service configs from ENVIRONMENT variable PGSERVICEFILE:"
        )
        full_config = pgserviceparser.full_config()
        for section in full_config.sections():
            full_pg_service_config_env[section] = dict(full_config[section])
            logging.info(f"  loaded service: {section}")
    except Exception as e:
        logging.info(f"  No service config loaded")
        logging.debug(f"  {e}")
    full_pg_service_config_passed = {}
    if pg_service_conf:
        try:
            logging.info("Loading pg_service configs from passed path")
            full_config = pgserviceparser.full_config(
                conf_file_path=Path(pg_service_conf)
            )
            for section in full_config.sections():
                full_pg_service_config_passed[section] = dict(full_config[section])
                logging.info(f"  loaded service: {section}")
        except Exception as e:
            logging.info(f"  No service config loaded")
            logging.debug(f"  {e}")
    full_pg_service_config = Exporter.merge_dicts(
        full_pg_service_config_env, full_pg_service_config_passed
    )
    return full_pg_service_config
