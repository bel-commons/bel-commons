# -*- coding: utf-8 -*-

"""SQLAlchemy models for BEL Commons."""

from __future__ import annotations

import codecs
import datetime
import itertools as itt
from operator import attrgetter
from pickle import dumps, loads
from typing import Dict, Iterable, List, Mapping, Tuple, Any

from flask_security import RoleMixin, UserMixin
from pandas import DataFrame
from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey, Index, Integer, LargeBinary, String, Table, Text, UniqueConstraint,
)
from sqlalchemy.orm import backref, relationship

import pybel.struct.query
from pybel import BELGraph, Manager
from pybel.dsl import BaseEntity
from pybel.manager.models import Base, Edge, LONGBLOB, Network
from pybel.struct import union
from .core.models import Query

EXPERIMENT_TABLE_NAME = 'pybel_experiment'
REPORT_TABLE_NAME = 'pybel_report'
ROLE_TABLE_NAME = 'pybel_role'
PROJECT_TABLE_NAME = 'pybel_project'
USER_TABLE_NAME = 'pybel_user'

ROLE_USER_TABLE_NAME = 'pybel_roles_users'
PROJECT_USER_TABLE_NAME = 'pybel_project_user'
PROJECT_NETWORK_TABLE_NAME = 'pybel_project_network'
USER_NETWORK_TABLE_NAME = 'pybel_user_network'
COMMENT_TABLE_NAME = 'pybel_comment'
VOTE_TABLE_NAME = 'pybel_vote'
OVERLAP_TABLE_NAME = 'pybel_overlap'
OMICS_TABLE_NAME = 'pybel_omic'

USER_QUERY_TABLE_NAME = 'pybel_user_query'

roles_users = Table(
    ROLE_USER_TABLE_NAME,
    Base.metadata,
    Column('user_id', Integer, ForeignKey(f'{USER_TABLE_NAME}.id'), primary_key=True),
    Column('role_id', Integer, ForeignKey(f'{ROLE_TABLE_NAME}.id'), primary_key=True),
)

users_networks = Table(
    USER_NETWORK_TABLE_NAME,
    Base.metadata,
    Column('user_id', Integer, ForeignKey(f'{USER_TABLE_NAME}.id'), primary_key=True),
    Column('network_id', Integer, ForeignKey(f'{Network.__tablename__}.id'), primary_key=True),
)

projects_users = Table(
    PROJECT_USER_TABLE_NAME,
    Base.metadata,
    Column('project_id', Integer, ForeignKey(f'{PROJECT_TABLE_NAME}.id'), primary_key=True),
    Column('user_id', Integer, ForeignKey(f'{USER_TABLE_NAME}.id'), primary_key=True),
)

projects_networks = Table(
    PROJECT_NETWORK_TABLE_NAME,
    Base.metadata,
    Column('project_id', Integer, ForeignKey(f'{PROJECT_TABLE_NAME}.id'), primary_key=True),
    Column('network_id', Integer, ForeignKey(f'{Network.__tablename__}.id'), primary_key=True),
)


class Role(Base, RoleMixin):
    """Represents the role of a user in BEL Commons."""

    __tablename__ = ROLE_TABLE_NAME
    id = Column(Integer, primary_key=True)

    name = Column(String(80), unique=True, nullable=False)
    description = Column(Text)

    def __str__(self):  # noqa: D105
        return self.name

    def to_json(self) -> Mapping:
        """Output this role as a JSON dictionary."""
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
        }


class User(Base, UserMixin):
    """Represents a user of BEL Commons."""

    __tablename__ = USER_TABLE_NAME
    id = Column(Integer, primary_key=True)

    email = Column(String(255), unique=True, doc="The user's email")
    password = Column(String(255))
    name = Column(String(255), doc="The user's name")
    active = Column(Boolean)
    confirmed_at = Column(DateTime)

    roles = relationship(Role, secondary=roles_users, backref=backref('users', lazy='dynamic'))
    networks = relationship(Network, secondary=users_networks, backref=backref('users', lazy='dynamic'))

    @property
    def is_admin(self) -> bool:
        """Return if this user is an administrator."""
        return self.has_role('admin')

    @property
    def is_beta_tester(self) -> bool:
        """Return if this user is a beta tester."""
        return self.is_admin or self.has_role('beta')

    def iter_owned_networks(self) -> Iterable[Network]:
        """Iterate over all networks this user owns."""
        return (
            report.network
            for report in self.reports
            if report.network
        )

    def iter_shared_networks(self) -> Iterable[Network]:
        """Iterate over all networks shared with this user."""
        return self.networks

    def iter_project_networks(self) -> Iterable[Network]:
        """Iterate over all networks for which projects have granted this user access."""
        # TODO rewrite with joins
        return (
            network
            for project in self.projects
            for network in project.networks
        )

    def iter_available_networks(self) -> Iterable[Network]:
        """Iterate over all owned, shared, and project networks."""
        # TODO write with unions
        return itt.chain(
            self.iter_owned_networks(),
            self.iter_shared_networks(),
            self.iter_project_networks(),
        )

    def get_sorted_queries(self) -> List[Query]:
        """Get a list of sorted queries for this user."""
        queries = (user_query.query for user_query in self.queries)
        return sorted(queries, key=attrgetter('created'), reverse=True)

    def pending_reports(self) -> List[Report]:
        """Get a list of pending reports for this user."""
        return [
            report
            for report in self.reports
            if report.incomplete
        ]

    def get_vote(self, edge: Edge) -> EdgeVote:
        """Get the vote that goes with this edge."""
        return self.votes.filter(EdgeVote.edge == edge).one_or_none()

    def has_project_rights(self, project: Project) -> bool:
        """Return if the given user has rights to the given project."""
        return self.is_authenticated and (self.is_admin or project.has_user(self))

    def has_experiment_rights(self, experiment: Experiment) -> bool:
        """Check if the user has rights to this experiment."""
        return (
            experiment.public or
            self.is_admin or
            self == experiment.user
        )

    def __hash__(self):
        """Hash this user by their email."""
        return hash(self.email)

    def __eq__(self, other) -> bool:
        """Check that this user is the same as another by email."""
        return isinstance(other, User) and self.email == other.email

    def __repr__(self):  # noqa: D105
        return f'<User email={self.email}>'

    def __str__(self):  # noqa: D105
        return self.email

    def to_json(self, include_id: bool = True) -> Mapping:
        """Output this User as a JSON dictionary."""
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

    def owns_network(self, network: Network) -> bool:
        """Check if the user uploaded the network."""
        return network.report and network.report.user == self


class UserQuery(Base):
    """Represents the ownership of a user to a query."""

    __tablename__ = USER_QUERY_TABLE_NAME
    id = Column(Integer, primary_key=True)

    created = Column(DateTime, default=datetime.datetime.utcnow, doc='The date and time of upload')

    user_id = Column(Integer, ForeignKey(f'{User.__tablename__}.id'), nullable=False,
                     doc='The user who created the query')
    user = relationship(User, backref=backref('queries', lazy='dynamic'))

    query_id = Column(Integer, ForeignKey(f'{Query.__tablename__}.id'), nullable=False,
                      doc='The user who created the query')
    query = relationship(Query, backref=backref('user_query', uselist=False))

    public = Column(Boolean, nullable=False, default=False, doc='Should the query be public? Note: users still need'
                                                                'appropriate rights to all networks in assembly')

    __table_args__ = (
        UniqueConstraint(user_id, query_id),
    )

    @staticmethod
    def from_networks(networks: List[Network], user: User) -> UserQuery:
        """Build a query from a list of networks."""
        return UserQuery(
            query=Query.from_networks(networks),
            user=user,
        )

    @staticmethod
    def from_network(network: Network, user: User) -> UserQuery:
        """Build a query from a network."""
        return UserQuery(
            query=Query.from_network(network),
            user=user,
        )

    @staticmethod
    def from_project(project: Project, user: User) -> UserQuery:
        """Build a query from a project."""
        return UserQuery.from_networks(networks=project.networks, user=user)

    @staticmethod
    def from_query(manager: Manager, query: pybel.struct.query.Query, user: User) -> UserQuery:
        """Build an ORM query from a PyBEL query."""
        q = Query.from_query(manager, query)
        return UserQuery(
            query=q,
            user=user,
        )

    def seeding_to_json(self):
        """Return this query's seeding as a JSON object."""
        return self.query.seeding_to_json()

    def pipeline_to_json(self):
        """Return this query's pipeline as a JSON object."""
        return self.query.pipeline_to_json()

    @property
    def networks(self) -> List[Network]:  # noqa: D401
        """The query's networks"""
        return self.query.networks


class Project(Base):
    """Stores projects."""

    __tablename__ = PROJECT_TABLE_NAME
    id = Column(Integer, primary_key=True)

    name = Column(String(80), unique=True, index=True, nullable=False)
    description = Column(Text)

    users = relationship(User, secondary=projects_users, backref=backref('projects', lazy='dynamic'))

    # TODO why not just use the Assembly table for the many to many relationship?
    networks = relationship(Network, secondary=projects_networks, backref=backref('projects', lazy='dynamic'))

    def has_user(self, user: User) -> bool:
        """Indicate if the given user belongs to the project."""
        return any(
            user.id == u.id
            for u in self.users
        )

    def as_bel(self) -> BELGraph:
        """Return a merged instance of all of the contained networks."""
        return union(network.as_bel() for network in self.networks)

    def __str__(self):  # noqa: D105
        return self.name

    def to_json(self, include_id: bool = True) -> Mapping[str, Any]:
        """Output this project as a JSON dictionary."""
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


class Omic(Base):
    """Represents a file filled with omic data."""

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
    user = relationship(User, backref=backref('omics', lazy='dynamic'))

    def __repr__(self):
        return f'<Omic id={self.id}, source_name={self.source_name}>'

    def __str__(self):  # noqa: D105
        return str(self.source_name)

    @property
    def pretty_source_name(self) -> str:
        """Get a pretty version of the source data's name."""
        for ext in ('.tsv', '.csv'):
            if self.source_name.endswith(ext):
                return self.source_name[:-len(ext)]

        return self.source_name

    def set_source_df(self, df: DataFrame) -> None:
        """Set the source with a DataFrame by pickling it."""
        self.source = dumps(df)

    def get_source_df(self) -> DataFrame:
        """Load the pickled pandas DataFrame from the source file."""
        return loads(self.source)

    def get_source_dict(self) -> Mapping[str, float]:
        """Get a dictionary from gene to value."""
        df = self.get_source_df()
        gene_column = self.gene_column
        data_column = self.data_column

        df_cols = [gene_column, data_column]

        return {
            gene: value
            for _, gene, value in df.loc[df[gene_column].notnull(), df_cols].itertuples()
        }

    def to_json(self, include_id: bool = True) -> Dict[str, Any]:
        """Serialize as a dictionary."""
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
    """Represents an experiment."""

    __tablename__ = EXPERIMENT_TABLE_NAME
    id = Column(Integer, primary_key=True)

    created = Column(DateTime, default=datetime.datetime.utcnow, doc='The date on which this analysis was run')
    public = Column(Boolean, nullable=False, default=False, doc='Should the experimental results be public?')

    query_id = Column(Integer, ForeignKey(f'{Query.__tablename__}.id'), nullable=False, index=True)
    query = relationship(Query, backref=backref("experiments", lazy='dynamic'))

    user_id = Column(Integer, ForeignKey(f'{User.__tablename__}.id'))
    user = relationship(User, backref=backref('experiments', lazy='dynamic'))

    omic_id = Column(Integer, ForeignKey(f'{Omic.__tablename__}.id'), nullable=False, index=True)
    omic = relationship(Omic, backref=backref('experiments', lazy='dynamic'))

    type = Column(String(8), nullable=False, default='CMPA', index=True,
                  doc='Analysis type. CMPA (Heat Diffusion), RCR, etc.')
    permutations = Column(Integer, nullable=False, default=100, doc='Number of permutations performed')
    result = Column(LargeBinary(LONGBLOB), doc='The result python dictionary')

    completed = Column(Boolean, default=False)
    time = Column(Float, nullable=True)

    def get_source_df(self) -> DataFrame:
        """Load the pickled pandas DataFrame from the source file."""
        return self.omic.get_source_df()

    def dump_results(self, scores: Mapping[BaseEntity, Tuple]) -> None:
        """Dump the results and marks this experiment as complete.

        :param scores: The scores to store in this experiment
        """
        self.result = dumps(scores)
        self.completed = True

    def get_results_df(self) -> Mapping[BaseEntity, Tuple]:
        """Load the pickled pandas DataFrame back into an object."""
        return loads(self.result)

    def get_data_list(self) -> List[Tuple[BaseEntity, Tuple]]:
        """Load the data into a usable list."""
        return [
            (node, scores)
            for node, scores in self.get_results_df().items()
            if scores[0]
        ]

    def __repr__(self):
        return f'<Experiment omic_id={self.omic_id}, query_id={self.query_id}>'

    @property
    def source_name(self) -> str:
        """Get a pretty version of the source data's name."""
        return self.omic.pretty_source_name


class Report(Base):
    """Stores information about compilation and uploading events."""

    __tablename__ = REPORT_TABLE_NAME
    id = Column(Integer, primary_key=True)

    task_uuid = Column(String(36), nullable=True, doc='The celery queue UUID')

    user_id = Column(Integer, ForeignKey('{}.id'.format(USER_TABLE_NAME)), doc='The user who uploaded the network')
    user = relationship(User, backref=backref('reports', lazy='dynamic'))

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
        ForeignKey(f'{Network.__tablename__}.id'),
        nullable=True,
        doc='The network that was uploaded'
    )
    network = relationship(Network, backref=backref('report', uselist=False))

    def get_lines(self) -> List[str]:
        """Decode the lines stored in this."""
        return codecs.decode(self.source, self.encoding or 'utf-8').split('\n')

    def dump_calculations(self, calculations: Mapping) -> None:
        """Store a summary calculations dictionary."""
        self.calculations = dumps(calculations)

    def get_calculations(self) -> Dict:
        """Get the summary calculations dictionary from this network."""
        return loads(self.calculations)

    @property
    def is_displayable(self) -> bool:
        """Is this network small enough to confidently display?"""
        return self.number_nodes and self.number_nodes < 100

    @property
    def incomplete(self) -> bool:
        """Check if this task is still running."""
        return self.completed is None and not self.message

    @property
    def failed(self) -> bool:
        """Check if this task failed."""
        return self.completed is not None and not self.completed

    @property
    def stalled(self) -> bool:
        """Return true if a job is older than 3 hours."""
        return datetime.datetime.utcnow() - self.created > datetime.timedelta(hours=3)

    def as_info_json(self) -> Dict:
        """Return this object as a JSON summary."""
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
            return f'<Report {self.id}: incomplete {self.source_name}>'

        if self.failed:
            return f'<Report {self.id}: failed)>'

        if self.network:
            return f'<Report {self.id}: completed {self.network}>'

        return f'<Report {self.id}: cancelled>'


class EdgeVote(Base):
    """Describes the vote on an edge."""

    __tablename__ = VOTE_TABLE_NAME
    id = Column(Integer, primary_key=True)

    edge_id = Column(Integer, ForeignKey(f'{Edge.__tablename__}.id'), nullable=False)
    edge = relationship(Edge, backref=backref('votes', lazy='dynamic', cascade="all, delete-orphan"))

    user_id = Column(Integer, ForeignKey(f'{User.__tablename__}.id'), nullable=False,
                     doc='The user who made this vote')
    user = relationship(User, backref=backref('votes', lazy='dynamic'))

    agreed = Column(Boolean, nullable=True)
    changed = Column(DateTime, default=datetime.datetime.utcnow)

    __table_args__ = (
        UniqueConstraint(edge_id, user_id),
    )

    def to_json(self) -> Dict:
        """Convert this vote to JSON."""
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
    """Describes the comments on an edge."""

    __tablename__ = COMMENT_TABLE_NAME
    id = Column(Integer, primary_key=True)

    edge_id = Column(Integer, ForeignKey(f'{Edge.__tablename__}.id'))
    edge = relationship(Edge, backref=backref('comments', lazy='dynamic', cascade="all, delete-orphan"))

    user_id = Column(Integer, ForeignKey(f'{User.__tablename__}.id'), nullable=False,
                     doc='The user who made this comment')
    user = relationship(User, backref=backref('comments', lazy='dynamic'))

    comment = Column(Text, nullable=False)
    created = Column(DateTime, default=datetime.datetime.utcnow)

    __table_args__ = (
        UniqueConstraint(edge_id, user_id),
    )

    def to_json(self) -> Dict:
        """Convert this comment to JSON."""
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
    """Describes the network overlap based on nodes."""

    __tablename__ = OVERLAP_TABLE_NAME

    left_id = Column(Integer, ForeignKey(f'{Network.__tablename__}.id'), primary_key=True)
    left = relationship(Network, foreign_keys=[left_id],
                        backref=backref('overlaps', lazy='dynamic', cascade="all, delete-orphan"))

    right_id = Column(Integer, ForeignKey(f'{Network.__tablename__}.id'), primary_key=True)
    right = relationship(Network, foreign_keys=[right_id],
                         backref=backref('incoming_overlaps', lazy='dynamic', cascade="all, delete-orphan"))

    overlap = Column(Float, nullable=False, doc='The node overlap between the two networks')

    @staticmethod
    def build(left: Network, right: Network, overlap: float) -> NetworkOverlap:
        """Build an overlap and ensure the order is correct."""
        if left.id < right.id:
            left, right = right, left

        return NetworkOverlap(left=left, right=right, overlap=overlap)
