#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""This file loads the three -omics data sets"""

import json
import logging
import os

from pybel.manager import Manager
from pybel_web.manager_utils import create_omic
from pybel_web.resources.constants import OMICS_DATA_DIR

log = logging.getLogger(__name__)

MANIFEST_FILE_NAME = 'manifest.json'


def load_metadata(directory):
    """Loads the manifest JSON file from this folder

    :param str directory:
    :rtype: list[dict[str,str]]
    """
    metadata_path = os.path.join(directory, 'metadata.json')
    log.info('loading metadata from %s', metadata_path)
    with open(metadata_path) as f:
        return json.load(f)


def create_omics_models(directory, metadata):
    """Creates multiple omics models

    :param str directory:
    :param list[dict[str,str]] metadata:
    :rtype: list[pybel_web.models.Omic]
    """
    results = []

    for omics_info in metadata:
        omics_path = os.path.join(directory, omics_info['source_name'])

        if not os.path.exists(omics_path):
            log.warning('omics file does not exist: %s', omics_path)
            continue

        log.info('creating omics from %s', omics_path)
        omics = create_omic(
            data=omics_path,
            **omics_info
        )
        results.append(omics)

    return results


def upload_omics_models(omics, manager):
    """Create a manager and upload omics models

    :param list[pybel_web.models.Omic] omics:
    :type manager: pybel.manager.Manager
    """
    log.info('adding omics models to session')
    manager.session.add_all(omics)

    log.info('committing omics models')
    manager.session.commit()


def write_manifest(directory, omics):
    """
    :param str directory:
    :param list[Omics] omics:
    """
    manifest_path = os.path.join(directory, MANIFEST_FILE_NAME)

    log.info('generating manifest for %s', directory)
    manifest_data = [
        omic.to_json(include_id=True)
        for omic in omics
    ]

    log.info('writing manifest to %s', manifest_path)
    with open(manifest_path, 'w') as file:
        json.dump(manifest_data, file, indent=2)


def work_omics(directory, connection=None, reload=False):
    """
    :param str directory: Directory containing omics data and a manifest
    :param connection: database connection string to cache, pre-built :class:`Manager`, or None to use default cache
    :type connection: Optional[str or pybel.manager.Manager]
    :param bool reload: Should the experiments be reloaded?
    """
    if not (os.path.exists(directory) and os.path.isdir(directory)):
        log.warning('directory does not exist: %s', directory)
        return

    if not reload and os.path.exists(os.path.join(directory, MANIFEST_FILE_NAME)):
        log.info('omics data already built for %s', directory)
        return

    metadata = load_metadata(directory)
    omics = create_omics_models(directory, metadata)
    upload_omics_models(omics, manager=connection)
    write_manifest(directory, omics)


def main(connection=None, reload=False):
    """Loads omics models to database

    :param connection: database connection string to cache, pre-built :class:`Manager`, or None to use default cache
    :type connection: Optional[str or pybel.manager.Manager]
    :param bool reload: Should the experiments be reloaded?
    """
    directories = [
        os.path.join(OMICS_DATA_DIR, 'GSE28146'),
        os.path.join(OMICS_DATA_DIR, 'GSE1297'),
        os.path.join(OMICS_DATA_DIR, 'GSE63063'),
    ]

    for directory in directories:
        try:
            work_omics(directory=directory, connection=connection, reload=reload)
        except Exception:
            log.exception('failed for directory %s', directory)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
    log.setLevel(logging.INFO)
    main(Manager())
