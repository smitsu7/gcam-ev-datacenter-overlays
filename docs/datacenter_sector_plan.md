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
