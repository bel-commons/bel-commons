# -*- coding: utf-8 -*-

"""Utilities in this package should not depend on anything (especially proxies), and should instead take arguments
corresponding to objects"""

import itertools as itt
import logging
import time
from typing import Dict, Mapping, Tuple

import networkx as nx
import pandas as pd
from flask import Response, abort, flash, jsonify, redirect, request

import pybel
from pybel import BELGraph
from pybel.constants import GENE, RELATION
from pybel.dsl import BaseEntity
from pybel.manager.models import Network
from pybel.struct.filters import filter_edges
from pybel.struct.mutation import collapse_to_genes
from pybel.struct.summary import (
    count_citations, count_functions, count_relations, get_syntax_errors, get_top_hubs, get_top_pathologies,
    get_unused_namespaces,
)
from pybel_tools.analysis.heat import calculate_average_scores_on_subgraphs
from pybel_tools.analysis.stability import (
    get_chaotic_pairs, get_chaotic_triplets, get_contradiction_summary, get_dampened_pairs, get_dampened_triplets,
    get_decrease_mismatch_triplets, get_increase_mismatch_triplets, get_jens_unstable,
    get_mutually_unstable_correlation_triples, get_regulatory_pairs, get_separate_unstable_correlation_triples,
)
from pybel_tools.filters import has_pathology_causal, remove_nodes_by_namespace
from pybel_tools.generation import generate_bioprocess_mechanisms
from pybel_tools.integration import overlay_type_data
from pybel_tools.mutation import rewire_variants_to_genes
from pybel_tools.summary import (
    count_error_types, count_unique_authors, get_citation_years, get_modifications_count,
    get_most_common_errors, get_naked_names, get_namespaces_with_incorrect_names, get_undefined_annotations,
    get_undefined_namespaces, get_unused_annotations, get_unused_list_annotation_values,
)
from .constants import LABEL
from .models import Omic, Report, User

log = logging.getLogger(__name__)


def make_graph_summary(graph: BELGraph) -> Dict:
    """Make a graph summary for sticking in the report including the summary from :func:`get_network_summary_dict`."""
    log.debug('summarizing %s', graph)
    t = time.time()

    number_nodes = graph.number_of_nodes()

    try:
        average_degree = graph.number_of_edges() / graph.number_of_nodes()
    except ZeroDivisionError:
        average_degree = 0.0

    rv = dict(
        number_nodes=number_nodes,
        number_edges=graph.number_of_edges(),
        number_warnings=len(graph.warnings),
        number_citations=count_citations(graph),
        number_authors=count_unique_authors(graph),
        number_components=nx.number_weakly_connected_components(graph),
        network_density=nx.density(graph),
        average_degree=average_degree,
        summary_dict=get_network_summary_dict(graph),
    )

    log.debug('summarized %s in %.2f seconds', graph, time.time() - t)

    return rv


def get_network_summary_dict(graph: BELGraph) -> Mapping:
    """Create a summary dictionary."""

    def get_pair_tuple(a, b):
        return a.as_bel(), a.sha512, b.as_bel(), b.sha512

    def get_triplet_tuple(a, b, c):
        return a.as_bel(), a.sha512, b.as_bel(), b.sha512, c.as_bel(), c.sha512

    return dict(
        regulatory_pairs=[
            get_pair_tuple(u, v)
            for u, v in get_regulatory_pairs(graph)
        ],
        unstable_pairs=list(itt.chain(
            (get_pair_tuple(u, v) + ('Chaotic',) for u, v, in get_chaotic_pairs(graph)),
            (get_pair_tuple(u, v) + ('Dampened',) for u, v, in get_dampened_pairs(graph)),
        )),
        contradictory_pairs=[
            get_pair_tuple(u, v) + (relation,)
            for u, v, relation in get_contradiction_summary(graph)
        ],
        contradictory_triplets=list(itt.chain(
            (get_triplet_tuple(a, b, c) + ('Separate',) for a, b, c in
             get_separate_unstable_correlation_triples(graph)),
            (get_triplet_tuple(a, b, c) + ('Mutual',) for a, b, c in get_mutually_unstable_correlation_triples(graph)),
            (get_triplet_tuple(a, b, c) + ('Jens',) for a, b, c in get_jens_unstable(graph)),
            (get_triplet_tuple(a, b, c) + ('Increase Mismatch',) for a, b, c in get_increase_mismatch_triplets(graph)),
            (get_triplet_tuple(a, b, c) + ('Decrease Mismatch',) for a, b, c in get_decrease_mismatch_triplets(graph)),
        )),
        unstable_triplets=list(itt.chain(
            (get_triplet_tuple(a, b, c) + ('Chaotic',) for a, b, c in get_chaotic_triplets(graph)),
            (get_triplet_tuple(a, b, c) + ('Dampened',) for a, b, c in get_dampened_triplets(graph)),
        )),
        causal_pathologies=sorted({
            get_pair_tuple(u, v) + (graph[u][v][k][RELATION],)
            for u, v, k in filter_edges(graph, has_pathology_causal)
        }),
        hub_data={
            node.sha512: degree
            for node, degree in get_top_hubs(graph)
        },
        disease_data={
            node.sha512: count
            for node, count in get_top_pathologies(graph)
        },
        undefined_namespaces=get_undefined_namespaces(graph),
        undefined_annotations=get_undefined_annotations(graph),
        namespaces_with_incorrect_names=get_namespaces_with_incorrect_names(graph),
        unused_namespaces=get_unused_namespaces(graph),
        unused_annotations=get_unused_annotations(graph),
        unused_list_annotation_values=get_unused_list_annotation_values(graph),
        citation_years=get_citation_years(graph),
        naked_names=get_naked_names(graph),
        function_count=count_functions(graph),
        relation_count=count_relations(graph),
        error_count=count_error_types(graph),
        modifications_count=get_modifications_count(graph),
        error_groups=get_most_common_errors(graph),
        syntax_errors=get_syntax_errors(graph),
    )


def fill_out_report(network: Network, report: Report, graph_summary):
    """Fill out the report for the network.

    :param dict graph_summary: Summary generated from :func:`make_graph_summary`
    """
    report.network = network
    report.number_nodes = graph_summary['number_nodes']
    report.number_edges = graph_summary['number_edges']
    report.number_warnings = graph_summary['number_warnings']
    report.number_citations = graph_summary['number_citations']
    report.number_authors = graph_summary['number_authors']
    report.number_components = graph_summary['number_components']
    report.network_density = graph_summary['network_density']
    report.average_degree = graph_summary['average_degree']
    report.dump_calculations(graph_summary['summary_dict'])
    report.completed = True


def insert_graph(manager, graph, user=1, public=False, use_tqdm:bool=False):
    """Insert a graph and also make a report.

    :param pybel.manager.Manager manager: A PyBEL manager
    :param pybel.BELGraph graph: A BEL graph
    :param user: The identifier of the user to report. Defaults to 1. Can also give user object.
    :type user: int or User
    :param bool public: Should the network be public? Defaults to false
    :rtype: Network
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
            raise TypeError('invalid user: {} {}'.format(user.__class__, user))

    graph_summary = make_graph_summary(graph)

    fill_out_report(network, report, graph_summary)

    manager.session.add(report)
    manager.session.commit()

    return network


def create_omic(data, gene_column, data_column, description, source_name, sep, public=False, user=None):
    """Create an omics model.

    :param str or file data:
    :param str gene_column:
    :param str data_column:
    :param str description:
    :param str source_name:
    :param str sep:
    :param bool public:
    :param Optional[User] user:
    :rtype: Omic
    """
    df = pd.read_csv(data, sep=sep)

    if gene_column not in df.columns:
        abort(500, 'The omic document does not have a column named: {}'.format(gene_column))

    if data_column not in df.columns:
        abort(500, 'The omic document does not have a column named: {}'.format(data_column))

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


def calculate_scores(graph: BELGraph, data, runs: int, use_tqdm: bool = False) -> Mapping[BaseEntity, Tuple]:
    """Calculate heat diffusion scores.

    :param graph: A BEL graph
    :param dict[str,float] data: A dictionary of {name: data}
    :param runs: The number of permutations
    :param bool use_tqdm:
    :return: A dictionary of {pybel node tuple: results tuple} from
     :py:func:`pybel_tools.analysis.ucmpa.calculate_average_scores_on_subgraphs`
    :rtype: dict[tuple,tuple]
    """
    remove_nodes_by_namespace(graph, {'MGI', 'RGD'})
    collapse_to_genes(graph)
    rewire_variants_to_genes(graph)

    overlay_type_data(graph, data, LABEL, GENE, 'HGNC', overwrite=False, impute=0)

    candidate_mechanisms = generate_bioprocess_mechanisms(graph, LABEL)
    scores = calculate_average_scores_on_subgraphs(candidate_mechanisms, LABEL, runs=runs, use_tqdm=use_tqdm)
    return scores


def run_heat_diffusion_helper(manager, experiment, use_tqdm=False):
    """Run the Heat Diffusion Workflow on an experiment and store information back into original experiment.

    :param pybel.manager.Manager manager:
    :param pybel_web.models.Experiment experiment:
    :param bool use_tqdm:
    """
    t = time.time()

    log.info('getting data from omic %s', experiment.omic)
    data = experiment.omic.get_source_dict()

    log.info('executing query %s', experiment.query)
    graph = experiment.query.run(manager)

    log.info('calculating scores for query [id=%d] with omic %s with %d permutations', experiment.query.id,
             experiment.omic, experiment.permutations)
    scores = calculate_scores(graph, data, experiment.permutations, use_tqdm=use_tqdm)
    experiment.dump_results(scores)
    experiment.time = time.time() - t


def next_or_jsonify(message, *args, status=200, category='message', **kwargs) -> Response:
    """Neatly wraps a redirect if the ``next`` argument is set in the request otherwise sends JSON
    feedback.

    :param str message: The message to send
    :param int status: The status to send
    :param str category: An optional category for the :func:`flask.flash`
    :return: A Flask Response object
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
