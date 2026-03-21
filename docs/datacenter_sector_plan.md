# Future Extension: Data Center Sector

This repository currently implements an EV transport overlay only. The next demand-side extension should treat `data centers` as a distinct `sector` or `service` inside GCAM's building/commercial demand structure, not as a direct override to primary energy.

## Recommended Modeling Choice

Model data centers as a new commercial building service, for example:

- `comm datacenter`

This is more GCAM-consistent than injecting primary energy directly because:

- final energy should appear first as additional electricity demand in the building/commercial system
- primary energy should then emerge endogenously from the electricity supply system
- the same SSP background assumptions can be preserved while changing only the new sector overlay

## Why Building / Commercial Is the Right Hook

The stock GCAM inputs already contain:

- commercial building consumers under `gcam-consumer name="comm"`
- building service inputs such as `comm others`
- query support for `building final energy by service and fuel`
- economy-wide accounting in `total final energy by aggregate sector`
- system-wide accounting in `primary energy consumption by region (direct equivalent)`

That means a data center sector can be tracked at three levels:

1. dedicated service-level final energy
2. aggregate building final energy
3. global primary energy response through electricity generation

## Proposed Input Strategy

Add SSP-specific overlays parallel to the EV workflow:

- `building_DC_SSP1.xml`
- `building_DC_SSP2.xml`
- `building_DC_SSP3.xml`
- `building_DC_SSP4.xml`
- `building_DC_SSP5.xml`

These overlays should:

- add or split out a `comm datacenter` service from the commercial building structure
- assign electricity demand through `elect_td_bld`
- optionally add efficiency and utilization improvements over time
- keep all non-data-center SSP inputs on the stock GCAM path

## Proposed Repository Additions

- `data/datacenter_ssp_assumptions.json`
- `scripts/generate_datacenter_sector_addon.py`
- `generated/input/gcamdata/xml/building_DC_SSP*.xml`
- `generated/exe/batch_SSP_EV_DC.xml` once EV and data center are combined

The repo should continue to treat each overlay as modular:

- EV transport overlay
- future data center building overlay
- future combined overlay batch

## Source Basis For A Future SSP Calibration

The recommended evidence stack is:

- `IEA (2025), Energy and AI`
  - use the global data-centre electricity pathways and sensitivity cases as the primary institutional basis
- `IEA (2025), Electricity 2025`
  - use for near-term power-sector context around data-centre-driven demand growth
- `Masanet et al. (2020), Science`
  - use for the pre-AI baseline and for caution against naive extrapolation from server growth alone
- `Shehabi et al. (2024), 2024 United States Data Center Energy Usage Report, LBNL, DOI 10.71468/P1WC7Q`
  - use for AI-era load growth, efficiency trends, and infrastructure detail
- `Zhang et al. (2023), Sustainable Cities and Society`
  - use for data-centre efficiency and low-carbon technology context

## Suggested SSP Mapping Logic

For a first academically defensible implementation, map SSP narratives to IEA-style data-centre demand cases instead of inventing free-form trajectories:

- `SSP1`: closest to an `IEA High Efficiency` interpretation
- `SSP2`: closest to the `IEA Base Case`
- `SSP3`: closest to an `IEA Headwinds` interpretation
- `SSP4`: between `Base Case` and `Headwinds`, but with stronger concentration in advanced regions
- `SSP5`: closest to an `IEA Lift-Off` interpretation

Anything beyond the published IEA horizon should be treated explicitly as a modeler's extension rather than a direct source value.

## Validation Queries For The Data Center Sector

At minimum, validate with:

- `building final energy by service and fuel`
- `total final energy by aggregate sector`
- `primary energy consumption by region (direct equivalent)`

Recommended interpretation:

- `building final energy by service and fuel` verifies that `comm datacenter` exists and consumes electricity as intended
- `total final energy by aggregate sector` shows whether the building-sector total changes at the global level
- `primary energy consumption by region (direct equivalent)` shows the upstream generation response at the global level

## Global Output Goal

If implemented this way, EV plus data center demand can both be evaluated at the global level without hard-coding primary energy:

- EV changes appear mainly through transport final energy and electricity/liquid shifts
- data center changes appear mainly through building final energy and electricity growth
- both then propagate into global primary energy through the same GCAM energy system

That is the recommended architecture for a future `EV + data center sector` version of this repository.

## Reference Shortlist

- IEA. 2025. *Energy and AI*. https://www.iea.org/reports/energy-and-ai
- IEA. 2025. *Energy demand from AI*. https://www.iea.org/reports/energy-and-ai/energy-demand-from-ai
- IEA. 2025. *Energy supply for AI*. https://www.iea.org/reports/energy-and-ai/energy-supply-for-ai
- IEA. 2025. *Electricity 2025*. https://www.iea.org/reports/electricity-2025
- Masanet, E., Shehabi, A., Lei, N., Smith, S. and Koomey, J. 2020. *Recalibrating global data center energy-use estimates*. *Science* 367(6481): 984-986. https://doi.org/10.1126/science.aba3758
- Shehabi, A. et al. 2024. *2024 United States Data Center Energy Usage Report*. Lawrence Berkeley National Laboratory. https://doi.org/10.71468/P1WC7Q
- Zhang, Y. et al. 2023. *Future data center energy-conservation and emission-reduction technologies in the context of smart and low-carbon city construction*. *Sustainable Cities and Society* 89:104322. https://doi.org/10.1016/j.scs.2022.104322
