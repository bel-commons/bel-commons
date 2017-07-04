# -*- coding: utf-8 -*-

"""This module runs the dictionary-backed PyBEL API"""

import itertools as itt
import logging
import sys

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
from pybel.constants import (
    FRAUNHOFER_RESOURCES,
    PYBEL_CONNECTION,
)
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
from pybel_tools.pipeline import no_arguments_map
from pybel_tools.utils import get_version as get_pybel_tools_version
from .application import create_celery
from .constants import *
from .models import User, Report, Query
from .utils import (
    render_network_summary,
    get_api,
    get_manager,
    calculate_overlap_dict,
)

log = logging.getLogger(__name__)


def unique_networks(networks):
    """Only yields unique networks

    :param list[Network] networks:
    :return: list[Network]
    """
    seen_ids = set()

    for network in networks:
        if network.id not in seen_ids:
            seen_ids.add(network.id)
            yield network


def get_networks_with_permission(api):
    """Gets all networks tagged as public or uploaded by the current user
    
    :param DatabaseService api: The database service
    :return: A list of all networks tagged as public or uploaded by the current user
    :rtype: list[Network]
    """
    if not current_user.is_authenticated:
        return api.list_public_networks()

    if current_user.admin:
        return api.list_recent_networks()

    networks = api.list_public_networks()

    return list(unique_networks(itt.chain(
        networks,
        current_user.get_owned_networks(),
        current_user.get_shared_networks(),
        current_user.get_project_networks()
    )))


def get_network_ids_with_permission(api):
    """Gets the set of networks ids tagged as public or uploaded by the current user

    :param DatabaseService api: The database service
    :return: A list of all networks tagged as public or uploaded by the current user
    :rtype: list[Network]
    """
    networks_with_permission = get_networks_with_permission(api)

    return {
        network.id
        for network in networks_with_permission
    }


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
        manager.session.rollback()
        return jsonify({'status': 200})

    @app.route('/admin/enrich')
    @roles_required('admin')
    def run_enrich_authors():
        """Enriches information in network. Be patient"""
        fix_pubmed_citations(api.universe)
        return jsonify({'status': 200})

    @app.route('/admin/ensure/simple')
    @roles_required('admin')
    def ensure_simple():
        """Parses and stores the PyBEL Test BEL Script"""
        url = 'https://raw.githubusercontent.com/pybel/pybel/develop/tests/bel/test_bel.bel'
        celery = create_celery(current_app)
        task = celery.send_task('parse-url', args=[current_app.config.get(PYBEL_CONNECTION), url])
        flash('Queued task to parse PyBEL Test 1: {}'.format(task))
        return redirect(url_for('home'))

    @app.route('/admin/ensure/gfam')
    @roles_required('admin')
    def ensure_gfam():
        """Parses and stores the HGNC Gene Family Definitions"""
        url = FRAUNHOFER_RESOURCES + 'gfam_members.bel'
        celery = create_celery(current_app)
        task = celery.send_task('parse-url', args=[current_app.config.get(PYBEL_CONNECTION), url])
        flash('Queued task to parse HGNC Gene Families: {}'.format(task))
        return redirect(url_for('home'))

    @app.route('/admin/ensure/aetionomy')
    @roles_required('admin')
    def ensure_aetionomy():
        """Parses and stores the AETIONOMY resources from the Biological Model Store repository"""
        celery = create_celery(current_app)
        task = celery.send_task('parse-aetionomy', args=[current_app.config.get(PYBEL_CONNECTION)])
        flash('Queued task to parse the AETIONOMY folder: {}'.format(task))
        return redirect(url_for('home'))

    @app.route('/admin/ensure/selventa')
    @roles_required('admin')
    def ensure_selventa():
        """Parses and stores the Selventa resources from the Biological Model Store repository"""
        celery = create_celery(current_app)
        task = celery.send_task('parse-selventa', args=[current_app.config.get(PYBEL_CONNECTION)])
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
        return render_template('index.html')

    @app.route('/networks', methods=['GET', 'POST'])
    def view_networks():
        """Renders a page for the user to choose a network"""
        networks = get_networks_with_permission(api)

        return render_template(
            'network_list.html',
            networks=networks,
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

    @app.route('/explore/query/<int:query_id>', methods=['GET'])
    def view_explorer_query(query_id):
        """Renders a page for the user to explore a network"""
        query = manager.session.query(Query).get(query_id)

        return render_template('explorer.html', query=query)

    @app.route('/explore/network/<int:network_id>', methods=['GET'])
    @login_required
    def view_explore_network(network_id):
        """Renders a page for the user to explore a network"""

        query = Query.from_query_args(manager, current_user, network_id)
        manager.session.add(query)
        manager.session.commit()
        return redirect(url_for('view_explorer_query', query_id=query.id))

    @app.route('/summary/<network_id>')
    @login_required
    def view_summary(network_id):
        """Renders a page with the parsing errors for a given BEL script"""
        try:
            network = manager.get_network_by_id(network_id)
            graph = from_bytes(network.blob, check_version=current_app.config.get('PYBEL_DS_CHECK_VERSION'))
        except Exception as e:
            flash("Problem getting graph {}: ({}) {}".format(network_id, type(e), e), category='error')
            return redirect(url_for('view_networks'))

        return render_network_summary(network_id, graph)

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

    @app.route('/my_activity')
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

    @app.route('/logging', methods=['GET'])
    def view_logging():
        """Shows the logging"""
        return send_file(log_path)

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
