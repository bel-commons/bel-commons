# -*- coding: utf-8 -*-

"""This module contains the user interface blueprint for the application"""

import datetime
import logging
import sys
import time
from collections import defaultdict

import flask
from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_security import current_user, login_required, roles_required

import pybel_tools.query
from pybel.manager.models import Annotation, Citation, Edge, Evidence, Namespace, Node
from pybel.utils import get_version as get_pybel_version
from pybel_tools.biogrammar.double_edges import summarize_competeness
from pybel_tools.mutation import (
    collapse_by_central_dogma_to_genes, remove_associations, remove_isolated_nodes,
    remove_pathologies,
)
from pybel_tools.pipeline import Pipeline, no_arguments_map
from pybel_tools.selection import get_subgraphs_by_annotation
from pybel_tools.summary import info_json
from pybel_tools.utils import get_version as get_pybel_tools_version
from pybel_web.manager_utils import next_or_jsonify
from . import models
from .constants import *
from .external_managers import *
from .external_managers import manager_dict
from .models import Assembly, EdgeComment, EdgeVote, Experiment, Omic, Project, Query, Report, User
from .utils import (
    calculate_overlap_dict, get_networks_with_permission, get_or_create_vote, manager, query_form_to_dict,
    query_from_network, render_network_summary_safe, safe_get_network, safe_get_node, safe_get_query,
)

log = logging.getLogger(__name__)

ui_blueprint = Blueprint('ui', __name__)
time_instantiated = str(datetime.datetime.now())

extract_useful_subgraph = Pipeline.from_functions([
    remove_pathologies,
    remove_associations,
    collapse_by_central_dogma_to_genes,
    remove_isolated_nodes
])


def format_big_number(n):
    if n > 1000000:
        return '{}M'.format(int(round(n / 1000000)))
    elif n > 1000:
        return '{}K'.format(int(round(n / 1000)))
    else:
        return str(n)


def redirect_to_view_explorer_query(query):
    """Returns the response for the biological network explorer in a given query to :func:`view_explorer_query`

    :param Query query: A query
    :rtype: flask.Response
    """
    return redirect(url_for('ui.view_explorer_query', query_id=query.id))


@ui_blueprint.route('/', methods=['GET', 'POST'])
def home():
    """The home page has links to the main components of the application:

    1. BEL Parser
    2. Curation Tools
    3. Namespace and Annotation Store
    4. Network/Edge/NanoPub Store Navigator
    5. Query Builder
    """
    number_networks = manager.count_networks()
    number_edges = manager.count_edges()
    number_nodes = manager.count_nodes()
    number_assemblies = manager.session.query(Assembly).count()
    number_queries = manager.session.query(Query).count()
    number_omics = manager.session.query(Omic).count()
    number_experiments = manager.session.query(Experiment).count()
    number_citations = manager.session.query(Citation).count()
    number_evidences = manager.session.query(Evidence).count()
    number_votes = manager.session.query(EdgeVote).count()
    number_comments = manager.session.query(EdgeComment).count()

    return render_template(
        'index.html',
        current_user=current_user,
        number_networks=format_big_number(number_networks),
        number_edges=format_big_number(number_edges),
        number_nodes=format_big_number(number_nodes),
        number_assemblies=format_big_number(number_assemblies),
        number_queries=format_big_number(number_queries),
        number_omics=number_omics,
        number_experiments=number_experiments,
        number_citations=format_big_number(number_citations),
        number_evidences=format_big_number(number_evidences),
        number_votes=format_big_number(number_votes),
        number_comments=format_big_number(number_comments),
        manager=manager,
    )


@ui_blueprint.route('/network', methods=['GET', 'POST'])
def view_networks():
    """The networks page has two components: a search box, and a list of networks. Each network is shown by name,
    with the version number and the first author. Each has several actions:

    1. View one of the following summaries:
       - Statistical summary
       - Compilation summary
       - Biological grammar summary
    2. Explore the full network, or a random subgraph if it is too big.
    3. Create a biological query starting with this network
    4. Analyze the network with one of the procedures (CMPA, etc.)
    5. Execute one of the following actions if the current user is the owner:
       - Drop
       - Make public/private
    """
    networks = get_networks_with_permission(manager)

    return render_template(
        'networks.html',
        networks=sorted(networks, key=lambda network: network.created, reverse=True),
        current_user=current_user,
        BMS_BASE=current_app.config.get('BMS_BASE'),
    )


def _render_nodes(template, nodes, count=None):
    """Renders a list of nodes

    :param iter[Node] nodes:
    :param Optional[int] count: The number of nodes displayed
    :return: flask.Response
    """
    return render_template(
        template,
        nodes=nodes,
        count=count,
        current_user=current_user,
        hgnc_manager=hgnc_manager,
        chebi_manager=chebi_manager,
        go_manager=go_manager,
        entrez_manager=entrez_manager,
        interpro_manager=interpro_manager,
    )


@ui_blueprint.route('/node')
@roles_required('admin')
def view_nodes():
    """Renders a page viewing all edges"""
    nodes = manager.session.query(Node)

    func = request.args.get('function')
    if func:
        nodes = nodes.filter(Node.type == func)

    namespace = request.args.get('namespace')
    if namespace:
        nodes = nodes.filter(Node.namespace_entry.namespace.name.contains(namespace))

    search = request.args.get('search')
    if search:
        nodes = nodes.filter(Node.bel.contains(search))

    count = nodes.count()

    limit = request.args.get('limit', 15, type=int)
    nodes = nodes.limit(limit)

    offset = request.args.get('offset', type=int)
    if offset:
        nodes = nodes.offset(offset)

    return render_template(
        'nodes.html',
        nodes=nodes,
        count=count,
        current_user=current_user,
        hgnc_manager=hgnc_manager,
        chebi_manager=chebi_manager,
        go_manager=go_manager,
        entrez_manager=entrez_manager,
        interpro_manager=interpro_manager,
    )


@ui_blueprint.route('/node/<node_hash>')
def view_node(node_hash):
    """View a node summary with a list of all edges incident to the node

    :param str node_hash: The node's hash
    """
    node = safe_get_node(manager, node_hash)

    return render_template(
        'node.html',
        node=node,
        current_user=current_user,
        hgnc_manager=hgnc_manager,
        chebi_manager=chebi_manager,
        go_manager=go_manager,
        entrez_manager=entrez_manager,
        interpro_manager=interpro_manager,
    )


@ui_blueprint.route('/evidence')
def view_evidences():
    """View a list of Evidence models"""
    limit = request.args.get('limit', type=int, default=10)
    offset = request.args.get('offset', type=int)

    evidences = manager.session.query(Evidence)
    evidences = evidences.limit(limit)
    if offset is not None:
        evidences = evidences.offset(offset)

    return render_template(
        'evidences.html',
        manager=manager,
        evidences=evidences.all(),
        count=manager.session.query(Evidence).count(),
    )


@ui_blueprint.route('/evidence/<int:evidence_id>')
def view_evidence(evidence_id):
    """View a single Evidence model"""
    evidence = manager.session.query(Evidence).get(evidence_id)
    if evidence is None:
        abort(404)
    return render_template('evidence.html', manager=manager, evidence=evidence)


@ui_blueprint.route('/node/<source_hash>/edges/<target_hash>')
def view_relations(source_hash, target_hash):
    """View a list of all relations between two nodes

    :param str source_hash: The source node's hash
    :param str target_hash: The target node's hash
    """
    source = safe_get_node(manager, source_hash)
    target = safe_get_node(manager, target_hash)

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
        'evidence_list.html',
        data=data,
        ev2cit=ev2cit,
        source_bel=source.bel,
        target_bel=target.bel if target else None,
    )


@ui_blueprint.route('/edge')
@roles_required('admin')
def view_edges():
    """Renders a page viewing all edges"""
    return render_template('edges.html', edges=manager.session.query(Edge).limit(15), current_user=current_user)


@ui_blueprint.route('/edge/<edge_hash>')
@roles_required('admin')
def view_edge(edge_hash):
    """Renders a page viewing a single edges

    :param str edge_hash: The identifier of the edge to display
    """
    return render_template('edge.html', edge=manager.get_edge_by_hash(edge_hash), current_user=current_user)


@ui_blueprint.route('/edge/<edge_hash>/vote/<int:vote>')
@login_required
def vote_edge(edge_hash, vote):
    """Renders a page viewing a single edges

    :param str edge_hash: The identifier of the edge to display
    :param int vote:
    """
    edge = manager.get_edge_by_hash(edge_hash)
    get_or_create_vote(manager, edge, current_user, agreed=(vote != 0))
    return redirect(url_for('.view_edge', edge_hash=edge_hash))


@ui_blueprint.route('/query/<int:query_id>')
def view_query(query_id):
    """Renders a single query page"""
    query = safe_get_query(query_id)
    return render_template('query.html', query=query, manager=manager, current_user=current_user)


@ui_blueprint.route('/query')
@roles_required('admin')
def view_queries():
    """Renders the query catalog"""
    q = manager.session.query(Query)

    if not current_user.is_admin:
        q = q.filter(Query.public)

    q = q.order_by(Query.created.desc())

    return render_template(
        'queries.html',
        queries=q.all(),
        manager=manager,
        current_user=current_user,
    )


@ui_blueprint.route('/citation')
@roles_required('admin')
def view_citations():
    """Renders the query catalog"""
    limit = request.args.get('limit', type=int, default=10)

    q = manager.session.query(Citation)
    q = q.limit(limit)

    return render_template(
        'citations.html',
        citations=q.all(),
        count=manager.session.query(Citation).count(),
        manager=manager,
        current_user=current_user
    )


@ui_blueprint.route('/citation/<int:citation_id>')
def view_citation(citation_id):
    """View a citation"""
    citation = manager.session.query(Citation).get(citation_id)
    return render_template('citation.html', citation=citation)


@ui_blueprint.route('/citation/pubmed/<pmid>')
def view_pubmed(pmid):
    """View all evidences and relations extracted from the article with the given PubMed identifier

    :param str pmid: The PubMed identifier
    """
    citation = manager.get_citation_by_pmid(pmid)
    return redirect(url_for('.view_citation', citation_id=citation.id))


@ui_blueprint.route('/network/<int:network_id>/explore')
def view_explore_network(network_id):
    """Renders a page for the user to explore a network

    :param int network_id: The identifier of the network to explore
    """
    network = safe_get_network(network_id)
    query = query_from_network(network)
    return redirect_to_view_explorer_query(query)


@ui_blueprint.route('/explore/<int:query_id>')
def view_explorer_query(query_id):
    """Renders a page for the user to explore a network

    :param int query_id: The identifier of the query
    """
    query = safe_get_query(query_id)
    return render_template('explorer.html', query=query, explorer_toolbox=get_explorer_toolbox())


@ui_blueprint.route('/node/<node_hash>/explore/')
def view_explorer_node(node_hash):
    """Builds an induction query around the node then sends it

    :param str node_hash: The hash of the node
    """
    node = safe_get_node(manager, node_hash)

    query_original = Query.from_networks(networks=node.networks, user=current_user)
    manager.session.flush()

    query = query_original.add_seed_neighbors([node])
    manager.session.add(query)
    manager.session.commit()

    return redirect(url_for('.view_explorer_query', query_id=query.id))


@ui_blueprint.route('/project/<int:project_id>/explore')
@login_required
def view_explore_project(project_id):
    """Renders a page for the user to explore the full network from a project

    :param int project_id: The identifier of the project to explore
    """
    project = manager.session.query(Project).get(project_id)

    query = Query.from_networks(project.networks, user=current_user)
    query.assembly.name = '{} query of {}'.format(time.asctime(), project.name)

    manager.session.add(query)
    manager.session.commit()

    return redirect_to_view_explorer_query(query)


@ui_blueprint.route('/query/build', methods=['GET', 'POST'])
def view_query_builder():
    """Renders the query builder page"""
    networks = get_networks_with_permission(manager)

    return render_template(
        'query_builder.html',
        networks=networks,
        current_user=current_user,
        preselected=request.args.get('start', type=int)
    )


@ui_blueprint.route('/query/compile', methods=['POST'])
def get_pipeline():
    """Executes a pipeline"""
    d = query_form_to_dict(request.form)
    q = pybel_tools.query.Query.from_json(d)
    query = models.Query.from_query(manager, q, current_user)

    manager.session.add(query)
    manager.session.commit()

    return redirect_to_view_explorer_query(query)


@ui_blueprint.route('/namespaces')
def view_namespaces():
    """Displays a page listing the namespaces."""
    return render_template(
        'namespaces.html',
        namespaces=manager.session.query(Namespace).order_by(Namespace.keyword).all(),
        current_user=current_user,
    )


@ui_blueprint.route('/annotations')
def view_annotations():
    """Displays a page listing the annotations."""
    return render_template(
        'annotations.html',
        annotations=manager.session.query(Annotation).order_by(Annotation.keyword).all(),
        current_user=current_user,
    )


@ui_blueprint.route('/imprint')
def view_imprint():
    """Renders the impressum"""
    return render_template('imprint.html')


@ui_blueprint.route('/about')
def view_about():
    """Sends the about page"""
    metadata = [
        ('Python Version', sys.version),
        ('PyBEL Version', get_pybel_version()),
        ('PyBEL Tools Version', get_pybel_tools_version()),
        ('BEL Commons Version', VERSION),
        ('Deployed', time_instantiated)
    ]

    return render_template('about.html', metadata=metadata, managers=manager_dict)


@ui_blueprint.route('/network/<int:network_id>')
def view_network(network_id):
    """Renders a page with the statistics of the contents of a BEL script

    :param int network_id: The identifier of the network to summarize
    """
    return render_network_summary_safe(manager, network_id, template='network.html')


@ui_blueprint.route('/network/<int:network_id>/compilation')
def view_summarize_compilation(network_id):
    """Renders a page with the compilation summary of the contents of a BEL script

    :param int network_id: The identifier of the network to summarize
    """
    return render_network_summary_safe(manager, network_id, template='summarize_compilation.html')


@ui_blueprint.route('/network/<int:network_id>/warnings')
def view_summarize_warnings(network_id):
    """Renders a page with the parsing errors from a BEL script

    :param int network_id: The identifier of the network to summarize
    """
    return render_network_summary_safe(manager, network_id, template='summarize_warnings.html')


@ui_blueprint.route('/network/<int:network_id>/biogrammar')
def view_summarize_biogrammar(network_id):
    """Renders a page with the summary of the biogrammar analysis of a BEL script

    :param int network_id: The identifier of the network to summarize
    """
    return render_network_summary_safe(manager, network_id, template='summarize_biogrammar.html')


@ui_blueprint.route('/network/<int:network_id>/completeness')
def view_summarize_completeness(network_id):
    """Renders a page with the summary of the completeness analysis of a BEL script

    :param int network_id: The identifier of the network to summarize
    """
    network = manager.get_network_by_id(network_id)
    graph = network.as_bel()

    entries = summarize_competeness(graph)

    return render_template('summarize_completeness.html', current_user=current_user, network=network, entries=entries)


@ui_blueprint.route('/network/<int:network_id>/stratified/<annotation>')
def view_summarize_stratified(network_id, annotation):
    """Show stratified summary of graph's subgraphs by annotation"""
    network = safe_get_network(network_id)
    graph = network.as_bel()
    graphs = get_subgraphs_by_annotation(graph, annotation)

    graph_summary = info_json(graph)

    summaries = {}
    useful_summaries = {}

    for name, subgraph in graphs.items():
        summaries[name] = info_json(subgraph)
        summaries[name]['node_overlap'] = subgraph.number_of_nodes() / graph.number_of_nodes()
        summaries[name]['edge_overlap'] = subgraph.number_of_edges() / graph.number_of_edges()
        summaries[name]['citation_overlap'] = summaries[name]['Citations'] / graph_summary['Citations']

        useful_subgraph = extract_useful_subgraph(subgraph)
        useful_summaries[name] = info_json(useful_subgraph)
        useful_summaries[name]['node_overlap'] = subgraph.number_of_nodes() / graph.number_of_nodes()
        useful_summaries[name]['edge_overlap'] = subgraph.number_of_edges() / graph.number_of_edges()
        useful_summaries[name]['citation_overlap'] = summaries[name]['Citations'] / graph_summary['Citations']

    return render_template(
        'summarize_stratified.html',
        network=network,
        annotation=annotation,
        full_summary=graph_summary,
        summaries=summaries,
        useful_summaries=useful_summaries,
    )


@ui_blueprint.route('/how_to_use')
def view_how_to_use():
    """Shows How to use PyBEL-web"""
    return render_template('how_to_use.html')


@ui_blueprint.route('/help/pipeline')
def view_pipeline_help():
    """View the help info for the functions"""

    data = []
    for fname, f in no_arguments_map.items():

        if f.__doc__ is None:
            log.warning('No documentation for %s', fname)
            continue

        data.append((fname.replace('_', ' ').title(), f.__doc__.split('\n\n')[0]))

    return render_template(
        'pipeline_help.html',
        function_dict=data
    )


@ui_blueprint.route('/help/download')
def view_download_help():
    """View the help info for the functions"""
    return render_template('help_download_format.html')


@ui_blueprint.route('/network/<int:network_1_id>/compare/<int:network_2_id>')
def view_network_comparison(network_1_id, network_2_id):
    """View the comparison between two networks

    :param int network_1_id: Identifier for the first network
    :param int network_2_id: Identifier for the second network
    """
    network_1 = safe_get_network(network_1_id)
    network_2 = safe_get_network(network_2_id)

    data = calculate_overlap_dict(
        g1=network_1.as_bel(),
        g1_label=str(network_1),
        g2=network_2.as_bel(),
        g2_label=str(network_2),
    )

    return render_template(
        'network_comparison.html',
        networks=[network_1, network_2],
        data=data,
    )


@ui_blueprint.route('/query/<int:query_1_id>/compare/<int:query_2_id>')
def view_query_comparison(query_1_id, query_2_id):
    """View the comparison between the result of two queries

    :param int query_1_id: The identifier of the first query
    :param int query_2_id: The identifier of the second query
    """

    query_1 = safe_get_query(query_1_id)
    query_2 = safe_get_query(query_2_id)

    query_1_result = query_1.run(manager)
    query_2_result = query_2.run(manager)

    data = calculate_overlap_dict(
        g1=query_1_result,
        g1_label='Query {}'.format(query_1_id),
        g2=query_2_result,
        g2_label='Query {}'.format(query_2_id),
    )

    return render_template(
        'query_comparison.html',
        query_1=query_1,
        query_2=query_2,
        data=data,
    )


@ui_blueprint.route('/download/bel/<fid>')
def download_saved_file(fid):
    """Downloads a BEL file

    :param str fid: The file's identifier
    """
    name = '{}.bel'.format(fid)
    path = os.path.join(merged_document_folder, name)

    if not os.path.exists(path):
        abort(404, 'BEL file does not exist')

    rv = flask.send_file(path)

    # TODO delete as cleanup
    return rv


##########################################
# The following endpoints are admin only #
##########################################

@ui_blueprint.route('/user')
@roles_required('admin')
def view_users():
    """Renders a list of users"""
    return render_template('users.html', users=manager.session.query(User))


def render_user(user):
    pending_reports = user.pending_reports()
    return render_template('user.html', user=user, pending_reports=pending_reports, manager=manager)


@ui_blueprint.route('/user/current')
@login_required
def view_current_user_activity():
    """Returns the current user's history."""
    return render_user(current_user)


@ui_blueprint.route('/user/<int:user_id>')
@roles_required('admin')
def view_user(user_id):
    """Returns the given user's history

    :param int user_id: The identifier of the user to summarize
    """
    user = manager.session.query(User).get(user_id)
    return render_user(user)


@ui_blueprint.route('/reporting', methods=['GET'])
@roles_required('admin')
def view_reports():
    """Shows the uploading reporting"""
    return render_template('reporting.html', reports=manager.session.query(Report).order_by(Report.created).all())


@ui_blueprint.route('/overview')
@roles_required('admin')
def view_overview():
    """Views the overview"""
    return render_template('overview.html')


@ui_blueprint.route('/admin/rollback')
@roles_required('admin')
def rollback():
    """Rolls back the transaction for when something bad happens"""
    manager.session.rollback()
    return next_or_jsonify('rolled back')


@ui_blueprint.route('/admin/nuke/')
@roles_required('admin')
def nuke():
    """Destroys the database and recreates it"""
    log.info('nuking database')
    manager.drop_all(checkfirst=True)
    log.info('   the dust settles')
    return next_or_jsonify('nuked the database')


@ui_blueprint.route('/admin/configuration')
@roles_required('admin')
def view_config():
    """Render the configuration"""
    return render_template('deployment.html', config=current_app.config)


#######################################
# The following endpoints are helpers #
#######################################

@ui_blueprint.route('/project/<int:project_id>/merge/<int:user_id>')
def send_async_project_merge(user_id, project_id):
    """A helper endpoint to submit a project to the asynchronous task queue to merge its associated networks.

    :param int user_id: The identifier of the user sending the task
    :param int project_id: The identifier of the project to merge
    """
    task = current_app.celery.send_task('merge-project', args=[
        current_app.config['SQLALCHEMY_DATABASE_URI'],
        user_id,
        project_id
    ])
    flash('Merge task sent: {}'.format(task))
    return redirect(url_for('ui.view_current_user_activity'))


@ui_blueprint.route('/network/<int:network_id>/induction-query/')
def build_summary_link_query(network_id):
    """Builds a query with the given network by inducing a subgraph over the nodes included in the request

    :param int network_id: The identifier of the network
    """
    nodes = [
        manager.get_node_tuple_by_hash(node_hash)
        for node_hash in request.args.getlist('nodes')
    ]

    q = pybel_tools.query.Query([network_id])
    q.append_seeding_induction(nodes)
    query = Query.from_query(manager, q, current_user)
    manager.session.add(query)
    manager.session.commit()

    return redirect_to_view_explorer_query(query)


@ui_blueprint.route('/network/<int:network_id>/sample/')
def build_subsample_query(network_id):
    """Builds and executes a query that induces a random subnetwork over the given network

    :param int network_id: The identifier of the network
    """
    q = pybel_tools.query.Query([network_id])
    q.append_seeding_sample()
    query = Query.from_query(manager, q, current_user)
    manager.session.add(query)
    manager.session.commit()

    return redirect_to_view_explorer_query(query)
