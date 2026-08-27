# data/

Nothing in this folder is committed. Recreate it with:

```sh
make data      # processeddata.zip: download (3.5 GB), md5 check, unzip, verify, delete zip
make epochs    # cut and cache the 4 s windows into data/derived/epochs/
```

| Path | Contents | Size |
|------|----------|------|
| `raw/figshare/meta/` | BIDS metadata files and the figshare article record | < 1 MB |
| `raw/figshare/*.zip` | Archives while downloading (deleted after a verified unzip) | 3.5 GB |
| `processed/sub-XX/{pre,post,follow}/` | The authors' preprocessed runs (`*_eeg.mat`, 43 channels, 250 Hz) | 3.6 GB |
| `source/` | Optional raw recordings (`*_original.set/.fdt`), only if needed | 6.5 GB |
| `derived/epochs/` | Cached windows (`*.npz`), `metadata.parquet`, `manifest.json` | about 1.7 GB |

Set `SIXTHFINGER_DATA=/some/other/disk/data` to keep the data elsewhere.

## Source and licence

Wang, Z., Liu, Y., Huang, S. et al. A multi-paradigm and longitudinal EEG
dataset including the "sixth-finger" and "affected-hand" motor imagery of
stroke patients. *Scientific Data* 13, 1109 (2026).
https://doi.org/10.1038/s41597-026-07787-y

Data: https://doi.org/10.6084/m9.figshare.30509165 (version 11), licensed
CC BY 4.0. The figshare page asks users not to use "Download all"; download
each archive separately, as `make data` does.
