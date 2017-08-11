# -*- coding: utf-8 -*-

import logging
from itertools import chain

from flask import redirect, request
from flask_admin import Admin
from flask_admin.contrib.sqla.ajax import QueryAjaxModelLoader
from flask_admin.model.ajax import DEFAULT_PAGE_SIZE
from flask_security import url_for_security, current_user
from sqlalchemy import or_

from pybel.manager.models import (
    Edge,
    Node,
    Citation,
    Evidence,
    Author
)
from pybel.manager.models import Network, Namespace, Annotation
from .admin_utils import (
    ModelViewBase,
    ModelView,
    UserView,
    NetworkView,
    NodeView,
    CitationView,
    EdgeView,
    EvidenceView,
    ExperimentView
)
from .application_utils import get_api, get_manager, get_scai_role
from .models import (
    Report,
    Experiment,
    Role,
    User,
    Query,
    Assembly,
    Project,
    EdgeVote,
    EdgeComments
)
from .utils import list_public_networks

log = logging.getLogger(__name__)


def build_admin_service(app):
    """Adds Flask-Admin database front-end
    
    :param flask.Flask app: A PyBEL web app
    :rtype flask_admin.Admin
    """
    manager = get_manager(app)
    api = get_api(app)

    admin = Admin(app, template_mode='bootstrap3')

    admin.add_view(UserView(User, manager.session))
    admin.add_view(ModelView(Role, manager.session))
    admin.add_view(ModelView(Namespace, manager.session))
    admin.add_view(ModelView(Annotation, manager.session))
    admin.add_view(NetworkView(Network, manager.session))
    admin.add_view(NodeView(Node, manager.session))
    admin.add_view(EdgeView(Edge, manager.session))
    admin.add_view(CitationView(Citation, manager.session))
    admin.add_view(EvidenceView(Evidence, manager.session))
    admin.add_view(ModelView(Author, manager.session))
    admin.add_view(ModelView(Report, manager.session))
    admin.add_view(ExperimentView(Experiment, manager.session))
    admin.add_view(ModelView(Query, manager.session))
    admin.add_view(ModelView(Assembly, manager.session))
    admin.add_view(ModelView(EdgeVote, manager.session))
    admin.add_view(ModelView(EdgeComments, manager.session))

    class NetworkAjaxModelLoader(QueryAjaxModelLoader):
        def __init__(self):
            super(NetworkAjaxModelLoader, self).__init__('networks', manager.session, Network, fields=[Network.name])

            self.scai_role = get_scai_role(app)

        def get_list(self, term, offset=0, limit=DEFAULT_PAGE_SIZE):
            """Overrides get_list to be lazy and tricky about only getting current user's networks"""
            query = self.session.query(self.model)

            filters = (field.ilike(u'%%%s%%' % term) for field in self._cached_fields)
            query = query.filter(or_(*filters))

            if not current_user.admin:
                network_chain = chain(
                    current_user.get_owned_networks(),
                    current_user.get_shared_networks(),
                    list_public_networks(api),
                )

                allowed_network_ids = {
                    network.id
                    for network in network_chain
                }

                if current_user.has_role('scai'):
                    for user in self.scai_role.users:
                        for network in user.get_owned_networks():
                            allowed_network_ids.add(network.id)

                if not allowed_network_ids:  # If the current user doesn't have any networks, then return nothing
                    return []

                query = query.filter(Network.id.in_(allowed_network_ids))

            return query.offset(offset).limit(limit).all()

    class ProjectView(ModelViewBase):
        """Special view to allow users of given projects to manage them"""

        def is_accessible(self):
            """Checks the current user is logged in"""
            return current_user.is_authenticated

        def inaccessible_callback(self, name, **kwargs):
            """redirect to login page if user doesn't have access"""
            return redirect(url_for_security('login', next=request.url))

        def get_query(self):
            """Only show projects that the user is part of"""
            parent_query = super(ProjectView, self).get_query()

            if current_user.admin:
                return parent_query

            current_projects = {
                project.id
                for project in current_user.projects
            }

            return parent_query.filter(Project.id.in_(current_projects))

        def on_model_change(self, form, model, is_created):
            """Hacky - automatically add user when they create a project"""
            model.users.append(current_user)

        form_ajax_refs = {
            'networks': NetworkAjaxModelLoader()
        }

    admin.add_view(ProjectView(Project, manager.session))

    return admin
