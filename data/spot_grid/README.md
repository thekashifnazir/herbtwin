# Spot grid: 1 km location priors for "What can I grow here?"

`grid.bin.gz` holds one record per 1 km British National Grid cell over Great Britain's
land (241,514 cells): the soil texture band and lime, a topsoil pH range, air-frost nights
by month, ground-frost nights a year, the coldest month's mean minimum and sunshine hours a
year. Read by `src/herbtwin/spot_priors.py`; format in its docstring.

Built by `scripts/build_spot_grid.py` (see its docstring for the command) from:

| Source | Licence | Credit |
|---|---|---|
| BGS Soil Parent Material Model 1 km (SPMM_1km.zip, fetched 11 Oct 2026) | Open Government Licence | Contains British Geological Survey materials © UKRI |
| UKCEH Countryside Survey topsoil pH 1 km model (fetched 11 Oct 2026) | Open Government Licence | Henrys, Keith, Robinson and Emmett (2012), NERC EIDC |
| Met Office HadUK-Grid v1.3.2 1 km monthly normals 1991-2020 (fetched 12 Oct 2026) | Open Government Licence v3 | Met Office HadUK-Grid, via CEDA |

Derived values, not the source files: texture words mapped to sandy, loamy or clayey;
pH as the 2007 modelled mean plus or minus 0.5; frost and sunshine rounded to 0.1 night
and whole hours. A cell with no Countryside Survey value (mostly built-up land) is marked
urban. Rebuilding from the same sources gives the same bytes.
