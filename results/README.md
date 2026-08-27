# results/

| Path | Committed | Contents |
|------|-----------|----------|
| `audit/` | yes | Archive listings, md5 records and the data integrity audit |
| `summary/` | yes | Small CSV tables that the paper, report and figures are built from |
| `runs/` | no | Full per-model scores (`scores.parquet`) and logs of each experiment |
| `cache/` | no | Intermediate files that can be recomputed |

Every row in a scores file records the git commit, config hash and data
manifest hash it was produced with, so any number can be traced back to the
code and data that made it.
