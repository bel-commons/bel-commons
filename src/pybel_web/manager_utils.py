# -*- coding: utf-8 -*-

"""Utilities in this package should not depend on anything (especially proxies), and should instead take arguments
corresponding to objects"""

import itertools as itt
import logging
import time
from collections import Counter

import networkx as nx
import pandas as pd
from flask import abort, flash, jsonify, redirect, request

import pybel
from pybel.canonicalize import calculate_canonical_name
from pybel.constants import GENE, RELATION
from pybel.manager.models import Network
from pybel.struct.filters import filter_edges
from pybel.struct.summary import count_functions, get_syntax_errors, get_unused_namespaces
from pybel.tokens import node_to_tuple
from pybel.utils import hash_node
from pybel_tools.analysis.stability import (
    get_chaotic_pairs, get_chaotic_triplets, get_contradiction_summary, get_dampened_pairs, get_dampened_triplets,
    get_decrease_mismatch_triplets, get_increase_mismatch_triplets, get_jens_unstable,
    get_mutually_unstable_correlation_triples, get_regulatory_pairs, get_separate_unstable_correlation_triples,
)
from pybel_tools.analysis.ucmpa import calculate_average_scores_on_subgraphs
from pybel_tools.filters import has_pathology_causal, iter_undefined_families, remove_nodes_by_namespace
from pybel_tools.generation import generate_bioprocess_mechanisms
from pybel_tools.integration import overlay_type_data
from pybel_tools.mutation import collapse_by_central_dogma_to_genes, rewire_variants_to_genes
from pybel_tools.summary import (
    count_error_types, count_pathologies, count_relations, count_unique_authors, count_unique_citations,
    get_citation_years, get_modifications_count, get_most_common_errors, get_naked_names,
    get_namespaces_with_incorrect_names, get_undefined_annotations, get_undefined_namespaces, get_unused_annotations,
    get_unused_list_annotation_values,
)
from .constants import LABEL
from .models import Experiment, Omic, Report

log = logging.getLogger(__name__)


def get_top_hubs(graph, count=15):
    """Gets the top hubs in the graph by BEL

    :param pybel.BELGraph graph: A BEL graph
    :param int count:
    :rtype: dict[str,int]
    """
    return {
        calculate_canonical_name(graph, node): v
        for node, v in Counter(graph.degree()).most_common(count)
    }


def count_top_pathologies(graph, count=15):
    """Gets the top highest relationship-having edges in the graph by BEL

    :param pybel.BELGraph graph: A BEL graph
    :param int count:
    :rtype: dict[str,int]
    """
    return {
        calculate_canonical_name(graph, node): v
        for node, v in count_pathologies(graph).most_common(count)
    }


def canonical_hash(graph, node):
    """Hashes the node

    :param pybel.BELGraph graph:
    :param tuple node:
    :rtype: str
    """
    data = graph.node[node]
    canonical_node_tuple = node_to_tuple(data)
    return hash_node(canonical_node_tuple)


def get_network_summary_dict(graph):
    """Creates a summary dictionary

    :param pybel.BELGraph graph:
    :rtype: dict
    """
    node_bel_cache = {}

    def dcn(node):
        """Decanonicalizes a node tuple to a BEL string

        :param tuple node: A BEL node
        """
        if node in node_bel_cache:
            return node_bel_cache[node]

        node_bel_cache[node] = graph.node_to_bel(node)
        return node_bel_cache[node]

    def get_pair_tuple(source_tuple, target_tuple):
        """

        :param source_tuple:
        :param target_tuple:
        :return:
        """
        return (
            dcn(source_tuple),
            canonical_hash(graph, source_tuple),
            dcn(target_tuple),
            canonical_hash(graph, target_tuple)
        )

    def get_triplet_tuple(a_tuple, b_tuple, c_tuple):
        """

        :param a_tuple:
        :param b_tuple:
        :param c_tuple:
        :return:
        """
        return (
            dcn(a_tuple),
            canonical_hash(graph, a_tuple),
            dcn(b_tuple),
            canonical_hash(graph, b_tuple),
            dcn(c_tuple),
            canonical_hash(graph, c_tuple)
        )

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
            get_pair_tuple(u, v) + (graph.edge[u][v][k][RELATION],)
            for u, v, k in filter_edges(graph, has_pathology_causal)
        }),

        undefined_families=[
            (dcn(node), canonical_hash(graph, node))
            for node in iter_undefined_families(graph, ['SFAM', 'GFAM'])
        ],

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
        hub_data=get_top_hubs(graph),
        disease_data=count_top_pathologies(graph),
        syntax_errors=get_syntax_errors(graph),
    )


def make_graph_summary(graph):
    """Makes a graph summary for sticking in the report including the summary from :func:`get_network_summary_dict`

    :param pybel.BELGraph graph:
    :rtype: dict
    """
    log.debug('summarizing %s', graph)
    t = time.time()

    number_nodes = graph.number_of_nodes()

    try:
        average_degree = sum(graph.in_degree().values()) / float(number_nodes)
    except ZeroDivisionError:
        average_degree = 0.0

    rv = dict(
        number_nodes=number_nodes,
        number_edges=graph.number_of_edges(),
        number_warnings=len(graph.warnings),
        number_citations=count_unique_citations(graph),
        number_authors=count_unique_authors(graph),
        number_components=nx.number_weakly_connected_components(graph),
        network_density=nx.density(graph),
        average_degree=average_degree,
        summary_dict=get_network_summary_dict(graph),
    )

    log.debug('summarized %s in %.2f seconds', graph, time.time() - t)

    return rv


def fill_out_report(network, report, graph_summary):
    """Fills out a report

    :param Network network:
    :param Report report:
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


def insert_graph(manager, graph, user_id=1, public=False):
    """Insert a graph and also make a report

    :param pybel.manager.Manager manager: A PyBEL manager
    :param pybel.BELGraph graph: A BEL graph
    :param int user_id: The identifier of the user to report. Defaults to 1.
    :param bool public: Should the network be public? Defaults to false
    :rtype: Network
    """
    if manager.has_name_version(graph.name, graph.version):
        log.info('database already has %s', graph)
        return manager.get_network_by_name_version(graph.name, graph.version)

    network = manager.insert_graph(graph)

    report = Report(public=public)

    if user_id:
        report.user_id = user_id

    graph_summary = make_graph_summary(graph)

    fill_out_report(network, report, graph_summary)

    manager.session.add(report)
    manager.session.commit()

    return network


def create_omic(data, gene_column, data_column, description, source_name, sep, public=False, user=None):
    """Creates an omics model

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


def calculate_scores(graph, data, runs, use_tqdm=False):
    """Calculates CMPA scores

    :param pybel.BELGraph graph: A BEL graph
    :param dict[str,float] data: A dictionary of {name: data}
    :param int runs: The number of permutations
    :param bool use_tqdm:
    :return: A dictionary of {pybel node tuple: results tuple} from :func:`calculate_average_cmpa_on_subgraphs`
    :rtype: dict[tuple,tuple]
    """
    remove_nodes_by_namespace(graph, {'MGI', 'RGD'})
    collapse_by_central_dogma_to_genes(graph)
    rewire_variants_to_genes(graph)

    overlay_type_data(graph, data, LABEL, GENE, 'HGNC', overwrite=False, impute=0)

    candidate_mechanisms = generate_bioprocess_mechanisms(graph, LABEL)
    scores = calculate_average_scores_on_subgraphs(candidate_mechanisms, LABEL, runs=runs, use_tqdm=use_tqdm)

    return scores


def run_cmpa_helper(manager, experiment, use_tqdm=False):
    """Helps run a CMPA experiment. Stores information back into original experiment

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
             experiment.omic,
             experiment.permutations)
    scores = calculate_scores(graph, data, experiment.permutations, use_tqdm=use_tqdm)
    experiment.dump_results(scores)

    experiment.time = time.time() - t


def user_has_rights_to_experiment(user, experiment):
    """

    :param User user:
    :param Experiment experiment:
    :return:
    """
    return (
            experiment.public or
            user.is_admin or
            user == experiment.user
    )


def safe_get_experiment(manager, experiment_id, user):
    """Safely gets an experiment

    :param pybel.manager.Manager manager:
    :param int experiment_id:
    :param User user:
    :rtype: Experiment
    :raises: werkzeug.exceptions.HTTPException
    """
    experiment = manager.session.query(Experiment).get(experiment_id)

    if experiment is None:
        abort(404, 'Experiment {} does not exist'.format(experiment_id))

    if not user_has_rights_to_experiment(user, experiment):
        abort(403, 'You do not have rights to drop this experiment')

    return experiment


def next_or_jsonify(message, *args, status=200, category='message', **kwargs):
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


def iter_public_networks(manager):
    """Lists the recent networks from :meth:`pybel.manager.Manager.list_recent_networks()` that have been made public

    :param pybel.manager.Manager manager: A manager
    :rtype: iter[Network]
    """
    return (
        network
        for network in manager.list_recent_networks()
        if network.report and network.report.public
    )


def _iterate_networks_for_user(user, manager, user_datastore):
    """
    :param models.User user: A user
    :param pybel.manager.Manager manager: A manager
    :param flask_security.datastore.UserDatastore user_datastore: A user datastore
    :rtype: iter[Network]
    """
    yield from iter_public_networks(manager)
    yield from user.get_owned_networks()
    yield from user.get_shared_networks()
    yield from user.get_project_networks()

    if user.is_scai:
        role = user_datastore.find_or_create_role(name='scai')
        for user in role.users:
            yield from user.get_owned_networks()


def networks_with_permission_iter_helper(user, manager, user_datastore):
    """Gets an iterator over all the networks from all the sources

    :param models.User user: A user
    :param pybel.manager.Manager manager: A manager
    :param flask_security.datastore.UserDatastore user_datastore: A user datastore
    :rtype: iter[Network]
    """
    if not user.is_authenticated:
        log.debug('getting only public networks for anonymous user')
        yield from iter_public_networks(manager)

    elif user.is_admin:
        log.debug('getting all recent networks for admin')
        yield from manager.list_recent_networks()

    else:
        log.debug('getting all networks for user [%s]', user)
        yield from _iterate_networks_for_user(user, manager, user_datastore)


def get_network_ids_with_permission_helper(user, manager, user_datastore):
    """Gets the set of networks ids tagged as public or uploaded by the current user

    :param User user: A user
    :param pybel.manager.Manager manager: A manager
    :param flask_security.datastore.UserDatastore user_datastore: A user datastore
    :return: A list of all networks tagged as public or uploaded by the current user
    :rtype: set[int]
    """
    networks = networks_with_permission_iter_helper(user, manager, user_datastore)
    return {network.id for network in networks}


def user_missing_query_rights_abstract(manager, user_datastore, user, query):
    """Checks if the user does not have the rights to run the given query

    :param pybel.manager.Manager manager: A manager
    :param flask_security.datastore.UserDatastore user_datastore: A user datastore
    :param models.User user: A user object
    :param models.Query query: A query object
    :rtype: bool
    """
    log.debug('checking if user [%s] has rights to query [id=%s]', user, query.id)

    if user.is_authenticated and user.is_admin:
        log.debug('[%s] is admin and can access query [id=%d]', user, query.id)
        return False  # admins are never missing the rights to a query

    permissive_network_ids = get_network_ids_with_permission_helper(user=user, manager=manager,
                                                                    user_datastore=user_datastore)

    return any(
        network.id not in permissive_network_ids
        for network in query.assembly.networks
    )
