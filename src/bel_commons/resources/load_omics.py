#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""This script loads the three -omics data sets."""

import json
import logging
import os
from typing import List

from bel_commons.manager_utils import create_omic
from bel_commons.models import Omic
from bel_commons.resources.constants import OMICS_DATA_DIR
from pybel import Manager

log = logging.getLogger(__name__)

MANIFEST_FILE_NAME = 'manifest.json'


def load_metadata(directory: str):
    """Load the manifest JSON file from this folder.

    :param directory:
    :rtype: list[dict[str,str]]
    """
    metadata_path = os.path.join(directory, 'metadata.json')
    log.info('loading metadata from %s', metadata_path)
    with open(metadata_path) as f:
        return json.load(f)


def create_omics_models(directory: str, metadata) -> List[Omic]:
    """Create multiple *-omics* models.

    :param directory:
    :param list[dict[str,str]] metadata:
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
            **omics_info,
        )
        results.append(omics)

    return results


def upload_omics_models(omics: List[Omic], manager: Manager):
    """Upload *-omics* models."""
    log.info('adding -omics models to session')
    manager.session.add_all(omics)

    log.info('committing -omics models')
    manager.session.commit()


def write_manifest(directory: str, omics: List[Omic]) -> None:
    """Write a manifest of *-omics* data."""
    manifest_path = os.path.join(directory, MANIFEST_FILE_NAME)

    log.info('generating manifest for %s', directory)
    manifest_data = [
        omic.to_json(include_id=True)
        for omic in omics
    ]

    log.info('writing manifest to %s', manifest_path)
    with open(manifest_path, 'w') as file:
        json.dump(manifest_data, file, indent=2)


def work_omics(directory: str, manager: Manager, reload: bool = False):
    """Generate models and manifest for data in the given directory.

    :param directory: Directory containing omics data and a manifest
    :param manager:
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
    upload_omics_models(omics, manager=manager)
    write_manifest(directory, omics)


def main(manager: Manager, reload: bool = False):
    """Load *-omics* models to database.

    :param bool reload: Should the experiments be reloaded?
    """
    directories = [
        os.path.join(OMICS_DATA_DIR, 'GSE28146'),
        os.path.join(OMICS_DATA_DIR, 'GSE1297'),
        os.path.join(OMICS_DATA_DIR, 'GSE63063'),
    ]

    for directory in directories:
        try:
            work_omics(directory=directory, manager=manager, reload=reload)
        except Exception:
            log.exception('failed for directory %s', directory)
            continue


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
    log.setLevel(logging.INFO)
    main(Manager())
