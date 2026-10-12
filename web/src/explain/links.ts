// Everything the page refers to, in one place. The repository links point at the public
// copy of this project.

const REPO = "https://github.com/rajveeerr/sixth-finger-bci";

export const LINKS = {
  paper: {
    url: "https://doi.org/10.1038/s41597-026-07787-y",
    title: "The dataset paper",
    note: "Wang et al., \"A multi-paradigm and longitudinal EEG dataset including the 'sixth-finger' and 'affected-hand' motor imagery of stroke patients\", Scientific Data 13, 1109 (2026).",
  },
  data: {
    url: "https://doi.org/10.6084/m9.figshare.30509165",
    title: "The recordings",
    note: "The EEG of all 24 patients on figshare, free to use with credit (CC BY 4.0).",
  },
  eegnet: {
    url: "https://doi.org/10.1088/1741-2552/aace8c",
    title: "EEGNet",
    note: "Lawhern et al., \"EEGNet: a compact convolutional neural network for EEG-based brain-computer interfaces\", Journal of Neural Engineering (2018). The model in the demo.",
  },
  code: {
    url: REPO,
    title: "Our code and results",
    note: "Everything behind this page: the analysis, the tests, the model and this demo.",
  },
  audit: {
    url: `${REPO}/blob/main/results/audit/audit_report.md`,
    title: "Our data audit",
    note: "Every pair of runs we compared and what we dropped.",
  },
  card: {
    url: `${REPO}/blob/main/docs/dataset-card.md`,
    title: "Dataset card",
    note: "The dataset in one page: patients, task, signals and known issues.",
  },
};
