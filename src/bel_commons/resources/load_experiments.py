#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""This script runs experiments on the sample BEL and *-omics* data then uploads it.

Prerequisites
-------------
1. Must have run load_omics.py
2. Must have run load_networks.py
"""

import json
import logging
import os
from typing import Any, Dict, List, Mapping, Optional

from bel_commons.core.models import Query
from bel_commons.manager_utils import run_heat_diffusion_helper
from bel_commons.models import Experiment, Omic
from bel_commons.resources.constants import BMS_BASE, OMICS_DATA_DIR
from pybel.manager import Manager

log = logging.getLogger(__name__)


# 1. build query from all of alzheimer's disease using manifest from AD folder
# 2. run experiment and upload

def get_manifest(directory: str) -> List[Dict]:
    """Get the manifest from a directory."""
    manifest_path = os.path.join(directory, 'manifest.json')
    if not os.path.exists(manifest_path):
        raise RuntimeError('manifest missing from {}'.format(directory))

    with open(manifest_path) as f:
        return json.load(f)


def build_query(directory: str, manager: Manager) -> Query:
    """Build a query for the Alzheimer's disease network.

    :param directory: Directory containing *-omics* data and a manifest
    """
    manifest = get_manifest(directory)

    network_ids = [
        network['id']
        for network in manifest
    ]

    query = Query.from_query_args(manager=manager, network_ids=network_ids)
    query.public = True
    manager.session.add(query)
    manager.session.commit()

    return query


def create_experiment(
        query: Query,
        directory: str,
        manager: Manager,
        permutations: Optional[int] = None,
) -> List[Experiment]:
    """Create experiment models.

    :param query:
    :param directory: the directory of -*omics* data resources
    :param manager:
    :param permutations: Number of permutations to run (defaults to 200)
    """
    omics_manifest = get_manifest(directory)

    return [
        Experiment(
            public=True,
            omic=manager.session.query(Omic).get(omic_metadata['id']),
            query=query,
            permutations=permutations or 200,
        )
        for omic_metadata in omics_manifest
    ]


def upload_experiments(experiments: List[Experiment], manager: Manager):
    """Upload experiments models."""
    log.info('adding experiments to session')
    manager.session.add_all(experiments)

    log.info('committing experiments')
    manager.session.commit()


def run_experiments(
        experiments: List[Experiment],
        manager: Manager,
        use_tqdm: bool = True,
        tqdm_kwargs: Optional[Mapping[str, Any]] = None,
) -> None:
    """Run experiments and commits after each."""
    log.info('running %d experiments', len(experiments))

    for experiment in experiments:
        run_heat_diffusion_helper(manager, experiment, use_tqdm=use_tqdm, tqdm_kwargs=tqdm_kwargs)
        log.info('done in %.2f seconds', experiment.time)
        manager.session.add(experiment)
        manager.session.commit()


def work_directory(
        query: Query,
        omic_directory: str,
        manager: Manager,
        permutations: Optional[int] = None,
        use_tqdm: bool = True,
) -> None:
    """Make models, upload, and run experiments for all data in a given directory."""
    log.info(f'making experiments for directory: {omic_directory}')
    experiments = create_experiment(query, directory=omic_directory, manager=manager, permutations=permutations)

    log.info(f'uploading experiments for directory: {omic_directory}')
    upload_experiments(experiments, manager=manager)

    log.info(f'running experiments for directory: {omic_directory}')
    run_experiments(experiments, manager=manager, use_tqdm=use_tqdm)


def work_group(
        network_directory: str,
        omics_directories: List[str],
        manager: Manager,
        permutations: Optional[int] = None,
) -> None:
    """Make models, upload, and run experiments for all data in several directories.

    :param network_directory:
    :param omics_directories:
    :param manager: database connection string to cache, pre-built :class:`Manager`, or None to use default cache
    :param  permutations: Number of permutations to run (defaults to 200)
    """
    query = build_query(directory=network_directory, manager=manager)
    log.info('made query %s for %s', query, network_directory)

    for omic_directory in omics_directories:
        work_directory(
            query=query,
            omic_directory=omic_directory,
            manager=manager,
            permutations=permutations,
        )


def main(manager: Manager, permutations: int = 25):
    """Run the experiments and uploads them."""
    network_directory = os.path.join(BMS_BASE, 'aetionomy', 'neurommsig')

    gse1297_directory = os.path.join(OMICS_DATA_DIR, 'GSE1297')
    gse28146_directory = os.path.join(OMICS_DATA_DIR, 'GSE28146')
    gse63063_directory = os.path.join(OMICS_DATA_DIR, 'GSE63063')

    omics_directories = [
        gse1297_directory,
        gse28146_directory,
        gse63063_directory,
    ]

    work_group(
        network_directory=network_directory,
        omics_directories=omics_directories,
        manager=manager,
        permutations=permutations,
    )


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
    log.setLevel(logging.INFO)
    main(Manager())
