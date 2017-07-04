# -*- coding: utf-8 -*-

import base64
import datetime
import itertools as itt
import logging
import pickle
from collections import defaultdict

import pandas
from flask import current_app
from flask import render_template
from flask_login import current_user
from matplotlib import pyplot as plt
from matplotlib_venn import venn2
from six import BytesIO
from sqlalchemy import func
from werkzeug.local import LocalProxy

import pybel
from pybel.canonicalize import decanonicalize_node
from pybel.constants import RELATION, GENE
from pybel.manager import Network
from pybel.struct.filters import filter_edges
from pybel_tools.analysis import npa
from pybel_tools.analysis.stability import *
from pybel_tools.filters import remove_nodes_by_namespace
from pybel_tools.filters.edge_filters import edge_has_pathology_causal
from pybel_tools.filters.node_filters import iter_undefined_families
from pybel_tools.generation import generate_bioprocess_mechanisms
from pybel_tools.integration import overlay_type_data
from pybel_tools.mutation import collapse_by_central_dogma_to_genes, rewire_variants_to_genes
from pybel_tools.summary import (
    get_contradiction_summary,
    count_functions,
    count_relations,
    count_error_types,
    get_translocated,
    get_degradations,
    get_activities,
    count_namespaces,
    group_errors,
    get_naked_names,
)
from pybel_tools.summary.edge_summary import (
    get_unused_annotations,
    get_unused_list_annotation_values
)
from pybel_tools.summary.error_summary import (
    get_undefined_namespaces,
    get_undefined_annotations,
    get_namespaces_with_incorrect_names
)
from pybel_tools.summary.export import info_list
from pybel_tools.summary.node_properties import count_variants
from pybel_tools.summary.node_summary import get_unused_namespaces
from pybel_tools.utils import prepare_c3, count_dict_values
from .application import get_manager, get_api, get_user_datastore
from .constants import *
from .models import User, Report, Experiment, Query

log = logging.getLogger(__name__)

LABEL = 'dgxa'


def get_manager_proxy():
    """Gets a proxy for the manager in the current app

    :rtype: pybel.manager.cache.CacheManager
    """
    return LocalProxy(lambda: get_manager(current_app))


def get_api_proxy():
    """
    Gets a proxy for the api from the current app

    :rtype: pybel_tools.api.DatabaseService
    """
    return LocalProxy(lambda: get_api(current_app))


def get_userdatastore_proxy():
    """Gets a proxy for the user datastore from the current app

    :rtype: flask_security.SQLAlchemyUserDataStore
    """
    return LocalProxy(lambda: get_user_datastore(current_app))


manager = get_manager_proxy()
api = get_api_proxy()
user_datastore = get_userdatastore_proxy()


def create_timeline(year_counter):
    """Completes the Counter timeline
    
    :param Counter year_counter: counter dict for each year
    :return: complete timeline
    :rtype: list[tuple]
    """
    if not year_counter:
        return []

    until_year = datetime.datetime.now().year
    from_year = min(year_counter)

    timeline = [
        (year, year_counter.get(year, 0))
        for year in range(from_year, until_year)
    ]

    return timeline


def sanitize_list_of_str(l):
    """Strips all strings in a list and filters to the non-empty ones
    
    :type l: iter[str]
    :rtype: list[str]
    """
    return [e for e in (e.strip() for e in l) if e]


def render_network_summary(network_id, graph):
    """Renders the graph summary page
    
    :param int network_id: 
    :param pybel.BELGraph graph: 
    :param pybel_tools.api.DatabaseService api:
    """
    hub_data = api.get_top_degree(network_id)
    centrality_data = api.get_top_centrality(network_id)
    disease_data = api.get_top_pathologies(network_id)

    node_bel_cache = {}

    def dcn(node):
        if node in node_bel_cache:
            return node_bel_cache[node]

        node_bel_cache[node] = decanonicalize_node(graph, node)
        return node_bel_cache[node]

    unstable_pairs = itt.chain.from_iterable([
        ((u, v, 'Chaotic') for u, v, in get_chaotic_pairs(graph)),
        ((u, v, 'Dampened') for u, v, in get_dampened_pairs(graph)),
    ])
    unstable_pairs = [
        (dcn(u), api.get_node_id(u), dcn(v), api.get_node_id(v), label)
        for u, v, label in unstable_pairs
    ]

    contradictory_pairs = [
        (dcn(u), api.get_node_id(u), dcn(v), api.get_node_id(v), relation)
        for u, v, relation in get_contradiction_summary(graph)
    ]

    contradictory_triplets = itt.chain.from_iterable([
        ((a, b, c, 'Separate') for a, b, c in get_separate_unstable_correlation_triples(graph)),
        ((a, b, c, 'Mutual') for a, b, c in get_mutually_unstable_correlation_triples(graph)),
        ((a, b, c, 'Jens') for a, b, c in get_jens_unstable_alpha(graph)),
        ((a, b, c, 'Increase Mismatch') for a, b, c in get_increase_mismatch_triplets(graph)),
        ((a, b, c, 'Decrease Mismatch') for a, b, c in get_decrease_mismatch_triplets(graph)),

    ])

    contradictory_triplets = [
        (dcn(a), api.get_node_id(a), dcn(b), api.get_node_id(b), dcn(c), api.get_node_id(c), d)
        for a, b, c, d in contradictory_triplets
    ]

    unstable_triplets = itt.chain.from_iterable([
        ((a, b, c, 'Chaotic') for a, b, c in get_chaotic_triplets(graph)),
        ((a, b, c, 'Dampened') for a, b, c in get_dampened_triplets(graph)),
    ])
    unstable_triplets = [
        (dcn(a), api.get_node_id(a), dcn(b), api.get_node_id(b), dcn(c), api.get_node_id(c), d)
        for a, b, c, d in unstable_triplets
    ]

    undefined_namespaces = get_undefined_namespaces(graph)
    undefined_annotations = get_undefined_annotations(graph)
    namespaces_with_incorrect_names = get_namespaces_with_incorrect_names(graph)

    unused_namespaces = get_unused_namespaces(graph)
    unused_annotations = get_unused_annotations(graph)
    unused_list_annotation_values = get_unused_list_annotation_values(graph)

    versions = api.manager.get_networks_by_name(graph.name)

    causal_pathologies = sorted({
        (dcn(u), api.get_node_id(u), d[RELATION], dcn(v), api.get_node_id(v))
        for u, v, _, d in filter_edges(graph, edge_has_pathology_causal)
    })

    undefined_sfam = [
        (dcn(node), api.get_node_id(node))
        for node in iter_undefined_families(graph, ['SFAM', 'GFAM'])
    ]

    # citation_years = create_timeline(count_citation_years(graph))

    overlap_counter = api.get_node_overlap(network_id)
    overlaps = [
        (api.manager.get_network_by_id(network_id), v)
        for network_id, v in overlap_counter.most_common(10)
    ]

    naked_names = get_naked_names(graph)

    return render_template(
        'summary.html',
        chart_1_data=prepare_c3(count_functions(graph), 'Entity Type'),
        chart_2_data=prepare_c3(count_relations(graph), 'Relationship Type'),
        chart_3_data=prepare_c3(count_error_types(graph), 'Error Type'),
        chart_4_data=prepare_c3({
            'Translocations': len(get_translocated(graph)),
            'Degradations': len(get_degradations(graph)),
            'Molecular Activities': len(get_activities(graph))
        }, 'Modifier Type'),
        chart_5_data=prepare_c3(count_variants(graph), 'Node Variants'),
        chart_6_data=prepare_c3(count_namespaces(graph), 'Namespaces'),
        chart_7_data=prepare_c3(hub_data, 'Top Hubs'),
        chart_8_data=prepare_c3(centrality_data, 'Top Central'),
        chart_9_data=prepare_c3(disease_data, 'Pathologies'),
        # chart_10_data=prepare_c3(citation_years, 'Most cited years'),
        error_groups=count_dict_values(group_errors(graph)).most_common(20),
        info_list=info_list(graph),
        contradictions=contradictory_pairs,
        unstable_pairs=unstable_pairs,
        contradictory_triplets=contradictory_triplets,
        unstable_triplets=unstable_triplets,
        graph=graph,
        network=manager.session.query(Network).get(network_id),
        network_id=network_id,
        time=None,
        undefined_namespaces=sorted(undefined_namespaces),
        unused_namespaces=sorted(unused_namespaces),
        undefined_annotations=sorted(undefined_annotations),
        unused_annotations=sorted(unused_annotations),
        unused_list_annotation_values=sorted(unused_list_annotation_values.items()),
        current_user=current_user,
        namespaces_with_incorrect_names=namespaces_with_incorrect_names,
        network_versions=versions,
        causal_pathologies=causal_pathologies,
        undefined_families=undefined_sfam,
        overlaps=overlaps,
        naked_names=naked_names,
    )


def run_experiment(file, filename, description, gene_column, data_column, permutations, manager, network_id, sep=','):
    t = time.time()

    df = pandas.read_csv(file, sep=sep)

    for column in (gene_column, data_column):
        if column not in df.columns:
            raise ValueError('{} not a column in document'.format(column))

    df = df.loc[df[gene_column].notnull(), [gene_column, data_column]]

    data = {k: v for _, k, v in df.itertuples()}

    network = manager.get_network_by_id(network_id)
    graph = network.as_bel()

    remove_nodes_by_namespace(graph, {'MGI', 'RGD'})
    collapse_by_central_dogma_to_genes(graph)
    rewire_variants_to_genes(graph)

    overlay_type_data(graph, data, LABEL, GENE, 'HGNC', overwrite=False, impute=0)

    candidate_mechanisms = generate_bioprocess_mechanisms(graph, LABEL)
    scores = npa.calculate_average_npa_on_subgraphs(candidate_mechanisms, LABEL, runs=permutations)

    log.info('done running CMPA in %.2fs', time.time() - t)

    experiment = Experiment(
        description=description,
        source_name=filename,
        source=pickle.dumps(df),
        result=pickle.dumps(scores),
        permutations=permutations,
        user=current_user,
        network=network,
    )

    manager.session.add(experiment)
    manager.session.commit()

    return experiment


def log_graph(graph, current_user, preparsed=False, failed=False):
    """

    :param pybel.BELGraph graph:
    :param current_user:
    :param bool preparsed:
    :param bool failed:
    """
    reporting_log.info(
        '%s%s %s %s v%s with %d nodes, %d edges, and %d warnings', 'FAILED ' if failed else '',
        current_user,
        'uploaded' if preparsed else 'compiled',
        graph.name,
        graph.version,
        graph.number_of_nodes(),
        graph.number_of_edges(),
        len(graph.warnings)
    )


def add_network_reporting(manager, network, current_user, number_nodes, number_edges, number_warnings,
                          preparsed=False, public=True):
    reporting_log.info(
        '%s %s %s v%s with %d nodes, %d edges, and %d warnings',
        current_user,
        'uploaded' if preparsed else 'compiled',
        network.name,
        network.version,
        number_nodes,
        number_edges,
        number_warnings
    )

    report = Report(
        network=network,
        user=current_user,
        precompiled=preparsed,
        number_nodes=number_nodes,
        number_edges=number_edges,
        number_warnings=number_warnings,
        public=public,
    )
    manager.session.add(report)
    manager.session.commit()


def get_recent_reports(manager, weeks=2):
    """Gets reports from the last two weeks

    :param pybel.manager.CacheManager manager: A cache manager
    :param int weeks: The number of weeks to look backwards (builds :class:`datetime.timedelta`)
    :return: An iterable of the string that should be reported
    :rtype: iter[str]
    """
    now = datetime.datetime.utcnow()
    delta = datetime.timedelta(weeks=weeks)
    q = manager.session.query(Report).filter(Report.created - now < delta).join(Network).group_by(Network.name)
    q1 = q.having(func.min(Report.created)).order_by(Network.name.asc()).all()
    q2 = q.having(func.max(Report.created)).order_by(Network.name.asc()).all()

    q3 = manager.session.query(Report, func.count(Report.network)). \
        filter(Report.created - now < delta). \
        join(Network).group_by(Network.name). \
        order_by(Network.name.asc()).all()

    for a, b, (_, count) in zip(q1, q2, q3):
        yield a.network.name

        if a.network.version == b.network.version:
            yield '\tUploaded only {}'.format(a.network.version)
            yield '\tNodes: {}'.format(a.number_nodes)
            yield '\tEdges: {}'.format(a.number_edges)
            yield '\tWarnings: {}'.format(a.number_warnings)
        else:
            yield '\tUploads: {}'.format(count)
            yield '\tVersion: {} -> {}'.format(a.network.version, b.network.version)
            yield '\tNodes: {} {:+d} {}'.format(a.number_nodes, b.number_nodes - a.number_nodes, b.number_nodes)
            yield '\tEdges: {} {:+d} {}'.format(a.number_edges, b.number_edges - a.number_edges, b.number_edges)
            yield '\tWarnings: {} {:+d} {}'.format(a.number_warnings, b.number_warnings - a.number_warnings,
                                                   b.number_warnings)
        yield ''


def iterate_user_strings(manager, with_passwords):
    for u in manager.session.query(User).all():
        yield '{}\t{}\t{}\t{}{}'.format(
            u.email,
            u.first_name,
            u.last_name,
            ','.join(sorted(r.name for r in u.roles)),
            '\t{}'.format(u.password) if with_passwords else ''
        )


def sanitize_pipeline(function_name):
    """Converts method.__name__ from capital and spaced to lower and underscore separated
    :param str function_name
    :return: function name sanitized
    :rtype: str
    """
    return function_name.replace(" ", "_").lower()


def sanitize_annotation(annotation_list):
    """Converts annotation (Annotation:value) to tuple
    :param list annotations
    :return: annotation dictionary
    :rtype: dict
    """
    annotation_dict = defaultdict(list)

    for annotation_string in annotation_list:
        annotation, annotation_value = annotation_string.split(":")[0:2]
        annotation_dict[annotation].append(annotation_value)

    return dict(annotation_dict)


def convert_seed_value(key, form, value):
    if key == 'annotation':
        return sanitize_annotation(form.getlist(value))
    elif key in {'pubmed', 'authors'}:
        return form.getlist(value)
    else:
        return api.get_nodes_by_ids(form.getlist(value, type=int))


def query_form_to_dict(form):
    """ Converts a request.form multidict to the query JSON format.

    :param werkzeug.datastructures.ImmutableMultiDict form:
    :return: json representation of the query
    :rtype: dict
    """
    query_dict = {}

    pairs = [
        ('pubmed', "pubmed_selection[]"),
        ('authors', 'author_selection[]'),
        ('annotation', 'annotation_selection[]'),
        (form["seed_method"], "node_selection[]")
    ]

    query_dict['seeding'] = [
        {"type": key, 'data': convert_seed_value(key, form, value)}
        for key, value in pairs
        if form.getlist(value)
    ]

    query_dict["pipeline"] = [
        {'function': sanitize_pipeline(function_name)}
        for function_name in form.getlist("pipeline[]")
        if function_name
    ]

    if form.getlist("network_ids[]"):
        query_dict["network_ids"] = form.getlist("network_ids[]")

    return query_dict


def get_query_ancestor_id(query_id):
    """Gets the oldest ancestor of the given query

    :param int query_id: The original query database identifier
    :rtype: models.Query
    """
    query = manager.session.query(Query).get(query_id)

    if not query.parent_id:
        return query_id

    return get_query_ancestor_id(query.parent_id)


def get_query_descendants(query_id):
    """Gets all ancestors to the root query as a list of queries. In this formulation, the original query comes first
    in the list, with its parent next, its grandparent third, and so-on.

    :param int query_id: The original query database identifier
    :rtype: list[models.Query]
    """
    query = manager.session.query(Query).get(query_id)

    if not query.parent_id:
        return [query]

    return [query] + get_query_descendants(query.parent_id)


def calculate_overlap_dict(g1, g2):
    nodes_overlap_file = BytesIO()
    venn2([set(g1.nodes_iter()), set(g2.nodes_iter())],
          set_labels=['Query 1', 'Query 2'])
    plt.savefig(nodes_overlap_file, format='png')
    nodes_overlap_file.seek(0)
    nodes_overlap_data = base64.b64encode(nodes_overlap_file.getvalue())

    return {
        'nodes': nodes_overlap_data.decode('utf-8')
    }
