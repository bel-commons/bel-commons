GSE63063
========
This folder contains the results from differential gene expression analysis performed using the attached R script,
which is slightly modified from the output from GEO2R on experiment for `GSE63063 <https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE63063>`_.
It comes from the public AddNeuroMed and has control, mild cognitive impairment (MCI), and Alzheimer's disease (AD)
patients.

The metadata associated with these three files is stored in ``metadata.json``.

How to Run
----------
Unfortunately, R is not the most reproducible language. These scripts were run with R version 3.4.2.

Requirements
************
Install the bioconductor dependencies based on the tutorial from https://www.bioconductor.org/install/. First, try:

.. code-block::r

    source("https://bioconductor.org/biocLite.R")
    biocLite(c("Biobase", "GEOquery", "limma"))

If that doesn't work, try:

.. code-block::r

    install.packages('Biobase')
    install.packages('GEOquery')
    install.packages('limma')

Execute
*******
``cd`` into the directory and user ``rscript process.r``

Reference
---------
Sood S, *et al.* (2015). `A novel multi-tissue RNA diagnostic of healthy ageing relates to cognitive health
status <https://www.ncbi.nlm.nih.gov/pubmed/26343147>`_. *Genome Biol* Sep 7;16:185
