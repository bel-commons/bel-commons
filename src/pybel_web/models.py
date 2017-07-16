# -*- coding: utf-8 -*-

import datetime
import json

from flask_security import RoleMixin, UserMixin
from sqlalchemy import Column, Integer, ForeignKey, DateTime, Boolean, Text, Binary, Table, String, Index
from sqlalchemy.orm import relationship, backref

import pybel_tools.query
from pybel.manager import Base
from pybel.manager.models import NETWORK_TABLE_NAME, Network
from pybel.struct import union

EXPERIMENT_TABLE_NAME = 'pybel_experiment'
REPORT_TABLE_NAME = 'pybel_report'
ROLE_TABLE_NAME = 'pybel_role'
PROJECT_TABLE_NAME = 'pybel_project'
USER_TABLE_NAME = 'pybel_user'
ASSEMBLY_TABLE_NAME = 'pybel_assembly'
ASSEMBLY_NETWORK_TABLE_NAME = 'pybel_assembly_network'
QUERY_TABLE_NAME = 'pybel_query'
ROLE_USER_TABLE_NAME = 'pybel_roles_users'
PROJECT_USER_TABLE_NAME = 'pybel_project_user'
PROJECT_NETWORK_TABLE_NAME = 'pybel_project_network'
USER_NETWORK_TABLE_NAME = 'pybel_user_network'
COMMENT_TABLE_NAME = 'pybel_comment'
VOTE_TABLE_NAME = 'pybel_vote'


class Experiment(Base):
    """Represents a Candidate Mechanism Perturbation Amplitude experiment run in PyBEL Web"""
    __tablename__ = EXPERIMENT_TABLE_NAME

    id = Column(Integer, primary_key=True)

    created = Column(DateTime, default=datetime.datetime.utcnow, doc='The date on which this analysis was run')
    description = Column(Text, nullable=True, doc='A description of the purpose of the analysis')
    permutations = Column(Integer, doc='Number of permutations performed')
    source_name = Column(Text, doc='The name of the source file')
    source = Column(Binary, doc='The source document holding the data')
    result = Column(Binary, doc='The result python dictionary')

    network_id = Column(Integer, ForeignKey('{}.id'.format(NETWORK_TABLE_NAME)))
    network = relationship('Network', backref=backref("experiments"))

    user_id = Column(Integer, ForeignKey('{}.id'.format(USER_TABLE_NAME)))
    user = relationship('User', backref=backref('experiments', lazy='dynamic'))

    def __repr__(self):
        return '<Experiment on {}>'.format(self.network)


class Report(Base):
    """Stores information about compilation and uploading events"""
    __tablename__ = REPORT_TABLE_NAME

    network_id = Column(
        Integer, ForeignKey('{}.id'.format(NETWORK_TABLE_NAME)),
        primary_key=True,
        doc='The network that was uploaded'
    )
    network = relationship('Network', backref=backref('report', uselist=False))

    user_id = Column(Integer, ForeignKey('{}.id'.format(USER_TABLE_NAME)), doc='The user who uploaded the network')
    user = relationship('User', backref=backref('reports', lazy='dynamic'))

    created = Column(DateTime, default=datetime.datetime.utcnow, doc='The date and time of upload')
    public = Column(Boolean, nullable=False, default=False, doc='Should the network be viewable to the public?')
    precompiled = Column(Boolean, doc='Was this document uploaded as a BEL script or a precompiled gpickle?')
    number_nodes = Column(Integer)
    number_edges = Column(Integer)
    number_warnings = Column(Integer)

    def __repr__(self):
        return '<Report on {}>'.format(self.network)

    def __str__(self):
        return repr(self)


roles_users = Table(
    ROLE_USER_TABLE_NAME,
    Base.metadata,
    Column('user_id', Integer, ForeignKey('{}.id'.format(USER_TABLE_NAME))),
    Column('role_id', Integer, ForeignKey('{}.id'.format(ROLE_TABLE_NAME)))
)

users_networks = Table(
    USER_NETWORK_TABLE_NAME,
    Base.metadata,
    Column('user_id', Integer, ForeignKey('{}.id'.format(USER_TABLE_NAME))),
    Column('network_id', Integer, ForeignKey('{}.id'.format(NETWORK_TABLE_NAME)))
)

projects_users = Table(
    PROJECT_USER_TABLE_NAME,
    Base.metadata,
    Column('project_id', Integer, ForeignKey('{}.id'.format(PROJECT_TABLE_NAME))),
    Column('user_id', Integer, ForeignKey('{}.id'.format(USER_TABLE_NAME)))
)

projects_networks = Table(
    PROJECT_NETWORK_TABLE_NAME,
    Base.metadata,
    Column('project_id', Integer, ForeignKey('{}.id'.format(PROJECT_TABLE_NAME))),
    Column('network_id', Integer, ForeignKey('{}.id'.format(NETWORK_TABLE_NAME)))
)


class Role(Base, RoleMixin):
    """Stores user roles"""
    __tablename__ = ROLE_TABLE_NAME

    id = Column(Integer(), primary_key=True)
    name = Column(String(80), unique=True, nullable=False)
    description = Column(String(255))

    def __str__(self):
        return self.name


class Project(Base):
    """Stores projects"""
    __tablename__ = PROJECT_TABLE_NAME

    id = Column(Integer(), primary_key=True)
    name = Column(String(80), unique=True, nullable=False)
    description = Column(String(255))

    users = relationship('User', secondary=projects_users, backref=backref('projects', lazy='dynamic'))
    networks = relationship('Network', secondary=projects_networks, backref=backref('projects', lazy='dynamic'))

    def has_user(self, user):
        """Indicates if the given user belongs to the project

        :param User user:
        :rtype: bool
        """
        return any(
            user.id == u.id
            for u in self.users
        )

    def __str__(self):
        return self.name


class User(Base, UserMixin):
    """Stores users"""
    __tablename__ = USER_TABLE_NAME

    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True)
    password = Column(String(255))
    first_name = Column(String(255))
    last_name = Column(String(255))
    active = Column(Boolean)
    confirmed_at = Column(DateTime)

    roles = relationship('Role', secondary=roles_users, backref=backref('users', lazy='dynamic'))
    networks = relationship('Network', secondary=users_networks, backref=backref('users', lazy='dynamic'))

    @property
    def admin(self):
        """Is this user an administrator?"""
        return self.has_role('admin')

    @property
    def name(self):
        """Shows the full name of the user"""
        return '{} {}'.format(self.first_name, self.last_name) if self.first_name else self.email

    def get_owned_networks(self):
        """Gets all networks this user owns

        :rtype: iter[Network]
        """
        return (
            report.network
            for report in self.reports
        )

    def get_shared_networks(self):
        """Gets all networks shared with this user

        :rtype: iter[Network]
        """
        return self.networks

    def get_project_networks(self):
        """Gets all networks for which projects have granted this user access

        :rtype: iter[Network]
        """
        return (
            network
            for project in self.projects
            for network in project.networks
        )

    def __str__(self):
        return repr(self)

    def __repr__(self):
        return self.email


assembly_network = Table(
    ASSEMBLY_NETWORK_TABLE_NAME,
    Base.metadata,
    Column('network_id', Integer, ForeignKey('{}.id'.format(NETWORK_TABLE_NAME))),
    Column('assembly_id', Integer, ForeignKey('{}.id'.format(ASSEMBLY_TABLE_NAME)))
)


class Assembly(Base):
    """Describes an assembly of networks"""
    __tablename__ = ASSEMBLY_TABLE_NAME

    id = Column(Integer(), primary_key=True)
    name = Column(String(255), unique=True, nullable=True)

    user_id = Column(Integer, ForeignKey('{}.id'.format(USER_TABLE_NAME)), doc='The creator of this assembly')
    user = relationship('User', backref='assemblies')

    networks = relationship('Network', secondary=assembly_network, backref=backref('assemblies', lazy='dynamic'))

    def as_bel(self):
        """Returns a merged instance of all of the contained networks

        :return: A merged BEL graph
        :rtype: pybel.BELGraph
        """
        return union(network.as_bel() for network in self.networks)

    @staticmethod
    def from_query(manager, query):
        """Builds an assembly from a query

        :param pybel_tools.query.Query query:
        :rtype: Assembly
        """
        return Assembly(networks=[
            manager.session.query(Network).get(network_id)
            for network_id in query.network_ids
        ])

    def __repr__(self):
        return '<Assembly {}>'.format(', '.join(str(network.id) for network in self.networks))


class Query(Base):
    """Describes a :class:`pybel_tools.query.Query`"""
    __tablename__ = QUERY_TABLE_NAME

    id = Column(Integer(), primary_key=True)

    user_id = Column(Integer, ForeignKey('{}.id'.format(USER_TABLE_NAME)), doc='The user who created the query')
    user = relationship('User', backref=backref('queries', lazy='dynamic'))

    assembly_id = Column(Integer, ForeignKey('{}.id'.format(ASSEMBLY_TABLE_NAME)),
                         doc='The network assembly used in this query')
    assembly = relationship('Assembly')

    seeding = Column(Text, doc="The stringified JSON of the list representation of the seeding")

    pipeline_protocol = Column(Text, doc="Protocol list")

    parent_id = Column(Integer, ForeignKey('{}.id'.format(QUERY_TABLE_NAME)), nullable=True)
    parent = relationship('Query', remote_side=[id], backref=backref('children', lazy='dynamic'))

    # TODO remove dump completely and have it reconstruct from parts
    dump = Column(Text, doc="The stringified JSON representing this query")

    @property
    def data(self):
        """Converts this object to a :class:`pybel_tools.query.Query` object

        :rtype: pybel_tools.query.Query
        """
        if not hasattr(self, '_query'):
            self._query = pybel_tools.query.Query.from_jsons(self.dump)

        return self._query

    def seeding_as_json(self):
        """Returns seeding json. It's also possible to get Query.data.seeding as well.

        :rtype: dict
        """
        return json.loads(self.seeding)

    def protocol_as_json(self):
        """Returns the pipeline as json

        :rtype: list[dict]
        """
        return json.loads(self.pipeline_protocol)

    def run(self, manager):
        """A wrapper around the :meth:`pybel_tools.query.Query.run` function of the enclosed
        :class:`pybel_tools.pipeline.Query` object.

        :type manager: pybel.cache.manager.CacheManager or pybel_tools.api.DatabaseService
        :return: The result of this query
        :rtype: pybel.BELGraph
        """
        return self.data.run(manager)

    @staticmethod
    def from_query(manager, user, query):
        """Builds a orm query from a pybel-tools query

        :param pybel.manager.CacheManager manager:
        :param pybel_web.models.User user:
        :param pybel_tools.query.Query query:
        :rtype: Query
        """
        query = Query(
            assembly=Assembly.from_query(manager, query),
            seeding=query.seeding_to_jsons(),
            pipeline_protocol=query.pipeline.to_jsons(),
            dump=query.to_jsons()
        )

        if user.is_authenticated:
            query.user = user

        return query

    @staticmethod
    def from_query_args(manager, user, network_ids, seed_list=None, pipeline=None):
        """Builds a orm query from the arguments for a pybel-tools query

        :param pybel.manager.CacheManager manager:
        :param pybel_web.models.User user:
        :param int or list[int] network_ids:
        :param list[dict] seed_list:
        :param Pipeline pipeline: Instance of a pipeline
        :rtype: Query
        """
        q = pybel_tools.query.Query(network_ids, seed_list=seed_list, pipeline=pipeline)
        return Query.from_query(manager, user, q)


class EdgeVote(Base):
    """Describes the vote on an edge"""
    __tablename__ = VOTE_TABLE_NAME

    id = Column(Integer, primary_key=True)

    edge_id = Column(Integer, nullable=False, index=True, doc='The hash of the edge for this comment')
    user_id = Column(Integer, ForeignKey('{}.id'.format(USER_TABLE_NAME)), nullable=False,
                     doc='The user who made this vote')
    user = relationship('User', backref=backref('votes', lazy='dynamic'))
    agreed = Column(Boolean, nullable=False)


Index('edgeUserIndex', EdgeVote.edge_id, EdgeVote.user_id)


class EdgeComments(Base):
    """Describes the comments on an edge"""
    __tablename__ = COMMENT_TABLE_NAME

    id = Column(Integer, primary_key=True)

    edge_id = Column(Integer, nullable=False, index=True, doc='The hash of the edge for this comment')
    comment = Column(Text, nullable=False)
    created = Column(DateTime, default=datetime.datetime.utcnow)

    user_id = Column(Integer, ForeignKey('{}.id'.format(USER_TABLE_NAME)), nullable=False,
                     doc='The user who made this comment')
    user = relationship('User', backref=backref('comments', lazy='dynamic'))
