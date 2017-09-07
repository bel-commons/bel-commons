# -*- coding: utf-8 -*-

"""This module runs the dictionary-backed PyBEL API"""

import logging
import sys
import time

from collections import defaultdict
from flask import (
    current_app,
    request,
    jsonify,
    url_for,
    redirect,
    send_file,
    flash,
    render_template,
    abort
)
from flask_security import (
    roles_required,
    current_user,
    login_required
)

import pybel_tools.query
from pybel import from_bytes
from pybel.constants import (
    PYBEL_CONNECTION,
    EVIDENCE,
    CITATION,
)
from pybel.manager.models import (
    Namespace,
    Annotation,
)
from pybel.utils import get_version as get_pybel_version
from pybel_tools.constants import BMS_BASE, GENE_FAMILIES
from pybel_tools.ioutils import upload_recursive, get_paths_recursive
from pybel_tools.mutation.metadata import enrich_pubmed_citations
from pybel_tools.pipeline import no_arguments_map
from pybel_tools.utils import get_version as get_pybel_tools_version
from . import models
from .application_utils import get_api, get_manager
from .celery_utils import create_celery
from .constants import *
from .models import User, Report, Query, Project
from .utils import (
    render_network_summary,
    calculate_overlap_dict,
    get_network_ids_with_permission_helper,
    get_networks_with_permission,
    safe_get_query,
    next_or_jsonify,
    query_form_to_dict
)

log = logging.getLogger(__name__)


def build_ensure_service(app):
    """Group all ensure services

    :param flask.Flask app: A Flask app
    """

    @app.route('/admin/ensure/simple')
    @roles_required('admin')
    def ensure_simple():
        """Parses and stores the PyBEL Test BEL Script"""
        url = 'https://raw.githubusercontent.com/pybel/pybel/develop/tests/bel/test_bel.bel'
        celery = create_celery(current_app)
        task = celery.send_task('parse-url', args=[current_app.config.get(PYBEL_CONNECTION), url])
        return next_or_jsonify('Queued task to parse PyBEL Test 1: {}'.format(task))

    @app.route('/admin/ensure/gfam')
    @roles_required('admin')
    def ensure_gfam():
        """Parses and stores the HGNC Gene Family Definitions"""
        celery = create_celery(current_app)
        task = celery.send_task('parse-url', args=[current_app.config.get(PYBEL_CONNECTION), GENE_FAMILIES])
        return next_or_jsonify('Queued task to parse HGNC Gene Families: {}'.format(task))

    @app.route('/admin/ensure/aetionomy')
    @roles_required('admin')
    def ensure_aetionomy():
        """Parses and stores the AETIONOMY resources from the Biological Model Store repository"""
        celery = create_celery(current_app)
        task = celery.send_task('parse-aetionomy', args=[current_app.config.get(PYBEL_CONNECTION)])
        return next_or_jsonify('Queued task to parse the AETIONOMY folder: {}'.format(task))

    @app.route('/admin/ensure/selventa')
    @roles_required('admin')
    def ensure_selventa():
        """Parses and stores the Selventa resources from the Biological Model Store repository"""
        celery = create_celery(current_app)
        task = celery.send_task('parse-selventa', args=[current_app.config.get(PYBEL_CONNECTION)])
        return next_or_jsonify('Queued task to parse the Selventa folder: {}'.format(task))

    @app.route('/admin/ensure/ptsd')
    @roles_required('admin')
    def ensure_ptsd():
        """Parses and stores the PTSD resources from the Biological Model Store repository"""
        celery = create_celery(current_app)
        task = celery.send_task('parse-ptsd', args=[current_app.config.get(PYBEL_CONNECTION)])
        return next_or_jsonify('Queued task to parse the PTSD folder: {}'.format(task))

    @app.route('/admin/ensure/tbi')
    @roles_required('admin')
    def ensure_tbi():
        """Parses and stores the TBI resources from the Biological Model Store repository"""
        celery = create_celery(current_app)
        task = celery.send_task('parse-tbi', args=[current_app.config.get(PYBEL_CONNECTION)])
        return next_or_jsonify('Queued task to parse the TBI folder: {}'.format(task))

    @app.route('/admin/ensure/bel4imocede')
    @roles_required('admin')
    def ensure_bel4imocede():
        """Parses and stores the BEL4IMOCEDE resources from the Biological Model Store repository"""
        celery = create_celery(current_app)
        task = celery.send_task('parse-bel4imocede', args=[current_app.config.get(PYBEL_CONNECTION)])
        return next_or_jsonify('Queued task to parse the BEL4IMOCEDE folder: {}'.format(task))

    @app.route('/admin/ensure/bms')
    @roles_required('admin')
    def ensure_bms():
        """Parses and stores the entire Biological Model Store repository"""
        celery = create_celery(current_app)
        task = celery.send_task('parse-bms', args=[current_app.config.get(PYBEL_CONNECTION)])
        return next_or_jsonify('Queued task to parse the BMS: {}'.format(task))


def build_dictionary_service_admin(app):
    """Dictionary Service Admin Functions"""
    manager = get_manager(app)
    api = get_api(app)

    build_ensure_service(app)

    @app.route('/admin/reload')
    @roles_required('admin')
    def run_reload():
        """Reloads the networks and supernetwork"""
        api.clear()
        api.cache_networks(force_reload=True)
        return next_or_jsonify('reloaded networks')

    @app.route('/admin/rollback')
    @roles_required('admin')
    def rollback():
        """Rolls back the transaction for when something bad happens"""
        manager.session.rollback()
        return next_or_jsonify('rolled back')

    @app.route('/admin/enrich')
    @roles_required('admin')
    def run_enrich_authors():
        """Enriches information in network. Be patient"""
        enrich_pubmed_citations(api.universe)
        return next_or_jsonify('enriched authors')

    @app.route('/admin/list/bms/pickles')
    @roles_required('admin')
    def list_bms_pickles():
        """Lists the pre-parsed gpickles in the Biological Model Store repository"""
        return jsonify(list(get_paths_recursive(os.environ[BMS_BASE], extension='.gpickle')))

    @app.route('/admin/upload/aetionomy')
    @roles_required('admin')
    def upload_aetionomy():
        """Uploads the gpickles in the AETIONOMY section of the Biological Model Store repository"""
        t = time.time()
        upload_recursive(os.path.join(os.environ[BMS_BASE], 'aetionomy'), connection=manager)
        flash('Uploaded the AETIONOMY folder in {:.2f} seconds'.format(time.time() - t))
        return redirect(url_for('home'))

    @app.route('/admin/upload/bms')
    @roles_required('admin')
    def upload_bms():
        """Synchronously uploads the gpickles in the Biological Model Store repository"""
        t = time.time()
        upload_recursive(os.path.join(os.environ[BMS_BASE]), connection=manager)
        flash('Uploaded the BMS folder in {:.2f} seconds'.format(time.time() - t))
        return redirect(url_for('home'))

    @app.route('/api/database/nuke/')
    @roles_required('admin')
    def nuke():
        """Destroys the database and recreates it"""
        log.info('nuking database')
        manager.drop_all()
        manager.create_all()
        log.info('restarting dictionary service')
        api.clear()
        log.info('   the dust settles')
        flash('Nuked the database')
        return redirect(url_for('home'))


def build_main_service(app):
    """Builds the PyBEL main service

    :param flask.Flask app: A Flask App
    """
    build_dictionary_service_admin(app)

    manager = get_manager(app)
    api = get_api(app)

    @app.route('/', methods=['GET', 'POST'])
    def home():
        """Renders the home page"""
        return render_template('index.html', current_user=current_user)

    @app.route('/networks', methods=['GET', 'POST'])
    def view_networks():
        """Renders a page for the user to choose a network"""
        networks = get_networks_with_permission(api)

        return render_template(
            'network_list.html',
            networks=networks,
            current_user=current_user,
        )

    @app.route('/query/build', methods=['GET', 'POST'])
    def view_query_builder():
        """Renders the query builder page"""
        networks = get_networks_with_permission(api)

        return render_template(
            'query_builder.html',
            networks=networks,
            current_user=current_user,
        )

    @app.route('/query/compile', methods=['POST'])
    def get_pipeline():
        """Executes a pipeline"""
        d = query_form_to_dict(request.form)
        q = pybel_tools.query.Query.from_json(d)
        qo = models.Query.from_query(manager, q, current_user)

        manager.session.add(qo)
        manager.session.commit()

        return redirect(url_for('view_explorer_query', query_id=qo.id))

    @app.route('/explore/query/<int:query_id>', methods=['GET'])
    def view_explorer_query(query_id):
        """Renders a page for the user to explore a network"""
        query = safe_get_query(query_id)
        return render_template('explorer.html', query=query)

    @app.route('/explore/project/<int:project_id>', methods=['GET'])
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

    @app.route('/explore/network/<int:network_id>', methods=['GET'])
    def view_explore_network(network_id):
        """Renders a page for the user to explore a network"""
        if network_id not in get_network_ids_with_permission_helper(current_user, api):
            abort(403, 'Insufficient rights for network {}'.format(network_id))

        query = Query.from_query_args(manager, network_id, current_user)
        manager.session.add(query)
        manager.session.commit()
        return redirect(url_for('view_explorer_query', query_id=query.id))

    @app.route('/summary/<int:network_id>')
    def view_summary(network_id):
        """Renders a page with the parsing errors for a given BEL script"""
        if network_id not in get_network_ids_with_permission_helper(current_user, api):
            abort(403, 'Insufficient rights for network {}'.format(network_id))

        try:
            network = manager.get_network_by_id(network_id)
            graph = from_bytes(network.blob, check_version=current_app.config.get('PYBEL_DS_CHECK_VERSION'))
        except Exception as e:
            flash("Problem getting graph {}: ({}) {}".format(network_id, type(e), e), category='error')
            return redirect(url_for('view_networks'))

        return render_network_summary(network_id, graph)

    @app.route('/summary/<int:network_id>/induction-query/')
    def build_summary_link_query(network_id):
        nodes = [
            api.get_node_by_id(node)
            for node in request.args.getlist('nodes', type=int)
        ]
        q = pybel_tools.query.Query(network_id)
        q.add_seed_induction(nodes)
        qo = Query.from_query(manager, q, current_user)
        manager.session.add(qo)
        manager.session.commit()
        return redirect(url_for('view_explorer_query', query_id=qo.id))

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
        return render_template('user_activity.html', user=current_user)

    @app.route('/user/<int:user_id>')
    @roles_required('admin')
    def view_user_activity(user_id):
        """Returns the given user's history"""
        user = manager.session.query(User).get(user_id)

        pending_reports = [
            report
            for report in user.reports
            if report.completed is None
        ]

        return render_template('user_activity.html', user=user, pending_reports=pending_reports)

    @app.route('/reporting', methods=['GET'])
    def view_reports():
        """Shows the uploading reporting"""
        reports = manager.session.query(Report).order_by(Report.created).all()
        return render_template('reporting.html', reports=reports)

    @app.route('/logging', methods=['GET'])
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

    @app.route('/query/compare/<int:query_1_id>/<int:query_2_id>')
    def view_query_comparison(query_1_id, query_2_id):
        """View the comparison between the result of two queries"""
        q1 = manager.session.query(Query).get(query_1_id).run(api)
        q2 = manager.session.query(Query).get(query_2_id).run(api)

        data = calculate_overlap_dict(q1, q2, set_labels=(query_1_id, query_2_id))

        return render_template(
            'query_comparison.html',
            query_1_id=query_1_id,
            query_2_id=query_2_id,
            data=data,
        )

    @app.route('/edges/<int:source_id>/<int:target_id>')
    @login_required
    def view_relations(source_id, target_id):
        """View a list of all relations between two nodes"""
        source = api.get_node_by_id(source_id)
        target = api.get_node_by_id(target_id)

        relations = api.get_edges(
            source,
            target,
            both_ways=('undirected' in request.args),
        )

        d = defaultdict(list)

        ev2cit = {}

        for relation in relations:
            ev = relation.get(EVIDENCE)
            d[ev].append(relation)

            ev2cit[ev] = relation[CITATION]

        return render_template(
            'evidence_list.html',
            data=d,
            ev2cit=ev2cit,
            source_bel=api.id_bel[source_id],
            target_bel=api.id_bel[target_id],
        )

    @app.route('/overview')
    @roles_required('admin')
    def view_overview():
        """Views the overview"""
        return render_template('overview.html')
