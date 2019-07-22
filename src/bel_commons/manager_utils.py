# -*- coding: utf-8 -*-

"""Utilities for the manager.

Utilities in this package should not depend on anything (especially proxies), and should instead take arguments
corresponding to objects.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Mapping, Optional, Tuple, Union

import networkx as nx
import pandas as pd
from flask import Response, abort, flash, jsonify, redirect, request

from pybel import BELGraph, Manager
from pybel.constants import GENE
from pybel.dsl import BaseEntity
from pybel.manager.models import Network
from pybel.struct.mutation import collapse_to_genes
from pybel_tools.analysis.heat import calculate_average_scores_on_subgraphs
from pybel_tools.filters import remove_nodes_by_namespace
from pybel_tools.generation import generate_bioprocess_mechanisms
from pybel_tools.integration import overlay_type_data
from pybel_tools.mutation import rewire_variants_to_genes
from pybel_tools.summary import BELGraphSummary
from .constants import LABEL
from .models import Experiment, Omic, Report, User

log = logging.getLogger(__name__)

__all__ = [
    'fill_out_report',
    'insert_graph',
    'create_omic',
    'calculate_scores',
    'run_heat_diffusion_helper',
    'next_or_jsonify',
]


def fill_out_report(graph: BELGraph, network: Network, report: Report) -> None:
    """Fill out the report for the network."""
    number_nodes = graph.number_of_nodes()

    try:
        average_degree = graph.number_of_edges() / graph.number_of_nodes()
    except ZeroDivisionError:
        average_degree = 0.0

    report.network = network
    report.number_nodes = number_nodes
    report.number_edges = graph.number_of_edges()
    report.number_warnings = graph.number_of_warnings()
    report.number_citations = graph.number_of_citations()
    report.number_authors = graph.number_of_authors()
    report.number_components = nx.number_weakly_connected_components(graph)
    report.network_density = nx.density(graph)
    report.average_degree = average_degree
    report.dump_calculations(BELGraphSummary.from_graph(graph))
    report.completed = True


def insert_graph(
        manager: Manager,
        graph: BELGraph,
        user: Union[int, User] = 1,
        public: bool = False,
        use_tqdm: bool = False,
) -> Network:
    """Insert a graph and also make a report.

    :param manager: A PyBEL manager
    :param graph: A BEL graph
    :param user: The identifier of the user to report. Defaults to 1. Can also give a user object.
    :param public: Should the network be public? Defaults to False.
    :param use_tqdm: Show a progress bar? Defaults to False.
    :raises: TypeError
    """
    if manager.has_name_version(graph.name, graph.version):
        log.info('database already has %s', graph)
        return manager.get_network_by_name_version(graph.name, graph.version)

    network = manager.insert_graph(graph, use_tqdm=use_tqdm)

    report = Report(public=public)

    if user:
        if isinstance(user, int):
            report.user_id = user
        elif isinstance(user, User):
            report.user = user
        else:
            raise TypeError(f'invalid user: {user.__class__}: {user}')

    fill_out_report(graph=graph, network=network, report=report)

    manager.session.add(report)
    manager.session.commit()

    return network


def create_omic(
        data,
        gene_column: str,
        data_column: str,
        description: str,
        source_name: str,
        sep: str,
        public: bool = False,
        user: Optional[User] = None,
) -> Omic:
    """Create an omics model."""
    df = pd.read_csv(data, sep=sep)

    if gene_column not in df.columns:
        abort(500, f'The omic document does not have a column named: {gene_column}')

    if data_column not in df.columns:
        abort(500, f'The omic document does not have a column named: {data_column}')

    result = Omic(
        description=description,
        source_name=source_name,
        gene_column=gene_column,
        data_column=data_column,
        public=public,
    )

    result.set_source_df(df)

    if user is not None:
        result.user = user

    return result


def calculate_scores(
        graph: BELGraph,
        data: Mapping[str, float],
        runs: int,
        use_tqdm: bool = False,
        tqdm_kwargs: Optional[Mapping[str, Any]] = None,
) -> Mapping[BaseEntity, Tuple]:
    """Calculate heat diffusion scores.

    :param graph: A BEL graph
    :param data: A dictionary of {name: data}
    :param runs: The number of permutations
    :param use_tqdm:
    :return: A dictionary of {pybel node: results tuple} from
     :py:func:`pybel_tools.analysis.ucmpa.calculate_average_scores_on_subgraphs`
    """
    remove_nodes_by_namespace(graph, {'MGI', 'RGD'})
    collapse_to_genes(graph)
    rewire_variants_to_genes(graph)

    overlay_type_data(graph, data, LABEL, GENE, 'HGNC', overwrite=False, impute=0)

    candidate_mechanisms = generate_bioprocess_mechanisms(graph, LABEL)
    return calculate_average_scores_on_subgraphs(
        candidate_mechanisms,
        LABEL,
        runs=runs,
        use_tqdm=use_tqdm,
        tqdm_kwargs=tqdm_kwargs,
    )


def run_heat_diffusion_helper(
        manager: Manager,
        experiment: Experiment,
        use_tqdm: bool = False,
        tqdm_kwargs: Optional[Mapping[str, Any]] = None,
) -> None:
    """Run the Heat Diffusion Workflow on an experiment and store information back into original experiment."""
    t = time.time()

    log.info('getting data from omic %s', experiment.omic)
    data = experiment.omic.get_source_dict()

    log.info('executing query %s', experiment.query)
    graph = experiment.query.run(manager)

    log.info('calculating scores for query [id=%d] with omic %s with %d permutations', experiment.query.id,
             experiment.omic, experiment.permutations)
    scores = calculate_scores(graph, data, experiment.permutations, use_tqdm=use_tqdm, tqdm_kwargs=tqdm_kwargs)
    experiment.dump_results(scores)
    experiment.time = time.time() - t


def next_or_jsonify(
        message: str,
        *args,
        status: int = 200,
        category: str = 'message',
        **kwargs,
) -> Response:
    """Wrap a redirect if the ``next`` argument is set in the request otherwise sends JSON feedback.

    :param message: The message to send
    :param status: The status to send
    :param category: An optional category for the :func:`flask.flash`
    """
    if args:
        raise ValueError("don't give args to this function")

    if 'next' in request.args:
        flash(message, category=category)
        return redirect(request.args['next'])

    return jsonify(
        status=status,
        message=message,
        **kwargs
    )
