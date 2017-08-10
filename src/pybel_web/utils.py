# -*- coding: utf-8 -*-

import base64
import datetime
import itertools as itt
import logging
import pickle
import time
from collections import defaultdict

import pandas
from flask import (
    current_app,
    render_template,
    abort,
    request,
    flash,
    redirect,
    jsonify,
)
from flask_security import current_user
from six import BytesIO
from sqlalchemy import func
from werkzeug.local import LocalProxy

import pybel
from pybel.canonicalize import decanonicalize_node
from pybel.constants import RELATION, GENE
from pybel.manager import Network
from pybel.struct.filters import filter_edges
from pybel_tools.analysis.cmpa import calculate_average_scores_on_subgraphs as calculate_average_cmpa_on_subgraphs
from pybel_tools.analysis.stability import (
    get_contradiction_summary,
    get_regulatory_pairs,
    get_chaotic_pairs,
    get_dampened_pairs,
    get_separate_unstable_correlation_triples,
    get_mutually_unstable_correlation_triples,
    get_jens_unstable,
    get_increase_mismatch_triplets,
    get_decrease_mismatch_triplets,
    get_chaotic_triplets,
    get_dampened_triplets,
)
from pybel_tools.filters import (
    remove_nodes_by_namespace,
    edge_has_pathology_causal,
    iter_undefined_families,
)
from pybel_tools.generation import generate_bioprocess_mechanisms
from pybel_tools.integration import overlay_type_data
from pybel_tools.mutation import collapse_by_central_dogma_to_genes, rewire_variants_to_genes
from pybel_tools.summary import (
    count_functions,
    count_relations,
    count_error_types,
    get_translocated,
    get_degradations,
    get_activities,
    count_namespaces,
    group_errors,
    get_naked_names,
    get_pubmed_identifiers,
    get_annotations,
    get_unused_annotations,
    get_unused_list_annotation_values,
    get_undefined_namespaces,
    get_undefined_annotations,
    get_namespaces_with_incorrect_names,
    info_list,
    count_variants,
    get_unused_namespaces,
    count_citation_years,
)
from pybel_tools.utils import prepare_c3, prepare_c3_time_series, count_dict_values
from .application_utils import get_api, get_manager, get_scai_role, get_user_datastore
from .constants import reporting_log, AND
from .models import User, Report, Experiment, Query, EdgeVote

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

scai_role = LocalProxy(lambda: get_scai_role(current_app))


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
    """
    hub_data = api.get_top_degree(network_id)
    disease_data = api.get_top_pathologies(network_id)

    node_bel_cache = {}

    def dcn(node):
        """Decanonicalizes a node tuple to a BEL string

        :param tuple node: A BEL node
        """
        if node in node_bel_cache:
            return node_bel_cache[node]

        node_bel_cache[node] = decanonicalize_node(graph, node)
        return node_bel_cache[node]

    def get_pair_tuple(u, v):
        return dcn(u), api.get_node_id(u), dcn(v), api.get_node_id(v)

    def get_triplet_tuple(a, b, c):
        return dcn(a), api.get_node_id(a), dcn(b), api.get_node_id(b), dcn(c), api.get_node_id(c)

    regulatory_pairs = [
        get_pair_tuple(u, v)
        for u, v in get_regulatory_pairs(graph)
    ]

    unstable_pairs = list(itt.chain(
        (get_pair_tuple(u, v) + ('Chaotic',) for u, v, in get_chaotic_pairs(graph)),
        (get_pair_tuple(u, v) + ('Dampened',) for u, v, in get_dampened_pairs(graph)),
    ))

    contradictory_pairs = [
        get_pair_tuple(u, v) + (relation,)
        for u, v, relation in get_contradiction_summary(graph)
    ]

    contradictory_triplets = list(itt.chain(
        (get_triplet_tuple(a, b, c) + ('Separate',) for a, b, c in get_separate_unstable_correlation_triples(graph)),
        (get_triplet_tuple(a, b, c) + ('Mutual',) for a, b, c in get_mutually_unstable_correlation_triples(graph)),
        (get_triplet_tuple(a, b, c) + ('Jens',) for a, b, c in get_jens_unstable(graph)),
        (get_triplet_tuple(a, b, c) + ('Increase Mismatch',) for a, b, c in get_increase_mismatch_triplets(graph)),
        (get_triplet_tuple(a, b, c) + ('Decrease Mismatch',) for a, b, c in get_decrease_mismatch_triplets(graph)),
    ))

    unstable_triplets = list(itt.chain(
        (get_triplet_tuple(a, b, c) + ('Chaotic',) for a, b, c in get_chaotic_triplets(graph)),
        (get_triplet_tuple(a, b, c) + ('Dampened',) for a, b, c in get_dampened_triplets(graph)),
    ))

    undefined_namespaces = get_undefined_namespaces(graph)
    undefined_annotations = get_undefined_annotations(graph)
    namespaces_with_incorrect_names = get_namespaces_with_incorrect_names(graph)

    unused_namespaces = get_unused_namespaces(graph)
    unused_annotations = get_unused_annotations(graph)
    unused_list_annotation_values = get_unused_list_annotation_values(graph)

    versions = api.manager.get_networks_by_name(graph.name)

    causal_pathologies = sorted({
        get_pair_tuple(u, v) + (d[RELATION],)
        for u, v, _, d in filter_edges(graph, edge_has_pathology_causal)
    })

    undefined_sfam = [
        (dcn(node), api.get_node_id(node))
        for node in iter_undefined_families(graph, ['SFAM', 'GFAM'])
    ]

    citation_years = create_timeline(count_citation_years(graph))

    overlap_counter = api.get_node_overlap(network_id)
    allowed_network_ids = get_network_ids_with_permission_helper(current_user, api)
    overlaps = [
        (api.manager.get_network_by_id(network_id), v)
        for network_id, v in overlap_counter.most_common()
        if network_id in allowed_network_ids
    ]
    top_overlaps = overlaps[:10]

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
        chart_9_data=prepare_c3(disease_data, 'Pathologies'),
        chart_10_data=prepare_c3_time_series(citation_years, 'Number of articles') if citation_years else None,
        error_groups=count_dict_values(group_errors(graph)).most_common(20),
        info_list=info_list(graph),
        regulatory_pairs=regulatory_pairs,
        contradictions=contradictory_pairs,
        unstable_pairs=unstable_pairs,
        contradictory_triplets=contradictory_triplets,
        unstable_triplets=unstable_triplets,
        graph=graph,
        network=manager.session.query(Network).get(network_id),
        network_id=network_id,
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
        overlaps=top_overlaps,
        naked_names=naked_names,
    )


def run_experiment(manager_, file, filename, description, gene_column, data_column, permutations, network, sep=','):
    """

    :param pybel.manager.CacheManager manager_: A cache manager
    :param file file:
    :param str filename:
    :param str description:
    :param str gene_column:
    :param str data_column:
    :param int permutations:
    :param Network network:
    :param str sep:
    :return:
    """
    t = time.time()

    df = pandas.read_csv(file, sep=sep)

    for column in (gene_column, data_column):
        if column not in df.columns:
            raise ValueError('{} not a column in document'.format(column))

    df = df.loc[df[gene_column].notnull(), [gene_column, data_column]]

    data = {k: v for _, k, v in df.itertuples()}

    graph = network.as_bel()

    remove_nodes_by_namespace(graph, {'MGI', 'RGD'})
    collapse_by_central_dogma_to_genes(graph)
    rewire_variants_to_genes(graph)

    overlay_type_data(graph, data, LABEL, GENE, 'HGNC', overwrite=False, impute=0)

    candidate_mechanisms = generate_bioprocess_mechanisms(graph, LABEL)
    scores = calculate_average_cmpa_on_subgraphs(candidate_mechanisms, LABEL, runs=permutations)

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

    manager_.session.add(experiment)
    manager_.session.commit()

    return experiment


def log_graph(graph, user, preparsed=False, failed=False):
    """

    :param pybel.BELGraph graph:
    :param User user:
    :param bool preparsed:
    :param bool failed:
    """
    reporting_log.info(
        '%s%s %s %s v%s with %d nodes, %d edges, and %d warnings', 'FAILED ' if failed else '',
        user,
        'uploaded' if preparsed else 'compiled',
        graph.name,
        graph.version,
        graph.number_of_nodes(),
        graph.number_of_edges(),
        len(graph.warnings)
    )


def add_network_reporting(manager_, network, user, number_nodes, number_edges, number_warnings, preparsed=False,
                          public=True):
    """

    :param manager_:
    :param network:
    :param user:
    :param number_nodes:
    :param number_edges:
    :param number_warnings:
    :param preparsed:
    :param public:
    :return:
    """
    reporting_log.info(
        '%s %s %s v%s with %d nodes, %d edges, and %d warnings',
        user,
        'uploaded' if preparsed else 'compiled',
        network.name,
        network.version,
        number_nodes,
        number_edges,
        number_warnings
    )

    report = Report(
        network=network,
        user=user,
        precompiled=preparsed,
        number_nodes=number_nodes,
        number_edges=number_edges,
        number_warnings=number_warnings,
        public=public,
    )
    manager_.session.add(report)
    manager_.session.commit()


def get_recent_reports(manager_, weeks=2):
    """Gets reports from the last two weeks

    :param pybel.manager.CacheManager manager_: A cache manager
    :param int weeks: The number of weeks to look backwards (builds :class:`datetime.timedelta`)
    :return: An iterable of the string that should be reported
    :rtype: iter[str]
    """
    now = datetime.datetime.utcnow()
    delta = datetime.timedelta(weeks=weeks)
    q = manager_.session.query(Report).filter(Report.created - now < delta).join(Network).group_by(Network.name)
    q1 = q.having(func.min(Report.created)).order_by(Network.name.asc()).all()
    q2 = q.having(func.max(Report.created)).order_by(Network.name.asc()).all()

    q3 = manager_.session.query(Report, func.count(Report.network)). \
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


def iterate_user_strings(manager_, with_passwords):
    """Iterates over strings to print describing users

    :param pybel.manager.CacheManager manager_:
    :param bool with_passwords:
    :rtype: iter[str]
    """
    for u in manager_.session.query(User).all():
        yield '{}\t{}\t{}\t{}{}'.format(
            u.email,
            u.first_name,
            u.last_name,
            ','.join(sorted(r.name for r in u.roles)),
            '\t{}'.format(u.password) if with_passwords else ''
        )


def sanitize_pipeline(function_name):
    """Converts method.__name__ from capital and spaced to lower and underscore separated

    :param str function_name:
    :return: function name sanitized
    :rtype: str
    """
    return function_name.replace(" ", "_").lower()


def sanitize_annotation(annotation_list):
    """Converts annotation (Annotation:value) to tuple

    :param list[str] annotation_list:
    :return: annotation dictionary
    :rtype: dict[str,list[str]]
    """
    annotation_dict = defaultdict(list)

    for annotation_string in annotation_list:
        annotation, annotation_value = annotation_string.split(":")[0:2]
        annotation_dict[annotation].append(annotation_value)

    return dict(annotation_dict)


# TODO @ddomingof document this
def convert_seed_value(key, form, value):
    """

    :param key:
    :param form:
    :param value:
    :return:
    """
    if key == 'annotation':
        query_type = not form.get(AND)
        return {'annotations': sanitize_annotation(form.getlist(value)), 'or': query_type}
    elif key in {'pubmed', 'authors'}:
        return form.getlist(value)
    else:
        return api.get_nodes_by_ids(form.getlist(value, type=int))


def query_form_to_dict(form):
    """Converts a request.form multidict to the query JSON format.

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


def calculate_overlap_dict(g1, g2, set_labels=('Query 1', 'Query 2')):
    """

    :param pybel.BELGraph g1:
    :param pybel.BELGraph g2:
    :param set_labels: A tuple of length two with the labels for the graphs
    :return: A dictionary containing important information for displaying base64 images
    :rtype: dict
    """
    import matplotlib
    # See: http://matplotlib.org/faq/usage_faq.html#what-is-a-backend
    matplotlib.use('AGG')

    from matplotlib_venn import venn2
    import matplotlib.pyplot as plt

    plt.clf()
    plt.cla()
    plt.close()

    nodes_overlap_file = BytesIO()
    venn2(
        [set(g1.nodes_iter()), set(g2.nodes_iter())],
        set_labels=set_labels
    )
    plt.savefig(nodes_overlap_file, format='png')
    nodes_overlap_file.seek(0)
    nodes_overlap_data = base64.b64encode(nodes_overlap_file.getvalue())

    plt.clf()
    plt.cla()
    plt.close()

    edges_overlap_file = BytesIO()
    venn2(
        [set(g1.edges_iter()), set(g2.edges_iter())],
        set_labels=set_labels
    )
    plt.savefig(edges_overlap_file, format='png')
    edges_overlap_file.seek(0)
    edges_overlap_data = base64.b64encode(edges_overlap_file.getvalue())

    plt.clf()
    plt.cla()
    plt.close()

    citations_overlap_file = BytesIO()
    venn2(
        [get_pubmed_identifiers(g1), get_pubmed_identifiers(g2)],
        set_labels=set_labels

    )
    plt.savefig(citations_overlap_file, format='png')
    citations_overlap_file.seek(0)
    citations_overlap_data = base64.b64encode(citations_overlap_file.getvalue())

    plt.clf()
    plt.cla()
    plt.close()

    annotations_overlap_file = BytesIO()
    venn2(
        [get_annotations(g1), get_annotations(g2)],
        set_labels=set_labels

    )
    plt.savefig(annotations_overlap_file, format='png')
    annotations_overlap_file.seek(0)
    annotations_overlap_data = base64.b64encode(annotations_overlap_file.getvalue())

    return {
        'nodes': nodes_overlap_data.decode('utf-8'),
        'edges': edges_overlap_data.decode('utf-8'),
        'citations': citations_overlap_data.decode('utf-8'),
        'annotations': annotations_overlap_data.decode('utf-8')
    }


def list_public_networks(api_):
    """Lists the graphs that have been made public

    :param DatabaseService api_:
    :rtype: list[Network]
    """
    return [
        network
        for network in api_.list_recent_networks()
        if network.report and network.report.public
    ]


def unique_networks(networks):
    """Only yields unique networks

    :param iter[Network] networks: An iterable of networks
    :return: An iterable over the unique network identifiers in the original iterator
    :rtype: iter[Network]
    """
    seen_ids = set()

    for network in networks:
        if not network:
            continue

        if network.id not in seen_ids:
            seen_ids.add(network.id)
            yield network


def networks_with_permission_iter_helper(user, api_):
    """Gets an iterator over all the networks from all the sources

    :param models.User user:
    :param pybel_tools.api.DatabaseService api_:
    :rtype: iter[Network]
    """
    if not user.is_authenticated:
        yield from list_public_networks(api_)

    elif user.admin:
        yield from api_.list_recent_networks()

    else:
        yield from list_public_networks(api_)
        yield from user.get_owned_networks()
        yield from user.get_shared_networks()
        yield from user.get_project_networks()

        if user.has_role('scai'):
            for user in scai_role.users:
                yield from user.get_owned_networks()
                yield from user.get_project_networks()
                yield from user.get_shared_networks()


def get_networks_with_permission(api_):
    """Gets all networks tagged as public or uploaded by the current user

    :param DatabaseService api_: The database service
    :return: A list of all networks tagged as public or uploaded by the current user
    :rtype: list[Network]
    """
    if not current_user.is_authenticated:
        return list_public_networks(api_)

    if current_user.admin:
        return api_.list_recent_networks()

    return list(unique_networks(networks_with_permission_iter_helper(current_user, api_)))


def get_network_ids_with_permission_helper(user, api_):
    """Gets the set of networks ids tagged as public or uploaded by the current user

    :param models.User user:
    :param DatabaseService api_: The database service
    :return: A list of all networks tagged as public or uploaded by the current user
    :rtype: set[int]
    """
    return {
        network.id
        for network in networks_with_permission_iter_helper(user, api_)
    }


def user_has_query_rights(user, query):
    """Checks if the user has rights to run the given query

    :param models.User user: A user object
    :param models.Query query: A query object
    :rtype: bool
    """
    if user.is_authenticated and user.admin:
        return True

    permissive_network_ids = get_network_ids_with_permission_helper(user, api)

    return all(
        network.id in permissive_network_ids
        for network in query.assembly.networks
    )


def current_user_has_query_rights(query_id):
    """Checks if the current user has rights to run the given query

    :param int query_id: The database identifier for a query
    :rtype: bool
    """
    if current_user.is_authenticated and current_user.admin:
        return True

    query = manager.session.query(Query).get(query_id)

    return user_has_query_rights(current_user, query)


def safe_get_query(query_id):
    """Gets a query or raises an abort

    :param int query_id:
    :rtype: pybel_web.models.Query
    """
    query = manager.session.query(Query).get(query_id)

    if query is None:
        abort(400, 'Query {} not found'.format(query_id))

    if not user_has_query_rights(current_user, query):
        abort(403, 'Insufficient rights to run query {}'.format(query_id))

    return query


def get_vote(edge_id, user_id):
    """Gets a vote for the given edge and user

    :param int edge_id:
    :param int user_id:
    :rtype: EdgeVote
    """
    return manager.session.query(EdgeVote).filter(EdgeVote.edge_id == edge_id,
                                                  EdgeVote.user_id == user_id).one_or_none()


def next_or_jsonify(message, *args, status=200, category='message', **kwargs):
    """Neatly wraps a redirect to a new URL if the ``next`` argument is set in the request otherwise sends JSON
    feedback.

    :param str message:
    :param int status:
    :param str category:
    :param dict kwargs:
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


def assert_user_owns_network(network, user):
    """Check that the user is the owner of the the network. Sends a Flask abort 403 signal if not.

    :param Network network: A network
    :param User user: A user
    """
    if not network.report or user != network.report.user:
        abort(403, 'You do not own this network')


def calculate_scores(graph, data, runs):
    remove_nodes_by_namespace(graph, {'MGI', 'RGD'})
    collapse_by_central_dogma_to_genes(graph)
    rewire_variants_to_genes(graph)

    overlay_type_data(graph, data, LABEL, GENE, 'HGNC', overwrite=False, impute=0)

    candidate_mechanisms = generate_bioprocess_mechanisms(graph, LABEL)
    scores = calculate_average_cmpa_on_subgraphs(candidate_mechanisms, LABEL, runs=runs)

    return scores
