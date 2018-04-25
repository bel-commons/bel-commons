# -*- coding: utf-8 -*-

"""This module contains the optional managers"""

import logging

from pybel.constants import get_cache_connection
from pybel_tools.pipeline import in_place_mutator

__all__ = [
    'chebi_manager',
    'hgnc_manager',
    'mirtarbase_manager',
    'expasy_manager',
    'go_manager',
    'entrez_manager',
    'interpro_manager',
    'manager_dict',
]

log = logging.getLogger(__name__)

connection = get_cache_connection()

try:
    import bio2bel_chebi
except ImportError:
    chebi_manager = None
else:
    log.info('Using Bio2BEL ChEBI')
    chebi_manager = bio2bel_chebi.Manager(connection=connection)
    chebi_manager.create_all()
    in_place_mutator(chebi_manager.enrich_chemical_hierarchy)

try:
    import bio2bel_hgnc
except ImportError:
    hgnc_manager = None
else:
    log.info('Using Bio2BEL HGNC')
    hgnc_manager = bio2bel_hgnc.Manager(connection=connection)
    hgnc_manager.create_all()
    in_place_mutator(hgnc_manager.enrich_genes_with_families)
    in_place_mutator(hgnc_manager.enrich_families_with_genes)

try:
    import bio2bel_mirtarbase
except ImportError:
    mirtarbase_manager = None
else:
    log.info('Using Bio2BEL miRTarBase')
    mirtarbase_manager = bio2bel_mirtarbase.Manager(connection=connection)
    mirtarbase_manager.create_all()
    in_place_mutator(mirtarbase_manager.enrich_mirnas)
    in_place_mutator(mirtarbase_manager.enrich_rnas)

try:
    import bio2bel_expasy
except ImportError:
    expasy_manager = None
else:
    log.info('Using Bio2BEL ExPASy')
    expasy_manager = bio2bel_expasy.Manager(connection=connection)
    expasy_manager.create_all()
    in_place_mutator(expasy_manager.enrich_proteins_with_enzyme_families)
    in_place_mutator(expasy_manager.enrich_enzymes)

try:
    import bio2bel_go
except ImportError:
    go_manager = None
else:
    log.info('Using Bio2BEL GO')
    go_manager = bio2bel_go.Manager()
    in_place_mutator(go_manager.enrich_bioprocesses)

try:
    import bio2bel_entrez
except ImportError:
    entrez_manager = None
else:
    log.info('Using Bio2BEL Entrez')
    entrez_manager = bio2bel_entrez.Manager(connection=connection)
    entrez_manager.create_all()

try:
    import bio2bel_interpro
except ImportError:
    interpro_manager = None
else:
    log.info('Using Bio2BEL InterPro')
    interpro_manager = bio2bel_interpro.Manager(connection=connection)
    interpro_manager.create_all()

try:
    import bio2bel_ctd
except ImportError:
    ctd_manager = None
else:
    log.info('Using Bio2BEL CTD')
    ctd_manager = bio2bel_ctd.Manager(connection=connection)
    ctd_manager.create_all()
    in_place_mutator(ctd_manager.enrich_graph_genes)

try:
    import bio2bel_hmdb
except ImportError:
    hmdb_manager = None
else:
    log.info('Using Bio2BEL HMDB')
    hmdb_manager = bio2bel_hmdb.Manager(connection=connection)
    hmdb_manager.create_all()

try:
    import bio2bel_hmdd
except ImportError:
    hmdd_manager = None
else:
    log.info('Using Bio2BEL HMDD')
    hmdd_manager = bio2bel_hmdd.Manager(connection=connection)
    hmdd_manager.create_all()

try:
    import bio2bel_mir2disease
except ImportError:
    mir2disease_manager = None
else:
    log.info('Using Bio2BEL mir2disease')
    mir2disease_manager = bio2bel_mir2disease.Manager(connection=connection)
    mir2disease_manager.create_all()

try:
    import bio2bel_drugbank
except ImportError:
    drugbank_manager = None
else:
    log.info('Using Bio2BEL DrugBank')
    drugbank_manager = bio2bel_drugbank.Manager(connection=connection)
    drugbank_manager.create_all()

try:
    import bio2bel_phosphosite
except ImportError:
    phosphosite_manager = None
else:
    log.info('Using Bio2BEL PhosphoSitePlus')
    phosphosite_manager = bio2bel_phosphosite.Manager(connection=connection)
    phosphosite_manager.create_all()

manager_dict = {
    name: manager
    for name, manager in locals().items()
    if name.endswith('_manager') and manager
}
