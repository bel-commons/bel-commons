# -*- coding: utf-8 -*-

"""
Module that contains the command line app

Why does this file exist, and why not put this in __main__?
You might be tempted to import things from __main__ later, but that will cause
problems--the code will get executed twice:
 - When you run `python3 -m pybel_web` python will execute
   ``__main__.py`` as a script. That means there won't be any
   ``pybel_web.__main__`` in ``sys.modules``.
 - When you import __main__ it will get executed again (as a module) because
   there's no ``pybel_web.__main__`` in ``sys.modules``.
Also see (1) from http://click.pocoo.org/5/setuptools/#setuptools-integration
"""

from __future__ import print_function

import datetime
import json
import logging
import multiprocessing
import os
import sys
import time

import click
from flask_security import SQLAlchemyUserDatastore

import pybel
from pybel.constants import PYBEL_CONNECTION, get_cache_connection
from pybel.manager import Manager
from pybel.manager.models import Network
from pybel.utils import get_version as pybel_version
from pybel_tools.utils import enable_cool_mode, get_version as pybel_tools_get_version
from .analysis_service import experiment_blueprint
from .application import create_application
from .bms_service import bms_blueprint
from .constants import CHARLIE_EMAIL
from .curation_service import curation_blueprint
from .database_service import api_blueprint
from .external_services import belief_blueprint, external_blueprint
from .main_service import ui_blueprint
from .manager_utils import insert_graph
from .models import Assembly, Base, EdgeComment, EdgeVote, Experiment, Omic, Project, Query, Report, Role, User
from .parser_endpoint import build_parser_service
from .parser_service import parser_blueprint
from .utils import iterate_user_strings

log = logging.getLogger('pybel_web')


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


def number_of_workers():
    return (multiprocessing.cpu_count() * 2) + 1


def make_gunicorn_app(app, host, port, workers):
    """Make a GUnicorn App

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


_config_map = {
    'local': 'pybel_web.config.LocalConfig',
    'test': 'pybel_web.config.TestConfig',
    'prod': 'pybel_web.config.ProductionConfig'
}

_main_help = "PyBEL-Tools Command Line Interface on {}\n with " \
             "PyBEL v{} and PyBEL Tools v{}".format(sys.executable,
                                                    pybel_version(),
                                                    pybel_tools_get_version())


@click.group(help=_main_help)
@click.version_option()
def main():
    pass


@main.command()
@click.option('--host', default='0.0.0.0', help='Flask host. Defaults to 0.0.0.0')
@click.option('--port', type=int, default=5000, help='Flask port. Defaults to 5000')
@click.option('--default-config', type=click.Choice(['local', 'test', 'prod']),
              help='Use different default config object')
@click.option('-v', '--debug', count=True, help="Turn on debugging. More v's, more debugging")
@click.option('--config', type=click.File('r'), help='Additional configuration in a JSON file')
@click.option('-e', '--examples', is_flag=True, help='Ensure examples')
@click.option('--with-gunicorn', is_flag=True)
@click.option('-w', '--workers', type=int, default=number_of_workers(), help='Number of workers')
def run(host, port, default_config, debug, config, examples, with_gunicorn, workers):
    """Run the web application"""
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

    config_dict = json.load(config) if config is not None else {}

    app = create_application(
        config_location=_config_map.get(default_config),
        examples=examples,
        **config_dict
    )

    app.register_blueprint(ui_blueprint)
    app.register_blueprint(curation_blueprint)
    app.register_blueprint(parser_blueprint)
    app.register_blueprint(api_blueprint)
    app.register_blueprint(experiment_blueprint)
    app.register_blueprint(belief_blueprint)
    app.register_blueprint(external_blueprint)

    if app.config.get('BMS_BASE'):
        app.register_blueprint(bms_blueprint)

    if app.config.get('PYBEL_WEB_PARSER_API'):
        build_parser_service(app)

    if 'BEL4IMOCEDE_DATA_PATH' in os.environ:
        try:
            from . import mozg_service
        except RuntimeError:
            log.exception('missing mozg service required data')
        else:
            app.register_blueprint(mozg_service.mozg_blueprint)

    log.info('Done building %s in %.2f seconds', app, time.time() - t)

    if with_gunicorn:
        gunicorn_app = make_gunicorn_app(app, host, port, workers)
        gunicorn_app.run()

    else:
        app.run(host=host, port=port)


@main.command()
@click.option('-c', '--concurrency', type=int, default=1)
@click.option('--debug', default='INFO', type=click.Choice(['INFO', 'DEBUG']))
def worker(concurrency, debug):
    """Run the celery worker"""
    from .celery_worker import celery
    from celery.bin import worker

    pybel_worker = worker.worker(app=celery)

    pybel_worker.run(
        broker='amqp://guest:guest@localhost:5672//',
        loglevel=debug,
        traceback=True,
        concurrency=concurrency
    )


@main.group()
@click.option('-c', '--connection', help='Cache connection. Defaults to {}'.format(get_cache_connection()))
@click.option('--config', type=click.File('r'), help='Specify configuration JSON file')
@click.pass_context
def manage(ctx, connection, config):
    """Manage the database"""
    if config:
        file = json.load(config)
        ctx.obj = Manager.ensure(file.get(PYBEL_CONNECTION, get_cache_connection()))
    else:
        ctx.obj = Manager.ensure(connection)

    Base.metadata.bind = ctx.obj.engine
    Base.query = ctx.obj.session.query_property()


@manage.command()
@click.pass_obj
def setup(manager):
    """Create the database"""
    manager.create_all()


@manage.command()
@click.option('-f', '--file', type=click.File('r'), default=sys.stdout, help='Input user/role file')
@click.pass_obj
def load(manager, file):
    """Load dumped stuff for loading later (in lieu of having proper migrations)"""
    ds = SQLAlchemyUserDatastore(manager, User, Role)

    for line in file:

        line = line.strip().split('\t')
        email, password = line[:2]
        u = ds.find_user(email=email)

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
    """Drop the database"""
    if yes or click.confirm('Drop database at {}?'.format(manager.connection)):
        click.echo('Dumping users to {}'.format(user_dump))
        for s in iterate_user_strings(manager):
            click.echo(s, file=user_dump)
        click.echo('Done dumping users')
        click.echo('Dropping database')
        manager.drop_all()
        click.echo('Done dropping database')


@manage.command()
@click.pass_obj
def sanitize_reports(manager):
    """Add charlie as the owner of all non-reported graphs"""
    ds = SQLAlchemyUserDatastore(manager, User, Role)
    user_ = ds.find_user(email=CHARLIE_EMAIL)
    click.echo('Adding {} as owner of unreported uploads'.format(user_))

    for network_ in manager.session.query(Network):
        if network_.report is not None:
            continue

        report = Report(
            network=network_,
            user=user_
        )

        manager.session.add(report)

        click.echo('Sanitizing {}'.format(network_))

    manager.session.commit()


@manage.group()
def networks():
    """Parse, upload, and manage networks"""


@networks.command()
@click.option('-p', '--path')
@click.option('--public', is_flag=True)
@click.pass_obj
def parse(manager, path, public):
    """Parses a BEL script and uploads"""
    enable_cool_mode()
    t = time.time()
    graph = pybel.from_path(path, manager=manager)
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
        graph = pybel.from_pickle(path)
        insert_graph(manager, graph)


@manage.group()
def users():
    """Create and manage users"""


@users.command()
@click.pass_obj
def ls(manager):
    """Lists all users"""
    for s in iterate_user_strings(manager):
        click.echo(s)


@users.command()
@click.argument('email')
@click.argument('password')
@click.option('-a', '--admin', is_flag=True, help="Add admin role")
@click.option('-s', '--scai', is_flag=True, help="Add SCAI role")
@click.pass_obj
def add(manager, email, password, admin, scai):
    """Creates a new user"""
    ds = SQLAlchemyUserDatastore(manager, User, Role)
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
def rm(manager, email):
    """Deletes a user"""
    ds = SQLAlchemyUserDatastore(manager, User, Role)
    user_ = ds.find_user(email=email)
    ds.delete_user(user_)
    ds.commit()


@users.command()
@click.argument('email')
@click.pass_obj
def make_admin(manager, email):
    """Makes a given user an admin"""
    ds = SQLAlchemyUserDatastore(manager, User, Role)
    try:
        ds.add_role_to_user(email, 'admin')
        ds.commit()
    except Exception:
        log.exception("Couldn't make admin")


@users.command()
@click.argument('email')
@click.argument('role')
@click.pass_obj
def add_role(manager, email, role):
    """Adds a role to a user"""
    ds = SQLAlchemyUserDatastore(manager, User, Role)
    try:
        ds.add_role_to_user(email, role)
        ds.commit()
    except Exception:
        log.exception("Couldn't add role")


@manage.group()
def roles():
    """Manage roles"""


@roles.command()
@click.argument('name')
@click.option('-d', '--description')
@click.pass_obj
def add(manager, name, description):
    """Creates a new role"""
    ds = SQLAlchemyUserDatastore(manager, User, Role)
    try:
        ds.create_role(name=name, description=description)
        ds.commit()
    except Exception:
        log.exception("Couldn't create role")


@roles.command()
@click.argument('name')
@click.pass_obj
def rm(manager, name):
    """Deletes a user"""
    ds = SQLAlchemyUserDatastore(manager, User, Role)
    user = ds.find_role(name)
    if user:
        ds.delete(user)
        ds.commit()


@roles.command()
@click.pass_obj
def ls(manager):
    """Lists roles"""
    click.echo('\t'.join(('id', 'name', 'description')))
    for role in manager.session.query(Role).all():
        click.echo('\t'.join((str(role.id), role.name, role.description)))


@manage.group()
def projects():
    """Manage projects"""


@projects.command()
@click.pass_obj
def ls(manager):
    """Lists projects"""
    click.echo('\t'.join(('id', 'name', 'users')))
    for project in manager.session.query(Project).all():
        click.echo('\t'.join((str(project.id), project.name, ','.join(map(str, project.users)))))


@projects.command()
@click.option('-o', '--output', type=click.File('w'), default=sys.stdout)
@click.pass_obj
def export(manager, output):
    json.dump(
        [
            project.to_json()
            for project in manager.session.query(Project).all()
        ],
        output
    )


@manage.group()
def experiments():
    """Manage experiments"""


@experiments.command()
@click.pass_obj
def ls(manager):
    """Lists experiments"""
    click.echo('\t'.join(('id', 'type', 'description', 'completed')))
    for experiment in manager.session.query(Experiment).order_by(Experiment.created.desc()).all():
        click.echo('\t'.join(map(str, (experiment.id, experiment.type, experiment.description, experiment.completed))))


@experiments.command()
@click.option('--experiment-id', type=int)
@click.option('-y', '--yes', is_flag=True)
@click.pass_obj
def drop(manager, experiment_id, yes):
    """Drops either a single or all Experiment models"""
    if experiment_id:
        manager.session.query(Experiment).get(experiment_id).delete()
        manager.session.commit()

    elif yes or click.confirm('Drop all Experiment models at {}?'.format(manager.connection)):
        manager.session.query(Experiment).delete()
        manager.session.commit()


@manage.group()
def omics():
    """Manages -omics data input for experiments"""


@omics.command()
@click.pass_obj
def ls(manager):
    """Lists -omics data sets"""
    click.echo('\t'.join(('id', 'name', 'description')))
    for omic in manager.session.query(Omic).all():
        click.echo('\t'.join((str(omic.id), omic.source_name, omic.description)))


@omics.command()
@click.option('--omic-id', type=int)
@click.option('-y', '--yes', is_flag=True)
@click.pass_obj
def drop(manager, omic_id, yes):
    """Drops either a single or all Omics models"""
    if omic_id:
        manager.session.query(Omic).get(omic_id).delete()
        manager.session.commit()

    elif yes or click.confirm('Drop all Omic models at {}?'.format(manager.connection)):
        manager.session.query(Omic).delete()
        manager.session.commit()


@manage.group()
def queries():
    """Manages queries"""


@queries.command()
@click.option('-l', '--limit', type=int, default=10, help='Limit, defaults to 10.')
@click.option('-o', '--offset', type=int)
@click.pass_obj
def ls(manager, limit, offset):
    """Lists queries"""
    click.echo('\t'.join(('id', 'created', 'assembly')))

    q = manager.session.query(Query).order_by(Query.created.desc())

    if limit:
        q = q.limit(limit)

    if offset:
        q = q.offset(offset)

    for query in q.all():
        click.echo('\t'.join(map(str, (query.id, query.created, query.assembly))))


@manage.command()
@click.pass_obj
def summarize(manager):
    """Summarizes the contents of the database"""
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


@manage.group()
def examples():
    """Load examples"""


@examples.command()
@click.option('-p', '--permutations', type=int, default=25)
@click.pass_obj
def load(manager, permutations):
    """Load omics, networks, and experiments"""
    from .resources.load_omics import main as load_omics_main
    from .resources.load_networks import main as load_networks_main
    from .resources.load_experiments import main as load_experiments_main

    set_debug(logging.INFO)

    load_omics_main(manager)
    load_networks_main(manager)
    load_experiments_main(manager, permutations=permutations)


@examples.command()
@click.pass_obj
def load_omics(manager):
    """Load omics"""
    from .resources.load_omics import main
    set_debug(logging.INFO)
    main(manager)


@examples.command()
@click.pass_obj
def load_networks(manager):
    """Load networks"""
    from .resources.load_networks import main
    set_debug(logging.INFO)
    main(manager)


@examples.command()
@click.option('-p', '--permutations', type=int, default=25)
@click.pass_obj
def load_experiments(manager, permutations):
    """Load experiments"""
    from .resources.load_experiments import main
    set_debug(logging.INFO)
    main(manager, permutations=permutations)


if __name__ == '__main__':
    main()
