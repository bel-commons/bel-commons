# -*- coding: utf-8 -*-

"""This module contains the optional managers."""

from __future__ import annotations

import logging
from typing import Optional

import flask
from flask import current_app
from werkzeug.local import LocalProxy

from pybel.struct.pipeline import in_place_transformation
from ..constants import SQLALCHEMY_DATABASE_URI

__all__ = [
    'FlaskBio2BEL',
]

logger = logging.getLogger(__name__)


class FlaskBio2BEL:
    """A wrapper around Bio2BEL repositories for Flask."""

    def __init__(self, app: Optional[flask.Flask] = None) -> None:  # noqa: D107
        self.app = app

        self.chebi_manager = None
        self.hgnc_manager = None
        self.mirtarbase_manager = None
        self.phosphosite_manager = None
        self.drugbank_manager = None
        self.mir2disease_manager = None
        self.hmdd_manager = None
        self.hmdb_manager = None
        self.ctd_manager = None
        self.interpro_manager = None
        self.entrez_manager = None
        self.expasy_manager = None
        self.go_manager = None
        self.rgd_manager = None
        self.mgi_manager = None
        self.mesh_manager = None
        self.sider_manager = None
        self.conso_manager = None

        self.manager_dict = {}

        if self.app is not None:
            self.init_app(self.app)

    @property
    def connection(self) -> str:
        """Get the app's connection."""
        return self.app.config[SQLALCHEMY_DATABASE_URI]

    def init_app(self, app: flask.Flask) -> None:  # noqa: C901
        """Initialize a Flask app."""
        self.app = app
        app.extensions['bio2bel'] = self

        try:
            import bio2bel_chebi
        except ImportError:
            pass
        else:
            logger.debug('Using Bio2BEL ChEBI')
            self.chebi_manager = bio2bel_chebi.Manager(connection=self.connection)
            self.chebi_manager.create_all()
            in_place_transformation(self.chebi_manager.enrich_chemical_hierarchy)

        try:
            import bio2bel_hgnc
        except ImportError:
            pass
        else:
            logger.debug('Using Bio2BEL HGNC')
            self.hgnc_manager = bio2bel_hgnc.Manager(connection=self.connection)
            self.hgnc_manager.create_all()
            in_place_transformation(self.hgnc_manager.enrich_genes_with_families)
            in_place_transformation(self.hgnc_manager.enrich_families_with_genes)

        try:
            import bio2bel_mirtarbase
        except ImportError:
            pass
        else:
            logger.debug('Using Bio2BEL miRTarBase')
            self.mirtarbase_manager = bio2bel_mirtarbase.Manager(connection=self.connection)
            self.mirtarbase_manager.create_all()
            in_place_transformation(self.mirtarbase_manager.enrich_mirnas)
            in_place_transformation(self.mirtarbase_manager.enrich_rnas)

        try:
            import bio2bel_expasy
        except ImportError:
            pass
        else:
            logger.debug('Using Bio2BEL ExPASy')
            self.expasy_manager = bio2bel_expasy.Manager(connection=self.connection)
            self.expasy_manager.create_all()
            in_place_transformation(self.expasy_manager.enrich_proteins_with_enzyme_families)
            in_place_transformation(self.expasy_manager.enrich_enzymes)

        try:
            import bio2bel_go
        except ImportError:
            pass
        else:
            logger.debug('Using Bio2BEL GO')
            self.go_manager = bio2bel_go.Manager(connection=self.connection)
            in_place_transformation(self.go_manager.enrich_bioprocesses)

        try:
            import bio2bel_entrez
        except ImportError:
            pass
        else:
            logger.debug('Using Bio2BEL Entrez')
            self.entrez_manager = bio2bel_entrez.Manager(connection=self.connection)
            self.entrez_manager.create_all()

        try:
            import bio2bel_interpro
        except ImportError:
            pass
        else:
            logger.debug('Using Bio2BEL InterPro')
            self.interpro_manager = bio2bel_interpro.Manager(connection=self.connection)
            self.interpro_manager.create_all()

        try:
            import bio2bel_ctd
        except ImportError:
            pass
        else:
            logger.debug('Using Bio2BEL CTD')
            self.ctd_manager = bio2bel_ctd.Manager(connection=self.connection)
            self.ctd_manager.create_all()
            in_place_transformation(self.ctd_manager.enrich_graph_genes)

        try:
            import bio2bel_hmdb
        except ImportError:
            pass
        else:
            logger.debug('Using Bio2BEL HMDB')
            self.hmdb_manager = bio2bel_hmdb.Manager(connection=self.connection)
            self.hmdb_manager.create_all()

        try:
            import bio2bel_hmdd
        except ImportError:
            pass
        else:
            logger.debug('Using Bio2BEL HMDD')
            self.hmdd_manager = bio2bel_hmdd.Manager(connection=self.connection)
            self.hmdd_manager.create_all()

        try:
            import bio2bel_mir2disease
        except ImportError:
            pass
        else:
            logger.debug('Using Bio2BEL mir2disease')
            self.mir2disease_manager = bio2bel_mir2disease.Manager(connection=self.connection)
            self.mir2disease_manager.create_all()

        try:
            import bio2bel_drugbank
        except ImportError:
            pass
        else:
            logger.debug('Using Bio2BEL DrugBank')
            self.drugbank_manager = bio2bel_drugbank.Manager(connection=self.connection)
            self.drugbank_manager.create_all()

        try:
            import bio2bel_phosphosite
        except ImportError:
            pass
        else:
            logger.debug('Using Bio2BEL PhosphoSitePlus')
            self.phosphosite_manager = bio2bel_phosphosite.Manager(connection=self.connection)
            self.phosphosite_manager.create_all()

        try:
            import bio2bel_sider
        except ImportError:
            pass
        else:
            logger.debug('Using Bio2BEL SIDER')
            self.sider_manager = bio2bel_sider.Manager(connection=self.connection)
            self.sider_manager.create_all()

        try:
            import bio2bel_mesh
        except ImportError:
            pass
        else:
            logger.debug('Using Bio2BEL MeSH')
            self.mesh_manager = bio2bel_mesh.Manager(connection=self.connection)
            self.mesh_manager.create_all()

        try:
            import bio2bel_mgi
        except ImportError:
            pass
        else:
            logger.debug('Using Bio2BEL MGI')
            self.mgi_manager = bio2bel_mgi.Manager(connection=self.connection)
            self.mgi_manager.create_all()

        try:
            import bio2bel_rgd
        except ImportError:
            pass
        else:
            logger.debug('Using Bio2BEL RGD')
            self.rgd_manager = bio2bel_rgd.Manager(connection=self.connection)
            self.rgd_manager.create_all()

        try:
            import conso.manager
        except ImportError:
            pass
        else:
            logger.debug('Using Bio2BEL CONSO')
            self.conso_manager = conso.manager.Manager()

        self.manager_dict.update({
            name: manager
            for name, manager in self.__dict__.items()
            if name.endswith('_manager') and manager is not None
        })

    @classmethod
    def get_proxy(cls) -> FlaskBio2BEL:
        """Get a proxy for the manager from this app."""
        return LocalProxy(cls._get_bio2bel)

    @classmethod
    def _get_bio2bel(cls) -> FlaskBio2BEL:
        return cls.get_bio2bel(current_app)

    @staticmethod
    def get_bio2bel(app: flask.Flask) -> FlaskBio2BEL:
        """Get the manager from this app."""
        return app.extensions['bio2bel']
