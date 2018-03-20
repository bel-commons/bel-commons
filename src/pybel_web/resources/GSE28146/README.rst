GSE28146
========
This folder contains the results from differential gene expression analysis performed using the attached R script,
which is slightly modified from the output from GEO2R on experiment for `GSE28146 <https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE28146>`_.
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
Blalock, E. M., *et al.* (2011). `Microarray analyses of laser-captured hippocampus reveal distinct gray and white
matter signatures associated with incipient Alzheimer’s disease <https://doi.org/10.1016/j.jchemneu.2011.06.007>`_.
Journal of Chemical Neuroanatomy, 42(2), 118–26.
