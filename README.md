# GCAM EV SSP Add-on

This repository adds a transport electrification overlay to `GCAM v7.0` without modifying GCAM C++ source code. The add-on installs scenario-specific XML overlays so that `SSP1` to `SSP5` can represent a more explicit light-duty vehicle transition with separate `BEV`, `PHEV`, `FCEV`, `Hybrid Liquids`, `Liquids`, and `NG` pathways.

The design goal is to keep the implementation consistent with GCAM's existing transport structure and energy accounting while making EV adoption assumptions transparent and reproducible.

The repository is also being prepared for future modular demand-side overlays beyond EV. The next planned extension is a dedicated `data center sector` overlay in the building/commercial demand system. See [docs/datacenter_sector_plan.md](docs/datacenter_sector_plan.md).

## What This Add-on Changes

- Adds `transportation_EV_SSP1.xml` to `transportation_EV_SSP5.xml` overlays for the GCAM `trn_pass_road_LDV_4W` sector.
- Keeps `BEV`, `FCEV`, `Hybrid Liquids`, `Liquids`, and `NG` as distinct transport technologies.
- Adds a new `PHEV` technology as a true dual-fuel GCAM technology with:
  - `elect_td_trn`
  - `refined liquids enduse`
- Applies SSP-specific schedules for:
  - transport technology share-weights
  - non-energy cost multipliers
  - energy-intensity coefficients
  - `PHEV` electric utility factor
- Generates:
  - `generated/exe/batch_SSP_EV.xml`
  - `generated/exe/configuration_ssp_ev.xml`
  - `generated/exe/run-gcam-ssp-ev.command`
  - `generated/output/queries/EV_SSP_queries.xml`

## Modeling Logic

### 1. GCAM-consistent transport implementation

This add-on follows GCAM's native transport technology structure. It does not create a new top-level electricity demand sector. Instead, EVs remain transport technologies inside the existing LDV subsectors, which means:

- final energy remains transport final energy by carrier and technology
- primary energy remains an emergent system outcome from electricity, refining, hydrogen, and upstream supply modules

That is the correct GCAM accounting logic. In practice:

- `BEV` final energy is observed in transport queries through `elect_td_trn`
- `PHEV` final energy is split across `elect_td_trn` and `refined liquids enduse`
- primary energy impacts are read from GCAM's existing primary energy queries, not hand-coded into transport XML

### 2. SSP mapping logic

The numeric schedules in this repository are not copied mechanically from IEA market shares. IEA publishes sales, stock, and scenario evidence, while GCAM uses logit-style share-weights and technology coefficients. The translation therefore follows a documented heuristic:

- preserve the ordering of technology adoption seen in authoritative scenario work
- translate that ordering into GCAM share-weights rather than raw sales shares
- apply faster cost and efficiency learning in high-innovation scenarios
- keep `PHEV` as a transition technology that grows early and declines later as `BEV` dominates

Current interpretation:

- `SSP1`: fastest EV transition; calibrated as an `IEA NZE`-like upper bound
- `SSP2`: central case; calibrated as an `IEA STEPS`-like pathway
- `SSP3`: delayed electrification below `STEPS`, informed by the weak-policy direction of `Current Policies`
- `SSP4`: currently uses the same transport overlay as `SSP3` because this repository does not yet distinguish within-region inequality effects in LDV adoption
- `SSP5`: high-income, high-mobility, high-innovation case with faster EV progress than `SSP2`, but not treated as a climate-constrained `NZE` path

This means the scenarios should be read as SSP-consistent EV overlays informed by IEA pathways, not as literal reproductions of IEA scenario outputs.

The rest of the SSP structure is intentionally left on the official GCAM pathway. `batch_SSP_EV.xml` is generated from the stock `batch_SSP_REF.xml`, and the only added SSP-specific input is the EV transport overlay:

- `SSP1`: `transportation_EV_SSP1.xml`
- `SSP2`: `transportation_EV_SSP2.xml`
- `SSP3`: `transportation_EV_SSP3.xml`
- `SSP4`: `transportation_EV_SSP4.xml`
- `SSP5`: `transportation_EV_SSP5.xml`

All other scenario-specific inputs continue to come from GCAM's official SSP batch file, including socioeconomic assumptions, buildings, AGLU, resource extraction, and non-CO2 controls.

### 3. PHEV logic

`PHEV` is implemented as a genuine two-input GCAM technology. Its calibration blends:

- non-energy costs from `BEV` and `Hybrid Liquids`
- electric energy use from `BEV`
- liquid fuel use from `Hybrid Liquids`

The `utility_factor` controls how much of the `PHEV` service demand is served by electricity versus liquids. Faster-electrifying SSPs use higher utility factors.

### 4. Final and primary energy accounting

To inspect energy accounting after a run, use the included query subset:

- `transport final energy by tech and fuel`
- `transport service output by tech`
- `LDV energy by primary fuel`
- `total final energy by aggregate sector`
- `primary energy consumption by region (direct equivalent)`
- `primary energy consumption by region (avg fossil efficiency)`

This combination is intentional:

- the first three queries show the transport-side EV technology transition and carrier split
- the latter two queries show whether electrification is flowing through to economy-wide final and primary energy accounting

## Source Basis

### Primary institutional sources

- `IEA (2025), Global EV Outlook 2025`
  - used for the direction of global EV adoption, the continued dominance of BEVs over PHEVs, and the role of policy support and model availability
- `IEA (2025), World Energy Outlook 2025`
  - used for the policy interpretation of `STEPS` and `NZE`
- `GCAM v7.0 documentation`
  - used for model execution, query structure, XML overlay behavior, and transport accounting

### Supporting academic sources

- `Kyle and Kim (2011)`
  - used as the closest GCAM-specific precedent for linking light-duty vehicle technology pathways to global greenhouse gas emissions and primary energy demand
- `Mishra et al. (2013), Transportation Module of GCAM`
  - used for transport module structure and technology logic
- `O'Neill et al. (2017)` and `Riahi et al. (2017)`
  - used for SSP narrative interpretation

## Installation

### Requirements

- a working `GCAM v7.0` package
- Python 3

### 1. Generate the overlay files

```bash
python3 scripts/generate_ev_addon.py --gcam-root /path/to/gcam-v7.0-Mac_arm64-Release-Package
```

If `--gcam-root` is omitted, the script defaults to a sibling directory named `gcam-v7.0-Mac_arm64-Release-Package`.

### 2. Install the generated files into the GCAM package

```bash
python3 scripts/install_addon.py --gcam-root /path/to/gcam-v7.0-Mac_arm64-Release-Package
```

### 3. Run GCAM with the EV batch configuration

```bash
cd /path/to/gcam-v7.0-Mac_arm64-Release-Package/exe
./gcam -C configuration_ssp_ev.xml
```

or use the generated launcher:

```bash
cd /path/to/gcam-v7.0-Mac_arm64-Release-Package/exe
./run-gcam-ssp-ev.command
```

The EV run writes its XML database to:

```text
../output/database_basexdb_ev_ssp
```

## Repository Layout

```text
data/ev_ssp_assumptions.json
scripts/generate_ev_addon.py
scripts/install_addon.py
generated/exe/configuration_ssp_ev.xml
generated/exe/batch_SSP_EV.xml
generated/exe/run-gcam-ssp-ev.command
generated/input/gcamdata/xml/transportation_EV_SSP*.xml
generated/output/queries/EV_SSP_queries.xml
scripts/check_batch_alignment.py
scripts/plot_validation_results.py
docs/figures/*.png
docs/datacenter_sector_plan.md
```

## Validation

This add-on now includes an `ahe_generator_gcam`-aligned validation path for the two energy outputs that matter for downstream AHE work:

- `primary energy consumption by region (direct equivalent)`
- `total final energy by aggregate sector`

These are the same query titles used in [`TokyoTechGUC/ahe_generator_gcam`](https://github.com/TokyoTechGUC/ahe_generator_gcam):

- `queries[2]` in `input/reference_files/all_query.xml`
- `queries[58]` in `input/reference_files/all_query.xml`

The validation workflow is:

```bash
cd /path/to/gcam-v7.0-Mac_arm64-Release-Package/exe
./run-gcam-ssp-baseline.command
./run-gcam-ssp-ev.command
./run-validate-ssp-vs-ev.command
```

This writes:

- `output/ev_validation/baseline_validation.csv`
- `output/ev_validation/ev_validation.csv`
- `output/ev_validation/ev_minus_baseline.csv`
- `output/ev_validation/ev_minus_baseline_summary.csv`

Interpretation:

- `ev_minus_baseline.csv` keeps the original query dimensions
  - `sector` for `total final energy by aggregate sector`
  - `fuel` for `primary energy consumption by region (direct equivalent)`
- `ev_minus_baseline_summary.csv` aggregates within each query, scenario, year, and unit
- a negative transport-sector delta in final energy is the expected efficiency signal from EV uptake
- primary energy deltas show the system-level upstream effect after electricity, hydrogen, and liquid-fuel supply are rebalanced by GCAM

To reproduce the validation figures from the generated CSV files:

```bash
python3 scripts/plot_validation_results.py \
  --detail /path/to/gcam-v7.0-Mac_arm64-Release-Package/output/ev_validation/ev_minus_baseline.csv \
  --summary /path/to/gcam-v7.0-Mac_arm64-Release-Package/output/ev_validation/ev_minus_baseline_summary.csv \
  --out-dir /path/to/gcam-v7.0-Mac_arm64-Release-Package/output/ev_validation/plots
```

## Validation Status

- XML generation completed for `SSP1` to `SSP5`
- installation into a local `GCAM v7.0` package completed
- baseline `SSP1` to `SSP5` batch completed successfully through database output
- EV vs baseline comparison was completed for `SSP1` to `SSP5` across every available model year from `1990` to `2100`
- `check_batch_alignment.py` confirmed that the only SSP-specific addition relative to the stock GCAM batch is the EV transport overlay
- `validation_report.json` confirmed full coverage for all requested scenarios, years, sectors, and primary fuels with no missing rows

The completed validation shows that:

- `PHEV` dual-fuel XML is accepted by `GCAM v7.0`
- the EV overlay produces visible and traceable changes in both final and primary energy accounting under the same SSP background assumptions
- the requested `ahe_generator_gcam` query pair is available for every `SSP` and model year in the comparison outputs

## Validation Figures

### Baseline vs EV across all SSPs and years

![Baseline vs EV across all SSPs and years](docs/figures/overview_before_after.png)

### Final energy delta by aggregate sector

![Final energy delta by aggregate sector](docs/figures/final_energy_sector_delta.png)

### Primary energy delta by fuel across all SSPs and years

![Primary energy delta by fuel across all SSPs and years](docs/figures/primary_energy_fuel_delta.png)

## Future Extension

The next planned module is a distinct `data center sector`, modeled as an additional commercial building service rather than a direct primary-energy shock. The design note is in [docs/datacenter_sector_plan.md](docs/datacenter_sector_plan.md).

To verify that the EV batch keeps all non-transport SSP inputs aligned with the stock GCAM SSP batch:

```bash
python3 scripts/check_batch_alignment.py --gcam-root /path/to/gcam-v7.0-Mac_arm64-Release-Package
```

## Limitations

- `SSP4` currently reuses the `SSP3` transport overlay; this is a pragmatic placeholder, not a claim that the two SSPs are identical.
- The EV schedules are calibrated heuristically from institutional scenarios and SSP narratives. They are defensible, but they are not an econometric re-estimation of market shares.
- The repository currently targets passenger light-duty road transport. It does not yet add separate EV detail for buses, trucks, two-wheelers, or non-road transport.

## References

- IEA. 2025. *Global EV Outlook 2025*. [https://www.iea.org/reports/global-ev-outlook-2025](https://www.iea.org/reports/global-ev-outlook-2025)
- IEA. 2025. *Executive summary*. [https://www.iea.org/reports/global-ev-outlook-2025/executive-summary](https://www.iea.org/reports/global-ev-outlook-2025/executive-summary)
- IEA. 2025. *Trends in the electric car industry*. [https://www.iea.org/reports/global-ev-outlook-2025/trends-in-the-electric-car-industry-3](https://www.iea.org/reports/global-ev-outlook-2025/trends-in-the-electric-car-industry-3)
- IEA. 2025. *Outlook for electric mobility*. [https://www.iea.org/reports/global-ev-outlook-2025/outlook-for-electric-mobility](https://www.iea.org/reports/global-ev-outlook-2025/outlook-for-electric-mobility)
- IEA. 2025. *Outlook for energy demand*. [https://www.iea.org/reports/global-ev-outlook-2025/outlook-for-energy-demand](https://www.iea.org/reports/global-ev-outlook-2025/outlook-for-energy-demand)
- IEA. 2025. *World Energy Outlook 2025*. [https://www.iea.org/reports/world-energy-outlook-2025](https://www.iea.org/reports/world-energy-outlook-2025)
- IEA. 2025. *Scenarios in the World Energy Outlook 2025*. [https://www.iea.org/commentaries/scenarios-in-the-world-energy-outlook-2025](https://www.iea.org/commentaries/scenarios-in-the-world-energy-outlook-2025)
- IEA. 2025. *Stated Policies Scenario*. [https://www.iea.org/reports/world-energy-outlook-2025/stated-policies-scenario](https://www.iea.org/reports/world-energy-outlook-2025/stated-policies-scenario)
- IEA. 2025. *Net Zero Emissions by 2050*. [https://www.iea.org/reports/world-energy-outlook-2025/net-zero-emissions-by-2050](https://www.iea.org/reports/world-energy-outlook-2025/net-zero-emissions-by-2050)
- IEA. 2025. *Current Policies Scenario*. [https://www.iea.org/reports/world-energy-outlook-2025/current-policies-scenario](https://www.iea.org/reports/world-energy-outlook-2025/current-policies-scenario)
- GCAM documentation v7.0. *How to Get Started Running GCAM*. [https://jgcri.github.io/gcam-doc/v7.0/how-to-run-gcam.html](https://jgcri.github.io/gcam-doc/v7.0/how-to-run-gcam.html)
- GCAM documentation v7.0. *Model Interface*. [https://jgcri.github.io/gcam-doc/v7.0/model-interface.html](https://jgcri.github.io/gcam-doc/v7.0/model-interface.html)
- GCAM documentation v7.0. *GCAM User Guide*. [https://jgcri.github.io/gcam-doc/v7.0/user-guide.html](https://jgcri.github.io/gcam-doc/v7.0/user-guide.html)
- Mishra, G. S., et al. 2013. *Transportation Module of Global Change Assessment Model (GCAM): Model Documentation Version 1.0*. [https://escholarship.org/uc/item/8nk2c96d](https://escholarship.org/uc/item/8nk2c96d)
- Kyle, P., and S. H. Kim. 2011. *Long-term implications of alternative light-duty vehicle technologies for global greenhouse gas emissions and primary energy demands*. [https://doi.org/10.1016/j.enpol.2011.03.016](https://doi.org/10.1016/j.enpol.2011.03.016)
- O'Neill, B. C., et al. 2017. *The roads ahead: Narratives for shared socioeconomic pathways describing world futures in the 21st century*. [https://link.springer.com/article/10.1007/s10584-016-1605-1](https://link.springer.com/article/10.1007/s10584-016-1605-1)
- Riahi, K., et al. 2017. *The shared socioeconomic pathways and their energy, land use, and greenhouse gas emissions implications: An overview*. [https://link.springer.com/article/10.1007/s10584-017-2005-2](https://link.springer.com/article/10.1007/s10584-017-2005-2)
