# The public evaluation data on Nebius Object Storage

The public half of `data/eval/` is mirrored to a public, read-only Nebius Object Storage
bucket, so anyone can fetch a report or a set without cloning the repo:

    https://storage.uk-south1.nebius.cloud/herbtwin-public-eval/<key>

A key is the file's path below `data/eval/`. For example, `data/eval/reports/README.md` is
`https://storage.uk-south1.nebius.cloud/herbtwin-public-eval/reports/README.md`.

## What is in it

The same files this repo carries under `data/eval/`, and nothing else:

- `reports/`: the evaluation reports and their summaries;
- `sets/`: the labelled sets, with ids and labels only (each row names where its photo or
  post came from, under that source's own licence);
- `seasonal/handcheck.json`: the seasonal hand check;
- `prereg/` and `labels/`: the pre-registrations and label files the reports cite.

No photos are in the bucket, and nothing from outside `data/eval/`.

The mirror is refreshed by hand, so it can trail this repo by a report or two; the copy
in this repo is the reference.

## Fetching

One file, with no account or key:

    curl -O https://storage.uk-south1.nebius.cloud/herbtwin-public-eval/reports/README.md

Anonymous listing is allowed, so the bucket URL itself returns an S3-style XML list of
keys; add `?prefix=` to narrow it:

    curl 'https://storage.uk-south1.nebius.cloud/herbtwin-public-eval/?prefix=reports/'

Any S3 client that can make unsigned requests works too, with the endpoint
`https://storage.uk-south1.nebius.cloud`.

## Cost

The mirror is about 1.5 MB. At Nebius's list prices (Oct 2026) storing and serving that
costs well under a cent a month.
