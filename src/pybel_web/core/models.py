# -*- coding: utf-8 -*-

"""SQLAlchemy models for PyBEL Web."""

import datetime
from typing import Dict, Iterable, List, Mapping, Optional, Union

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Table, Text
from sqlalchemy.orm import backref, relationship

import pybel.struct
from pybel import BELGraph, Manager, Pipeline, union
from pybel.dsl import BaseEntity
from pybel.manager import Base, Network
from pybel.struct.query import Seeding
from pybel.utils import _hash_tuple

__all__ = [
    'Assembly',
    'assembly_network',
    'Query',
]

ASSEMBLY_TABLE_NAME = 'pybel_assembly'
ASSEMBLY_NETWORK_TABLE_NAME = 'pybel_assembly_network'
QUERY_TABLE_NAME = 'pybel_query'

assembly_network = Table(
    ASSEMBLY_NETWORK_TABLE_NAME,
    Base.metadata,
    Column('network_id', Integer, ForeignKey('{}.id'.format(Network.__tablename__))),
    Column('assembly_id', Integer, ForeignKey('{}.id'.format(ASSEMBLY_TABLE_NAME)))
)


class Assembly(Base):
    """Describes an assembly of networks."""

    __tablename__ = ASSEMBLY_TABLE_NAME
    id = Column(Integer, primary_key=True)

    created = Column(DateTime, default=datetime.datetime.utcnow, doc='The date and time of upload')

    name = Column(String(255), unique=True, nullable=True)
    sha512 = Column(String(255), nullable=True, index=True)

    networks = relationship(Network, secondary=assembly_network, backref=backref('assemblies', lazy='dynamic'))

    def as_bel(self) -> BELGraph:
        """Return a merged instance of all of the contained networks."""
        return union(network.as_bel() for network in self.networks)

    @classmethod
    def from_networks(cls, networks: List[Network]) -> 'Assembly':
        """Build an assembly from a list of networks."""
        return Assembly(
            networks=networks,
            sha512=cls.get_network_list_sha512(networks),
        )

    @staticmethod
    def get_network_list_sha512(networks: List[Network]) -> str:
        """Build a sorted tuple of the unique network identifiers and hash it with SHA-512."""
        return _hash_tuple(tuple(sorted({network.id for network in networks})))

    @staticmethod
    def from_network(network: Network) -> 'Assembly':
        """Builds an assembly from a singular network."""
        return Assembly.from_networks(networks=[network])

    def to_json(self) -> Mapping:
        """Return a JSON summary of this assembly."""
        result = {
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
    """Describes a :class:`pybel_tools.query.Query`."""

    __tablename__ = QUERY_TABLE_NAME
    id = Column(Integer, primary_key=True)

    created = Column(DateTime, default=datetime.datetime.utcnow, doc='The date and time of upload')

    assembly_id = Column(Integer, ForeignKey('{}.id'.format(Assembly.__tablename__)),
                         doc='The network assembly used in this query')
    assembly = relationship(Assembly, backref=backref('queries'))

    seeding = Column(Text, doc="The stringified JSON of the list representation of the seeding")
    pipeline = Column(Text, doc="Protocol list")

    parent_id = Column(Integer, ForeignKey('{}.id'.format(__tablename__)), nullable=True)
    parent = relationship('Query', remote_side=[id],
                          backref=backref('children', lazy='dynamic', cascade="all, delete-orphan"))

    @property
    def networks(self) -> List[Network]:
        """Get the networks from the contained assembly."""
        return self.assembly.networks

    @property
    def network_ids(self) -> List[int]:
        """Get the network identifiers from the contained assembly."""
        return [network.id for network in self.assembly.networks]

    def __repr__(self):
        return '<Query id={}>'.format(self.id)

    """Seeding"""

    def set_seeding_from_query(self, query: pybel.struct.query.Query) -> None:
        """Set the seeding container from a PyBEL Query."""
        self.seeding = query.seeding.dumps()

    def get_seeding(self) -> Optional[Seeding]:
        """Get the seeding container, if it has any entries."""
        if self.seeding:
            return Seeding.loads(self.seeding)

    def seeding_to_json(self) -> Optional[List[Mapping]]:
        """Return seeding json, if it has any entries."""
        seeding = self.get_seeding()
        if seeding:
            return seeding.to_json()

    def set_pipeline_from_query(self, query: pybel.struct.query.Query) -> None:
        """Set the pipeline value from a PyBEL Tools query."""
        self.pipeline = query.pipeline.dumps()

    """Pipeline"""

    def get_pipeline(self) -> Optional[Pipeline]:
        """Get the pipeline, if it has any entries."""
        if self.pipeline:
            return Pipeline.loads(self.pipeline)

    def pipeline_to_json(self) -> Optional[List[Mapping]]:
        """Return the pipeline as json, if it has any entries."""
        pipeline = self.get_pipeline()
        if pipeline:
            return pipeline.to_json()

    def _get_query(self) -> pybel.struct.query.Query:
        """Convert this object to a query object."""
        if not hasattr(self, '_query'):
            self._query = pybel.struct.query.Query(
                network_ids=self.network_ids,
                seeding=self.get_seeding(),
                pipeline=self.get_pipeline(),
            )

        return self._query

    def to_json(self, include_id: bool = True) -> Dict:
        """Serialize this object to JSON.

        :param include_id: Should the identifier be included?
        """
        result = self._get_query().to_json()

        if include_id:
            result['id'] = self.id

        return result

    def run(self, manager: Manager) -> Optional[BELGraph]:
        """Run the enclosed query."""
        return self._get_query().run(manager)

    """Constructors"""

    @staticmethod
    def from_assembly(assembly: Assembly) -> 'Query':
        """Build a query from an assembly."""
        return Query(assembly=assembly)

    @staticmethod
    def from_networks(networks: List[Network]) -> 'Query':
        """Build a query from a network."""
        assembly = Assembly.from_networks(networks)
        return Query.from_assembly(assembly)

    @staticmethod
    def from_network(network: Network) -> 'Query':
        """Build a query from a network"""
        return Query.from_networks(networks=[network])

    @staticmethod
    def from_query(manager: Manager, query: pybel.struct.query.Query) -> 'Query':
        """Build an ORM query from a PyBEL query."""
        networks = manager.get_networks_by_ids(query.network_ids)
        result = Query.from_networks(networks)
        result.set_seeding_from_query(query)
        result.set_pipeline_from_query(query)
        return result

    @staticmethod
    def from_query_args(manager: Manager, network_ids: List[int], seeding: Optional[Seeding] = None,
                        pipeline: Optional[Pipeline] = None) -> 'Query':
        """Build an ORM model from the arguments for a PyBEL query."""
        q = pybel.struct.query.Query(network_ids, seeding=seeding, pipeline=pipeline)
        return Query.from_query(manager, q)

    """Derived queries"""

    def get_assembly_query(self) -> 'Query':
        """Return a new query, just with the same assembly as this one."""
        return Query(
            assembly=self.assembly,
            parent=self,
        )

    def build_appended(self, name, *args, **kwargs) -> 'Query':
        """Build a new query with the given function appended to the current query's pipeline.

        :param str name: Append function name
        :param args: Append function positional arguments
        :param kwargs: Append function keyword arguments
        """
        pipeline = self.get_pipeline() or Pipeline()
        pipeline.append(name, *args, **kwargs)

        return Query(
            parent_id=self.id,
            assembly=self.assembly,
            seeding=self.seeding,
            pipeline=pipeline.dumps(),
        )

    def add_seed_neighbors(self, nodes: Union[BaseEntity, Iterable[BaseEntity]]) -> 'Query':
        """Add a seed by neighbors and return a new query."""
        seeding = self.get_seeding() or Seeding()
        seeding.append_neighbors(nodes)

        return Query(
            parent_id=self.id,
            assembly=self.assembly,
            seeding=seeding.dumps(),
            pipeline=self.pipeline,
        )
