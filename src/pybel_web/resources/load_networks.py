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
import time

import pybel
from pybel import from_path, from_pickle, to_pickle
from pybel.manager import Manager
from pybel.struct.mutation import strip_annotations
from pybel_tools.io import get_corresponding_gpickle_path, iter_from_pickles_from_directory, iter_paths_from_directory
from pybel_tools.utils import enable_cool_mode
from pybel_web.external_managers import (
    chebi_manager, entrez_manager, expasy_manager, go_manager, hgnc_manager,
    interpro_manager, mirtarbase_manager,
)
from sqlalchemy.exc import OperationalError
from pybel_web.manager_utils import insert_graph

log = logging.getLogger(__name__)
enable_cool_mode()

BMS_BASE = os.environ.get('BMS_BASE')

if BMS_BASE is None:
    raise RuntimeError('BMS_BASE is not set in the environment')

alzheimer_directory = os.path.join(BMS_BASE, 'aetionomy', 'alzheimers')
selventa_directory = os.path.join(BMS_BASE, 'selventa')
cbn_human = os.path.join(BMS_BASE, 'cbn', 'Human-2.0')
cbn_mouse = os.path.join(BMS_BASE, 'cbn', 'Mouse-2.0')
cbn_rat = os.path.join(BMS_BASE, 'cbn', 'Rat-2.0')


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


def upload_bel_directory(directory, connection=None):
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


_jgf_extension = '.jgf'


def iter_jgf(directory):
    for path in os.listdir(directory):
        if path.endswith(_jgf_extension):
            yield os.path.join(directory, path)


def get_jgf_corresponding_gpickle_path(path):
    return path[:-len(_jgf_extension)] + '.gpickle'


def upload_jgf_directory(directory, connection=None):
    """Uploads CBN data to edge store

    :param str directory: Directory full of CBN JGIF files
    :param connection: database connection string to cache, pre-built :class:`Manager`, or None to use default cache
    :type connection: Optional[str or pybel.manager.Manager]
    """
    if not (os.path.exists(directory) and os.path.isdir(directory)):
        log.warning('directory does not exist: %s', directory)
        return

    manager = Manager.ensure(connection=connection)

    t = time.time()

    for path in iter_jgf(directory):
        gpickle_path = get_jgf_corresponding_gpickle_path(path)

        if os.path.exists(gpickle_path):
            graph = from_pickle(gpickle_path)
            strip_annotations(graph)
        else:
            with open(path) as f:
                cbn_jgif_dict = json.load(f)

            graph = pybel.from_cbn_jgif(cbn_jgif_dict)
            strip_annotations(graph)
            to_pickle(graph, gpickle_path)


        try:
            insert_graph(manager, graph, public=True)
        except OperationalError:
            manager.session.rollback()
            log.info('could not insert %s', graph)

    log.info('done in %.2f seconds', time.time() - t)


def upload_with_manager(external_manager, connection=None):
    if external_manager is None:
        log.info('no %s', external_manager)
        return

    manager = Manager.ensure(connection=connection)

    try:
        graph = external_manager.to_bel()
    except AttributeError:
        log.warning('%s has no to_bel function', external_manager)
        return
    except Exception:
        log.exception('error with %s', external_manager)
        return

    insert_graph(manager, graph)


def upload_managers(connection=None):
    managers = (
        chebi_manager, entrez_manager, expasy_manager, go_manager, hgnc_manager,
        interpro_manager, mirtarbase_manager,
    )
    for manager in managers:
        upload_with_manager(manager, connection=connection)


def main(connection=None):
    """Load BEL

    :param connection: database connection string to cache, pre-built :class:`Manager`, or None to use default cache
    :type connection: Optional[str or pybel.manager.Manager]
    """
    upload_bel_directory(alzheimer_directory, connection=connection)
    upload_bel_directory(selventa_directory, connection=connection)

    upload_jgf_directory(cbn_human, connection=connection)
    upload_jgf_directory(cbn_mouse, connection=connection)
    upload_jgf_directory(cbn_rat, connection=connection)

    upload_managers(connection=connection)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
    log.setLevel(logging.INFO)
    main(Manager())
