# -*- coding: utf-8 -*-

"""This module runs the dictionary-backed PyBEL API"""

import logging
import os
import sys
import time

import pandas as pd
from flask import (
    current_app,
    request,
    jsonify,
    url_for,
    redirect,
    make_response,
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
from six import BytesIO

from pybel import from_bytes
from pybel import from_url
from pybel.constants import FRAUNHOFER_RESOURCES, PYBEL_CONNECTION
from pybel.manager.models import (
    Namespace,
    Annotation,
    Network,
)
from pybel.utils import get_version as get_pybel_version
from pybel_tools.api import DatabaseService
from pybel_tools.constants import BMS_BASE
from pybel_tools.ioutils import upload_recursive, get_paths_recursive
from pybel_tools.mutation.metadata import fix_pubmed_citations
from pybel_tools.selection.induce_subgraph import SEED_TYPE_PROVENANCE
from pybel_tools.utils import get_version as get_pybel_tools_version
from .application import create_celery
from .constants import *
from .forms import SeedProvenanceForm, SeedSubgraphForm
from .models import User, Report
from .utils import (
    render_network_summary,
    try_insert_graph,
    sanitize_list_of_str,
    get_api,
    get_manager
)

log = logging.getLogger(__name__)


def get_networks_with_permission(api):
    """Gets all networks tagged as public or uploaded by the current user
    
    :param DatabaseService api: The database service
    :return: A list of all networks tagged as public or uploaded by the current user
    :rtype: list[Network]
    """
    if not current_user.is_authenticated:
        return api.list_public_networks()

    if current_user.admin or current_user.has_role('scai'):
        return api.list_recent_networks()

    networks = api.list_public_networks()

    public_ids = {network.id for network in networks}

    for report in current_user.reports:
        if report.network_id in public_ids:
            continue
        networks.append(report.network)

    return networks


def build_dictionary_service_admin(app):
    """Dictionary Service Admin Functions"""
    manager = get_manager(app)
    api = get_api(app)

    @app.route('/admin/reload')
    @roles_required('admin')
    def run_reload():
        """Reloads the networks and supernetwork"""
        api.clear()
        api.cache_networks(force_reload=True)
        return jsonify({'status': 200})

    @app.route('/admin/rollback')
    @roles_required('admin')
    def rollback():
        """Rolls back the transaction for when something bad happens"""
        manager.rollback()
        return jsonify({'status': 200})

    @app.route('/admin/enrich')
    @roles_required('admin')
    def run_enrich_authors():
        """Enriches information in network. Be patient"""
        fix_pubmed_citations(api.universe)
        return jsonify({'status': 200})

    @app.route('/admin/ensure/abstract3')
    @roles_required('admin')
    def ensure_abstract3():
        """Parses and stores Selventa Example 3"""
        url = 'http://resources.openbel.org/belframework/20150611/knowledge/full_abstract3.bel'
        graph = from_url(url, manager=manager, citation_clearing=False, allow_nested=True)
        return try_insert_graph(manager, graph, api)

    @app.route('/admin/ensure/simple')
    @roles_required('admin')
    def ensure_simple():
        """Parses and stores the PyBEL Test BEL Script"""
        url = 'https://raw.githubusercontent.com/pybel/pybel/develop/tests/bel/test_bel.bel'
        graph = from_url(url, manager=manager)
        return try_insert_graph(manager, graph, api)

    @app.route('/admin/ensure/gfam')
    @roles_required('admin')
    def ensure_gfam():
        """Parses and stores the HGNC Gene Family Definitions"""
        graph = from_url(FRAUNHOFER_RESOURCES + 'gfam_members.bel', manager=manager)
        return try_insert_graph(manager, graph, api)

    @app.route('/admin/ensure/aetionomy')
    @roles_required('admin')
    def ensure_aetionomy():
        """Parses and stores the AETIONOMY resources from the Biological Model Store repository"""
        celery = create_celery(current_app)
        task = celery.send_task('parse-aetionomy', args=[app.config.get(PYBEL_CONNECTION)])
        flash('Queued task to parse the AETIONOMY folder: {}'.format(task))
        return redirect(url_for('home'))

    @app.route('/admin/upload/selventa')
    @roles_required('admin')
    def upload_selventa():
        """Uploads the gpickles in the Selventa section of the Biological Model Store repository"""
        celery = create_celery(current_app)
        task = celery.send_task('parse-selventa', args=[app.config.get(PYBEL_CONNECTION)])
        flash('Queued task to parse the Selventa folder: {}'.format(task))
        return redirect(url_for('home'))

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
        flash('Uploaded the AETIONOMY folder in {:.2f}'.format(time.time() - t))
        return redirect(url_for('home'))

    @app.route('/api/database/nuke/')
    @roles_required('admin')
    def nuke():
        """Destroys the database and recreates it"""
        log.info('nuking database')
        manager.drop_database()
        manager.create_all()
        log.info('restarting dictionary service')
        api.clear()
        log.info('   the dust settles')
        flash('Nuked the database')
        return redirect(url_for('home'))

    log.info('added dict service admin functions')


def build_main_service(app):
    """Builds the PyBEL main sergice

    :param flask.Flask app: A Flask App
    """
    build_dictionary_service_admin(app)

    manager = get_manager(app)
    api = get_api(app)

    @app.route('/', methods=['GET', 'POST'])
    def home():
        """Renders the home page"""
        return render_template('index.html')

    @app.route('/networks', methods=['GET', 'POST'])
    def view_networks():
        """Renders a page for the user to choose a network"""
        seed_subgraph_form = SeedSubgraphForm()
        seed_provenance_form = SeedProvenanceForm()

        if seed_subgraph_form.validate_on_submit() and seed_subgraph_form.submit_subgraph.data:
            seed_data_nodes = seed_subgraph_form.node_list.data.split(',')
            seed_method = seed_subgraph_form.seed_method.data
            filter_pathologies = seed_subgraph_form.filter_pathologies.data
            log.info('got subgraph seed: %s', dict(
                nodes=seed_data_nodes,
                method=seed_method,
                filter_path=filter_pathologies
            ))
            url = url_for('view_explorer', **{
                NETWORK_ID: '0',
                SEED_TYPE: seed_method,
                SEED_DATA_NODES: seed_data_nodes,
                FILTER_PATHOLOGIES: filter_pathologies,
                AUTOLOAD: 'yes',
            })
            log.info('redirecting to %s', url)
            return redirect(url)
        elif seed_provenance_form.validate_on_submit() and seed_provenance_form.submit_provenance.data:
            authors = sanitize_list_of_str(seed_provenance_form.author_list.data.split(','))
            pmids = sanitize_list_of_str(seed_provenance_form.pubmed_list.data.split(','))
            filter_pathologies = seed_provenance_form.filter_pathologies.data
            log.info('got prov: %s', dict(authors=authors, pmids=pmids))
            url = url_for('view_explorer', **{
                NETWORK_ID: '0',
                SEED_TYPE: SEED_TYPE_PROVENANCE,
                SEED_DATA_PMIDS: pmids,
                SEED_DATA_AUTHORS: authors,
                FILTER_PATHOLOGIES: filter_pathologies,
                AUTOLOAD: 'yes',
            })
            log.info('redirecting to %s', url)
            return redirect(url)

        networks = get_networks_with_permission(api)

        return render_template(
            'network_list.html',
            networks=networks,
            provenance_form=seed_provenance_form,
            subgraph_form=seed_subgraph_form,
            analysis_enabled=True,
            current_user=current_user,
        )

    @app.route('/query', methods=['GET', 'POST'])
    @login_required
    def view_query_builder():
        """Renders the query builder page"""

        networks = get_networks_with_permission(api)

        return render_template(
            'query_builder.html',
            networks=networks,
            current_user=current_user,
        )

    @app.route('/explore', methods=['GET'])
    def view_explorer():
        """Renders a page for the user to explore a network"""
        return render_template('explorer.html')

    @app.route('/summary/<network_id>')
    def view_summary(network_id):
        """Renders a page with the parsing errors for a given BEL script"""
        try:
            network = manager.get_network_by_id(network_id)
            graph = from_bytes(network.blob, check_version=app.config.get('PYBEL_DS_CHECK_VERSION'))
        except Exception as e:
            flash("Problem getting graph {}: ({}) {}".format(network_id, type(e), e), category='error')
            return redirect(url_for('view_networks'))

        return render_network_summary(network_id, graph, api)

    @app.route('/definitions')
    def view_definitions():
        """Displays a page listing the namespaces and annotations."""
        return render_template(
            'definitions_list.html',
            namespaces=manager.session.query(Namespace).order_by(Namespace.keyword).all(),
            annotations=manager.session.query(Annotation).order_by(Annotation.keyword).all(),
            current_user=current_user,
        )

    @app.route('/overlap')
    def view_overlap():
        """Produces an image assessing the overlaps between networks using PyUpset"""
        import pyupset as pyu
        import matplotlib.pyplot as plt

        network_ids = request.args.get('networks')
        if not network_ids:
            return abort(500)

        networks = [
            api.get_network_by_id(int(network_id.strip()))
            for network_id in network_ids.split(',')
        ]

        data_dict = {network.name.replace('_', ' '): pd.DataFrame(network.nodes()) for network in networks}
        pyu.plot(data_dict)
        buf = BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        output = make_response(buf.getvalue())
        output.headers["Content-type"] = "image/png"
        return output

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
        for rule in app.url_map.iter_rules():
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
        """Returns all user history."""
        return render_template('user_activity.html', user=current_user)

    @app.route('/swagger.json')
    def get_swagger():
        """Gets the Swagger definition of this API"""
        return send_file('static/json/swagger.json')

    @app.route('/reporting', methods=['GET'])
    def view_reports():
        """Shows the uploading reporting"""
        reports = manager.session.query(Report).order_by(Report.created).all()
        return render_template('reporting.html', reports=reports)

    log.info('Added main to %s', app)
