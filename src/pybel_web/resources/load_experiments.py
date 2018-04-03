#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""This file runs experiments on the sample BEL and -omics data then uploads it.

Prerequisites
-------------
1. Must have run load_omics.py
2. Must have run load_networks.py
"""

import json
import logging
import os

from pybel.manager import Manager
from pybel_tools.utils import enable_cool_mode
from pybel_web.manager_utils import run_cmpa_helper
from pybel_web.models import Experiment, Omic, Query
from pybel_web.resources.constants import BMS_BASE
from .constants import OMICS_DATA_DIR

log = logging.getLogger(__name__)
enable_cool_mode()


# 1. build query from all of alzheimer's disease using manifest from AD folder
# 2. run experiment and upload

def get_manifest(directory):
    """Gets the manifest from a directory

    :param str directory:
    :rtype: list[dict]
    """
    manifest_path = os.path.join(directory, 'manifest.json')
    if not os.path.exists(manifest_path):
        raise RuntimeError('manifest missing from {}'.format(directory))

    with open(manifest_path) as f:
        return json.load(f)


def build_query(directory, connection=None):
    """Builds a query for the Alzheimer's disease network

    :param str directory: Directory containing omics data and a manifest
    :param connection: database connection string to cache, pre-built :class:`Manager`, or None to use default cache
    :type connection: Optional[str or pybel.manager.Manager]
    :rtype: pybel_web.models.Query
    """
    manager = Manager.ensure(connection=connection)

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


def create_experiment(query, directory, connection=None, permutations=None):
    """Creates experiment models

    :param Query query:
    :param str directory: the directory of omics data resources
    :param connection: database connection string to cache, pre-built :class:`Manager`, or None to use default cache
    :type connection: Optional[str or pybel.manager.Manager]
    :param Optional[int] permutations: Number of permutations to run (defaults to 200)
    :rtype: list[Experiment]
    """
    manager = Manager.ensure(connection=connection)

    omics_manifest = get_manifest(directory)

    results = []

    for omic_metadata in omics_manifest:
        omic = manager.session.query(Omic).get(omic_metadata['id'])

        experiment = Experiment(
            public=True,
            omic=omic,
            query=query,
            permutations=permutations or 200
        )

        results.append(experiment)

    return results


def upload_experiments(experiments, connection=None):
    """Create a manager and upload experiments models

    :param list[pybel_web.models.Experiments] experiments:
    :param connection: database connection string to cache, pre-built :class:`Manager`, or None to use default cache
    :type connection: Optional[str or pybel.manager.Manager]
    """
    manager = Manager.ensure(connection=connection)

    log.info('adding experiments to session')
    manager.session.add_all(experiments)

    log.info('committing experiments')
    manager.session.commit()


def run_experiments(experiments, connection=None):
    """Runs experiments and commits after each

    :param iter[Experiment] experiments:
    :param connection: database connection string to cache, pre-built :class:`Manager`, or None to use default cache
    :type connection: Optional[str or pybel.manager.Manager]
    """
    manager = Manager.ensure(connection=connection)

    log.info('running %d experiments', len(experiments))

    for experiment in experiments:
        run_cmpa_helper(manager, experiment, use_tqdm=True)
        log.info('done in %.2f seconds', experiment.time)
        manager.session.add(experiment)
        manager.session.commit()


def work_directory(query, omic_directory, connection=None, permutations=None):
    """

    :param Query query:
    :param str omic_directory:
    :param connection: database connection string to cache, pre-built :class:`Manager`, or None to use default cache
    :type connection: Optional[str or pybel.manager.Manager]
    :param Optional[int] permutations: Number of permutations to run (defaults to 200)
    """
    log.info('making experiments for directory: %s', omic_directory)
    experiments = create_experiment(query, directory=omic_directory, connection=connection, permutations=permutations)

    log.info('uploading experiments for directory: %s', omic_directory)
    upload_experiments(experiments, connection=connection)

    log.info('running experiments for directory: %s', omic_directory)
    run_experiments(experiments, connection=connection)


def work_group(network_directory, omics_directories, connection=None, permutations=None):
    """

    :param str network_directory:
    :param iter[str] omics_directories:
    :param connection: database connection string to cache, pre-built :class:`Manager`, or None to use default cache
    :type connection: Optional[str or pybel.manager.Manager]
    :param Optional[int] permutations: Number of permutations to run (defaults to 200)
    """
    query = build_query(directory=network_directory, connection=connection)
    log.info('made query %s for %s', query, network_directory)

    for omic_directory in omics_directories:
        work_directory(
            query=query,
            omic_directory=omic_directory,
            connection=connection,
            permutations=permutations,
        )


def main(connection=None, permutations=25):
    """Runs the experiments and uploads them

    :param connection: database connection string to cache, pre-built :class:`Manager`, or None to use default cache
    :type connection: Optional[str or pybel.manager.Manager]
    :param int permutations:
    """
    network_directory = os.path.join(BMS_BASE, 'aetionomy', 'neurommsig')

    gse1297_directory = os.path.join(OMICS_DATA_DIR, 'GSE1297')
    gse28146_directory = os.path.join(OMICS_DATA_DIR, 'GSE28146')
    gse63063_directory = os.path.join(OMICS_DATA_DIR, 'GSE63063')

    omics_directories = [
        gse1297_directory,
        gse28146_directory,
        gse63063_directory
    ]

    work_group(
        network_directory=network_directory,
        omics_directories=omics_directories,
        connection=connection,
        permutations=permutations
    )


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
    log.setLevel(logging.INFO)
    main(Manager())
