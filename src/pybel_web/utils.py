# -*- coding: utf-8 -*-

import base64
import datetime
import itertools as itt
import logging
import pickle
import time
import warnings
from collections import Counter, defaultdict

import networkx as nx
import pandas
from flask import abort, current_app, flash, jsonify, redirect, render_template, request
from flask_security import current_user
from six import BytesIO
from sqlalchemy import func
from werkzeug.local import LocalProxy

import pybel
from pybel.canonicalize import calculate_canonical_name, node_to_bel
from pybel.constants import GENE, RELATION
from pybel.manager import Network
from pybel.parser.canonicalize import node_to_tuple
from pybel.struct.filters import filter_edges
from pybel.summary import get_syntax_errors
from pybel.utils import hash_node
from pybel_tools.analysis.cmpa import calculate_average_scores_on_subgraphs as calculate_average_cmpa_on_subgraphs
from pybel_tools.analysis.stability import (
    get_chaotic_pairs, get_chaotic_triplets, get_contradiction_summary,
    get_dampened_pairs, get_dampened_triplets, get_decrease_mismatch_triplets, get_increase_mismatch_triplets,
    get_jens_unstable, get_mutually_unstable_correlation_triples, get_regulatory_pairs,
    get_separate_unstable_correlation_triples,
)
from pybel_tools.filters import edge_has_pathology_causal, iter_undefined_families, remove_nodes_by_namespace
from pybel_tools.generation import generate_bioprocess_mechanisms
from pybel_tools.integration import overlay_type_data
from pybel_tools.mutation import collapse_by_central_dogma_to_genes, rewire_variants_to_genes
from pybel_tools.summary import (
    count_error_types, count_functions, count_namespaces, count_pathologies,
    count_relations, count_unique_authors, count_unique_citations, count_variants, get_annotations, get_citation_years,
    get_modifications_count, get_most_common_errors, get_naked_names, get_namespaces_with_incorrect_names,
    get_pubmed_identifiers, get_undefined_annotations, get_undefined_namespaces, get_unused_annotations,
    get_unused_list_annotation_values, get_unused_namespaces,
)
from pybel_tools.utils import min_tanimoto_set_similarity, prepare_c3, prepare_c3_time_series
from .application_utils import get_manager, get_user_datastore
from .constants import AND, reporting_log
from .models import EdgeVote, Experiment, NetworkOverlap, Query, Report, User

log = logging.getLogger(__name__)

LABEL = 'dgxa'


def get_manager_proxy():
    """Gets a proxy for the manager in the current app

    :rtype: pybel.manager.Manager
    """
    return LocalProxy(lambda: get_manager(current_app))


def get_userdatastore_proxy():
    """Gets a proxy for the user datastore from the current app

    :rtype: flask_security.SQLAlchemyUserDataStore
    """
    return LocalProxy(lambda: get_user_datastore(current_app))


manager = get_manager_proxy()
user_datastore = get_userdatastore_proxy()


def sanitize_list_of_str(l):
    """Strips all strings in a list and filters to the non-empty ones
    
    :type l: iter[str]
    :rtype: list[str]
    """
    return [e for e in (e.strip() for e in l) if e]


def get_top_overlaps(network_id, number=10):
    overlap_counter = get_node_overlaps(network_id)
    allowed_network_ids = get_network_ids_with_permission_helper(current_user, manager)
    overlaps = [
        (manager.get_network_by_id(network_id), v)
        for network_id, v in overlap_counter.most_common()
        if network_id in allowed_network_ids and v > 0.0
    ]
    return overlaps[:number]


def canonical_hash(graph, node):
    data = graph.node[node]
    canonical_node_tuple = node_to_tuple(data)
    return hash_node(canonical_node_tuple)


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


def get_network_summary_dict(graph):
    node_bel_cache = {}

    def dcn(node):
        """Decanonicalizes a node tuple to a BEL string

        :param tuple node: A BEL node
        """
        if node in node_bel_cache:
            return node_bel_cache[node]

        node_bel_cache[node] = node_to_bel(graph, node)
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
            get_pair_tuple(u, v) + (d[RELATION],)
            for u, v, _, d in filter_edges(graph, edge_has_pathology_causal)
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
    )


def render_network_summary(network_id, template):
    """Renders the graph summary page
    
    :param int network_id:
    :param str template:
    """
    network = manager.session.query(Network).get(network_id)
    graph = network.as_bel()

    try:
        er = network.report.get_calculations()
    except:  # TODO remove this later
        log.warning('Falling back to on-the-fly calculation of summary of %s', network)
        er = get_network_summary_dict(graph)

        if network.report:
            network.report.dump_calculations(er)
            manager.session.commit()

    citation_years = er['citation_years']
    function_count = er['function_count']
    relation_count = er['relation_count']
    error_count = er['error_count']
    modifications_count = er['modifications_count']

    hub_data = er.get('hub_data')  # FIXME assume it's there

    if not hub_data:
        log.warning('Calculating hub data on the fly')
        hub_data = get_top_hubs(graph)

    disease_data = er.get('disease_data')  # FIXME assume it's there

    if not disease_data:
        disease_data = count_top_pathologies(graph)

    overlaps = get_top_overlaps(network_id)
    network_versions = manager.get_networks_by_name(graph.name)

    syntax_errors = get_syntax_errors(graph)

    return render_template(
        template,
        current_user=current_user,
        network=network,
        graph=graph,
        network_id=network_id,
        network_versions=network_versions,
        overlaps=overlaps,
        chart_1_data=prepare_c3(function_count, 'Entity Type'),
        chart_2_data=prepare_c3(relation_count, 'Relationship Type'),
        chart_3_data=prepare_c3(error_count, 'Error Type') if error_count else None,
        chart_4_data=prepare_c3(modifications_count) if modifications_count else None,
        chart_5_data=prepare_c3(count_variants(graph), 'Node Variants'),
        chart_6_data=prepare_c3(count_namespaces(graph), 'Namespaces'),
        chart_7_data=prepare_c3(hub_data, 'Top Hubs'),
        chart_9_data=prepare_c3(disease_data, 'Pathologies') if disease_data else None,
        chart_10_data=prepare_c3_time_series(citation_years, 'Number of articles') if citation_years else None,
        syntax_errors=syntax_errors,
        **er
    )


def run_experiment(manager_, file, filename, description, gene_column, data_column, permutations, network, sep=','):
    """

    :param pybel.manager.Manager manager_: A cache manager
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


def get_recent_reports(manager_, weeks=2):
    """Gets reports from the last two weeks

    :param pybel.manager.Manager manager_: A cache manager
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


def iterate_user_strings(manager_):
    """Iterates over strings to print describing users

    :param pybel.manager.Manager manager_:
    :rtype: iter[str]
    """
    for user in manager_.session.query(User).all():
        yield '{email}\t{password}\t{roles}\t{name}'.format(
            email=user.email,
            password=user.password,
            roles=','.join(sorted(r.name for r in user.roles)),
            name=(user.name if user.name else '')
        )


def to_snake_case(function_name):
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


def convert_seed_value(key, form, value):
    """ Normalize the form to type:data format

    :param str key: seed method
    :param ImmutableMultiDict form: Form dictionary
    :param str value: data (nodes, authors...)
    :return: Normalized data depending on the seeding method
    """
    if key == 'annotation':
        query_type = not form.get(AND)
        return {'annotations': sanitize_annotation(form.getlist(value)), 'or': query_type}
    elif key in {'pubmed', 'authors'}:
        return form.getlist(value)
    else:
        node_hashes = form.getlist(value)
        return [
            manager.get_node_tuple_by_hash(node_hash)
            for node_hash in node_hashes
        ]


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
        {'function': to_snake_case(function_name)}
        for function_name in form.getlist("pipeline[]")
        if function_name
    ]

    if form.getlist("network_ids[]"):
        query_dict["network_ids"] = form.getlist("network_ids[]")

    return query_dict


def get_query_ancestor_id(query_id):
    """Gets the oldest ancestor of the given query

    :param int query_id: The original query database identifier
    :rtype: Query
    """
    query = manager.session.query(Query).get(query_id)

    if not query.parent_id:
        return query_id

    return get_query_ancestor_id(query.parent_id)


def get_query_descendants(query_id):
    """Gets all ancestors to the root query as a list of queries. In this formulation, the original query comes first
    in the list, with its parent next, its grandparent third, and so-on.

    :param int query_id: The original query database identifier
    :rtype: list[Query]
    """
    query = manager.session.query(Query).get(query_id)

    if not query.parent_id:
        return [query]

    return [query] + get_query_descendants(query.parent_id)


def calculate_overlap_dict(g1, g2, g1_label=None, g2_label=None):
    """Creates a dictionary of images depicting the graphs' overlaps in multiple categories

    :param pybel.BELGraph g1: A BEL graph
    :param pybel.BELGraph g2: A BEL graph
    :return: A dictionary containing important information for displaying base64 images
    :rtype: dict
    """
    set_labels = (g1_label, g2_label)

    import matplotlib
    # See: http://matplotlib.org/faq/usage_faq.html#what-is-a-backend
    matplotlib.use('AGG')

    from matplotlib_venn import venn2
    import matplotlib.pyplot as plt

    plt.clf()
    plt.cla()
    plt.close()

    nodes_overlap_file = BytesIO()
    g1_nodes = set(g1)
    g2_nodes = set(g2)
    venn2(
        [g1_nodes, g2_nodes],
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
    g1_annotations = get_annotations(g1)
    g2_annotations = get_annotations(g2)
    venn2(
        [g1_annotations, g2_annotations],
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


def iter_public_networks(manager_):
    """Lists the graphs that have been made public

    :param pybel.manager.Manager manager_:
    :rtype: list[Network]
    """
    return (
        network
        for network in manager_.list_recent_networks()
        if network.report and network.report.public
    )


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


def networks_with_permission_iter_helper(user, manager_):
    """Gets an iterator over all the networks from all the sources

    :param models.User user:
    :param pybel.manager.Manager manager_:
    :rtype: iter[Network]
    """
    if not user.is_authenticated:
        yield from iter_public_networks(manager_)

    elif user.is_admin:
        yield from manager_.list_recent_networks()

    else:
        yield from iter_public_networks(manager_)
        yield from user.get_owned_networks()
        yield from user.get_shared_networks()
        yield from user.get_project_networks()

        if user.is_scai:
            role = user_datastore.find_or_create_role(name='scai')
            for user in role.users:
                yield from user.get_owned_networks()


def get_networks_with_permission(manager_):
    """Gets all networks tagged as public or uploaded by the current user

    :param DatabaseService manager_: The database service
    :return: A list of all networks tagged as public or uploaded by the current user
    :rtype: list[Network]
    """
    if not current_user.is_authenticated:
        return list(iter_public_networks(manager_))

    if current_user.is_admin:
        return manager_.list_recent_networks()

    return list(unique_networks(networks_with_permission_iter_helper(current_user, manager_)))


def get_network_ids_with_permission_helper(user, manager_):
    """Gets the set of networks ids tagged as public or uploaded by the current user

    :param User user:
    :param pybel.manager.Manager manager_: The database service
    :return: A list of all networks tagged as public or uploaded by the current user
    :rtype: set[int]
    """
    return {
        network.id
        for network in networks_with_permission_iter_helper(user, manager_)
    }


def user_has_query_rights(user, query):
    """Checks if the user has rights to run the given query

    :param models.User user: A user object
    :param models.Query query: A query object
    :rtype: bool
    """
    if user.is_authenticated and user.is_admin:
        return True

    permissive_network_ids = get_network_ids_with_permission_helper(user, manager)

    return all(
        network.id in permissive_network_ids
        for network in query.assembly.networks
    )


def current_user_has_query_rights(query_id):
    """Checks if the current user has rights to run the given query

    :param int query_id: The database identifier for a query
    :rtype: bool
    """
    if current_user.is_authenticated and current_user.is_admin:
        return True

    query = manager.session.query(Query).get(query_id)

    return user_has_query_rights(current_user, query)


def get_query_or_404(query_id):
    query = manager.session.query(Query).get(query_id)

    if query is None:
        abort(404, 'Missing query: {}'.format(query_id))

    return query


def safe_get_query(query_id):
    """Gets a query or raises an abort

    :param int query_id: The database identifier for a query
    :rtype: Query
    """
    query = get_query_or_404(query_id)

    if not user_has_query_rights(current_user, query):
        abort(403, 'Insufficient rights to run query {}'.format(query_id))

    return query


def get_or_create_vote(edge, user, agreed=None):
    """Gets a vote for the given edge and user

    :param Edge edge: The edge that is being evaluated
    :param User user: The user making the vote
    :param bool agreed: Optional value of agreement to put into vote
    :rtype: EdgeVote
    """
    vote = manager.session.query(EdgeVote).filter(EdgeVote.edge == edge, EdgeVote.user == user).one_or_none()

    if vote is None:
        vote = EdgeVote(
            edge=edge,
            user=user,
            agreed=agreed
        )
        manager.session.add(vote)
        manager.session.commit()

    # If there was already a vote, and it's being changed
    elif agreed is not None:
        vote.agreed = agreed
        vote.changed = datetime.datetime.utcnow()
        manager.session.commit()

    return vote


def next_or_jsonify(message, *args, status=200, category='message', **kwargs):
    """Neatly wraps a redirect to a new URL if the ``next`` argument is set in the request otherwise sends JSON
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


def user_owns_network_or_403(network, user):
    """Check that the user is the owner of the the network. Sends a Flask abort 403 signal if not.

    :param Network network: A network
    :param User user: A user
    """
    if not user.is_authenticated or not network.report or user != network.report.user:
        abort(403, 'You do not own this network')


def calculate_scores(graph, data, runs):
    """Calculates CMPA scores"""
    remove_nodes_by_namespace(graph, {'MGI', 'RGD'})
    collapse_by_central_dogma_to_genes(graph)
    rewire_variants_to_genes(graph)

    overlay_type_data(graph, data, LABEL, GENE, 'HGNC', overwrite=False, impute=0)

    candidate_mechanisms = generate_bioprocess_mechanisms(graph, LABEL)
    scores = calculate_average_cmpa_on_subgraphs(candidate_mechanisms, LABEL, runs=runs)

    return scores


def get_node_by_hash_or_404(node_hash):
    """Gets a node's hash or sends a 404 missing message

    :param str node_hash: Node hash
    :rtype: pybel.manager.models.Node
    """
    node = manager.get_node_by_hash(node_hash)

    if node is None:
        abort(404, 'Node not found: {}'.format(node_hash))

    return node


def get_edge_by_hash_or_404(edge_hash):
    """Gets an edge if it exists or sends a 404

    :param str edge_hash: A PyBEL edge hash
    :rtype: Edge
    """
    edge = manager.get_edge_by_hash(edge_hash)

    if edge is None:
        abort(404, 'Edge {} not found'.format(edge_hash))

    return edge


def relabel_nodes_to_hashes(graph, copy=False):
    """Relabels nodes to hashes in the graph

    :param pybel.BELGraph graph:
    :param bool copy: Copy the graph?
    :rtype: pybel.BELGraph
    """
    warnings.warn('should use the pybel implementation of this', DeprecationWarning)
    if 'PYBEL_RELABELED' in graph.graph:
        log.warning('%s has already been relabeled', graph.name)
        return graph

    mapping = {}
    for node in graph:
        mapping[node] = hash_node(node)

    nx.relabel.relabel_nodes(graph, mapping, copy=copy)

    graph.graph['PYBEL_RELABELED'] = True

    return graph


def get_node_overlaps(network_id):
    """Calculates overlaps to all other networks in the database

    :param int network_id: The network database identifier
    :return: A dictionary from {int network_id: float similarity} for this network to all other networks
    :rtype: collections.Counter[int,float]
    """
    t = time.time()

    network = manager.get_network_by_id(network_id)
    nodes = set(node.id for node in network.nodes)

    rv = Counter({
        ol.right.id: ol.overlap
        for ol in network.overlaps
    })

    uncached_networks = list(
        other_network
        for other_network in manager.list_recent_networks()
        if other_network.id != network_id and  other_network.id not in rv
    )

    if uncached_networks:
        for other_network in uncached_networks:
            other_network_nodes = set(node.id for node in other_network.nodes)

            overlap = min_tanimoto_set_similarity(nodes, other_network_nodes)

            rv[other_network.id] = overlap

            no = NetworkOverlap(left=network, right=other_network, overlap=overlap)
            manager.session.add(no)

        manager.session.commit()

        log.debug('Cached node overlaps for network %s in %.2f seconds', network_id, time.time() - t)

    return rv


def make_graph_summary(graph):
    """Makes a graph summary for sticking in the report

    :param pybel.BELGraph graph:
    :rtype: dict
    """
    log.info('summarizing %s',graph)
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
