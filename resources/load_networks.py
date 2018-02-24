#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""This file loads the sample BEL stuff

Prerequisites
-------------
1. Must have BMS installed and set environment variable ``BMS_BASE``
"""

import json
import logging
import os

from pybel import from_path, to_pickle
from pybel.manager import Manager
from pybel_tools.io import get_corresponding_gpickle_path, iter_from_pickles_from_directory, iter_paths_from_directory
from pybel_tools.utils import enable_cool_mode
from pybel_web.manager_utils import insert_graph

log = logging.getLogger(__name__)
enable_cool_mode()

BMS_BASE = os.environ.get('BMS_BASE')

if BMS_BASE is None:
    raise RuntimeError('BMS_BASE is not set in the environment')

alzheimer_directory = os.path.join(BMS_BASE, 'aetionomy', 'alzheimers')
selventa_directory = os.path.join(BMS_BASE, 'selventa')


def ensure_pickles(directory, connection=None, **kwargs):
    """
    :param str directory:
    :param connection: database connection string to cache, pre-built :class:`Manager`, or None to use default cache
    :type connection: Optional[str or pybel.manager.Manager]
    """
    log.info('ensuring pickles in %s', directory)
    manager = Manager.ensure(connection=connection)

    for filename in iter_paths_from_directory(directory):
        path = os.path.join(directory, filename)
        gpickle_path = get_corresponding_gpickle_path(path)
        if os.path.exists(gpickle_path):
            continue

        graph = from_path(path, manager=manager, **kwargs)
        to_pickle(graph, gpickle_path)


def upload_pickles(directory, connection=None):
    """
    :param str directory:
    :param connection: database connection string to cache, pre-built :class:`Manager`, or None to use default cache
    :type connection: Optional[str or pybel.manager.Manager]
    :rtype: list[Network]
    """
    log.info('loading pickles in %s', directory)

    manager = Manager.ensure(connection=connection)

    results = []

    for graph in iter_from_pickles_from_directory(directory):
        network = insert_graph(manager, graph, public=True)
        results.append(network)

    return results


def write_manifest(directory, networks):
    """

    :param str directory:
    :param list[Network] networks:
    """
    manifest_path = os.path.join(directory, 'manifest.json')

    log.info('generating manifest for %s', directory)
    manifest_data = [
        network.to_json(include_id=True)
        for network in networks
    ]

    log.info('writing manifest to %s', manifest_path)
    with open(manifest_path, 'w') as file:
        json.dump(manifest_data, file, indent=2)


def work_directory(directory, connection=None):
    """

    :param str directory:
    :param connection: database connection string to cache, pre-built :class:`Manager`, or None to use default cache
    :type connection: Optional[str or pybel.manager.Manager]
    """
    if not (os.path.exists(directory) and os.path.isdir(directory)):
        log.warning('directory does not exist: %s', directory)
        return

    ensure_pickles(directory, connection=connection)
    networks = upload_pickles(directory, connection=connection)
    write_manifest(directory, networks)


def main():
    """Load BEL"""
    manager = Manager()

    work_directory(alzheimer_directory, connection=manager)
    # work_directory(selventa_directory, connection=manager)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
    log.setLevel(logging.INFO)
    main()
