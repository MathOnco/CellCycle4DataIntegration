This repository is an accompaniment to the paper: Cell identity revealed by precise cell cycle state mapping links
data modalities. 

### Contents
  1. data4paper
  2. figs4paper
  3. continuousCCprediction_figures4paper.Rmd

### data4paper
This folder contains three subfolders which hold much of the data required to generate the results of the paper.
  1. A01_rawData: The original images; three channels, 70 z slices, and 4 fields of view; along with the metadata from image collection.
  2. A06_multiSignals_Linked: Single cell visualizations, cell segmentation coordinates per channel per cell, and the raw cell feature data as a .txt.
  3. A08_Pseudotime: The cycle predictions from the models discussed in the paper, along with data objects for use in R.

### figs4paper
This folder contains input images for generating the figures in the paper. Some of these images are required as they are:
  1. Raw images
  2. Processed in ImageJ
  3. Hand spliced for better resolution, spacing, and coherency

### continuousCCprediction_figures4paper.Rmd
This Rmarkdown contains the code required to generate the majority of the figures included in the paper: Fig1, 3, 4, 5; Supplementary Fig1, 2, 3, 5; and Supplementary Tables 1, 2.

For insight into the generation of Supplementary Figure 4, see doi: 10.1016/j.patter.2022.100523.
