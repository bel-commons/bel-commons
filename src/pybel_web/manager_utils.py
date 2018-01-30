# -*- coding: utf-8 -*-

import itertools as itt
import logging
import time
from collections import Counter

import networkx as nx

import pybel
from pybel.canonicalize import calculate_canonical_name, node_to_bel
from pybel.constants import RELATION
from pybel.manager import Network
from pybel.struct.filters import filter_edges
from pybel.struct.summary import (
    count_functions, get_syntax_errors, get_unused_namespaces,
)
from pybel.tokens import node_to_tuple
from pybel.utils import hash_node
from pybel_tools.analysis.stability import (
    get_chaotic_pairs, get_chaotic_triplets, get_contradiction_summary, get_dampened_pairs, get_dampened_triplets,
    get_decrease_mismatch_triplets, get_increase_mismatch_triplets, get_jens_unstable,
    get_mutually_unstable_correlation_triples, get_regulatory_pairs, get_separate_unstable_correlation_triples,
)
from pybel_tools.filters import has_pathology_causal, iter_undefined_families
from pybel_tools.summary import (
    count_error_types, count_pathologies, count_relations, count_unique_authors, count_unique_citations,
    get_citation_years, get_modifications_count, get_most_common_errors, get_naked_names,
    get_namespaces_with_incorrect_names, get_undefined_annotations, get_undefined_namespaces, get_unused_annotations,
    get_unused_list_annotation_values,
)
from .models import Report

log = logging.getLogger(__name__)


def get_top_hubs(graph, count=15):
    return {
        calculate_canonical_name(graph, node): v
        for node, v in Counter(graph.degree()).most_common(count)
    }


def count_top_pathologies(graph, count=15):
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
    node_bel_cache = {}

    def dcn(node):
        """Decanonicalizes a node tuple to a BEL string

        :param tuple node: A BEL node
        """
        if node in node_bel_cache:
            return node_bel_cache[node]

        node_bel_cache[node] = node_to_bel(graph.node[node])
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
    """Makes a graph summary for sticking in the report

    :param pybel.BELGraph graph:
    :rtype: dict
    """
    log.info('summarizing %s', graph)
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

    log.info('summarized %s in %.2f seconds', graph, time.time() - t)

    return rv


def fill_out_report(network, report, graph_summary):
    """Fills out a report

    :param Network network:
    :param Report report:
    :param dict graph_summary:
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


def insert_graph(m, graph, user_id=1, public=False):  # TODO put this in extended manager for PyBEL Web
    """Insert a graph and also make a report

    :param pybel.manager.Manager m: A PyBEL manager
    :param pybel.BELGraph graph: A BEL graph
    :param int user_id: The identifier of the user to report. Defaults to 1.
    :param bool public: Should the network be public? Defaults to false
    """
    network = m.insert_graph(graph)

    report = Report(
        user_id=user_id,
        public=public,
    )

    graph_summary = make_graph_summary(graph)

    fill_out_report(network, report, graph_summary)

    m.session.add(report)
    m.session.commit()
