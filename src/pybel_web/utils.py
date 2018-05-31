# -*- coding: utf-8 -*-

import base64
import datetime
import logging
from collections import Counter, defaultdict
from functools import lru_cache
from io import BytesIO

import time
from flask import abort, render_template
from flask_security import current_user
from sqlalchemy import and_, func

import pybel
from pybel.manager import Network
from pybel.struct.summary import count_namespaces, get_annotation_values_by_annotation, get_pubmed_identifiers
from pybel_tools.summary import count_variants, get_annotations
from pybel_tools.utils import min_tanimoto_set_similarity, prepare_c3, prepare_c3_time_series
from .constants import AND, VERSION
from .content import safe_get_query
from .manager_utils import get_network_summary_dict
from .models import EdgeComment, EdgeVote, NetworkOverlap, Query, Report, User
from .proxies import manager

log = logging.getLogger(__name__)


def sanitize_list_of_str(l):
    """Strips all strings in a list and filters to the non-empty ones
    
    :type l: iter[str]
    :rtype: list[str]
    """
    return [e for e in (e.strip() for e in l) if e]


def get_top_overlaps(network_id, number=10):
    overlap_counter = get_node_overlaps(network_id)
    allowed_network_ids = manager.get_network_ids_with_permission_helper(current_user)
    overlaps = [
        (manager.get_network_by_id(network_id), v)
        for network_id, v in overlap_counter.most_common()
        if network_id in allowed_network_ids and v > 0.0
    ]
    return overlaps[:number]


def render_network_summary(network_id, template):
    """Renders the graph summary page
    
    :param int network_id:
    :param str template:
    :rtype: flask.Response
    """
    network = manager.get_network_by_id(network_id)
    graph = network.as_bel()

    try:
        er = network.report.get_calculations()
    except Exception:  # TODO remove this later
        log.warning('Falling back to on-the-fly calculation of summary of %s', network)
        er = get_network_summary_dict(graph)

        if network.report:
            network.report.dump_calculations(er)
            manager.session.commit()

    citation_years = er['citation_years']
    function_count = er['function_count']
    relation_count = er['relation_count']
    error_count = er['error_count']
    transformations_count = er['modifications_count']
    hub_data = er['hub_data']
    disease_data = er['disease_data']
    overlaps = get_top_overlaps(network_id)
    network_versions = manager.get_networks_by_name(graph.name)
    variants_count = count_variants(graph)
    namespaces_count = count_namespaces(graph)

    return render_template(
        template,
        current_user=current_user,
        network=network,
        graph=graph,
        network_versions=network_versions,
        overlaps=overlaps,
        chart_1_data=prepare_c3(function_count, 'Entity Type'),
        chart_2_data=prepare_c3(relation_count, 'Relationship Type'),
        chart_3_data=prepare_c3(error_count, 'Error Type') if error_count else None,
        chart_4_data=prepare_c3(transformations_count) if transformations_count else None,
        number_transformations=sum(transformations_count.values()),
        chart_5_data=prepare_c3(variants_count, 'Node Variants'),
        number_variants=sum(variants_count.values()),
        chart_6_data=prepare_c3(namespaces_count, 'Namespaces'),
        number_namespaces=len(namespaces_count),
        chart_7_data=prepare_c3(hub_data, 'Top Hubs'),
        chart_9_data=prepare_c3(disease_data, 'Pathologies') if disease_data else None,
        chart_10_data=prepare_c3_time_series(citation_years, 'Number of articles') if citation_years else None,
        **er
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
        return {
            'annotations': sanitize_annotation(form.getlist(value)),
            'or': not form.get(AND)
        }

    if key in {'pubmed', 'authors'}:
        return form.getlist(value)

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
        {
            "type": seed_method,
            'data': convert_seed_value(seed_method, form, seed_data_argument)
        }
        for seed_method, seed_data_argument in pairs
        if form.getlist(seed_data_argument)
    ]

    query_dict["pipeline"] = [
        {
            'function': to_snake_case(function_name)
        }
        for function_name in form.getlist("pipeline[]")
        if function_name
    ]

    network_ids = form.getlist("network_ids[]", type=int)
    if network_ids:
        query_dict["network_ids"] = network_ids

    return query_dict


def get_query_ancestor_id(query_id):  # TODO refactor this to be part of Query class
    """Gets the oldest ancestor of the given query

    :param int query_id: The original query database identifier
    :rtype: Query
    """
    query = manager.session.query(Query).get(query_id)

    if not query.parent_id:
        return query_id

    return get_query_ancestor_id(query.parent_id)


def get_query_descendants(query_id):  # TODO refactor this to be part of Query class
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
    :param str g1_label: The label for the first fraph
    :param str g2_label: The label for the first fraph
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


def get_networks_with_permission(manager_):
    """Gets all networks tagged as public or uploaded by the current user

    :param pybel_web.manager.WebManager manager: A manager
    :return: A list of all networks tagged as public or uploaded by the current user
    :rtype: list[Network]
    """
    if not current_user.is_authenticated:
        return list(manager_.iter_public_networks())

    if current_user.is_admin:
        return manager_.list_recent_networks()

    return list(unique_networks(manager_.networks_with_permission_iter_helper(current_user)))


@lru_cache(maxsize=256)
def get_graph_from_request(query_id):
    """Process the GET request returning the filtered network.

    :param int query_id: The database query identifier
    :rtype: Optional[pybel.BELGraph]
    :raises: werkzeug.exceptions.HTTPException
    """
    log.debug('getting query [id=%d] from database', query_id)
    query = safe_get_query(query_id)

    log.debug('running query [id=%d]', query_id)
    result = query.run(manager)

    return result


def get_tree_annotations(graph):
    """Builds tree structure with annotation for a given graph

    :param pybel.BELGraph graph: A BEL Graph
    :return: The JSON structure necessary for building the tree box
    :rtype: list[dict]
    """
    annotations = get_annotation_values_by_annotation(graph)
    return [
        {
            'text': annotation,
            'children': [
                {'text': value}
                for value in sorted(values)
            ]
        }
        for annotation, values in sorted(annotations.items())
    ]


@lru_cache(maxsize=256)
def get_tree_from_query(query_id):
    """Gets the tree json for a given network

    :param int query_id: The database query identifier
    :rtype: Optional[dict]
    :raises: werkzeug.exceptions.HTTPException
    """
    graph = get_graph_from_request(query_id)

    if graph is None:
        return

    return get_tree_annotations(graph)


def get_edge_vote_by_user(manager_, edge, user):
    """Looks up a vote by the edge and user

    :param pybel.manager.Manager manager_: The database service
    :param Edge edge: The edge that is being evaluated
    :param User user: The user making the vote
    :rtype: Optional[EdgeVote]
    """
    vote_filter = and_(EdgeVote.edge == edge, EdgeVote.user == user)
    return manager_.session.query(EdgeVote).filter(vote_filter).one_or_none()


def get_or_create_vote(manager_, edge, user, agreed=None):
    """Gets a vote for the given edge and user

    :param pybel.manager.Manager manager_: The database service
    :param Edge edge: The edge that is being evaluated
    :param User user: The user making the vote
    :param bool agreed: Optional value of agreement to put into vote
    :rtype: EdgeVote
    """
    vote = get_edge_vote_by_user(manager_, edge, user)

    if vote is None:
        vote = EdgeVote(
            edge=edge,
            user=user,
            agreed=agreed
        )
        manager_.session.add(vote)
        manager_.session.commit()

    # If there was already a vote, and it's being changed
    elif agreed is not None:
        vote.agreed = agreed
        vote.changed = datetime.datetime.utcnow()
        manager_.session.commit()

    return vote


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
        if other_network.id != network_id and other_network.id not in rv
    )

    if uncached_networks:
        log.debug('caching overlaps for network [id=%d]', network_id)

        for other_network in uncached_networks:
            other_network_nodes = set(node.id for node in other_network.nodes)

            overlap = min_tanimoto_set_similarity(nodes, other_network_nodes)

            rv[other_network.id] = overlap

            no = NetworkOverlap(left=network, right=other_network, overlap=overlap)
            manager.session.add(no)

        manager.session.commit()

        log.debug('cached overlaps for network [id=%s] in %.2f seconds', network_id, time.time() - t)

    return rv


def help_get_edge_entry(manager_, edge):
    """Gets edge information by edge identifier

    :type manager_: pybel.Manager
    :param Edge edge: The  given edge
    :return: A dictionary representing the information about the given edge
    :rtype: dict
    """
    data = edge.to_json()

    data['comments'] = [
        {
            'user': {
                'id': ec.user_id,
                'email': ec.user.email
            },
            'comment': ec.comment,
            'created': ec.created,
        }
        for ec in manager_.session.query(EdgeComment).filter(EdgeComment.edge == edge)
    ]

    if current_user.is_authenticated:
        vote = get_or_create_vote(manager_, edge, current_user)
        data['vote'] = 0 if (vote is None or vote.agreed is None) else 1 if vote.agreed else -1

    return data


def render_network_summary_safe(manager_, network_id, template):
    """Renders a network if the current user has the necessary rights

    :param manager_: The manager
    :param int network_id: The network to render
    :param str template: The name of the template to render
    :rtype: flask.Response
    """
    if network_id not in manager.get_network_ids_with_permission_helper(current_user):
        abort(403, 'Insufficient rights for network {}'.format(network_id))

    return render_network_summary(network_id, template=template)


@lru_cache(maxsize=256)
def query_from_network_with_current_user(user, network, autocommit=True):
    """Makes a query from the given network

    :param User user: The user making the query
    :param Network network: The network
    :param bool autocommit: Should the query be committed immediately
    :rtype: Query
    """
    query = Query.from_network(network, user=user)

    if autocommit:
        manager.session.add(query)
        manager.session.commit()

    return query


def safe_get_report(manager_, report_id):
    """
    :param pybel.manager.Manager manager_: A PyBEL manager
    :param int report_id: The identifier of the report
    :rtype: Report
    :raises: ValueError
    """
    report = manager_.session.query(Report).get(report_id)

    if report is None:
        raise ValueError('Report {} not found'.format(report_id))

    return report


def safe_get_node(manager_, node_hash):
    """Gets a node

    :param pybel.manager.Manager manager_:
    :param str node_hash:
    :rtype: Node
    """
    node = manager_.get_node_by_hash(node_hash)

    if node is None:
        abort(404, 'Node with following hash not found. This is most likely because it comes from a namespace that has '
                   'not been finalized, and is therefore not cached. {}'.format(node_hash))

    return node


def get_version():
    """Gets the current BEL Commons version

    :return: The current BEL Commons version
    :rtype: str
    """
    return VERSION
