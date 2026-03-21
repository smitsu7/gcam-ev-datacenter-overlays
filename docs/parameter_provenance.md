# Parameter Provenance and Derivation

This note is the explicit provenance map for the current implementation.
It is intended to answer two reviewer questions directly:

1. Which numbers are direct imports from IEA-style sources?
2. Which numbers are translation parameters introduced by this add-on?

The answer is not the same for `EV` and `datacenter`.

## Short Answer

- `Datacenter`
  - `2030` and `2035` global electricity-demand anchors are implemented as direct IEA case-style anchors in `TWh`.
  - `2020` and `2025` are bridging anchors chosen by the add-on.
  - `2050+` values are author-defined extrapolations from the `2035` anchor.
  - regional allocation and GCAM income elasticities are author-defined, but fully formula-based and reproducible.
- `EV`
  - the current `share-weight`, `cost multiplier`, `coefficient multiplier`, and `PHEV utility factor` schedules are not direct IEA numeric imports.
  - they are translation parameters created by the add-on to map IEA scenario direction into GCAM control variables.
  - therefore, these EV schedules should be cited as "add-on assumptions informed by IEA", not as "IEA values".

## Machine-Readable Sources

- EV assumptions:
  - [ev_ssp_assumptions.json](/Users/sekiyamitsuna/CodexCLI/GCAM/gcam-ev-datacenter-overlays/data/ev_ssp_assumptions.json)
- Datacenter assumptions:
  - [datacenter_ssp_assumptions.json](/Users/sekiyamitsuna/CodexCLI/GCAM/gcam-ev-datacenter-overlays/data/datacenter_ssp_assumptions.json)
- EV generator:
  - [generate_ev_addon.py](/Users/sekiyamitsuna/CodexCLI/GCAM/gcam-ev-datacenter-overlays/scripts/generate_ev_addon.py)
- Datacenter generator:
  - [generate_datacenter_addon.py](/Users/sekiyamitsuna/CodexCLI/GCAM/gcam-ev-datacenter-overlays/scripts/generate_datacenter_addon.py)

## Datacenter: Exact Transformation Logic

### Step 1. Global electricity anchors

The current implementation starts from the global `TWh` series in
[datacenter_ssp_assumptions.json](/Users/sekiyamitsuna/CodexCLI/GCAM/gcam-ev-datacenter-overlays/data/datacenter_ssp_assumptions.json):

- common bridge values:
  - `2020 = 300 TWh`
  - `2025 = 430 TWh`
- scenario anchors:
  - `SSP1`: `2030 = 800 TWh`, `2035 = 960 TWh`
  - `SSP2`: `2030 = 945 TWh`, `2035 = 1200 TWh`
  - `SSP3`: `2030 = 620 TWh`, `2035 = 700 TWh`
  - `SSP4`: `2030 = 760 TWh`, `2035 = 900 TWh`
  - `SSP5`: `2030 = 1150 TWh`, `2035 = 1700 TWh`

Interpretation:

- `2030` and `2035` are treated as direct case anchors.
- `2020` and `2025` are add-on bridge values inserted to move from historical calibration into the IEA scenario horizon without a jump discontinuity.

### Step 2. Convert `TWh` to `EJ`

The script uses:

```text
1 TWh = 0.0036 EJ
D_global_EJ(s, t) = D_global_TWh(s, t) * 0.0036
```

Example, `SSP2`:

```text
2030: 945 TWh * 0.0036 = 3.402 EJ
2035: 1200 TWh * 0.0036 = 4.320 EJ
```

### Step 3. Piecewise interpolation through 2035

For all modeled years from `2020` to `2035`, the script linearly interpolates between anchors:

```text
D(t) = D(t_left) + (D(t_right) - D(t_left)) * (t - t_left) / (t_right - t_left)
```

This is applied over:

- `2020 -> 2025`
- `2025 -> 2030`
- `2030 -> 2035`

### Step 4. Post-2035 extrapolation

After `2035`, the script applies explicit annual growth rates by SSP:

```text
D(t) = D(t_prev) * (1 + g_phase)^(t - t_prev)
```

with:

- `2035 -> 2050`: `g = post_2035_growth_rates[SSP]["2035_to_2050"]`
- `2050 -> 2100`: `g = post_2035_growth_rates[SSP]["2050_to_2100"]`

So, for `SSP2`:

```text
g_2035_2050 = 0.02
g_2050_2100 = 0.006

2040 global EJ
= 4.320 * (1.02)^5
= 4.7696 EJ
```

### Step 5. Regionalize the global total

The script first creates group-level pre-weights:

```text
w_group_raw(g, s) = base_share(g) * multiplier(g, s)
```

Then normalizes them:

```text
w_group(g, s) = w_group_raw(g, s) / sum_g w_group_raw(g, s)
```

Within each group, it splits demand using GCAM's `2015` calibrated commercial electricity use from
`building_det.xml`:

```text
split_region(r | g) = E_comm_2015(r) / sum_{r in g} E_comm_2015(r)
```

Then the final regional target is:

```text
D_region(r, s, t) = D_global(s, t) * w_group(g(r), s) * split_region(r | g(r))
```

### Step 6. Historical seed

To avoid breaking GCAM calibration, the sector is almost zero in the historical periods:

```text
D_region(r, s, 1975) = 0
D_region(r, s, 1990) = 0
D_region(r, s, 2005) = 0
D_region(r, s, 2010) = 0
D_region(r, s, 2015) = 0.01 * D_region(r, s, 2020)
```

This `1%` seed is the current add-on design choice, not an IEA number.

### Step 7. Convert target demand into GCAM income elasticities

The datacenter sector is implemented as `energy-final-demand`, so the script solves backward for the required income elasticity:

```text
epsilon(r, s, t) =
  ln(D_region(r, s, t) / D_region(r, s, t_prev)) /
  ln(GDP(r, s, t) / GDP(r, s, t_prev))
```

with GDP read from the official GCAM SSP files `socioeconomics_SSP*.xml`.

This is the exact reason the early elasticities can be very large: the `2015` seed is intentionally tiny.

### Worked Example: `USA`, `SSP2`

Because `USA` is the only member of the `usa` group, its within-group split is `1.0`.
In `SSP2`, all group multipliers are `1.0`, so the normalized USA group share remains `0.45`.

```text
Global 2020  = 300 TWh * 0.0036 = 1.0800 EJ
USA 2020     = 1.0800 * 0.45    = 0.4860 EJ
USA 2015 seed= 0.4860 * 0.01    = 0.00486 EJ

Global 2025  = 430 TWh * 0.0036 = 1.5480 EJ
USA 2025     = 1.5480 * 0.45    = 0.6966 EJ

Global 2030  = 945 TWh * 0.0036 = 3.4020 EJ
USA 2030     = 3.4020 * 0.45    = 1.5309 EJ

Global 2035  = 1200 TWh * 0.0036 = 4.3200 EJ
USA 2035     = 4.3200 * 0.45     = 1.9440 EJ
```

Using GDP from `socioeconomics_SSP2.xml`:

```text
GDP_2015 = 11061575
GDP_2020 = 12766015
GDP_2025 = 14303768
GDP_2030 = 15710491
```

the solved elasticities are:

```text
epsilon_2020
= ln(0.4860 / 0.00486) / ln(12766015 / 11061575)
= 32.1345

epsilon_2025
= ln(0.6966 / 0.4860) / ln(14303768 / 12766015)
= 3.1652

epsilon_2030
= ln(1.5309 / 0.6966) / ln(15710491 / 14303768)
= 8.3939
```

These are exactly the numbers that the generator writes into the sector XML.

## EV: Exact Transformation Logic

### Step 1. Source interpretation

The EV module does not read IEA tables and mechanically convert them into GCAM values.
Instead, it maps IEA scenario direction into GCAM control variables.

The current scenario mapping is:

- `SSP1 -> NZE-like upper bound`
- `SSP2 -> STEPS-like central case`
- `SSP3 -> delayed case below STEPS, with CPS-like weakness`
- `SSP4 -> same transport path as SSP3 in the current version`
- `SSP5 -> faster-than-STEPS technology-led case, but not a climate-constrained NZE`

This mapping is stored in
[ev_ssp_assumptions.json](/Users/sekiyamitsuna/CodexCLI/GCAM/gcam-ev-datacenter-overlays/data/ev_ssp_assumptions.json).

### Step 2. What is direct and what is not

The following EV values are currently add-on translation parameters, not direct IEA numbers:

- `share_weights`
- `cost_multipliers`
- `coefficient_multipliers`
- `PHEV utility_factor`

They are deterministic and reproducible, but they are still author-defined.
For a reviewer, the correct description is:

```text
EV schedules = add-on assumptions informed by IEA scenario ordering and GCAM transport structure
```

not:

```text
EV schedules = direct IEA data
```

### Step 3. Schedule fill rule

For every EV schedule in the JSON file, the generator applies:

```text
schedule(year_anchor_i) = listed value_i
schedule(t > last_anchor) = value_last_anchor
```

In the current code:

- anchor years: `2020, 2025, 2030, 2035, 2040, 2045, 2050`
- years after `2050`: fixed at the `2050` value

So, for `SSP2`:

```text
BEV share-weight schedule:
2020 0.05
2025 0.15
2030 0.30
2035 0.50
2040 0.75
2045 0.95
2050 1.10
2055-2100 1.10
```

Again, those numbers are not IEA values; they are the current GCAM translation knobs.

### Step 4. Existing technology updates

For `BEV` and `FCEV`, the generator multiplies the base GCAM values:

```text
capital_coef_new(t) = capital_coef_base(t) * cost_multiplier(t)
input_cost_new(t)   = input_cost_base(t)   * cost_multiplier(t)
energy_coef_new(t)  = energy_coef_base(t)  * coefficient_multiplier(t)
```

### Step 5. PHEV formulas

`PHEV` is fully formula-based inside the generator.

The cost and capital coefficient are blended from `BEV` and `Hybrid Liquids`:

```text
capital_coef_PHEV(t) =
  cost_multiplier_PHEV(t) *
  [0.4 * capital_coef_BEV(t) + 0.6 * capital_coef_Hybrid(t)]

input_cost_PHEV(t) =
  cost_multiplier_PHEV(t) *
  [0.4 * input_cost_BEV(t) + 0.6 * input_cost_Hybrid(t)]
```

The energy inputs are split using the `utility_factor`:

```text
elec_coef_PHEV(t) =
  coefficient_multiplier_PHEV(t) *
  utility_factor(t) *
  coef_BEV(t)

liquids_coef_PHEV(t) =
  coefficient_multiplier_PHEV(t) *
  [1 - utility_factor(t)] *
  coef_Hybrid(t)
```

### Worked Example: `USA`, `Car`, `SSP2`, `2030`

From `transportation_UCD_CORE.xml`:

```text
capital_coef_BEV     = 0.00184757627334951
capital_coef_Hybrid  = 0.00186066163095890
input_cost_BEV       = 0.2243
input_cost_Hybrid    = 0.2228
coef_BEV             = 817.1283434
coef_Hybrid          = 1408.4078473
```

From `ev_ssp_assumptions.json` for `SSP2 2030`:

```text
share_weight_BEV     = 0.30
share_weight_PHEV    = 0.18
share_weight_FCEV    = 0.06
share_weight_Hybrid  = 1.00
share_weight_Liquids = 0.90
share_weight_NG      = 0.65

cost_multiplier_PHEV = 0.95
coef_multiplier_PHEV = 0.99
utility_factor_PHEV  = 0.56
```

Then:

```text
capital_coef_PHEV
= 0.95 * [0.4 * 0.00184757627334951 + 0.6 * 0.00186066163095890]
= 0.0017626561135193866

input_cost_PHEV
= 0.95 * [0.4 * 0.2243 + 0.6 * 0.2228]
= 0.21223

elec_coef_PHEV
= 0.99 * 0.56 * 817.1283434
= 453.01595358096

liquids_coef_PHEV
= 0.99 * (1 - 0.56) * 1408.4078473
= 613.5024582838798
```

So the `PHEV` internals are formula-derived, but the scenario schedule inputs that drive them are still add-on assumptions.

## Reviewer's Bottom Line

If the question is "Are the datacenter and EV numbers author-defined?", the exact answer is:

- `Datacenter`
  - partly no, partly yes
  - the `2030/2035` global case anchors are treated as direct source anchors
  - the bridge years, extrapolation years, regional allocation, and elasticity inversion are add-on transformations
- `EV`
  - yes for the current scenario schedules
  - the EV schedule arrays are author-defined translation parameters informed by IEA scenario direction
  - the PHEV blending formulas are explicit and reproducible, but the schedules feeding those formulas are still assumptions

If a paper or public release needs stronger defensibility than this, the next step is to replace the current EV schedule tables with a direct translation layer from reported IEA stock or sales shares into GCAM share-weights.
