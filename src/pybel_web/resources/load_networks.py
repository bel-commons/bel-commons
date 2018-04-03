#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""This file loads the sample BEL stuff

Prerequisites
-------------
1. Must have BMS installed and set environment variable ``BMS_BASE``
"""

import json
import logging
import time

from sqlalchemy.exc import OperationalError

import pybel
from pybel import from_path, from_pickle, to_pickle
from pybel.manager import Manager
from pybel.struct.mutation import strip_annotations
from pybel_tools.grouping import get_subgraphs_by_annotation_filtered
from pybel_tools.io import get_corresponding_gpickle_path, iter_from_pickles_from_directory, iter_paths_from_directory
from pybel_tools.utils import enable_cool_mode
from pybel_web.external_managers import (
    chebi_manager, entrez_manager, expasy_manager, go_manager, hgnc_manager,
    interpro_manager, mirtarbase_manager,
)
from pybel_web.manager_utils import insert_graph
from pybel_web.resources.constants import *

log = logging.getLogger(__name__)
enable_cool_mode()

neurommsig_sample_networks = [
    'Low density lipoprotein subgraph',
    'GABA subgraph',
    'Notch signaling subgraph',
    'Reactive oxygen species subgraph',
]

_jgf_extension = '.jgf'


def _ensure_pickle(path, manager, **kwargs):
    gpickle_path = get_corresponding_gpickle_path(path)

    if not os.path.exists(gpickle_path):
        graph = from_path(path, manager=manager, use_tqdm=True, **kwargs)
        to_pickle(graph, gpickle_path)
    else:
        graph = from_pickle(gpickle_path)

    return insert_graph(manager, graph, public=True)


def ensure_pickles(directory, connection=None, blacklist=None, **kwargs):
    """
    :param str directory:
    :param connection: database connection string to cache, pre-built :class:`Manager`, or None to use default cache
    :type connection: Optional[str or pybel.manager.Manager]
    :param Optional[list[str]] blacklist: An optional list of file names not to use
    """
    log.info('ensuring pickles in %s', directory)
    manager = Manager.ensure(connection=connection)

    for filename in iter_paths_from_directory(directory):
        path = os.path.join(directory, filename)

        if blacklist and filename in blacklist:
            log.info('skipping %s', path)
            continue

        _ensure_pickle(path, manager, **kwargs)


def upload_pickles(directory, connection=None, blacklist=None):
    """Uploads all of the pickles in a given directory

    :param str directory:
    :param connection: database connection string to cache, pre-built :class:`Manager`, or None to use default cache
    :type connection: Optional[str or pybel.manager.Manager]
    :param Optional[list[str]] blacklist: An optional list of file names not to use
    :rtype: list[Network]
    """
    log.info('loading pickles in %s', directory)

    manager = Manager.ensure(connection=connection)

    results = []

    for graph in iter_from_pickles_from_directory(directory, blacklist=blacklist):
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


def upload_bel_directory(directory, connection=None, blacklist=None):
    """Handles parsing, pickling, then uploading all BEL files in a given directory

    :param str directory:
    :param connection: database connection string to cache, pre-built :class:`Manager`, or None to use default cache
    :type connection: Optional[str or pybel.manager.Manager]
    :param Optional[list[str]] blacklist: An optional list of file names not to use. NO FILE EXTENSIONS
    """
    if not (os.path.exists(directory) and os.path.isdir(directory)):
        log.warning('directory does not exist: %s', directory)
        return

    if blacklist is not None and not isinstance(blacklist, (set, tuple, list)):
        raise TypeError('blacklist is wrong type: {}'.format(blacklist.__class__.__name__))

    ensure_pickles(
        directory,
        connection=connection,
        blacklist=[e + '.bel' for e in blacklist] if blacklist is not None else None
    )
    networks = upload_pickles(
        directory,
        connection=connection,
        blacklist=[e + '.gpickle' for e in blacklist] if blacklist is not None else None
    )

    write_manifest(directory, networks)


def upload_neurommsig_graphs(connection=None):
    """Only upload NeuroMMSig Sample Networks

    :param connection: database connection string to cache, pre-built :class:`Manager`, or None to use default cache
    :type connection: Optional[str or pybel.manager.Manager]
    """
    manager = Manager.ensure(connection=connection)

    if not (os.path.exists(alzheimer_directory) and os.path.isdir(alzheimer_directory)):
        log.warning('directory does not exist: %s', alzheimer_directory)
        return

    if not os.path.exists(neurommsig_directory):
        log.info('created neurommsig directory: %s', neurommsig_directory)
        os.makedirs(neurommsig_directory)

    path = os.path.join(alzheimer_directory, 'alzheimers.bel')
    gpickle_path = os.path.join(alzheimer_directory, 'alzheimers.gpickle')

    if os.path.exists(gpickle_path):
        graph = from_pickle(gpickle_path)
    elif os.path.exists(path):
        graph = from_path(path, manager=manager)
    else:
        raise RuntimeError('missing NeuroMMSig source file: {}'.format(path))

    subgraphs = get_subgraphs_by_annotation_filtered(graph, annotation='Subgraph', values=neurommsig_sample_networks)
    networks = []

    for subgraph_name, subgraph in subgraphs.items():
        subgraph.name = 'NeuroMMSig AD {}'.format(subgraph_name)
        subgraph.authors = 'Daniel Domingo-Fernandez et. al'
        subgraph.version = graph.version
        subgraph.license = graph.license

        # output to directory as gpickle
        to_pickle(subgraph, os.path.join(neurommsig_directory, '{}.gpickle'.format(subgraph_name)))

        network = insert_graph(manager, subgraph, public=True)
        networks.append(network)

    write_manifest(neurommsig_directory, networks)


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
    upload_neurommsig_graphs(connection=connection)
    upload_bel_directory(selventa_directory, connection=connection)
    upload_bel_directory(alzheimer_directory, connection=connection, blacklist=['alzheimers'])
    upload_bel_directory(parkinsons_directory, connection=connection, blacklist=['parkinsons'])

    upload_jgf_directory(cbn_human, connection=connection)
    upload_jgf_directory(cbn_mouse, connection=connection)
    upload_jgf_directory(cbn_rat, connection=connection)

    upload_managers(connection=connection)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
    log.setLevel(logging.INFO)
    main(Manager())
