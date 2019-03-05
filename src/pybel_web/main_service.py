# -*- coding: utf-8 -*-

"""This module contains the user interface blueprint for the application."""

import datetime
import logging
import sys
from collections import defaultdict
from operator import itemgetter

import flask
from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_security import current_user, login_required, roles_required

import pybel.struct.query
from pybel.manager.models import Citation, Edge, Evidence, Namespace, NamespaceEntry
from pybel.struct.grouping.annotations import get_subgraphs_by_annotation
from pybel.struct.mutation import collapse_to_genes, remove_associations, remove_isolated_nodes, remove_pathologies
from pybel.struct.pipeline import Pipeline
from pybel.struct.pipeline.exc import MissingPipelineFunctionError
from pybel.struct.query import QueryMissingNetworksError
from pybel_tools.biogrammar.double_edges import summarize_completeness
from pybel_tools.summary.error_summary import calculate_error_by_annotation
from .constants import SQLALCHEMY_DATABASE_URI
from .core.models import Query
from .core.proxies import flask_bio2bel, celery, manager
from .explorer_toolbox import get_explorer_toolbox
from .manager_utils import next_or_jsonify
from .models import EdgeComment, EdgeVote, Experiment, Omic, User
from .utils import calculate_overlap_info, get_version as get_bel_commons_version

__all__ = [
    'ui_blueprint',
]

log = logging.getLogger(__name__)

ui_blueprint = Blueprint('ui', __name__)

time_instantiated = str(datetime.datetime.now())
extract_useful_subgraph = Pipeline.from_functions([
    remove_pathologies,
    remove_associations,
    collapse_to_genes,
    remove_isolated_nodes
])


def _format_big_number(n: int) -> str:
    if n > 1000000:
        return '{}M'.format(int(round(n / 1000000)))
    elif n > 1000:
        return '{}K'.format(int(round(n / 1000)))
    else:
        return str(n)


def redirect_to_view_explorer_query(query: Query) -> flask.Response:
    """Return the response for the biological network explorer in a given query to :func:`view_explorer_query`."""
    return redirect(url_for('ui.view_explorer_query', query_id=query.id))


@ui_blueprint.route('/')
def home():
    """Return the home page.

    The home page has links to the main components of the application:

    1. BEL Parser
    2. Curation Tools
    3. Namespace and Annotation Store
    4. Network/Edge/NanoPub Store Navigator
    5. Query Builder
    """
    hist = None
    if current_user.is_authenticated and current_user.is_admin:
        hist = [
            ('Network', manager.count_networks(), url_for('.view_networks')),
            ('Edge', manager.count_edges(), url_for('.view_edges')),
            ('Node', manager.count_nodes(), url_for('.view_nodes')),
            ('Query', manager.count_queries(), url_for('.view_queries')),
            ('Citation', manager.count_citations(), url_for('.view_citations')),
            ('Evidence', manager.session.query(Evidence).count(), url_for('.view_evidences')),
            ('Assembly', manager.count_assemblies(), None),
            ('Vote', manager.session.query(EdgeVote).count(), None),
            ('Comment', manager.session.query(EdgeComment).count(), None),
        ]
        if 'analysis' in current_app.blueprints:
            hist.extend([
                ('Omic', manager.session.query(Omic).count(), url_for('analysis.view_omics')),
                ('Experiment', manager.session.query(Experiment).count(), url_for('analysis.view_experiments')),
            ])

        hist = sorted(hist, key=itemgetter(1), reverse=True)

    return render_template(
        'index.html',
        database_histogram=hist,
        manager=manager,
        blueprints=set(current_app.blueprints),
    )


@ui_blueprint.route('/network')
def view_networks():
    """The networks page has two components: a search box, and a list of networks. Each network is shown by name,
    with the version number and the first author. Each has several actions:

    1. View one of the following summaries:
       - Statistical summary
       - Compilation summary
       - Biological grammar summary
    2. Explore the full network, or a random subgraph if it is too big.
    3. Create a biological query starting with this network
    4. Analyze the network with one of the procedures (Heat Diffusion, etc.)
    5. Execute one of the following actions if the current user is the owner:
       - Drop
       - Make public/private
    """
    networks = manager.cu_list_networks()
    return render_template(
        'network/networks.html',
        networks=networks,
        blueprints=set(current_app.blueprints),
    )


@ui_blueprint.route('/node')
@roles_required('admin')
def view_nodes():
    """Render a page viewing all edges."""
    search = request.args.get('search')
    nodes = manager.query_nodes(
        type=request.args.get('function'),
        namespace=request.args.get('namespace'),
        bel=search,
    )
    if search:
        flask.flash(f'Searched for "{search}"')

    count = nodes.count()

    limit = request.args.get('limit', 10, type=int)
    nodes = nodes.limit(limit)

    offset = request.args.get('offset', 0, type=int)
    if offset:
        nodes = nodes.offset(offset)

    return render_template(
        'node/nodes.html',
        nodes=nodes,
        count=count,
        limit=limit,
        offset=offset,
        **flask_bio2bel.manager_dict
    )


@ui_blueprint.route('/node/<node_hash>')
def view_node(node_hash: str):
    """View a node summary with a list of all edges incident to the node."""
    node = manager.get_node_by_hash_or_404(node_hash)
    return render_template(
        'node/node.html',
        node=node,
        **flask_bio2bel.manager_dict
    )


@ui_blueprint.route('/evidence')
def view_evidences():
    """View a list of Evidence models."""
    limit = request.args.get('limit', type=int, default=10)
    offset = request.args.get('offset', type=int)

    evidences = manager.session.query(Evidence)
    evidences = evidences.limit(limit)
    if offset is not None:
        evidences = evidences.offset(offset)

    return render_template(
        'evidence/evidences.html',
        manager=manager,
        evidences=evidences.all(),
        count=manager.session.query(Evidence).count(),
    )


@ui_blueprint.route('/evidence/<int:evidence_id>')
def view_evidence(evidence_id: int):
    """View a single Evidence model."""
    evidence = manager.get_evidence_by_id_or_404(evidence_id)
    return render_template(
        'evidence/evidence.html',
        evidence=evidence,
        manager=manager,
    )


@ui_blueprint.route('/node/<source_hash>/edges/<target_hash>')
def view_relations(source_hash: str, target_hash: str):
    """View a list of all relations between two nodes.

    :param source_hash: The source node's hash
    :param target_hash: The target node's hash
    """
    source = manager.get_node_by_hash_or_404(source_hash)
    target = manager.get_node_by_hash_or_404(target_hash)

    edges = list(manager.query_edges(source=source, target=target))

    if 'undirected' in request.args:
        edges.extend(manager.query_edges(source=target, target=source))

    data = defaultdict(list)
    ev2cit = {}
    for edge in edges:
        if not edge.evidence:
            continue
        ev = edge.evidence.text
        data[ev].append((edge, edge.to_json()))
        ev2cit[ev] = edge.evidence.citation.to_json()

    return render_template(
        'evidence/evidence_list.html',
        data=data,
        ev2cit=ev2cit,
        source_bel=source.bel,
        target_bel=target.bel if target else None,
    )


@ui_blueprint.route('/edge')
@roles_required('admin')
def view_edges():
    """Render a page viewing all edges."""
    return render_template('edge/edges.html', edges=manager.session.query(Edge).limit(15))


@ui_blueprint.route('/edge/<edge_hash>')
def view_edge(edge_hash: str):
    """Render a page viewing a single edge."""
    edge = manager.get_edge_by_hash(edge_hash)
    return render_template(
        'edge/edge.html',
        edge=edge,
    )


@ui_blueprint.route('/edge/<edge_hash>/vote/<int:vote>')
@login_required
def vote_edge(edge_hash: str, vote: int):
    """Render a page viewing a single edges.

    :param edge_hash: The identifier of the edge to display
    :param vote:
    """
    edge = manager.get_edge_by_hash(edge_hash)
    manager.get_or_create_vote(edge, current_user, agreed=(vote != 0))
    return redirect(url_for('.view_edge', edge_hash=edge_hash))


@ui_blueprint.route('/query/<int:query_id>')
def view_query(query_id: int):
    """Render a single query page."""
    query = manager.cu_get_query_by_id_or_404(query_id)
    log.debug(f'got query {query_id}: {query}')
    return render_template(
        'query/query.html',
        query=query,
        manager=manager,
        blueprints=set(current_app.blueprints),
    )


@ui_blueprint.route('/query')
@roles_required('admin')
def view_queries():
    """Render the query catalog."""
    queries = manager.list_queries()
    return render_template(
        'query/queries.html',
        queries=queries,
        manager=manager,
    )


@ui_blueprint.route('/citation')
@roles_required('admin')
def view_citations():
    """Render the query catalog."""
    limit = request.args.get('limit', type=int, default=10)

    q = manager.session.query(Citation)
    q = q.limit(limit)

    return render_template(
        'citation/citations.html',
        citations=q.all(),
        count=manager.count_citations(),
        manager=manager,
    )


@ui_blueprint.route('/citation/<int:citation_id>')
def view_citation(citation_id: int):
    """View a citation."""
    citation = manager.session.query(Citation).get(citation_id)
    return render_template(
        'citation/citation.html',
        citation=citation,
    )


@ui_blueprint.route('/citation/pubmed/<pmid>')
def view_pubmed(pmid: str):
    """View all evidences and relations extracted from the article with the given PubMed identifier.

    :param pmid: The PubMed identifier
    """
    citation = manager.get_citation_by_pmid(pmid)
    return redirect(url_for('.view_citation', citation_id=citation.id))


@ui_blueprint.route('/network/<int:network_id>/explore')
def view_explore_network(network_id: int):
    """Render a page for the user to explore a network."""
    query = manager.cu_query_from_network_by_id_or_404(network_id)
    return redirect_to_view_explorer_query(query)


@ui_blueprint.route('/explore/<int:query_id>')
def view_explorer_query(query_id: int):
    """Render a page for the user to explore a network."""
    query = manager.cu_get_query_by_id_or_404(query_id=query_id)
    return render_template(
        'network/explorer.html',
        query_id=query.id,
        explorer_toolbox=get_explorer_toolbox(),
        blueprints=set(current_app.blueprints),
    )


@ui_blueprint.route('/node/<node_hash>/explore/')
def view_explorer_node(node_hash: str):
    """Build and send an induction query around the given node."""
    node = manager.get_node_by_hash_or_404(node_hash)
    query = manager.build_query_from_node(node)
    return redirect_to_view_explorer_query(query)


@ui_blueprint.route('/project/<int:project_id>/explore')
@login_required
def view_explore_project(project_id: int):
    """Render a page for the user to explore the full network from a project."""
    project = manager.get_project_by_id(project_id)
    query = manager.build_query_from_project(project)
    return redirect_to_view_explorer_query(query)


@ui_blueprint.route('/query/build', methods=['GET', 'POST'])
def view_query_builder():
    """Render the query builder page."""
    networks = manager.cu_list_networks()
    return render_template(
        'query/query_builder.html',
        networks=networks,
        current_user=current_user,
        preselected=request.args.get('start', type=int)
    )


@ui_blueprint.route('/network/<int:network_id>/query', methods=['GET', 'POST'])
def view_build_query_from_network(network_id: int):
    network = manager.cu_get_network_by_id_or_404(network_id)
    return render_template(
        'query/query_builder.html',
        current_user=current_user,
        network=network,
    )


@ui_blueprint.route('/query/compile', methods=['POST'])
def get_pipeline():
    """Execute a pipeline that's posted to this endpoint."""
    d = manager.query_form_to_dict(request.form)
    try:
        q = pybel.struct.query.Query.from_json(d)
    except (QueryMissingNetworksError, MissingPipelineFunctionError) as e:
        flash(f'Error building query: {e}')
        return redirect(url_for('.view_query_builder'))
    else:
        return redirect_from_query(q)


@ui_blueprint.route('/namespace')
def view_namespaces():
    """Display a page listing the namespaces."""
    namespaces = manager.session.query(Namespace).order_by(Namespace.keyword).all()
    return render_template(
        'namespace/namespaces.html',
        namespaces=namespaces,
    )


@ui_blueprint.route('/namespace/<int:namespace_id>')
def view_namespace(namespace_id: int):
    """View a namespace."""
    namespace = manager.get_namespace_by_id_or_404(namespace_id)
    return render_template(
        'namespace/namespace.html',
        namespace=namespace,
    )


@ui_blueprint.route('/name/')
@roles_required('admin')
def view_namespace_entries():
    """View a summary of all namespace entries."""
    # TODO get namespace entries with most edges
    # TODO get namespaces with least edges (non-zero)
    # TODO get co-occurrence of namespace entries

    namespace_entries = manager.session.query(NamespaceEntry).limit(10).all()
    namespace_entry_count = manager.count_namespace_entries()

    return render_template(
        'namespace/namespace_entries.html',
        namespace_entries=namespace_entries,
        namespace_entry_count=namespace_entry_count,
    )


@ui_blueprint.route('/name/<int:name_id>')
def view_name(name_id: int):
    """View a namespace entry."""
    namespace_entry = manager.session.query(NamespaceEntry).get(name_id)
    return render_template(
        'namespace/namespace_entry.html',
        namespace_entry=namespace_entry,
    )


@ui_blueprint.route('/legal')
def view_legal():
    """Render the legal info."""
    return render_template('meta/legal.html')


@ui_blueprint.route('/about')
def view_about():
    """Send the about page."""
    from pybel.utils import get_version as get_pybel_version
    from pybel_tools.utils import get_version as get_pybel_tools_version

    metadata = [
        ('Python Version', sys.version),
        ('PyBEL Version', get_pybel_version()),
        ('PyBEL Tools Version', get_pybel_tools_version()),
        ('BEL Commons Version', get_bel_commons_version()),
        ('Deployed', time_instantiated),
    ]

    if current_user.is_authenticated and current_user.is_admin:
        metadata.extend([
            ('Database', current_app.config[SQLALCHEMY_DATABASE_URI]),
        ])

    return render_template(
        'meta/about.html',
        metadata=metadata,
        managers=flask_bio2bel.manager_dict,
        blueprints=set(current_app.blueprints),
    )


@ui_blueprint.route('/network/<int:network_id>')
def view_network(network_id: int):
    """Render a page with the statistics of the contents of a BEL script."""
    return manager.cu_render_network_summary_or_404(network_id, template='network/network.html')


@ui_blueprint.route('/network/<int:network_id>/delete')
def delete_network(network_id: int):
    """Drop the network and go to the network catalog."""
    network = manager.cu_owner_get_network_by_id_or_404(network_id=network_id)
    if network.report:
        manager.session.delete(network.report)
    manager.drop_network(network)
    flash(f'Dropped {network} (id:{network.id})')
    return redirect(url_for('view_networks'))


@ui_blueprint.route('/network/<int:network_id>/compilation')
def view_summarize_compilation(network_id):
    """Render a page with the compilation summary of the contents of a BEL script."""
    return manager.cu_render_network_summary_or_404(network_id, template='network/summarize_compilation.html')


@ui_blueprint.route('/network/<int:network_id>/warnings')
def view_summarize_warnings(network_id: int):
    """Render a page with the parsing errors from a BEL script."""
    return manager.cu_render_network_summary_or_404(network_id, template='network/summarize_warnings.html')


@ui_blueprint.route('/network/<int:network_id>/biogrammar')
def view_summarize_biogrammar(network_id: int):
    """Render a page with the summary of the biogrammar analysis of a BEL script."""
    return manager.cu_render_network_summary_or_404(network_id, template='network/summarize_biogrammar.html')


@ui_blueprint.route('/network/<int:network_id>/completeness')
def view_summarize_completeness(network_id: int):
    """Render a page with the summary of the completeness analysis of a BEL script."""
    network = manager.get_network_by_id(network_id)
    graph = network.as_bel()
    entries = summarize_completeness(graph)
    return render_template(
        'network/summarize_completeness.html',
        network=network,
        entries=entries,
    )


@ui_blueprint.route('/network/<int:network_id>/stratified/<annotation>')
def view_summarize_stratified(network_id: int, annotation: str):
    """Show stratified summary of graph's sub-graphs by annotation."""
    network = manager.cu_get_network_by_id_or_404(network_id)
    graph = network.as_bel()
    graphs = get_subgraphs_by_annotation(graph, annotation)

    graph_summary = graph.summary_dict()

    errors = calculate_error_by_annotation(graph, annotation)

    summaries = {}
    useful_summaries = {}

    for name, subgraph in graphs.items():
        summaries[name] = subgraph.summary_dict()
        summaries[name]['node_overlap'] = subgraph.number_of_nodes() / graph.number_of_nodes()
        summaries[name]['edge_overlap'] = subgraph.number_of_edges() / graph.number_of_edges()
        summaries[name]['citation_overlap'] = summaries[name]['Citations'] / graph_summary['Citations']
        summaries[name]['errors'] = len(errors[name]) if name in errors else 0
        summaries[name]['error_density'] = (len(errors[name]) / graph.number_of_nodes()) if name in errors else 0

        useful_subgraph = extract_useful_subgraph(subgraph)
        useful_summaries[name] = useful_subgraph.summary_dict()
        useful_summaries[name]['node_overlap'] = subgraph.number_of_nodes() / graph.number_of_nodes()
        useful_summaries[name]['edge_overlap'] = subgraph.number_of_edges() / graph.number_of_edges()
        useful_summaries[name]['citation_overlap'] = summaries[name]['Citations'] / graph_summary['Citations']

    return render_template(
        'network/summarize_stratified.html',
        network=network,
        annotation=annotation,
        full_summary=graph_summary,
        summaries=summaries,
        useful_summaries=useful_summaries,
    )


@ui_blueprint.route('/network/<int:network_1_id>/compare/<int:network_2_id>')
def view_network_comparison(network_1_id: int, network_2_id: int):
    """View the comparison between two networks.

    :param network_1_id: Identifier for the first network
    :param network_2_id: Identifier for the second network
    """
    network_1 = manager.cu_get_network_by_id_or_404(network_1_id)
    network_2 = manager.cu_get_network_by_id_or_404(network_2_id)
    data = calculate_overlap_info(network_1.as_bel(), network_2.as_bel())
    return render_template(
        'network/network_comparison.html',
        network_1=network_1,
        network_2=network_2,
        data=data,
    )


@ui_blueprint.route('/query/<int:query_1_id>/compare/<int:query_2_id>')
def view_query_comparison(query_1_id: int, query_2_id: int):
    """View the comparison between the result of two queries.

    :param query_1_id: The identifier of the first query
    :param query_2_id: The identifier of the second query
    """
    g1 = manager.cu_get_graph_from_query_id_or_404(query_1_id)
    g2 = manager.cu_get_graph_from_query_id_or_404(query_2_id)
    data = calculate_overlap_info(g1, g2)
    return render_template(
        'query/query_comparison.html',
        query_1_id=query_1_id,
        query_2_id=query_2_id,
        data=data,
    )


##########################################
# The following endpoints are admin only #
##########################################

@ui_blueprint.route('/debug-celery')
def debug_celery():
    """Send a debug task to celery."""
    task = celery.send_task('debug-task')
    flash('Task sent: {task}'.format(task=task))
    return redirect(url_for('ui.home'))


@ui_blueprint.route('/user')
@roles_required('admin')
def view_users():
    """Render a list of users."""
    users = manager.session.query(User)
    return render_template(
        'user/users.html',
        users=users,
    )


@ui_blueprint.route('/user/current')
@login_required
def view_current_user_activity():
    """Return the current user's history."""
    return render_user(current_user)


@ui_blueprint.route('/user/<int:user_id>')
@roles_required('admin')
def view_user(user_id: int):
    """Return the given user's history."""
    return render_user(manager.get_user_by_id(user_id))


def render_user(user: User) -> flask.Response:
    """Render a user and their pending reports."""
    pending_reports = user.pending_reports()
    queries = user.get_sorted_queries()
    return render_template(
        'user/user.html',
        user=user,
        pending_reports=pending_reports,
        manager=manager,
        queries=queries,
    )


@ui_blueprint.route('/overview')
@roles_required('admin')
def view_overview():
    """View the overview."""
    return render_template('network/overview.html')


@ui_blueprint.route('/admin/rollback')
@roles_required('admin')
def rollback():
    """Roll back the transaction for when something bad happens."""
    manager.session.rollback()
    return next_or_jsonify('rolled back')


@ui_blueprint.route('/admin/nuke/')
@roles_required('admin')
def nuke():
    """Destroy the database and recreates it."""
    log.info('nuking database')
    manager.drop_all(checkfirst=True)
    log.info('   the dust settles')
    return next_or_jsonify('nuked the database')


@ui_blueprint.route('/admin/configuration')
@roles_required('admin')
def view_config():
    """Render the configuration."""
    return render_template('meta/deployment.html', config=current_app.config)


#######################################
# The following endpoints are helpers #
#######################################

@ui_blueprint.route('/project/<int:project_id>/merge/<int:user_id>')
def send_async_project_merge(user_id: int, project_id: int):
    """A helper endpoint to submit a project to the asynchronous task queue to merge its associated networks.

    :param user_id: The identifier of the user sending the task
    :param project_id: The identifier of the project to merge
    """
    task = celery.send_task('merge-project', args=[
        current_app.config['SQLALCHEMY_DATABASE_URI'],
        user_id,
        project_id
    ])
    flash(f'Merge task sent: {task}')
    return redirect(url_for('ui.view_current_user_activity'))


@ui_blueprint.route('/network/<int:network_id>/induction-query/')
def build_summary_link_query(network_id: int):
    """Build a query with the given network by inducing a sub-graph over the nodes included in the request."""
    nodes = [
        manager.get_dsl_by_hash(node_hash)
        for node_hash in request.args.getlist('nodes')
    ]

    q = pybel.struct.query.Query(network_id)
    q.append_seeding_induction(nodes)
    return redirect_from_query(q)


@ui_blueprint.route('/network/<int:network_id>/sample/')
def build_subsample_query(network_id: int):
    """Build and execute a query that induces a random sub-network over the given network."""
    q = pybel.struct.query.Query(network_id)
    q.append_seeding_sample()
    return redirect_from_query(q)


def redirect_from_query(q: pybel.struct.query.Query) -> flask.Response:
    query = manager.build_query(q)
    return redirect_to_view_explorer_query(query)
