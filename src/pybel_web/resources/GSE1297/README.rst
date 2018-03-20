GSE1297
=======
This folder contains the results from differential gene expression analysis performed using the attached R script,
which is slightly modified from the output from GEO2R on experiment for `GSE1297 <https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE1297>`_.
It contains results for three different stages of Alzheimer's disease patients - incipient, moderate, and severe.

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
Blalock, E. M., *et al.* (2004). `Incipient Alzheimer’s disease: microarray correlation analyses reveal major
transcriptional and tumor suppressor responses <https://doi.org/10.1073/pnas.0308512100>`_. Proceedings of the National
Academy of Sciences of the United States of America, 101(7), 2173–8.
