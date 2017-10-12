# -*- coding: utf-8 -*-

import datetime
import json

import codecs
from flask_security import RoleMixin, UserMixin
from operator import attrgetter
from six.moves.cPickle import dumps, loads
from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey, Index, Integer, LargeBinary, String, Table, Text,
    UniqueConstraint,
)
from sqlalchemy.orm import backref, relationship

import pybel_tools.query
from pybel import from_lines
from pybel.manager import Base
from pybel.manager.models import EDGE_TABLE_NAME, LONGBLOB, NETWORK_TABLE_NAME, Network
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
OVERLAP_TABLE_NAME = 'pybel_overlap'


class Experiment(Base):
    """Represents a Candidate Mechanism Perturbation Amplitude experiment run in PyBEL Web"""
    __tablename__ = EXPERIMENT_TABLE_NAME

    id = Column(Integer, primary_key=True)

    created = Column(DateTime, default=datetime.datetime.utcnow, doc='The date on which this analysis was run')
    description = Column(Text, nullable=True, doc='A description of the purpose of the analysis')
    permutations = Column(Integer, doc='Number of permutations performed')
    source_name = Column(Text, doc='The name of the source file')
    source = Column(LargeBinary(LONGBLOB), doc='The source document holding the data')
    result = Column(LargeBinary(LONGBLOB), doc='The result python dictionary')

    query_id = Column(Integer, ForeignKey('{}.id'.format(QUERY_TABLE_NAME)), nullable=False)
    query = relationship('Query', backref=backref("experiments"))

    user_id = Column(Integer, ForeignKey('{}.id'.format(USER_TABLE_NAME)))
    user = relationship('User', backref=backref('experiments', lazy='dynamic'))

    gene_column = Column(Text, nullable=False)
    data_column = Column(Text, nullable=False)

    completed = Column(Boolean, default=False)

    def __repr__(self):
        return '<Experiment on {}>'.format(self.query)


class Report(Base):
    """Stores information about compilation and uploading events"""
    __tablename__ = REPORT_TABLE_NAME

    id = Column(Integer, primary_key=True)

    user_id = Column(Integer, ForeignKey('{}.id'.format(USER_TABLE_NAME)), doc='The user who uploaded the network')
    user = relationship('User', backref=backref('reports', lazy='dynamic'))

    created = Column(DateTime, default=datetime.datetime.utcnow, doc='The date and time of upload')
    public = Column(Boolean, nullable=False, default=False, doc='Should the network be viewable to the public?')

    source_name = Column(Text, nullable=True, doc='The name of the source file')
    source = Column(LargeBinary(LONGBLOB), nullable=True, doc='The source BEL Script')
    source_hash = Column(String(128), nullable=True, index=True, doc='SHA512 hash of source file')
    encoding = Column(Text, nullable=True)

    allow_nested = Column(Boolean, default=False)
    citation_clearing = Column(Boolean, default=False)
    infer_origin = Column(Boolean, default=False)

    number_nodes = Column(Integer, nullable=True)
    number_edges = Column(Integer, nullable=True)
    number_citations = Column(Integer, nullable=True)
    number_authors = Column(Integer, nullable=True)
    network_density = Column(Float, nullable=True)
    average_degree = Column(Float, nullable=True)
    number_components = Column(Integer, nullable=True)
    number_warnings = Column(Integer, nullable=True)
    calculations = Column(LargeBinary(LONGBLOB), nullable=True, doc='A place to store a pickle of random stuf')

    message = Column(Text, nullable=True, doc='Error message')
    completed = Column(Boolean, nullable=True)
    time = Column(Float, nullable=True, doc='Time took to complete')

    network_id = Column(
        Integer,
        ForeignKey('{}.id'.format(NETWORK_TABLE_NAME)),
        nullable=True,
        doc='The network that was uploaded'
    )
    network = relationship('Network', backref=backref('report', uselist=False))

    def get_lines(self):
        """Decodes the lines stored in this

        :rtype: list[str]
        """
        return codecs.decode(self.source, self.encoding).split('\n')

    def parse_graph(self, manager):
        """Parses the graph from the latent BEL Script

        :param pybel.manager.Manager manager: A cache manager
        :rtype: pybel.BELGraph
        """
        return from_lines(
            self.get_lines(),
            manager=manager,
            allow_nested=self.allow_nested,
            citation_clearing=self.citation_clearing,
        )

    def dump_calculations(self, calculations_dict):
        """Stores a calculations dict

        :param dict calculations_dict:
        """
        self.calculations = dumps(calculations_dict)

    def get_calculations(self):
        """Gets the summary calculations dictionary from this network

        :rtype: dict
        """
        return loads(self.calculations)

    @property
    def incomplete(self):
        return self.completed is None and not self.message

    @property
    def failed(self):
        return self.completed is not None and not self.completed

    def as_info_json(self):
        """Returns this object as a JSON summary

        :rtype: dict
        """
        return dict([
            ('Nodes', self.number_nodes),
            ('Edges', self.number_edges),
            ('Citations', self.number_citations),
            ('Authors', self.number_authors),
            ('Network density', self.network_density),
            ('Components', self.number_components),
            ('Average degree', self.average_degree),
            ('Compilation warnings', self.number_warnings)
        ])

    def __repr__(self):
        if self.incomplete:
            return '<Report {}: incomplete {}>'.format(self.id, self.source_name)

        if self.failed:
            return '<Report {}: failed)>'.format(self.id)

        if self.network:
            return '<Report {}: completed {}>'.format(self.id, self.network)

        return '<Report {}: cancelled>'.format(self.id)


roles_users = Table(
    ROLE_USER_TABLE_NAME,
    Base.metadata,
    Column('user_id', Integer, ForeignKey('{}.id'.format(USER_TABLE_NAME)), primary_key=True),
    Column('role_id', Integer, ForeignKey('{}.id'.format(ROLE_TABLE_NAME)), primary_key=True)
)

users_networks = Table(
    USER_NETWORK_TABLE_NAME,
    Base.metadata,
    Column('user_id', Integer, ForeignKey('{}.id'.format(USER_TABLE_NAME)), primary_key=True),
    Column('network_id', Integer, ForeignKey('{}.id'.format(NETWORK_TABLE_NAME)), primary_key=True)
)

projects_users = Table(
    PROJECT_USER_TABLE_NAME,
    Base.metadata,
    Column('project_id', Integer, ForeignKey('{}.id'.format(PROJECT_TABLE_NAME)), primary_key=True),
    Column('user_id', Integer, ForeignKey('{}.id'.format(USER_TABLE_NAME)), primary_key=True)
)

projects_networks = Table(
    PROJECT_NETWORK_TABLE_NAME,
    Base.metadata,
    Column('project_id', Integer, ForeignKey('{}.id'.format(PROJECT_TABLE_NAME)), primary_key=True),
    Column('network_id', Integer, ForeignKey('{}.id'.format(NETWORK_TABLE_NAME)), primary_key=True)
)


class Role(Base, RoleMixin):
    """Stores user roles"""
    __tablename__ = ROLE_TABLE_NAME

    id = Column(Integer, primary_key=True)
    name = Column(String(80), unique=True, nullable=False)
    description = Column(Text)

    def __str__(self):
        return self.name

    def to_json(self):
        """Outputs this role as a JSON dictionary

        :rtype: dict
        """
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
        }


class Project(Base):
    """Stores projects"""
    __tablename__ = PROJECT_TABLE_NAME

    id = Column(Integer, primary_key=True)
    name = Column(String(80), unique=True, index=True, nullable=False)
    description = Column(Text)

    users = relationship('User', secondary=projects_users, backref=backref('projects', lazy='dynamic'))

    # TODO why not just use the Assembly table for the many to many relationship?
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

    def as_bel(self):
        """Returns a merged instance of all of the contained networks

        :return: A merged BEL graph
        :rtype: pybel.BELGraph
        """
        return union(network.as_bel() for network in self.networks)
        # return self.assembly.as_bel()

    def __str__(self):
        return self.name

    def to_json(self, include_id=True):
        """Outputs this project as a JSON dictionary

        :rtype: dict
        """
        result = {
            'name': self.name,
            'description': self.description,
            'users': [
                {
                    'id': user.id,
                    'email': user.email,
                }
                for user in self.users
            ],
            'networks': [
                {
                    'id': network.id,
                    'name': network.name,
                    'version': network.version,
                }
                for network in self.networks
            ]
        }

        if include_id:
            result['id'] = self.id

        return result


class User(Base, UserMixin):
    """Stores users"""
    __tablename__ = USER_TABLE_NAME

    id = Column(Integer, primary_key=True)

    email = Column(String(255), unique=True, doc="The user's email")
    password = Column(String(255))
    name = Column(String(255), doc="The user's name")
    active = Column(Boolean)
    confirmed_at = Column(DateTime)

    roles = relationship('Role', secondary=roles_users, backref=backref('users', lazy='dynamic'))
    networks = relationship('Network', secondary=users_networks, backref=backref('users', lazy='dynamic'))

    @property
    def is_admin(self):
        """Is this user an administrator?"""
        return self.has_role('admin')

    @property
    def is_scai(self):
        """Is this user from SCAI?"""
        return (
            self.has_role('scai') or
            self.email.endswith('@scai.fraunhofer.de') or
            self.email.endswith('@scai-extern.fraunhofer.de')
        )

    @property
    def is_beta_tester(self):
        """Is this user cut out for the truth?"""
        return self.is_admin or self.has_role('beta')

    def get_owned_networks(self):
        """Gets all networks this user owns

        :rtype: iter[Network]
        """
        return (
            report.network
            for report in self.reports
            if report.network
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

    def get_sorted_queries(self):
        """Gets a list of sorted queries for this user

        :rtype: list[Query]
        """
        return sorted(self.queries, key=attrgetter('created'), reverse=True)

    def __str__(self):
        return self.email

    def to_json(self, include_id=True):
        """Outputs this User as a JSON dictionary

        :rtype: dict
        """
        result = {
            'email': self.email,
            'roles': [
                role.name
                for role in self.roles
            ],
        }

        if include_id:
            result['id'] = self.id

        if self.name:
            result['name'] = self.name

        return result


assembly_network = Table(
    ASSEMBLY_NETWORK_TABLE_NAME,
    Base.metadata,
    Column('network_id', Integer, ForeignKey('{}.id'.format(NETWORK_TABLE_NAME))),
    Column('assembly_id', Integer, ForeignKey('{}.id'.format(ASSEMBLY_TABLE_NAME)))
)


class Assembly(Base):
    """Describes an assembly of networks"""
    __tablename__ = ASSEMBLY_TABLE_NAME

    id = Column(Integer, primary_key=True)
    name = Column(String(255), unique=True, nullable=True)

    user_id = Column(Integer, ForeignKey('{}.id'.format(USER_TABLE_NAME)), doc='The creator of this assembly')
    user = relationship('User', backref='assemblies')

    created = Column(DateTime, default=datetime.datetime.utcnow, doc='The date and time of upload')

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

        :param manager: A PyBEL cache manager
        :param pybel_tools.query.Query query:
        :rtype: Assembly
        """
        return Assembly(
            networks=[
                manager.session.query(Network).get(network_id)
                for network_id in query.network_ids
            ],
        )

    def __repr__(self):
        return '<Assembly {} with [{}]>'.format(
            self.id,
            ', '.join(str(network.id) for network in self.networks)
        )

    def to_json(self):
        """

        :rtype: dict
        """
        result = {
            'user': {
                'id': self.user.id,
                'email': self.user.email,
            },

            'networks': [
                network.to_json()
                for network in self.networks
            ]
        }

        if self.name:
            result['name'] = self.name

        return result


class Query(Base):
    """Describes a :class:`pybel_tools.query.Query`"""
    __tablename__ = QUERY_TABLE_NAME

    id = Column(Integer, primary_key=True)

    user_id = Column(Integer, ForeignKey('{}.id'.format(USER_TABLE_NAME)), doc='The user who created the query')
    user = relationship('User', backref=backref('queries', lazy='dynamic'))

    assembly_id = Column(Integer, ForeignKey('{}.id'.format(ASSEMBLY_TABLE_NAME)),
                         doc='The network assembly used in this query')
    assembly = relationship('Assembly')

    created = Column(DateTime, default=datetime.datetime.utcnow, doc='The date and time of upload')

    seeding = Column(Text, doc="The stringified JSON of the list representation of the seeding")

    pipeline_protocol = Column(Text, doc="Protocol list")

    parent_id = Column(Integer, ForeignKey('{}.id'.format(QUERY_TABLE_NAME)), nullable=True)
    parent = relationship('Query', remote_side=[id], backref=backref('children', lazy='dynamic'))

    # TODO remove dump completely and have it reconstruct from parts
    dump = Column(Text, doc="The stringified JSON representing this query")

    def __repr__(self):
        return '<Query {}>'.format(self.id)

    @property
    def data(self):
        """Converts this object to a :class:`pybel_tools.query.Query` object

        :rtype: pybel_tools.query.Query
        """
        if not hasattr(self, '_query'):
            self._query = pybel_tools.query.Query.from_jsons(self.dump)

        return self._query

    def to_json(self):
        """Serializes this object to JSON

        :rtype: dict
        """
        result = {'id': self.id}
        result.update(self.data.to_json())
        return result

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

        :type manager: pybel.manager.Manager
        :return: The result of this query
        :rtype: Optional[pybel.BELGraph]
        """
        return self.data.run(manager)

    @staticmethod
    def from_query(manager, query, user=None):
        """Builds a orm query from a pybel-tools query

        :param pybel.manager.Manager manager:
        :param pybel_web.models.User user:
        :param pybel_tools.query.Query query:
        :rtype: Query
        """
        assembly = Assembly.from_query(manager, query)

        query = Query(
            assembly=assembly,
            seeding=query.seeding_to_jsons(),
            pipeline_protocol=query.pipeline.to_jsons(),
            dump=query.to_jsons()
        )

        if user is not None and user.is_authenticated:
            assembly.user = user
            query.user = user

        return query

    @staticmethod
    def from_query_args(manager, network_ids, user=None, seed_list=None, pipeline=None):
        """Builds a orm query from the arguments for a pybel-tools query

        :param pybel.manager.Manager manager:
        :param pybel_web.models.User user:
        :param int or list[int] network_ids:
        :param list[dict] seed_list:
        :param Pipeline pipeline: Instance of a pipeline
        :rtype: Query
        """
        q = pybel_tools.query.Query(network_ids, seed_list=seed_list, pipeline=pipeline)
        return Query.from_query(manager, q, user=user)


class EdgeVote(Base):
    """Describes the vote on an edge"""
    __tablename__ = VOTE_TABLE_NAME

    id = Column(Integer, primary_key=True)

    edge_id = Column(Integer, ForeignKey('{}.id'.format(EDGE_TABLE_NAME)), nullable=False)
    edge = relationship('Edge', backref=backref('votes', lazy='dynamic'))

    user_id = Column(Integer, ForeignKey('{}.id'.format(USER_TABLE_NAME)), nullable=False,
                     doc='The user who made this vote')
    user = relationship('User', backref=backref('votes', lazy='dynamic'))

    agreed = Column(Boolean, nullable=True)
    changed = Column(DateTime, default=datetime.datetime.utcnow)

    __table_args__ = (
        UniqueConstraint(edge_id, user_id),
    )

    def to_json(self):
        """Converts this vote to JSON

        :rtype: dict
        """
        return {
            'id': self.id,
            'edge': {
                'id': self.edge.id
            },
            'user': {
                'id': self.user.id,
                'email': self.user.email,
            },
            'vote': self.agreed
        }


Index('edgeUserIndex', EdgeVote.edge_id, EdgeVote.user_id)


class EdgeComment(Base):
    """Describes the comments on an edge"""
    __tablename__ = COMMENT_TABLE_NAME

    id = Column(Integer, primary_key=True)

    edge_id = Column(Integer, ForeignKey('{}.id'.format(EDGE_TABLE_NAME)))
    edge = relationship('Edge', backref=backref('comments', lazy='dynamic'))

    user_id = Column(Integer, ForeignKey('{}.id'.format(USER_TABLE_NAME)), nullable=False,
                     doc='The user who made this comment')
    user = relationship('User', backref=backref('comments', lazy='dynamic'))

    comment = Column(Text, nullable=False)
    created = Column(DateTime, default=datetime.datetime.utcnow)

    def to_json(self):
        """Converts this comment to JSON

        :rtype: dict
        """
        return {
            'id': self.id,
            'edge': {
                'id': self.edge.id
            },
            'user': {
                'id': self.user.id,
                'email': self.user.email,
            },
            'comment': self.comment
        }


class NetworkOverlap(Base):
    """Describes the network overlap based on nodes"""
    __tablename__ = OVERLAP_TABLE_NAME

    left_id = Column(Integer, ForeignKey('{}.id'.format(NETWORK_TABLE_NAME)), primary_key=True)
    left = relationship('Network', foreign_keys=[left_id],
                        backref=backref('overlaps', lazy='dynamic', cascade="all, delete-orphan"))

    right_id = Column(Integer, ForeignKey('{}.id'.format(NETWORK_TABLE_NAME)), primary_key=True)
    right = relationship('Network', foreign_keys=[right_id])

    overlap = Column(Float, nullable=False, doc='The node overlap between the two networks')
