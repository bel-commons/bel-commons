# -*- coding: utf-8 -*-

import base64
import datetime
import logging
import pickle
import time
from collections import Counter, defaultdict
from io import BytesIO

import pandas
from flask import abort, flash, jsonify, redirect, render_template, request, url_for
from flask_security import current_user
from sqlalchemy import and_, func

import pybel
from pybel.constants import GENE
from pybel.manager import Network
from pybel.struct.summary import count_namespaces, get_pubmed_identifiers
from pybel_tools.analysis.cmpa import calculate_average_scores_on_subgraphs as calculate_average_cmpa_on_subgraphs
from pybel_tools.filters import remove_nodes_by_namespace
from pybel_tools.generation import generate_bioprocess_mechanisms
from pybel_tools.integration import overlay_type_data
from pybel_tools.mutation import collapse_by_central_dogma_to_genes, rewire_variants_to_genes
from pybel_tools.summary import count_variants, get_annotations
from pybel_tools.utils import min_tanimoto_set_similarity, prepare_c3, prepare_c3_time_series
from .constants import AND
from .manager_utils import get_network_summary_dict
from .models import EdgeComment, EdgeVote, Experiment, NetworkOverlap, Project, Query, Report, User
from .proxies import manager, user_datastore

log = logging.getLogger(__name__)

LABEL = 'dgxa'


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
        network_id=network_id,
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


def iter_public_networks(manager_):
    """Lists the recent networks from :meth:`pybel.manager.Manager.list_recent_networks()` that have been made public

    :param pybel.manager.Manager manager_:
    :rtype: iter[Network]
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
    """Gets a query or returns a HTTPException with 404 message if it does not exist

    :param int query_id: The database identifier for a query
    :rtype: Query
    :raises: werkzeug.exceptions.HTTPException
    """
    query = manager.session.query(Query).get(query_id)

    if query is None:
        abort(404, 'Missing query: {}'.format(query_id))

    return query


def safe_get_query(query_id):
    """Gets a query by ite database identifier. Raises an HTTPException with 404 if the query does not exist or
    raises an HTTPException with 403 if the user does not have the appropriate permissions for all networks in the
    query's assembly

    :param int query_id: The database identifier for a query
    :rtype: Query
    :raises: werkzeug.exceptions.HTTPException
    """
    query = get_query_or_404(query_id)

    if not user_has_query_rights(current_user, query):
        abort(403, 'Insufficient rights to run query {}'.format(query_id))

    return query


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


def calculate_scores(graph, data, runs):
    """Calculates CMPA scores

    :param pybel.BELGraph graph: A BEL graph
    :param dict[str,float] data: A dictionary of {name: data}
    :param int runs: The number of permutations
    :rtype: dict[tuple,tuple]
    :return: A dictionary of {pybel node tuple: results tuple} from :func:`calculate_average_cmpa_on_subgraphs`
    """
    remove_nodes_by_namespace(graph, {'MGI', 'RGD'})
    collapse_by_central_dogma_to_genes(graph)
    rewire_variants_to_genes(graph)

    overlay_type_data(graph, data, LABEL, GENE, 'HGNC', overwrite=False, impute=0)

    candidate_mechanisms = generate_bioprocess_mechanisms(graph, LABEL)
    scores = calculate_average_cmpa_on_subgraphs(candidate_mechanisms, LABEL, runs=runs)

    return scores


def get_node_by_hash_or_404(node_hash):
    """Gets a node's hash or sends a 404 missing message

    :param str node_hash: A PyBEL node hash
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
        abort(404, 'Edge not found: {}'.format(edge_hash))

    return edge


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
        for other_network in uncached_networks:
            other_network_nodes = set(node.id for node in other_network.nodes)

            overlap = min_tanimoto_set_similarity(nodes, other_network_nodes)

            rv[other_network.id] = overlap

            no = NetworkOverlap(left=network, right=other_network, overlap=overlap)
            manager.session.add(no)

        manager.session.commit()

        log.debug('Cached node overlaps for network %s in %.2f seconds', network_id, time.time() - t)

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


def redirect_explorer(query):
    """Returns the response for the biological network explorer in a given query

    :param Query query: A query
    :rtype: flask.Response
    """
    return redirect(url_for('ui.view_explorer_query', query_id=query.id))


def render_network_summary_safe(manager_, network_id, template):
    """Renders a network if the current user has the necessary rights

    :param manager_: The manager
    :param int network_id: The network to render
    :param str template: The name of the template to render
    :rtype: flask.Response
    """
    if network_id not in get_network_ids_with_permission_helper(current_user, manager_):
        abort(403, 'Insufficient rights for network {}'.format(network_id))

    return render_network_summary(network_id, template=template)


def get_project_or_404(project_id):
    """Get a project by id and aborts 404 if doesn't exist

    :param int project_id: The identifier of the project
    :rtype: Project
    :raises: HTTPException
    """
    project = manager.session.query(Project).get(project_id)

    if project is None:
        abort(404, 'Project {} does not exist'.format(project_id))

    return project


def user_has_project_rights(user, project):
    """Returns if the given user has rights to the given project

    :type user: User
    :type project: Project
    :rtype: bool
    """
    return user.is_authenticated and (user.is_admin or project.has_user(current_user))


def safe_get_project(project_id):
    """Gets a project by identifier, aborts 404 if doesn't exist and aborts 403 if current user does not have rights

    :param int project_id: The identifier of the project
    :rtype: Project
    :raises: HTTPException
    """
    project = get_project_or_404(project_id)

    if not user_has_project_rights(current_user, project):
        abort(403, 'User {} does not have permission to access Project {}'.format(current_user, project))

    return project


def get_network_or_404(network_id):
    """Gets a network or aborts 404 if it doesn't exist

    :param int network_id: The identifier of the network
    :rtype: Network
    :raises: HTTPException
    """
    network = manager.session.query(Network).get(network_id)

    if network is None:
        abort(404, 'Network {} does not exist'.format(network_id))

    return network


def safe_get_network(network_id):
    """Aborts if the current user is not the owner of the network

    :param int network_id: The identifier of the network
    :rtype: Network
    :raises: HTTPException
    """
    network = get_network_or_404(network_id)

    if network.report and network.report.public:
        return network

    # FIXME what about networks in a project?

    if not current_user.owns_network(network):
        abort(403, 'User {} does not have permission to access Network {}'.format(current_user, network))

    return network


def query_from_network(network, autocommit=True):
    """Makes a query from the given network

    :param Network network: The network
    :param bool autocommit: Should the query be committed immediately
    :rtype: Query
    """
    query = Query.from_network(network, user=current_user)

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
        abort(404, 'Node not found: {}'.format(node_hash))

    return node
