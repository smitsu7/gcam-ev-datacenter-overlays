# Parameter Provenance and Derivation

This note defines the provenance standard used in this repository after the
`2026-03-22` source audit.

The rule is simple:

- if a number is claimed as `IEA`, it must be visible in the archived public source extract
- if a number is not directly visible in the archived public source extract, it must be written as an explicit calculation from those source numbers
- if a number is still neither of those things, it must be labeled as a repository-side modeling device

## Machine-Readable Source Packages

- EV public extract:
  - [iea_global_ev_outlook_2024_public_extract.json](/Users/sekiyamitsuna/CodexCLI/GCAM/gcam-ev-datacenter-overlays/data/source_exports/iea_global_ev_outlook_2024_public_extract.json)
- Datacenter public extract:
  - [iea_energy_and_ai_2025_public_extract.json](/Users/sekiyamitsuna/CodexCLI/GCAM/gcam-ev-datacenter-overlays/data/source_exports/iea_energy_and_ai_2025_public_extract.json)
- EV assumptions:
  - [ev_ssp_assumptions.json](/Users/sekiyamitsuna/CodexCLI/GCAM/gcam-ev-datacenter-overlays/data/ev_ssp_assumptions.json)
- Datacenter assumptions:
  - [datacenter_ssp_assumptions.json](/Users/sekiyamitsuna/CodexCLI/GCAM/gcam-ev-datacenter-overlays/data/datacenter_ssp_assumptions.json)
- EV generator:
  - [generate_ev_addon.py](/Users/sekiyamitsuna/CodexCLI/GCAM/gcam-ev-datacenter-overlays/scripts/generate_ev_addon.py)
- Datacenter generator:
  - [generate_datacenter_addon.py](/Users/sekiyamitsuna/CodexCLI/GCAM/gcam-ev-datacenter-overlays/scripts/generate_datacenter_addon.py)

## Short Answer

- `EV`
  - now anchored to one IEA edition only: `Global EV Outlook 2024`
  - the public anchors are archived in-repo
  - the GCAM conversion is explicit
  - the remaining non-IEA element is the use of a public `BEV stock share = 70%` statement as a proxy for the within-EV `BEV/PHEV/FCEV` mix
- `Datacenter`
  - now anchored to one IEA edition only: `Energy and AI 2025`
  - the public anchors are archived in-repo
  - the bridge years, regionalization, and post-2035 extension are explicit formulas written from those public anchors
  - the only remaining repository-side modeling device is the tiny `2015` seed used to keep GCAM calibration stable

## EV: Exact Source Logic

### Source edition

The EV module now uses only:

- `IEA (2024), Global EV Outlook 2024`

The archived public extract is:

- [iea_global_ev_outlook_2024_public_extract.json](/Users/sekiyamitsuna/CodexCLI/GCAM/gcam-ev-datacenter-overlays/data/source_exports/iea_global_ev_outlook_2024_public_extract.json)

### Public EV numbers used directly

- `2018 electric-car sales share = 2%`
- `2023 electric-car sales share = 18%`
- `2023 BEV share of electric-car stock = 70%`
- `STEPS 2030 LDV sales share = 40%`
- `STEPS 2035 LDV sales share = 55%`
- `APS 2030 electric LDV sales = 47 million`
- `APS 2035 electric LDV sales = 75 million and two-thirds sales share`
- `NZE 2030 EV sales share = 65%`
- `NZE 2035 light-vehicle sales are zero-emission`

### Scenario mapping

- `SSP1 -> NZE`
- `SSP2 -> STEPS`
- `SSP3 -> STEPS`
- `SSP4 -> STEPS`
- `SSP5 -> APS`

`SSP3` and `SSP4` do not currently have separate EV anchor paths because the chosen single IEA edition does not provide a distinct public global weak-policy pathway that can be archived alongside `STEPS / APS / NZE`.

### EV anchor calculations

The repository computes:

```text
share_2020
= 2.0 * (18.0 / 2.0)^((2020 - 2018) / (2023 - 2018))
= 4.816449370561385%
```

For each scenario `s`, the `2025` point is:

```text
share_2025(s)
= 18.0 + (share_2030(s) - 18.0) * ((2025 - 2023) / (2030 - 2023))
```

Examples:

```text
STEPS 2025
= 18.0 + (40.0 - 18.0) * (2 / 7)
= 24.285714285714285%

APS 2025
= 18.0 + (43.72093023255814 - 18.0) * (2 / 7)
= 25.348837209302324%

NZE 2025
= 18.0 + (65.0 - 18.0) * (2 / 7)
= 31.42857142857143%
```

For `APS 2030`, the repository uses a direct calculation from the same public GEVO-2024 page:

```text
total_LDV_sales_2030
= 43.0 / 0.40
= 107.5 million

APS_share_2030
= 47.0 / 107.5
= 43.72093023255814%
```

After `2035`, the EV sales-share anchor is held constant through `2100`.

### EV technology mix logic

The repository no longer uses unarchived IEA Data Explorer decimals for `BEV/PHEV/FCEV` sales mix.

Instead:

- non-`NZE` scenarios use the public `2023 BEV stock share = 70%` as a transparent proxy:

```text
BEV  = 0.70
PHEV = 0.30
FCEV = 0.00
```

- `NZE` sets:

```text
BEV  = 1.00
PHEV = 0.00
FCEV = 0.00
```

by `2035`, because the same IEA edition states that light-vehicle sales are zero-emission by then.

This is not a direct IEA sales table. It is a documented proxy built from a public IEA stock-share statement.

### EV share-weight conversion

GCAM does not take market shares directly. The add-on converts the target EV shares into GCAM `share-weight` ratios.

Let:

- `N_ref = 3` for `Hybrid Liquids`, `Liquids`, and `NG`
- each non-plugin technology keep `share-weight = 1`
- `clipped_total_ev_share = min(total_ev_share, 0.99)`
- `residual_floor = 0.01`

Then:

```text
target_plugin_share(tech, t) = total_ev_share(t) * plugin_mix(tech, t)

share_weight_plugin(tech, t) =
  N_ref * target_plugin_share(tech, t) /
  max(1 - clipped_total_ev_share(t), residual_floor)
```

Worked example for `SSP2` at `2030`:

```text
total_ev_share = 0.40
plugin_mix_BEV  = 0.70
plugin_mix_PHEV = 0.30
plugin_mix_FCEV = 0.00

share_weight_BEV
= 3 * (0.40 * 0.70) / 0.60
= 1.4

share_weight_PHEV
= 3 * (0.40 * 0.30) / 0.60
= 0.6

share_weight_FCEV
= 0
```

### EV items that are still modeling choices

- using `BEV stock share` as a proxy for `sales mix`
- keeping the proxy mix flat in non-`NZE` scenarios
- `PHEV utility_factor = 0.55`
- `PHEV` `40/60` cost and capital blending weights
- the GCAM `share-weight` conversion itself

## Datacenter: Exact Source Logic

### Source edition

The datacenter module now uses only:

- `IEA (2025), Energy and AI`

The archived public extract is:

- [iea_energy_and_ai_2025_public_extract.json](/Users/sekiyamitsuna/CodexCLI/GCAM/gcam-ev-datacenter-overlays/data/source_exports/iea_energy_and_ai_2025_public_extract.json)

### Public datacenter numbers used directly

- `2024 global data-centre electricity demand = 415 TWh`
- `2024 regional shares = USA 45%, China 25%, Europe 15%`
- `historical growth since 2017 = 12% per year`
- `2030 Base Case = 945 TWh`
- `2035 Base Case = 1200 TWh`
- `2035 High Efficiency = 970 TWh`
- `2035 Headwinds = 700 TWh`
- `2035 Lift-Off = 1700 TWh`
- `USA increase from 2024 to 2030 = 240 TWh`

### Scenario mapping

- `SSP1 -> High Efficiency`
- `SSP2 -> Base Case`
- `SSP3 -> Headwinds`
- `SSP4 -> Headwinds`
- `SSP5 -> Lift-Off`

### Global datacenter calculations

The repository computes `2020` from the public `2024` level and the public historical growth note:

```text
global_2020
= 415 / (1.12^4)
= 263.7400025380049 TWh
```

The `2025` point is a direct linear bridge:

```text
global_2025
= 415 + (945 - 415) * ((2025 - 2024) / (2030 - 2024))
= 503.3333333333333 TWh
```

`2035` uses the mapped public case endpoint:

- `SSP1 = 970 TWh`
- `SSP2 = 1200 TWh`
- `SSP3 = 700 TWh`
- `SSP4 = 700 TWh`
- `SSP5 = 1700 TWh`

After `2035`, the total is held constant through `2100`.

### Datacenter regionalization logic

The regionalization starts from the public `2024` shares:

```text
USA    = 0.45
China  = 0.25
Europe = 0.15
Rest   = 0.15
```

So:

```text
USA_2024    = 415 * 0.45 = 186.75 TWh
China_2024  = 415 * 0.25 = 103.75 TWh
Europe_2024 = 415 * 0.15 = 62.25 TWh
Rest_2024   = 415 * 0.15 = 62.25 TWh
```

For `2030`, the only direct regional increment that is currently archived is the US value:

```text
USA_2030 = 186.75 + 240 = 426.75 TWh
```

The remaining `2030` total is then allocated across non-US groups in proportion to their `2024` public shares:

```text
remaining_2030 = 945 - 426.75 = 518.25 TWh

China_2030
= 518.25 * (103.75 / (103.75 + 62.25 + 62.25))
= 230.35714285714286 TWh

Europe_2030
= 518.25 * (62.25 / (103.75 + 62.25 + 62.25))
= 138.21428571428572 TWh

Rest_2030
= 518.25 * (62.25 / (103.75 + 62.25 + 62.25))
= 149.67857142857144 TWh
```

For `2035`, the repository scales the `2030` regional composition to the mapped public `2035` global endpoint:

```text
group_2035(g, s) = group_2030(g) * global_2035(s) / global_2030
```

After `2035`, that `2035` regional composition is held constant through `2100`.

### Within-group GCAM split

Within each group:

- `USA = [USA]`
- `China = [China]`
- `Europe = [EU-12, EU-15, Europe_Eastern, Europe_Non_EU, European Free Trade Association]`
- `Rest of world = all remaining GCAM regions`

The split within each group is:

```text
split_region(r | g) = E_comm_2015(r) / sum_{r in g} E_comm_2015(r)
```

where `E_comm_2015` comes from GCAM's calibrated `building_det.xml`.

### Historical seed and elasticity inversion

The datacenter sector is implemented as `energy-final-demand`, so the repository must solve for the `income-elasticity` that reproduces the target path.

Historical handling:

```text
1975 = 0
1990 = 0
2005 = 0
2010 = 0
2015 = 0.01 * 2020_target
```

This `1%` seed is not an IEA demand value. It is a calibration device to keep GCAM numerically stable.

Then:

```text
epsilon(r, s, t) =
  ln(D_region(r, s, t) / D_region(r, s, t_prev)) /
  ln(GDP(r, s, t) / GDP(r, s, t_prev))
```

with GDP taken from GCAM's stock `socioeconomics_SSP*.xml`.

## Bottom Line

The repository now satisfies the stronger provenance rule more cleanly:

- `EV`
  - one IEA edition
  - public source extract archived in-repo
  - explicit bridge formulas
- `Datacenter`
  - one IEA edition
  - public source extract archived in-repo
  - explicit bridge, regionalization, and extension formulas

The claims that should still be avoided are:

- `all numbers are direct IEA table imports`
- `the archived source packages are raw IEA chart CSV files`

The correct wording is:

```text
The repository archives public IEA source extracts and derives all additional anchor points with explicit formulas that are documented in-repo.
```
