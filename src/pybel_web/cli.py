# -*- coding: utf-8 -*-

"""A command line application for managing BEL Commons.

Run with ``python -m pybel_web`` or simply as ``pybel-web``.
"""

import datetime
import json
import logging
import multiprocessing
import os
import sys
import time

import click
from pybel_tools.utils import enable_cool_mode, get_version as pybel_tools_get_version

from pybel import from_path, from_pickle
from pybel.constants import get_cache_connection
from pybel.manager.models import Network
from pybel.utils import get_version as pybel_version
from .application import create_application
from .constants import PYBEL_WEB_REGISTER_EXAMPLES, PYBEL_WEB_USE_PARSER_API, get_admin_email
from .database_service import api_blueprint
from .main_service import ui_blueprint
from .manager import WebManager
from .manager_utils import insert_graph
from .models import Assembly, EdgeComment, EdgeVote, Experiment, Omic, Project, Query, Report, Role, User
from .views import (
    build_parser_service, curation_blueprint, experiment_blueprint, help_blueprint, receiving_blueprint,
    reporting_blueprint, uploading_blueprint,
)

log = logging.getLogger('pybel_web')


def _iterate_user_strings(manager_: WebManager):
    """Iterate over strings to print describing users.

    :param manager_:
    :rtype: iter[str]
    """
    for user in manager_.session.query(User).all():
        yield '{email}\t{password}\t{roles}\t{name}'.format(
            email=user.email,
            password=user.password,
            roles=','.join(sorted(r.name for r in user.roles)),
            name=(user.name if user.name else '')
        )


def set_debug(level):
    logging.basicConfig(level=level, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s", datefmt='%H:%M:%S')

    pybel_log = logging.getLogger('pybel')
    pybel_log.setLevel(level)

    pbt_log = logging.getLogger('pybel_tools')
    pbt_log.setLevel(level)

    pbw_log = logging.getLogger('pybel_web')
    pbw_log.setLevel(level)

    logging.getLogger('bio2bel_hgnc').setLevel(level)
    logging.getLogger('bio2bel_mirtarbase').setLevel(level)
    logging.getLogger('bio2bel_chebi').setLevel(level)


def set_debug_param(debug):
    if debug == 1:
        set_debug(logging.INFO)
    elif debug == 2:
        set_debug(logging.DEBUG)

    logging.getLogger('passlib.registry').setLevel(logging.WARNING)


def number_of_workers():
    return (multiprocessing.cpu_count() * 2) + 1


def make_gunicorn_app(app, host, port, workers):
    """Make a GUnicorn App.

    :param flask.Flask app:
    :param str host:
    :param int port:
    :param int workers:
    :rtype: gunicorn.app.base.BaseApplication
    """
    import gunicorn.app.base

    class StandaloneApplication(gunicorn.app.base.BaseApplication):
        def __init__(self, options=None):
            self.options = options or {}
            self.application = app
            super(StandaloneApplication, self).__init__()

        def load_config(self):
            for key, value in self.options.items():
                if key in self.cfg.settings and value is not None:
                    self.cfg.set(key.lower(), value)

        def load(self):
            return self.application

    return StandaloneApplication({
        'bind': '%s:%s' % (host, port),
        'workers': workers,
    })


_main_help = "BEL Commons Command Line Interface on {}\n with " \
             "PyBEL v{} and PyBEL Tools v{}".format(sys.executable,
                                                    pybel_version(),
                                                    pybel_tools_get_version())


@click.group(help=_main_help)
@click.version_option()
def main():
    """Run the PyBEL-Web command line interface."""


@main.command()
@click.option('--host', default='0.0.0.0', help='Flask host. Defaults to 0.0.0.0')
@click.option('--port', type=int, default=5000, help='Flask port. Defaults to 5000')
@click.option('-v', '--debug', count=True, help="Turn on debugging. More v's, more debugging")
@click.option('--config', type=click.File('r'), help='Additional configuration in a JSON file')
@click.option('--enable-parser', is_flag=True)
@click.option('-e', '--ensure-examples', is_flag=True, help='Ensure examples')
@click.option('--with-gunicorn', is_flag=True)
@click.option('-w', '--workers', type=int, default=number_of_workers(), help='Number of workers')
def run(host, port, debug, config, enable_parser, ensure_examples, with_gunicorn, workers):
    """Run the web application."""
    set_debug_param(debug)
    if debug < 3:
        enable_cool_mode()

    log.info('Running PyBEL v%s', pybel_version())
    log.info('Running PyBEL Tools v%s', pybel_tools_get_version())

    if host is not None:
        log.info('Running on host: %s', host)

    if port is not None:
        log.info('Running on port: %d', port)

    t = time.time()

    config = json.load(config) if config is not None else {}
    config.setdefault(PYBEL_WEB_REGISTER_EXAMPLES, ensure_examples)

    app = create_application(**config)

    app.register_blueprint(ui_blueprint)
    app.register_blueprint(curation_blueprint)
    app.register_blueprint(uploading_blueprint)
    app.register_blueprint(help_blueprint)
    app.register_blueprint(api_blueprint)
    app.register_blueprint(experiment_blueprint)
    app.register_blueprint(reporting_blueprint)
    app.register_blueprint(receiving_blueprint)

    if enable_parser or app.config.get(PYBEL_WEB_USE_PARSER_API):
        build_parser_service(app)

    log.info('Done building %s in %.2f seconds', app, time.time() - t)

    if with_gunicorn:
        gunicorn_app = make_gunicorn_app(app, host, port, workers)
        gunicorn_app.run()
    else:
        app.run(host=host, port=port)


@main.command()
@click.option('-c', '--concurrency', type=int, default=1)
@click.option('-b', '--broker', default='amqp://guest:guest@localhost:5672//')
@click.option('--debug', default='INFO', type=click.Choice(['INFO', 'DEBUG']))
def worker(concurrency, broker, debug):
    """Run the celery worker."""
    from .celery_worker import celery
    from celery.bin import worker

    pybel_worker = worker.worker(app=celery)
    pybel_worker.run(
        broker=broker,
        loglevel=debug,
        traceback=True,
        concurrency=concurrency
    )


@main.group()
@click.option('-c', '--connection', help='Cache connection. Defaults to {}'.format(get_cache_connection()))
@click.pass_context
def manage(ctx, connection):
    """Manage the database."""
    ctx.obj = WebManager(connection=connection)
    ctx.obj.bind()
    ctx.obj.create_all()


@manage.command()
@click.option('-f', '--file', type=click.File('r'), default=sys.stdout, help='Input user/role file')
@click.pass_obj
def load(manager: WebManager, file):
    """Load dumped stuff for loading later (in lieu of having proper migrations)."""
    ds = manager.user_datastore

    for line in file:
        line = line.strip().split('\t')
        email, password = line[:2]
        u = manager.user_datastore.find_user(email=email)

        if not u:
            u = ds.create_user(
                email=email,
                password=password,

                confirmed_at=datetime.datetime.now()
            )

            if 4 <= len(line):
                u.name = line[3]

            click.echo('added {}'.format(u))
            ds.commit()

            if 3 <= len(line):
                roles = line[2].strip().split(',')
                for role_name in roles:
                    r = ds.find_or_create_role(name=role_name)
                    ds.add_role_to_user(u, r)

    ds.commit()


@manage.command()
@click.option('-y', '--yes', is_flag=True)
@click.option('-u', '--user-dump', type=click.File('w'), default=sys.stdout, help='Place to dump user data')
@click.pass_obj
def drop(manager, yes, user_dump):
    """Drop the database."""
    if yes or click.confirm('Drop database at {}?'.format(manager.connection)):
        click.echo('Dumping users to {}'.format(user_dump))
        for s in _iterate_user_strings(manager):
            click.echo(s, file=user_dump)
        click.echo('Done dumping users')
        click.echo('Dropping database')
        manager.drop_all()
        click.echo('Done dropping database')


@manage.command()
@click.pass_obj
def sanitize_reports(manager: WebManager):
    """Add admin as the owner of all non-reported graphs"""
    u = manager.user_datastore.find_user(email=get_admin_email())
    click.echo('Adding {} as owner of unreported uploads'.format(u))

    for n in manager.list_networks():
        if n.report is not None:
            continue

        report = Report(
            network=n,
            user=u
        )

        manager.session.add(report)

        click.echo('Sanitizing {}'.format(n))

    manager.session.commit()


@manage.group()
def networks():
    """Parse, upload, and manage networks."""


@networks.command()
@click.option('-p', '--path')
@click.option('--public', is_flag=True)
@click.pass_obj
def parse(manager, path, public):
    """Parses a BEL script and uploads."""
    enable_cool_mode()
    t = time.time()
    graph = from_path(path, manager=manager)
    log.info('parsing done in %.2f seconds', time.time() - t)
    insert_graph(manager, graph, public=public)


@networks.command()
@click.option('-p', '--path', help='A path or directory of gpickles to upload. Defaults to cwd {}'.format(os.getcwd()),
              default=os.getcwd())
@click.pass_obj
def upload(manager, path):
    """Upload a gpickle"""
    if os.path.isdir(path):
        from pybel_tools.io import iter_from_pickles_from_directory
        for graph in iter_from_pickles_from_directory(path):
            click.echo('inserting {}'.format(graph))
            insert_graph(manager, graph)

    else:
        graph = from_pickle(path)
        insert_graph(manager, graph)


@manage.group()
def users():
    """Manage users."""


@users.command()
@click.pass_obj
def ls(manager):
    """Lists all users"""
    for s in _iterate_user_strings(manager):
        click.echo(s)


@users.command()
@click.argument('email')
@click.argument('password')
@click.option('-a', '--admin', is_flag=True, help="Add admin role")
@click.option('-s', '--scai', is_flag=True, help="Add SCAI role")
@click.pass_obj
def add(manager: WebManager, email, password, admin, scai):
    """Create a new user."""
    ds = manager.user_datastore
    try:
        user = ds.create_user(email=email, password=password, confirmed_at=datetime.datetime.now())

        if admin:
            ds.add_role_to_user(user, 'admin')

        if scai:
            ds.add_role_to_user(user, 'scai')

        ds.commit()
    except Exception:
        log.exception("Couldn't create user")


@users.command()
@click.argument('email')
@click.pass_obj
def rm(manager: WebManager, email):
    """Delete a user."""
    ds = manager.user_datastore
    user_ = ds.find_user(email=email)
    ds.delete_user(user_)
    ds.commit()


@users.command()
@click.argument('email')
@click.pass_obj
def make_admin(manager: WebManager, email):
    """Make a given user an admin."""
    ds = manager.user_datastore
    try:
        ds.add_role_to_user(email, 'admin')
        ds.commit()
    except Exception:
        log.exception("Couldn't make admin")


@users.command()
@click.argument('email')
@click.argument('role')
@click.pass_obj
def add_role(manager: WebManager, email, role):
    """Add a role to a user."""
    ds = manager.user_datastore
    try:
        ds.add_role_to_user(email, role)
        ds.commit()
    except Exception:
        log.exception("Couldn't add role")


@manage.group()
def roles():
    """Manage roles."""


@roles.command()
@click.argument('name')
@click.option('-d', '--description')
@click.pass_obj
def add(manager: WebManager, name, description):
    """Create a new role."""
    ds = manager.user_datastore
    try:
        ds.create_role(name=name, description=description)
        ds.commit()
    except Exception:
        log.exception("Couldn't create role")


@roles.command()
@click.argument('name')
@click.pass_obj
def rm(manager: WebManager, name):
    """Delete a user."""
    ds = manager.user_datastore
    user = ds.find_role(name)
    if user:
        ds.delete(user)
        ds.commit()


@roles.command()
@click.pass_obj
def ls(manager):
    """List roles."""
    click.echo('\t'.join(('id', 'name', 'description')))
    for role in manager.session.query(Role).all():
        click.echo('\t'.join((str(role.id), role.name, role.description)))


@manage.group()
def projects():
    """Manage projects."""


@projects.command()
@click.pass_obj
def ls(manager):
    """List projects."""
    click.echo('\t'.join(('id', 'name', 'users')))
    for project in manager.session.query(Project).all():
        click.echo('\t'.join((str(project.id), project.name, ','.join(map(str, project.users)))))


@projects.command()
@click.option('-o', '--output', type=click.File('w'), default=sys.stdout)
@click.pass_obj
def export(manager, output):
    """Export projects as a JSON file."""
    json.dump(
        [
            project.to_json()
            for project in manager.session.query(Project).all()
        ],
        output
    )


@manage.group()
def queries():
    """Manage queries."""


@queries.command()
@click.option('--query-id', type=int)
@click.option('-y', '--yes', is_flag=True)
@click.pass_obj
def drop(manager, query_id, yes):
    """Drops either a single or all Experiment models"""
    if query_id:
        manager.session.query(query_id).get(query_id).delete()
        manager.session.commit()

    elif yes or click.confirm('Drop all Query models at {}?'.format(manager.connection)):
        manager.session.query(Query).delete()
        manager.session.commit()


@queries.command()
@click.option('-l', '--limit', type=int, default=10, help='Limit, defaults to 10.')
@click.option('-o', '--offset', type=int)
@click.pass_obj
def ls(manager, limit, offset):
    """List queries."""
    click.echo('\t'.join(('id', 'created', 'assembly')))

    q = manager.session.query(Query).order_by(Query.created.desc())

    if limit:
        q = q.limit(limit)

    if offset:
        q = q.offset(offset)

    for query in q.all():
        click.echo('\t'.join(map(str, (query.id, query.created, query.assembly))))


@manage.group()
def assemblies():
    """Manage assemblies."""


@assemblies.command()
@click.option('--assembly-id', type=int)
@click.option('-y', '--yes', is_flag=True)
@click.pass_obj
def drop(manager, assembly_id, yes):
    """Drops either a single or all Experiment models"""
    if assembly_id:
        manager.session.query(assembly_id).get(assembly_id).delete()
        manager.session.commit()

    elif yes or click.confirm('Drop all Assembly models at {}?'.format(manager.connection)):
        manager.session.query(Assembly).delete()
        manager.session.commit()


@manage.group()
def experiments():
    """Manage experiments."""


@experiments.command()
@click.pass_obj
def ls(manager):
    """List experiments."""
    click.echo('\t'.join(('id', 'type', 'omics description', 'completed')))
    for experiment in manager.session.query(Experiment).order_by(Experiment.created.desc()).all():
        click.echo('\t'.join(map(str, (
            experiment.id,
            experiment.type,
            experiment.omic.description,
            experiment.completed
        ))))


@experiments.command()
@click.option('--experiment-id', type=int)
@click.option('-y', '--yes', is_flag=True)
@click.pass_obj
def drop(manager, experiment_id, yes):
    """Drop either a single or all Experiment models."""
    if experiment_id:
        manager.session.query(Experiment).get(experiment_id).delete()
        manager.session.commit()

    elif yes or click.confirm('Drop all Experiment models at {}?'.format(manager.connection)):
        manager.session.query(Experiment).delete()
        manager.session.commit()


@manage.group()
def omics():
    """Manage -omics."""


@omics.command()
@click.pass_obj
def ls(manager):
    """List -omics data sets."""
    click.echo('\t'.join(('id', 'name', 'description')))
    for omic in manager.session.query(Omic).all():
        click.echo('\t'.join((str(omic.id), omic.source_name, omic.description)))


@omics.command()
@click.option('--omic-id', type=int)
@click.option('-y', '--yes', is_flag=True)
@click.pass_obj
def drop(manager, omic_id, yes):
    """Drop either a single or all -omics models."""
    if omic_id:
        manager.session.query(Omic).get(omic_id).delete()
        manager.session.commit()

    elif yes or click.confirm('Drop all Omic models at {}?'.format(manager.connection)):
        manager.session.query(Omic).delete()
        manager.session.commit()


@manage.command()
@click.pass_obj
def summarize(manager):
    """Summarize the contents of the database/"""
    click.echo('Users: {}'.format(manager.session.query(User).count()))
    click.echo('Roles: {}'.format(manager.session.query(Role).count()))
    click.echo('Projects: {}'.format(manager.session.query(Project).count()))
    click.echo('Reports: {}'.format(manager.session.query(Report).count()))
    click.echo('Assemblies: {}'.format(manager.session.query(Assembly).count()))
    click.echo('Votes: {}'.format(manager.session.query(EdgeVote).count()))
    click.echo('Comments: {}'.format(manager.session.query(EdgeComment).count()))
    click.echo('Queries: {}'.format(manager.session.query(Query).count()))
    click.echo('Omics: {}'.format(manager.session.query(Omic).count()))
    click.echo('Experiments: {}'.format(manager.session.query(Experiment).count()))


_default_bms_dir = os.path.join(os.path.expanduser('~'), 'dev', 'bms')
_default_omics_dir = os.path.join(os.path.expanduser('~'), 'dev', 'bel-commons-manuscript', 'data')

omics_dir = (
    _default_omics_dir
    if os.path.exists(_default_omics_dir)
    else os.environ.get('BEL_COMMONS_EXAMPLES_OMICS_DATA_DIR')
)
bms_dir = (
    _default_bms_dir
    if os.path.exists(_default_bms_dir)
    else os.environ.get('BMS_BASE')
)

if omics_dir is not None or bms_dir is not None:
    @manage.group()
    def examples():
        """Load examples"""


    if omics_dir is not None:
        @examples.command(help='Load omics from {}'.format(omics_dir))
        @click.option('-r', '--reload', is_flag=True, help='Reload')
        @click.pass_obj
        def load_omics(manager, reload):
            """Load omics."""
            from .resources.load_omics import main
            set_debug(logging.INFO)
            main(manager, reload=reload)

    if bms_dir is not None:
        @examples.command()
        @click.option('--skip-cbn', is_flag=True)
        @click.pass_obj
        def load_networks(manager, skip_cbn):
            """Load networks."""
            from .resources.load_networks import load_bms, load_cbn
            set_debug(logging.INFO)
            load_bms(manager)

            if not skip_cbn:
                load_cbn(manager)

    if omics_dir is not None and bms_dir is not None:
        @examples.command()
        @click.option('--reload-omics', is_flag=True, help='Reload')
        @click.option('-p', '--permutations', type=int, help='Number of permutations to run. Defaults to 25.',
                      default=25)
        @click.option('--skip-bio2bel', is_flag=True)
        @click.option('--skip-cbn', is_flag=True)
        @click.pass_obj
        def load(manager, reload_omics, permutations, skip_bio2bel, skip_cbn):
            """Load omics, networks, and experiments."""
            from .resources.load_omics import main as load_omics_main
            from .resources.load_networks import load_bms, load_bio2bel, load_cbn
            from .resources.load_experiments import main as load_experiments_main

            set_debug(logging.INFO)

            load_omics_main(manager, reload=reload_omics)
            load_bms(manager)
            load_experiments_main(manager, permutations=permutations)

            if not skip_bio2bel:
                load_bio2bel(manager)

            if not skip_cbn:
                load_cbn(manager)


        @examples.command()
        @click.option('-p', '--permutations', type=int, help='Number of permutations to run. Defaults to 25.',
                      default=25)
        @click.pass_obj
        def load_experiments(manager, permutations):
            """Load experiments."""
            from .resources.load_experiments import main
            set_debug(logging.INFO)
            main(manager, permutations=permutations)


@manage.command()
@click.pass_obj
def wasteland(manager):
    """Drop a lot"""
    manager.session.query(Experiment).delete()
    manager.session.commit()
    manager.session.query(Query).delete()
    manager.session.commit()
    manager.session.query(Assembly).delete()
    manager.session.commit()
    manager.session.query(Network).delete()
    manager.session.commit()


if __name__ == '__main__':
    main()
