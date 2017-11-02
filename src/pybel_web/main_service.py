# -*- coding: utf-8 -*-

"""This module runs the dictionary-backed PyBEL API"""

import itertools as itt
import logging
import sys
import time
from collections import defaultdict

import flask
from flask import abort, current_app, flash, redirect, render_template, request, send_file, url_for
from flask_security import current_user, login_required, roles_required

import pybel_tools.query
from pybel.manager.models import Annotation, Namespace
from pybel.utils import get_version as get_pybel_version
from pybel_tools.constants import GENE_FAMILIES
from pybel_tools.pipeline import no_arguments_map
from pybel_tools.utils import get_version as get_pybel_tools_version
from . import models
from .application_utils import get_manager
from .constants import *
from .models import Base, Project, Query, Report, User
from .utils import (
    calculate_overlap_dict, get_network_ids_with_permission_helper, get_networks_with_permission,
    next_or_jsonify, query_form_to_dict, render_network_summary, safe_get_query,
)

log = logging.getLogger(__name__)


def build_dictionary_service_admin(app):
    """Dictionary Service Admin Functions"""
    manager = get_manager(app)

    @app.route('/admin/rollback')
    @roles_required('admin')
    def rollback():
        """Rolls back the transaction for when something bad happens"""
        manager.session.rollback()
        return next_or_jsonify('rolled back')

    @app.route('/admin/nuke/')
    @roles_required('admin')
    def nuke():
        """Destroys the database and recreates it"""
        log.info('nuking database')
        Base.metadata.drop_all(manager.engine, checkfirst=True)
        log.info('   the dust settles')
        return next_or_jsonify('nuked the database')

    @app.route('/admin/ensure/simple')
    @roles_required('admin')
    def ensure_simple():
        """Parses and stores the PyBEL Test BEL Script"""
        url = 'https://raw.githubusercontent.com/pybel/pybel/develop/tests/bel/test_bel.bel'
        task = current_app.celery.send_task('parse-url', args=[url])
        return next_or_jsonify('Queued task to parse PyBEL Test 1: {}'.format(task))

    @app.route('/admin/ensure/gfam')
    @roles_required('admin')
    def ensure_gfam():
        """Parses and stores the HGNC Gene Family Definitions"""
        task = current_app.celery.send_task('parse-url', args=[GENE_FAMILIES])
        return next_or_jsonify('Queued task to parse HGNC Gene Families: {}'.format(task))

    @app.route('/admin/configuration')
    @roles_required('admin')
    def view_config():
        """Render the configuration"""
        return render_template('deployment.html', config=current_app.config)


def build_main_service(app):
    """Builds the PyBEL main service

    :param flask.Flask app: A Flask App
    """
    build_dictionary_service_admin(app)

    manager = get_manager(app)

    @app.route('/', methods=['GET', 'POST'])
    def home():
        """Renders the home page"""
        return render_template('index.html', current_user=current_user)

    @app.route('/networks', methods=['GET', 'POST'])
    def view_networks():
        """Renders a page for the user to choose a network"""
        networks = get_networks_with_permission(manager)

        return render_template(
            'network_list.html',
            networks=sorted(networks, key=lambda network: network.created, reverse=True),
            current_user=current_user,
            BMS_BASE=app.config.get('BMS_BASE'),
        )

    @app.route('/query/build', methods=['GET', 'POST'])
    def view_query_builder():
        """Renders the query builder page"""
        networks = get_networks_with_permission(manager)

        return render_template(
            'query_builder.html',
            networks=networks,
            current_user=current_user,
            preselected=request.args.get('start', type=int)
        )

    @app.route('/query/compile', methods=['POST'])
    def get_pipeline():
        """Executes a pipeline"""
        d = query_form_to_dict(request.form)
        q = pybel_tools.query.Query.from_json(d)
        query = models.Query.from_query(manager, q, current_user)

        manager.session.add(query)
        manager.session.commit()

        return redirect(url_for('view_explorer_query', query_id=query.id))

    @app.route('/explore/<int:query_id>', methods=['GET'])
    def view_explorer_query(query_id):
        """Renders a page for the user to explore a network"""
        query = safe_get_query(query_id)
        return render_template('explorer.html', query=query)

    @app.route('/project/<int:project_id>/explore', methods=['GET'])
    @login_required
    def view_explore_project(project_id):
        """Renders a page for the user to explore the full network from a project"""
        project = manager.session.query(Project).get(project_id)

        q = pybel_tools.query.Query(network_ids=[
            network.id
            for network in project.networks
        ])

        query = Query.from_query(manager, q, current_user)
        query.assembly.name = '{} query of {}'.format(time.asctime(), project.name)

        manager.session.add(query)
        manager.session.commit()
        return redirect(url_for('view_explorer_query', query_id=query.id))

    @app.route('/project/<int:project_id>/merge/<int:user_id>')
    def send_async_project_merge(user_id, project_id):
        """Sends async merge task"""
        task = current_app.celery.send_task('merge-project', args=[user_id, project_id])
        flash('Merge task sent: {}'.format(task))
        return redirect(url_for('view_current_user_activity'))

    @app.route('/network/<int:network_id>/explore', methods=['GET'])
    def view_explore_network(network_id):
        """Renders a page for the user to explore a network"""
        if network_id not in get_network_ids_with_permission_helper(current_user, manager):
            abort(403, 'Insufficient rights for network {}'.format(network_id))

        query = Query.from_query_args(manager, network_id, current_user)
        manager.session.add(query)
        manager.session.commit()
        return redirect(url_for('view_explorer_query', query_id=query.id))

    @app.route('/summary/<int:network_id>')
    def view_summarize_statistics(network_id):
        """Renders a page with the parsing errors for a given BEL script"""
        if network_id not in get_network_ids_with_permission_helper(current_user, manager):
            abort(403, 'Insufficient rights for network {}'.format(network_id))

        return render_network_summary(network_id, template='summarize_statistics.html')

    @app.route('/summary/<int:network_id>/compilation')
    def view_summarize_compilation(network_id):
        if network_id not in get_network_ids_with_permission_helper(current_user, manager):
            abort(403, 'Insufficient rights for network {}'.format(network_id))

        return render_network_summary(network_id, template='summarize_compilation.html')

    @app.route('/summary/<int:network_id>/biogrammar')
    def view_summarize_biogrammar(network_id):
        if network_id not in get_network_ids_with_permission_helper(current_user, manager):
            abort(403, 'Insufficient rights for network {}'.format(network_id))

        return render_network_summary(network_id, template='summarize_biogrammar.html')

    @app.route('/network/<int:network_id>/induction-query/')
    def build_summary_link_query(network_id):
        """Induces over the nodes in a network"""
        nodes = [
            manager.get_node_tuple_by_hash(node_hash)
            for node_hash in request.args.getlist('nodes')
        ]

        q = pybel_tools.query.Query([network_id])
        q.add_seed_induction(nodes)
        query = Query.from_query(manager, q, current_user)
        manager.session.add(query)
        manager.session.commit()
        return redirect(url_for('view_explorer_query', query_id=query.id))

    @app.route('/definitions')
    def view_definitions():
        """Displays a page listing the namespaces and annotations."""
        return render_template(
            'definitions_list.html',
            namespaces=manager.session.query(Namespace).order_by(Namespace.keyword).all(),
            annotations=manager.session.query(Annotation).order_by(Annotation.keyword).all(),
            current_user=current_user,
        )

    @app.route('/imprint')
    def view_imprint():
        """Renders the impressum"""
        return render_template('imprint.html')

    @app.route('/about')
    def view_about():
        """Sends the about page"""
        return render_template('about.html')

    @app.route("/sitemap")
    @roles_required('admin')
    def view_site_map():
        """Displays a page with the site map"""
        api_links = []
        page_links = []
        for rule in current_app.url_map.iter_rules():
            try:
                url = url_for(rule.endpoint)
                item = url, rule.endpoint
                if not current_user.admin and (url.startswith('/admin') or url.startswith('/api/admin')):
                    continue
                elif url.startswith('/api'):
                    api_links.append(item)
                else:
                    page_links.append((url, rule.endpoint))
            except:
                pass

        metadata = [
            ('Python Version', sys.version),
            ('PyBEL Version', get_pybel_version()),
            ('PyBEL Tools Version', get_pybel_tools_version()),
            ('PyBEL Web version', PYBEL_WEB_VERSION)
        ]
        return render_template(
            'sitemap.html',
            metadata=metadata,
            links=sorted(set(page_links)),
            api_links=sorted(set(api_links))
        )

    @app.route('/users')
    @roles_required('admin')
    def view_users():
        """Renders a list of users"""
        return render_template('view_users.html', users=manager.session.query(User))

    @app.route('/user')
    @login_required
    def view_current_user_activity():
        """Returns the current user's history."""
        pending_reports = [
            report
            for report in current_user.reports
            if report.incomplete
        ]

        return render_template('user_activity.html', user=current_user, pending_reports=pending_reports)

    @app.route('/user/<int:user_id>')
    @roles_required('admin')
    def view_user_activity(user_id):
        """Returns the given user's history"""
        user = manager.session.query(User).get(user_id)

        pending_reports = [
            report
            for report in user.reports
            if report.incomplete
        ]

        return render_template('user_activity.html', user=user, pending_reports=pending_reports)

    @app.route('/reporting', methods=['GET'])
    def view_reports():
        """Shows the uploading reporting"""
        reports = manager.session.query(Report).order_by(Report.created).all()
        return render_template('reporting.html', reports=reports)

    @app.route('/logging', methods=['GET'])
    @roles_required('admin')
    def view_logging():
        """Shows the logging"""
        return send_file(log_runner_path)

    @app.route('/how_to_use', methods=['GET'])
    def view_how_to_use():
        """Shows How to use PyBEL-web"""
        return render_template('how_to_use.html')

    @app.route('/pipeline/help', methods=['GET'])
    def view_pipeline_help():
        """View the help info for the functions"""

        data = [
            (fname.replace('_', ' ').title(), f.__doc__.split('\n\n')[0])
            for fname, f in no_arguments_map.items()
        ]

        return render_template(
            'pipeline_help.html',
            function_dict=data
        )

    @app.route('/query/<int:query_1_id>/compare/<int:query_2_id>')
    def view_query_comparison(query_1_id, query_2_id):
        """View the comparison between the result of two queries"""

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
            query_1_id=query_1_id,
            query_2_id=query_2_id,
            data=data,
        )

    def serve_relations(edges, source, target=None):
        """Serves a list of edges

        :param list[Edge] edges:
        :param Node source:
        :param Node target:
        """
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

    @app.route('/node/<source_id>/edges/<target_id>')
    def view_relations(source_id, target_id):
        """View a list of all relations between two nodes"""
        source = manager.get_node_by_hash(source_id)
        target = manager.get_node_by_hash(target_id)
        relations = list(manager.query_edges(source=source, target=target))

        if 'undirected' in request.args:
            relations.extend(manager.query_edges(source=target, target=source))

        return serve_relations(relations, source, target)

    @app.route('/node/<node_id>')
    def view_node(node_id):
        """View a node summary with a list of all edges incident to the node"""
        node = manager.get_node_by_hash(node_id)

        if node is None:
            abort(404, 'Node not found: {}'.format(node_id))

        relations = list(itt.chain(
            manager.query_edges(source=node),
            manager.query_edges(target=node)
        ))
        return serve_relations(relations, node)

    @app.route('/overview')
    @roles_required('admin')
    def view_overview():
        """Views the overview"""
        return render_template('overview.html')

    @app.route('/download/bel/<fid>')
    def download_saved_file(fid):
        """Downloads a BEL file"""
        name = '{}.bel'.format(fid)
        path = os.path.join(merged_document_folder, name)

        if not os.path.exists(path):
            abort(404, 'BEL file does not exist')

        return flask.send_file(path)  # TODO delete as cleanup
