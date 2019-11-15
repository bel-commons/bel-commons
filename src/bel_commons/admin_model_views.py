# -*- coding: utf-8 -*-

"""This module contains model views for the Flask-admin interface."""

from itertools import chain

from flask import redirect, request
from flask_admin.contrib.sqla import ModelView as ModelViewBase
from flask_admin.contrib.sqla.ajax import QueryAjaxModelLoader
from flask_admin.model.ajax import DEFAULT_PAGE_SIZE
from flask_security import current_user, url_for_security
from sqlalchemy import or_

from pybel import Manager
from pybel.manager.models import Network
from .manager_base import iter_recent_public_networks
from .models import Project


class ModelView(ModelViewBase):
    """Adds plugin for Flask-Security to Flask-Admin model views."""

    def is_accessible(self):
        """Check if the current user is an admin."""
        return current_user.is_authenticated and current_user.is_admin

    def inaccessible_callback(self, name, **kwargs):
        """Redirect to login page if user doesn't have access."""
        return redirect(url_for_security('login', next=request.url))


class NetworkView(ModelView):
    """Special view for PyBEL Networks."""

    column_exclude_list = ['blob', 'md5', 'authors', 'description', 'copyright', 'disclaimer', 'licenses']


class AnnotationView(ModelView):
    """Special view for PyBEL annotations."""

    column_exclude_list = ['type', 'usage', 'author', 'license', 'citation_description']


class NamespaceView(ModelView):
    """Special view for PyBEL namespaces."""

    column_exclude_list = ['query_url', 'description', 'author', 'license', 'citation_description']


class ReportView(ModelView):
    """Special view for reports."""

    column_exclude_list = ['source', 'calculations', 'source_hash']
    column_display_pk = True
    column_default_sort = ('created', True)
    page_size = 50
    can_set_page_size = True


class NodeView(ModelView):
    """A :mod:`flask_admin` view for PyBEL Nodes."""

    column_exclude_list = ['blob', 'md5']


class EdgeView(ModelView):
    """A :mod:`flask_admin` view for PyBEL Edges."""

    column_exclude_list = ['blob', 'md5']


class CitationView(ModelView):
    """A :mod:`flask_admin` view for citations."""

    column_exclude_list = ['blob', 'md5']


class EvidenceView(ModelView):
    """A :mod:`flask_admin` for evidences."""

    column_exclude_list = ['blob', 'md5']


class ExperimentView(ModelView):
    """A :mod:`flask_admin` for experiments."""

    column_exclude_list = ['source', 'result']


class UserView(ModelView):
    """A :mod:`flask_admin` view for users."""

    column_exclude_list = ['password']


class QueryView(ModelView):
    """A :mod:`flask_admin` view for queries."""

    column_exclude_list = ['dump']
    column_default_sort = ('created', True)
    column_display_pk = True


def build_network_ajax_manager(manager: Manager) -> QueryAjaxModelLoader:  # noqa: D202
    """Build an AJAX manager class for use with Flask-Admin."""

    class NetworkAjaxModelLoader(QueryAjaxModelLoader):
        """A custom Network AJAX loader for Flask Admin."""

        def __init__(self):
            super(NetworkAjaxModelLoader, self).__init__(
                'networks',
                manager.session,
                Network,
                fields=[Network.name],
            )

        def get_list(self, term, offset=0, limit=DEFAULT_PAGE_SIZE):
            """Call ``get_list`` but override to be lazy and tricky about only getting current user's networks."""
            query = self.session.query(self.model)

            filters = (field.ilike(u'%%%s%%' % term) for field in self._cached_fields)
            query = query.filter(or_(*filters))

            if not (current_user.is_authenticated and current_user.is_admin):
                network_chain = chain(
                    current_user.iter_owned_networks(),
                    current_user.iter_shared_networks(),
                    iter_recent_public_networks(manager),
                )

                allowed_network_ids = {
                    network.id
                    for network in network_chain
                }

                if not allowed_network_ids:  # If the current user doesn't have any networks, then return nothing
                    return []

                query = query.filter(Network.id.in_(allowed_network_ids))

            return query.offset(offset).limit(limit).all()

    return NetworkAjaxModelLoader()


def build_project_view(manager: Manager) -> ModelView:  # noqa: D202
    """Build a Flask-Admin model view for a project."""

    class ProjectView(ModelViewBase):
        """Special view to allow users of given projects to manage them."""

        def is_accessible(self) -> bool:
            """Check the current user is logged in."""
            return current_user.is_authenticated

        def inaccessible_callback(self, name, **kwargs):
            """Redirect to login page if user doesn't have access."""
            return redirect(url_for_security('login', next=request.url))

        def get_query(self):
            """Show only projects that the user is part of."""
            parent_query = super(ProjectView, self).get_query()

            if current_user.is_authenticated and current_user.is_admin:
                return parent_query

            current_projects = {
                project.id
                for project in current_user.projects
            }

            return parent_query.filter(Project.id.in_(current_projects))

        def on_model_change(self, form, model, is_created):
            """Add the current user when they creating a project, automatically."""
            if current_user not in model.users:
                model.users.append(current_user)

        form_ajax_refs = {
            'networks': build_network_ajax_manager(manager=manager),
        }

    return ProjectView(Project, manager.session)
