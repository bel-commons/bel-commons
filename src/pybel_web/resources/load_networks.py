#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""This file loads the sample BEL stuff.

Prerequisites
-------------
1. Must have BMS installed and set environment variable ``BMS_BASE``
"""

import json
import logging
import os
import time
from typing import Iterable, List, Optional, Set

from sqlalchemy.exc import OperationalError

import pybel
from bel_repository import BELRepository
from bio2bel import AbstractManager
from pybel import from_path, from_pickle, to_pickle
from pybel.manager import Manager
from pybel.manager.models import Network
from pybel.struct.grouping import get_subgraphs_by_annotation
from pybel.struct.mutation import strip_annotations
from pybel_web.external_managers import (
    chebi_manager, entrez_manager, expasy_manager, go_manager, hgnc_manager, interpro_manager, mirtarbase_manager,
)
from pybel_web.manager_utils import insert_graph
from pybel_web.resources.constants import (
    alzheimer_directory, cbn_human, cbn_mouse, cbn_rat, neurommsig_directory, parkinsons_directory, selventa_directory,
)

__all__ = [
    'load_cbn',
    'load_bio2bel',
    'load_bms',
]

log = logging.getLogger(__name__)

neurommsig_sample_networks = [
    'Low density lipoprotein subgraph',
    'GABA subgraph',
    'Notch signaling subgraph',
    'Reactive oxygen species subgraph',
]

_jgf_extension = '.jgf'


def upload_pickles(directory: str, manager: Manager, blacklist: Optional[Set[str]] = None) -> List[Network]:
    """Uploads all of the BEL documents in a given directory."""
    results = []
    repo = BELRepository(directory)
    graphs = repo.get_graphs(manager=manager)
    for name, graph in graphs.items():
        if blacklist and name in blacklist:
            log.info(f'skipping {name}: {graph}')
            continue
        network = insert_graph(manager, graph, public=True, use_tqdm=True)
        results.append(network)
    return results


def write_manifest(directory: str, networks: List[Network]) -> None:
    """Write the manifest to the given directory."""
    manifest_path = os.path.join(directory, 'manifest.json')

    log.info('generating manifest for %s', directory)
    manifest_data = [
        network.to_json(include_id=True)
        for network in networks
    ]

    log.info('writing manifest to %s', manifest_path)
    with open(manifest_path, 'w') as file:
        json.dump(manifest_data, file, indent=2)


def upload_bel_directory(directory: str, manager: Manager, blacklist: Optional[List[str]] = None) -> None:
    """Handle parsing, pickling, then uploading all BEL files in a given directory.

    :param blacklist: An optional list of file names not to use. NO FILE EXTENSIONS
    """
    if not (os.path.exists(directory) and os.path.isdir(directory)):
        log.warning('directory does not exist: %s', directory)
        return

    if blacklist is not None and not isinstance(blacklist, (set, tuple, list)):
        raise TypeError(f'blacklist is wrong type: {blacklist.__class__.__name__}')

    networks = upload_pickles(directory=directory, manager=manager)
    write_manifest(directory=directory, networks=networks)


def upload_neurommsig_graphs(manager: Manager):
    """Only upload NeuroMMSig Sample Networks."""
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
        to_pickle(graph, gpickle_path)
    else:
        raise RuntimeError('missing NeuroMMSig source file: {}'.format(path))

    subgraphs = {
        name: subgraph
        for name, subgraph in get_subgraphs_by_annotation(graph, annotation='Subgraph').items()
        if name in neurommsig_sample_networks
    }

    networks = []

    for subgraph_name, subgraph in subgraphs.items():
        subgraph.name = 'NeuroMMSig AD {}'.format(subgraph_name)
        subgraph.authors = 'Daniel Domingo-Fernandez et. al'
        subgraph.version = graph.version
        subgraph.license = graph.license

        # output to directory as gpickle
        to_pickle(subgraph, os.path.join(neurommsig_directory, '{}.gpickle'.format(subgraph_name)))

        network = insert_graph(manager, subgraph, public=True, use_tqdm=True)
        networks.append(network)

    write_manifest(neurommsig_directory, networks)


def iter_jgf(directory: str) -> Iterable[str]:
    for path in os.listdir(directory):
        if path.endswith(_jgf_extension):
            yield os.path.join(directory, path)


def get_jgf_corresponding_gpickle_path(path: str) -> str:
    return path[:-len(_jgf_extension)] + '.gpickle'


def upload_jgf_directory(directory: str, manager: Manager):
    """Upload CBN data to edge store."""
    if not (os.path.exists(directory) and os.path.isdir(directory)):
        log.warning('directory does not exist: %s', directory)
        return

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
            insert_graph(manager, graph, public=True, use_tqdm=True)
        except OperationalError:
            manager.session.rollback()
            log.info('could not insert %s', graph)

    log.info('done in %.2f seconds', time.time() - t)


def load_bio2bel(manager: Manager) -> None:
    """Load Bio2BEL content as BEL."""
    bio2bel_managers = (
        chebi_manager,
        entrez_manager,
        expasy_manager,
        go_manager,
        hgnc_manager,
        interpro_manager,
        mirtarbase_manager,
    )

    for bio2bel_manager in bio2bel_managers:
        upload_with_manager(bio2bel_manager=bio2bel_manager, manager=manager)


def upload_with_manager(bio2bel_manager: AbstractManager, manager: Manager) -> Optional[Network]:
    """Upload Bio2BEL data."""
    if bio2bel_manager is None:
        log.info('skipping missing manager')
        return

    if not isinstance(bio2bel_manager, AbstractManager):
        log.info('manager is not a Bio2BEL manager: %s', bio2bel_manager)
        return

    log.info('%s manager connection: %s', bio2bel_manager.module_name, bio2bel_manager.engine.url)

    if not bio2bel_manager.is_populated():
        log.info('populating %s', bio2bel_manager)
        bio2bel_manager.populate()

    try:
        graph = bio2bel_manager.to_bel()
    except AttributeError:
        log.warning('%s has no to_bel function', bio2bel_manager)
        return

    return insert_graph(manager, graph, use_tqdm=True)


def load_cbn(manager: Manager):
    """Load CBN data as BEL."""
    upload_jgf_directory(cbn_human, manager)
    upload_jgf_directory(cbn_mouse, manager)
    upload_jgf_directory(cbn_rat, manager)


def load_bms(manager: Manager):
    """Load BEL."""
    upload_neurommsig_graphs(manager)
    upload_bel_directory(selventa_directory, manager)
    upload_bel_directory(alzheimer_directory, manager, blacklist=['alzheimers'])
    upload_bel_directory(parkinsons_directory, manager, blacklist=['parkinsons'])


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
    log.setLevel(logging.INFO)
    load_bms(Manager())
