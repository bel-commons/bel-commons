# -*- coding: utf-8 -*-

import codecs
import datetime
import json
from operator import attrgetter
from pickle import dumps, loads

from flask_security import RoleMixin, UserMixin
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
from pybel.utils import list2tuple
from pybel_tools.query import SEED_DATA, SEED_METHOD

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
OMICS_TABLE_NAME = 'pybel_omic'


class Omic(Base):
    """Represents a file filled with omic data"""
    __tablename__ = OMICS_TABLE_NAME

    id = Column(Integer, primary_key=True)

    created = Column(DateTime, default=datetime.datetime.utcnow, doc='The date on which this file was uploaded')
    public = Column(Boolean, nullable=False, default=False, doc='Should the omic data be public?')
    description = Column(Text, nullable=True, doc='A description of the purpose of the analysis')

    source_name = Column(Text, doc='The name of the source file')
    source = Column(LargeBinary(LONGBLOB), doc='The source document holding the data')

    gene_column = Column(Text, nullable=False)
    data_column = Column(Text, nullable=False)

    user_id = Column(Integer, ForeignKey('{}.id'.format(USER_TABLE_NAME)))
    user = relationship('User', backref=backref('omics', lazy='dynamic'))

    def __repr__(self):
        return '<Omic id={}, source_name={}>'.format(self.id, self.source_Name)

    def __str__(self):
        return str(self.source_name)

    def get_source_df(self):
        """Loads the pickled pandas DataFrame from the source file

        :rtype: pandas.DataFrame
        """
        return loads(self.source)

    def get_source_dict(self):
        """Get a dictionary from gene to value

        :rtype: dict[str,float]
        """
        df = self.get_source_df()
        gene_column = self.gene_column
        data_column = self.data_column

        df_cols = [gene_column, data_column]

        result = {
            gene: value
            for _, gene, value in df.loc[df[gene_column].notnull(), df_cols].itertuples()
        }

        return result

    def to_json(self, include_id=True):
        """Serializes as a dictionary

        :param bool include_id:
        :rtype: dict
        """
        result = {
            'created': str(self.created),
            'public': self.public,
            'description': self.description,
            'source_name': self.source_name,
            'gene_column': self.gene_column,
            'data_column': self.data_column
        }

        if self.user:
            result['user'] = self.user.to_json(include_id=include_id)

        if include_id:
            result['id'] = self.id

        return result


class Experiment(Base):
    """Represents a Candidate Mechanism Perturbation Amplitude experiment or RCR experiment"""
    __tablename__ = EXPERIMENT_TABLE_NAME

    id = Column(Integer, primary_key=True)

    created = Column(DateTime, default=datetime.datetime.utcnow, doc='The date on which this analysis was run')
    public = Column(Boolean, nullable=False, default=False, doc='Should the experimental results be public?')

    query_id = Column(Integer, ForeignKey('{}.id'.format(QUERY_TABLE_NAME)), nullable=False, index=True)
    query = relationship('Query', backref=backref("experiments"))

    user_id = Column(Integer, ForeignKey('{}.id'.format(USER_TABLE_NAME)))
    user = relationship('User', backref=backref('experiments', lazy='dynamic'))

    omic_id = Column(Integer, ForeignKey('{}.id'.format(OMICS_TABLE_NAME)), nullable=False, index=True)
    omic = relationship('Omic', backref=backref('experiments', lazy='dynamic'))

    type = Column(String(8), nullable=False, default='CMPA', index=True, doc='Analysis type. CMPA, RCR, etc.')
    permutations = Column(Integer, nullable=False, default=100, doc='Number of permutations performed')
    result = Column(LargeBinary(LONGBLOB), doc='The result python dictionary')

    completed = Column(Boolean, default=False)
    time = Column(Float, nullable=True)

    def get_source_df(self):
        """Loads the pickled pandas DataFrame from the source file

        :rtype: pandas.DataFrame
        """
        return self.omic.get_source_df()

    def dump_results(self, scores):
        """Dumps the results and marks this experiment as complete

        :param dict[tuple,tuple] scores: The scores to store in this experiment
        """
        self.result = dumps(scores)
        self.completed = True

    def get_results_df(self):
        """Loads the pickled pandas DataFrame back into an object

        :rtype: pandas.DataFrame
        """
        return loads(self.result)

    def get_data_list(self):
        """Loads the data into a usable list

        :rtype: list[tuple]
        """
        result = self.get_results_df()
        return [
            (k, v)
            for k, v in result.items()
            if v[0]
        ]

    def __repr__(self):
        return '<Experiment omics={}, query={}>'.format(self.omics.id, self.query.id)

    @property
    def source_name(self):
        for ext in ('.tsv', '.csv'):
            if self.omic.source_name.endswith(ext):
                return self.omic.source_name[:-len(ext)]

        return self.omic.source_name

    @property
    def gene_column(self):
        return self.omic.gene_column

    @property
    def data_column(self):
        return self.omic.data_column

    @property
    def description(self):
        return self.omic.description


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
        return codecs.decode(self.source, self.encoding or 'utf-8').split('\n')

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
    def is_displayable(self):
        """Is this network small enough to confidently display?

        :rtype: bool
        """
        return self.number_nodes and self.number_nodes < 100

    @property
    def incomplete(self):
        """Is this still running?

        :rtype: bool
        """
        return self.completed is None and not self.message

    @property
    def failed(self):
        """Did this fail?

        :rtype: bool
        """
        return self.completed is not None and not self.completed

    @property
    def stalled(self):
        """Returns true if a job is older than 3 hours

        :rtype: bool
        """
        return datetime.datetime.utcnow() - self.created > datetime.timedelta(hours=3)

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

    def pending_reports(self):
        """Gets a list of pending reports for this user

        :rtype: list[Report]
        """
        return [
            report
            for report in self.reports
            if report.incomplete
        ]

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

    def owns_network(self, network):
        """Returns if this user owns this network

        :type network: Network
        :rtype: bool
        """
        return self.is_admin or (self.is_authenticated and network.report and self == network.report.user)


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
    def from_networks(networks, user=None):
        """Builds an assembly from a list of networks

        :param iter[Network] networks: The network in this assembly
        :param Optional[User] user: The user who created this assembly
        :rtype: Assembly
        """
        assembly = Assembly(networks=networks)

        if user is not None and user.is_authenticated:
            assembly.user = user

        return assembly

    @staticmethod
    def from_network(network, user=None):
        """Builds an assembly from a singular network

        :param Network network: The network in this assembly
        :param Optional[User] user: The user who created this assembly
        :rtype: Assembly
        """
        return Assembly.from_networks(networks=[network], user=user)

    @staticmethod
    def from_query(manager, query, user=None):
        """Builds an assembly from a query

        :param manager: A PyBEL cache manager
        :param pybel_tools.query.Query query: A query object
        :param Optional[User] user: The user who created this assembly
        :rtype: Assembly
        """
        networks = [
            manager.session.query(Network).get(network_id)
            for network_id in query.network_ids
        ]
        return Assembly.from_networks(networks, user=user)

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

    def __repr__(self):
        return '<Assembly {} with [{}]>'.format(
            self.id,
            ', '.join(str(network.id) for network in self.networks)
        )

    def __str__(self):
        return ', '.join(map(str, self.networks))


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
    parent = relationship('Query', remote_side=[id],
                          backref=backref('children', lazy='dynamic', cascade="all, delete-orphan"))

    def __repr__(self):
        return '<Query id={}>'.format(self.id)

    @property
    def data(self):
        """Converts this object to a :class:`pybel_tools.query.Query` object

        :rtype: pybel_tools.query.Query
        """
        if not hasattr(self, '_query'):
            self._query = pybel_tools.query.Query(network_ids=[network.id for network in self.assembly.networks])

            if self.seeding:
                self._query.seeding = self.seeding_to_json()

            if self.pipeline_protocol:
                self._query.pipeline.protocol = self.protocol_to_json()

        return self._query

    def to_json(self, include_id=True):
        """Serializes this object to JSON

        :param bool include_id: Should the identifier be included?
        :rtype: dict
        """
        result = self.data.to_json()
        if include_id:
            result['id'] = self.id
        return result

    def seeding_to_json(self):
        """Returns seeding json. It's also possible to get Query.data.seeding as well.

        :rtype: list[dict]
        """
        if self.seeding is None:
            return []

        seeding = json.loads(self.seeding)

        result = []
        for seed in seeding:
            if seed[SEED_METHOD] not in {'pubmed', 'authors', 'annotation'}:
                seed[SEED_DATA] = list2tuple(seed[SEED_DATA])
            result.append(seed)

        return result

    def protocol_to_json(self):
        """Returns the pipeline as json

        :rtype: list[dict]
        """
        if self.pipeline_protocol is None:
            return []

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
    def from_assembly(assembly, user=None):
        """Builds a query from an assembly

        :param Assembly assembly: An assembly
        :param Optional[User] user: The user who owns this query
        :rtype: Query
        """
        query = Query(assembly=assembly)

        if user is not None and user.is_authenticated:
            query.user = user

        return query

    @staticmethod
    def from_networks(networks, user=None):
        """Builds a query from a network

        :param list[Network] networks: A network
        :param Optional[User] user: The user who owns this query
        :rtype: Query
        """
        assembly = Assembly.from_networks(networks, user=user)
        query = Query.from_assembly(assembly, user=user)
        return query

    @staticmethod
    def from_network(network, user=None):
        """Builds a query from a network

        :param Network network: A network
        :param Optional[User] user: The user who owns this query
        :rtype: Query
        """
        return Query.from_networks(networks=[network], user=user)

    @staticmethod
    def from_query(manager, query, user=None):
        """Builds a orm query from a pybel-tools query

        :param pybel.manager.Manager manager: A database manager
        :param pybel_tools.query.Query query: A query
        :param Optional[User] user: A user
        :rtype: Query
        """
        assembly = Assembly.from_query(manager, query, user=user)

        result = Query.from_assembly(assembly, user=user)
        result.seeding = query.seeding_to_jsons()
        result.pipeline_protocol = query.pipeline.to_jsons()

        return result

    @staticmethod
    def from_query_args(manager, network_ids, user=None, seed_list=None, pipeline=None):
        """Builds a orm query from the arguments for a pybel-tools query

        :param pybel.manager.Manager manager:
        :param list[int] network_ids: A list of network identifiers
        :param Optional[User] user:
        :param Optional[list[dict]] seed_list:
        :param Optional[Pipeline] pipeline: Instance of a pipeline
        :rtype: Query
        """
        q = pybel_tools.query.Query(network_ids, seeding=seed_list, pipeline=pipeline)
        return Query.from_query(manager, q, user=user)

    def build_appended(self, name, *args, **kwargs):
        """Builds a new query with the given function appended to the current query's pipeline

        :param str name: Append function name
        :param args: Append function positional arguments
        :param kwargs: Append function keyword arguments
        :rtype: Query
        """
        _query = self.data
        _query.pipeline.append(name, *args, **kwargs)

        return Query(
            parent_id=self.id,
            assembly=self.assembly,
            seeding=self.seeding,
            pipeline_protocol=_query.pipeline.to_jsons(),
        )

    def add_seed_neighbors(self, nodes):
        """Adds a seed by neighbors. Returns a new query

        :param list[pybel.manager.models.Node] nodes: A list of nodes
        :rtype: Query
        """
        _query = self.data
        _query.append_seeding_neighbors([node.to_tuple() for node in nodes])

        return Query(
            parent_id=self.id,
            assembly=self.assembly,
            seeding=_query.seeding_to_jsons(),
            pipeline_protocol=self.pipeline_protocol,
        )


class EdgeVote(Base):
    """Describes the vote on an edge"""
    __tablename__ = VOTE_TABLE_NAME

    id = Column(Integer, primary_key=True)

    edge_id = Column(Integer, ForeignKey('{}.id'.format(EDGE_TABLE_NAME)), nullable=False)
    edge = relationship('Edge', backref=backref('votes', lazy='dynamic', cascade="all, delete-orphan"))

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
    edge = relationship('Edge', backref=backref('comments', lazy='dynamic', cascade="all, delete-orphan"))

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
    right = relationship('Network', foreign_keys=[right_id],
                         backref=backref('incoming_overlaps', lazy='dynamic', cascade="all, delete-orphan"))

    overlap = Column(Float, nullable=False, doc='The node overlap between the two networks')
