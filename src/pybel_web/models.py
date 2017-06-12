# -*- coding: utf-8 -*-

import datetime

from flask_security import RoleMixin, UserMixin
from sqlalchemy import Column, Integer, ForeignKey, DateTime, Boolean, Text, Binary, Table, String
from sqlalchemy.orm import relationship, backref

from pybel.manager import Base
from pybel.manager.models import NETWORK_TABLE_NAME

import pybel_tools.query
from pybel_tools import pipeline

EXPERIMENT_TABLE_NAME = 'pybel_experiment'
REPORT_TABLE_NAME = 'pybel_report'
ROLE_TABLE_NAME = 'pybel_role'
USER_TABLE_NAME = 'pybel_user'
ASSEMBLY_TABLE_NAME = 'pybel_assembly'
ASSEMBLY_NETWORK_TABLE_NAME = 'pybel_assembly_network'
QUERY_TABLE_NAME = 'pybel_query'


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
    'roles_users',
    Base.metadata,
    Column('user_id', Integer, ForeignKey('{}.id'.format(USER_TABLE_NAME))),
    Column('role_id', Integer, ForeignKey('{}.id'.format(ROLE_TABLE_NAME)))
)


class Role(Base, RoleMixin):
    """Stores user roles"""
    __tablename__ = ROLE_TABLE_NAME
    id = Column(Integer(), primary_key=True)
    name = Column(String(80), unique=True, nullable=False)
    description = Column(String(255))

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

    @property
    def admin(self):
        """Is this user an administrator?"""
        return self.has_role('admin')

    @property
    def name(self):
        """Shows the full name of the user"""
        return '{} {}'.format(self.first_name, self.last_name) if self.first_name else self.email

    def __str__(self):
        return repr(self)

    def __repr__(self):
        return '<User {}>'.format(self.email)


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


class Query(Base):
    """Describes a :class:`pybel_tools.pipeline.Query`"""
    __tablename__ = QUERY_TABLE_NAME

    id = Column(Integer(), primary_key=True)

    user_id = Column(Integer, ForeignKey('{}.id'.format(USER_TABLE_NAME)), doc='The user who created the query')
    user = relationship('User', backref=backref('queries', lazy='dynamic'))

    assembly_id = Column(Integer, ForeignKey('{}.id'.format(ASSEMBLY_TABLE_NAME)), doc='The network assembly used in this query')
    assembly = relationship('Assembly')

    seeding = Column(Text, doc="List representation of the seeding")

    pipeline_protocol = Column(Text, doc="Protocol list")

    dump = Column(Text, doc="The stringified JSON representing this query")

    @property
    def data(self):
        """Converts this object to a :class:`pybel_tools.pipeline.Query` object

        :rtype: pybel_tools.query.Query
        """
        return pybel_tools.query.Query.from_jsons(self.dump)

    def run(self, api):
        """A wrapper around the :meth:`pybel_tools.pipeline.Query.run` function of the enclosed
        :class:`pybel_tools.pipeline.Query` object.

        :param pybel_tools.api.DatabaseService api:
        :rtype: pybel.BELGraph
        """
        return self.data.run(api)
