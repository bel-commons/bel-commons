# -*- coding: utf-8 -*-

"""
Module that contains the command line app

Why does this file exist, and why not put this in __main__?
You might be tempted to import things from __main__ later, but that will cause
problems--the code will get executed twice:
 - When you run `python3 -m pybel_tools` python will execute
   ``__main__.py`` as a script. That means there won't be any
   ``pybel_tools.__main__`` in ``sys.modules``.
 - When you import __main__ it will get executed again (as a module) because
   there's no ``pybel_tools.__main__`` in ``sys.modules``.
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
import gunicorn.app.base
from flask_security import SQLAlchemyUserDatastore
from pybel.constants import PYBEL_CONNECTION, PYBEL_DATA_DIR, get_cache_connection
from pybel.manager import Manager
from pybel.manager.models import Base, Network
from pybel.utils import get_version as pybel_version
from pybel_tools.utils import enable_cool_mode, get_version as pybel_tools_get_version

from .analysis_service import analysis_blueprint
from .application import create_application
from .bms_service import bms_blueprint
from .constants import CHARLIE_EMAIL
from .curation_service import curation_blueprint
from .database_service import api_blueprint
from .external_services import belief_blueprint, external_blueprint
from .main_service import build_main_service
from .models import Experiment, Project, Report, Role, User
from .parser_async_service import parser_async_blueprint
from .parser_endpoint import build_parser_service
from .utils import iterate_user_strings

log = logging.getLogger('pybel_web')

user_dump_path = os.path.join(PYBEL_DATA_DIR, 'users.tsv')


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


class StandaloneApplication(gunicorn.app.base.BaseApplication):
    def __init__(self, app, options=None):
        self.options = options or {}
        self.application = app
        super(StandaloneApplication, self).__init__()

    def load_config(self):
        for key, value in self.options.items():
            if key in self.cfg.settings and value is not None:
                self.cfg.set(key.lower(), value)

    def load(self):
        return self.application


_config_map = {
    'local': 'pybel_web.config.LocalConfig',
    'test': 'pybel_web.config.TestConfig',
    'prod': 'pybel_web.config.ProductionConfig'
}


@click.group(help="PyBEL-Tools Command Line Interface on {}\n with PyBEL v{}".format(sys.executable, pybel_version()))
@click.version_option()
def main():
    """PyBEL Tools Command Line Interface"""


@main.command()
@click.option('--host', default='0.0.0.0', help='Flask host. Defaults to 0.0.0.0')
@click.option('--port', type=int, default=5000, help='Flask port. Defaults to 5000')
@click.option('--default-config', type=click.Choice(['local', 'test', 'prod']),
              help='Use different default config object')
@click.option('-v', '--debug', count=True, help="Turn on debugging. More v's, more debugging")
@click.option('--config', type=click.File('r'), help='Additional configuration in a JSON file')
@click.option('--with-gunicorn', is_flag=True)
@click.option('-w', '--workers', type=int, default=number_of_workers(), help='Number of workers')
def run(host, port, default_config, debug, config, with_gunicorn, workers):
    """Runs PyBEL Web"""
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
        **config_dict
    )

    build_main_service(app)
    app.register_blueprint(curation_blueprint)
    app.register_blueprint(parser_async_blueprint)
    app.register_blueprint(api_blueprint)
    app.register_blueprint(analysis_blueprint)
    app.register_blueprint(belief_blueprint)
    app.register_blueprint(external_blueprint)

    if app.config.get('BMS_BASE'):
        app.register_blueprint(bms_blueprint)

    if app.config.get('PYBEL_WEB_PARSER_API'):
        build_parser_service(app)

    if 'BEL4IMOCEDE_DATA_PATH' in os.environ:
        from . import mozg_service
        app.register_blueprint(mozg_service.mozg_blueprint)

    log.info('Done building %s in %.2f seconds', app, time.time() - t)

    if with_gunicorn:
        gunicorn_app = StandaloneApplication(app, {
            'bind': '%s:%s' % (host, port),
            'workers': workers,
        })
        gunicorn_app.run()

    else:
        app.run(host=host, port=port)


@main.command()
@click.option('-c', '--concurrency', type=int, default=1)
@click.option('--debug', default='INFO', type=click.Choice(['INFO', 'DEBUG']))
def worker(concurrency, debug):
    """Runs the celery worker"""
    from .celery_worker import app
    from celery.bin import worker

    pybel_worker = worker.worker(app=app.celery)

    options = {
        'broker': 'amqp://guest:guest@localhost:5672//',
        'loglevel': debug,
        'traceback': True,
        'concurrency': concurrency
    }

    pybel_worker.run(**options)


@main.group()
@click.option('-c', '--connection', help='Cache connection. Defaults to {}'.format(get_cache_connection()))
@click.option('--config', type=click.File('r'), help='Specify configuration JSON file')
@click.pass_context
def manage(ctx, connection, config):
    """Manage database"""
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
    """Creates the database"""
    manager.create_all()


@manage.command()
@click.option('-f', '--file', type=click.File('r'), default=user_dump_path, help='Input user/role file')
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
@click.option('-u', '--user-dump', type=click.File('w'), default=user_dump_path, help='Place to dump user data')
@click.pass_obj
def drop(manager, yes, user_dump):
    """Drops database"""
    if yes or click.confirm('Drop database at {}?'.format(manager.connection)):
        click.echo('Dumping users to {}'.format(user_dump_path))
        for s in iterate_user_strings(manager):
            click.echo(s, file=user_dump)
        click.echo('Done dumping users')
        click.echo('Dropping database')
        manager.drop_all()
        click.echo('Done dropping database')


@manage.command()
@click.pass_obj
def sanitize_reports(manager):
    """Adds charlie as the owner of all non-reported graphs"""
    ds = SQLAlchemyUserDatastore(manager, User, Role)
    user = ds.find_user(email=CHARLIE_EMAIL)
    click.echo('Adding {} as owner of unreported uploads'.format(user))

    for network in manager.session.query(Network):
        if network.report is not None:
            continue

        report = Report(
            network=network,
            user=user
        )

        manager.session.add(report)

        click.echo('Sanitizing {}'.format(network))

    manager.session.commit()


@manage.group()
def user():
    """Manage users"""


@user.command()
@click.pass_obj
def ls(manager):
    """Lists all users"""
    for s in iterate_user_strings(manager):
        click.echo(s)


@user.command()
@click.argument('email')
@click.argument('password')
@click.option('-a', '--admin', is_flag=True, help="Add admin role")
@click.option('-s', '--scai', is_flag=True, help="Add SCAI role")
@click.pass_obj
def add(manager, email, password, admin, scai):
    """Creates a new user"""
    ds = SQLAlchemyUserDatastore(manager, User, Role)
    try:
        u = ds.create_user(email=email, password=password, confirmed_at=datetime.datetime.now())

        if admin:
            ds.add_role_to_user(u, 'admin')

        if scai:
            ds.add_role_to_user(u, 'scai')

        ds.commit()
    except:
        log.exception("Couldn't create user")


@user.command()
@click.argument('email')
@click.pass_obj
def rm(manager, email):
    """Deletes a user"""
    ds = SQLAlchemyUserDatastore(manager, User, Role)
    u = ds.find_user(email=email)
    ds.delete_user(u)
    ds.commit()


@user.command()
@click.argument('email')
@click.pass_obj
def make_admin(manager, email):
    """Makes a given user an admin"""
    ds = SQLAlchemyUserDatastore(manager, User, Role)
    try:
        ds.add_role_to_user(email, 'admin')
        ds.commit()
    except:
        log.exception("Couldn't make admin")


@user.command()
@click.argument('email')
@click.argument('role')
@click.pass_obj
def add_role(manager, email, role):
    """Adds a role to a user"""
    ds = SQLAlchemyUserDatastore(manager, User, Role)
    try:
        ds.add_role_to_user(email, role)
        ds.commit()
    except:
        log.exception("Couldn't add role")


@manage.group()
def role():
    """Manage roles"""


@role.command()
@click.argument('name')
@click.option('-d', '--description')
@click.pass_obj
def add(manager, name, description):
    """Creates a new role"""
    ds = SQLAlchemyUserDatastore(manager, User, Role)
    try:
        ds.create_role(name=name, description=description)
        ds.commit()
    except:
        log.exception("Couldn't create role")


@role.command()
@click.argument('name')
@click.pass_obj
def rm(manager, name):
    """Deletes a user"""
    ds = SQLAlchemyUserDatastore(manager, User, Role)
    u = ds.find_role(name)
    if u:
        ds.delete(u)
        ds.commit()


@role.command()
@click.pass_obj
def ls(manager):
    """Lists roles"""
    for r in manager.session.query(Role).all():
        click.echo('{}\t{}'.format(r.name, r.description))


@manage.group()
def projects():
    """Manage projects"""


@projects.command()
@click.pass_obj
def ls(manager):
    """Lists projects"""
    for project in manager.session.query(Project).all():
        click.echo('{}\t{}'.format(project.name, ','.join(map(str, project.users))))


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
def dropall(manager):
    """Drops all experiments"""
    if click.confirm('Drop all experiments at {}?'.format(manager.connection)):
        manager.session.query(Experiment).delete()


if __name__ == '__main__':
    main()
