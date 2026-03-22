#!/usr/bin/env python3
import argparse
import json
import shutil
import xml.etree.ElementTree as ET
from copy import deepcopy
from pathlib import Path


HISTORIC_YEARS = [1975, 1990, 2005, 2010, 2015]
LDV_SUBSECTORS = ["Car", "Large Car and Truck", "Mini Car"]
PLUGIN_TECHS = {"BEV", "PHEV", "FCEV"}


def parse_args():
    script_dir = Path(__file__).resolve().parent
    addon_root = script_dir.parent
    default_gcam = addon_root.parent / "gcam-v7.0-Mac_arm64-Release-Package"
    parser = argparse.ArgumentParser(description="Generate EV SSP overlay files for GCAM.")
    parser.add_argument("--gcam-root", type=Path, default=default_gcam)
    return parser.parse_args()


def load_json(path: Path):
    return json.loads(path.read_text())


def load_source_package(addon_root: Path, assumptions):
    return load_json(addon_root / assumptions["source_package"])


def neutral_schedule(future_years, value=1.0):
    return {year: value for year in future_years}


def interpolate_series(anchor_points, years):
    points = sorted((int(year), float(value)) for year, value in anchor_points.items())
    if not points:
        raise ValueError("No anchor points supplied")
    out = {}
    for year in years:
        if year <= points[0][0]:
            out[year] = points[0][1]
            continue
        if year >= points[-1][0]:
            out[year] = points[-1][1]
            continue
        for (left_year, left_value), (right_year, right_value) in zip(points, points[1:]):
            if left_year <= year <= right_year:
                span = right_year - left_year
                if span == 0:
                    out[year] = right_value
                else:
                    weight = (year - left_year) / span
                    out[year] = left_value + (right_value - left_value) * weight
                break
    return out


def normalize_mix(mix):
    total = sum(mix.values())
    if total <= 0:
        raise ValueError(f"Invalid powertrain mix with non-positive total: {mix}")
    return {tech: value / total for tech, value in mix.items()}


def interpolate_mix(anchor_mixes, years):
    techs = sorted(next(iter(anchor_mixes.values())).keys())
    series_by_tech = {
        tech: interpolate_series({year: mix[tech] for year, mix in anchor_mixes.items()}, years)
        for tech in techs
    }
    out = {}
    for year in years:
        out[year] = normalize_mix({tech: series_by_tech[tech][year] for tech in techs})
    return out


def build_total_ev_share_schedule(assumptions, source_package, ssp_name: str):
    iea_scenario = assumptions["scenario_to_iea"][ssp_name]
    historical = source_package["public_numeric_anchors"]["historical_sales_share_percent"]
    scenario_anchors = source_package["public_numeric_anchors"]["ldv_or_car_sales_share_percent"][iea_scenario]

    share_2018 = historical["2018"] / 100.0
    share_2023 = historical["2023"] / 100.0
    share_2030 = scenario_anchors["2030"] / 100.0
    share_2035 = scenario_anchors["2035"] / 100.0

    share_2020 = share_2018 * ((share_2023 / share_2018) ** ((2020 - 2018) / (2023 - 2018)))
    share_2025 = share_2023 + (share_2030 - share_2023) * ((2025 - 2023) / (2030 - 2023))

    anchor_points = {
        2020: share_2020,
        2025: share_2025,
        2030: share_2030,
        2035: share_2035,
    }

    return interpolate_series(anchor_points, assumptions["future_years"])


def build_powertrain_mix_schedule(assumptions, ssp_name: str):
    default_mix = assumptions["powertrain_proxy"]["default_mix"]
    mix_2035 = (
        assumptions["powertrain_proxy"]["nze_2035_mix"]
        if assumptions["scenario_to_iea"][ssp_name] == "NZE"
        else default_mix
    )

    anchor_mixes = {
        2020: default_mix,
        2025: default_mix,
        2030: default_mix,
        2035: mix_2035,
    }
    return interpolate_mix(anchor_mixes, assumptions["future_years"])


def build_share_weight_schedule(assumptions, source_package, ssp_name: str):
    future_years = assumptions["future_years"]
    total_ev_share = build_total_ev_share_schedule(assumptions, source_package, ssp_name)
    powertrain_mix = build_powertrain_mix_schedule(assumptions, ssp_name)

    rule = assumptions["weight_translation"]
    reference_non_plugin_techs = rule["reference_non_plugin_techs"]
    n_ref = len(reference_non_plugin_techs)
    non_plugin_weight = float(rule["non_plugin_share_weight"])
    ev_share_clip = float(rule["ev_share_clip"])
    residual_floor = float(rule["residual_floor"])

    share_sched = {tech: {} for tech in sorted(PLUGIN_TECHS.union(reference_non_plugin_techs))}
    for year in future_years:
        clipped_ev_share = min(total_ev_share[year], ev_share_clip)
        residual_share = max(1.0 - clipped_ev_share, residual_floor)

        for tech in reference_non_plugin_techs:
            share_sched[tech][year] = non_plugin_weight

        for tech in PLUGIN_TECHS:
            target_plugin_share = clipped_ev_share * powertrain_mix[year][tech]
            share_sched[tech][year] = n_ref * target_plugin_share / residual_share

    return share_sched


def text_as_float(elem, path):
    return float(elem.findtext(path))


def ensure_indent(tree: ET.ElementTree):
    try:
        ET.indent(tree, space="  ")
    except AttributeError:
        pass


def write_xml(root: ET.Element, dest: Path):
    dest.parent.mkdir(parents=True, exist_ok=True)
    tree = ET.ElementTree(root)
    ensure_indent(tree)
    tree.write(dest, encoding="utf-8", xml_declaration=True)


def write_text(dest: Path, text: str, executable: bool = False):
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text)
    if executable:
        dest.chmod(0o755)


def copy_file(src: Path, dest: Path, executable: bool = False):
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    if executable:
        dest.chmod(0o755)


def find_base_location_info(root: ET.Element, subsector: str):
    for loc in root.findall(".//global-technology-database/location-info"):
        if loc.get("sector-name") == "trn_pass_road_LDV_4W" and loc.get("subsector-name") == subsector:
            return loc
    return None


def find_query_by_title(root: ET.Element, title: str):
    for elem in root.iter():
        if elem.get("title") == title:
            return elem
    return None


def ensure_batch_scenario_name(root: ET.Element):
    strings = root.find("./Strings")
    if strings is None:
        strings = ET.SubElement(root, "Strings")
    scenario_value = None
    for value in strings.findall("./Value"):
        if value.get("name") == "scenarioName":
            scenario_value = value
            break
    if scenario_value is None:
        scenario_value = ET.SubElement(strings, "Value", {"name": "scenarioName"})
    scenario_value.text = ""


def tech_periods_by_year(tech: ET.Element):
    return {int(period.get("year")): period for period in tech.findall("./period")}


def build_existing_stub_tech(source_tech: ET.Element, tech_name: str, future_years, cost_sched, coef_sched):
    period_map = tech_periods_by_year(source_tech)
    out = ET.Element("stub-technology", {"name": tech_name})
    for year in future_years:
        src = period_map[year]
        period = ET.SubElement(out, "period", {"year": str(year)})
        ET.SubElement(period, "loadFactor").text = src.findtext("loadFactor")

        tracking_src = src.find("./tracking-non-energy-input")
        tracking = ET.SubElement(period, "tracking-non-energy-input", {"name": tracking_src.get("name")})
        ET.SubElement(tracking, "capital-coef").text = f"{text_as_float(src, './tracking-non-energy-input/capital-coef') * cost_sched[year]:.15g}"
        ET.SubElement(tracking, "tracking-market").text = tracking_src.findtext("tracking-market")
        ET.SubElement(tracking, "depreciation-rate").text = tracking_src.findtext("depreciation-rate")
        ET.SubElement(tracking, "input-cost").text = f"{text_as_float(src, './tracking-non-energy-input/input-cost') * cost_sched[year]:.15g}"

        mei_src = src.find("./minicam-energy-input")
        mei = ET.SubElement(period, "minicam-energy-input", {"name": mei_src.get("name")})
        ET.SubElement(mei, "coefficient").text = f"{text_as_float(src, './minicam-energy-input/coefficient') * coef_sched[year]:.15g}"
        ET.SubElement(mei, "market-name").text = mei_src.findtext("market-name")
    return out


def build_phev_stub_tech(bev_tech: ET.Element, hybrid_tech: ET.Element, future_years, uf_sched, cost_sched, coef_sched, cost_blend, capital_blend):
    bev_periods = tech_periods_by_year(bev_tech)
    hybrid_periods = tech_periods_by_year(hybrid_tech)
    out = ET.Element("stub-technology", {"name": "PHEV"})
    for year in future_years:
        bev = bev_periods[year]
        hev = hybrid_periods[year]
        utility_factor = uf_sched[year]

        bev_cost = text_as_float(bev, "./tracking-non-energy-input/input-cost")
        hev_cost = text_as_float(hev, "./tracking-non-energy-input/input-cost")
        bev_capital = text_as_float(bev, "./tracking-non-energy-input/capital-coef")
        hev_capital = text_as_float(hev, "./tracking-non-energy-input/capital-coef")
        bev_coef = text_as_float(bev, "./minicam-energy-input/coefficient")
        hev_coef = text_as_float(hev, "./minicam-energy-input/coefficient")

        period = ET.SubElement(out, "period", {"year": str(year)})
        ET.SubElement(period, "loadFactor").text = bev.findtext("loadFactor")

        tracking = ET.SubElement(period, "tracking-non-energy-input", {"name": "non-energy"})
        blended_capital = (capital_blend["BEV"] * bev_capital + capital_blend["Hybrid Liquids"] * hev_capital) * cost_sched[year]
        blended_cost = (cost_blend["BEV"] * bev_cost + cost_blend["Hybrid Liquids"] * hev_cost) * cost_sched[year]
        ET.SubElement(tracking, "capital-coef").text = f"{blended_capital:.15g}"
        ET.SubElement(tracking, "tracking-market").text = bev.findtext("./tracking-non-energy-input/tracking-market")
        ET.SubElement(tracking, "depreciation-rate").text = bev.findtext("./tracking-non-energy-input/depreciation-rate")
        ET.SubElement(tracking, "input-cost").text = f"{blended_cost:.15g}"

        elec = ET.SubElement(period, "minicam-energy-input", {"name": "elect_td_trn"})
        ET.SubElement(elec, "coefficient").text = f"{bev_coef * utility_factor * coef_sched[year]:.15g}"
        ET.SubElement(elec, "market-name").text = bev.findtext("./minicam-energy-input/market-name")

        liq = ET.SubElement(period, "minicam-energy-input", {"name": "refined liquids enduse"})
        ET.SubElement(liq, "coefficient").text = f"{hev_coef * (1 - utility_factor) * coef_sched[year]:.15g}"
        ET.SubElement(liq, "market-name").text = hev.findtext("./minicam-energy-input/market-name")
    return out


def add_interpolation_rule(parent: ET.Element, tech_name: str):
    rule = ET.SubElement(parent, "interpolation-rule", {"apply-to": "share-weight", "from-year": "2020", "to-year": "2050"})
    func_name = "s-curve" if tech_name in PLUGIN_TECHS else "fixed"
    ET.SubElement(rule, "interpolation-function", {"name": func_name})


def build_tran_technology(tech_name: str, future_years, share_sched):
    tech = ET.Element("tranTechnology", {"name": tech_name})
    add_interpolation_rule(tech, tech_name)
    years = future_years
    if tech_name == "PHEV":
        years = HISTORIC_YEARS + future_years
    for year in years:
        period = ET.SubElement(tech, "period", {"year": str(year)})
        share_value = 0 if year in HISTORIC_YEARS else share_sched[year]
        ET.SubElement(period, "share-weight").text = f"{share_value:.15g}"
        ET.SubElement(period, "CO2", {"name": "CO2"})
    return tech


def build_transport_overlay(gcam_root: Path, assumptions, source_package, ssp_name: str):
    transport_file = gcam_root / "input" / "gcamdata" / "xml" / assumptions["base_transport_files"][ssp_name]
    root = ET.parse(transport_file).getroot()

    future_years = assumptions["future_years"]
    share_sched = build_share_weight_schedule(assumptions, source_package, ssp_name)
    cost_sched = {tech: neutral_schedule(future_years, 1.0) for tech in ["BEV", "FCEV", "PHEV"]}
    coef_sched = {tech: neutral_schedule(future_years, 1.0) for tech in ["BEV", "FCEV", "PHEV"]}
    uf_sched = neutral_schedule(future_years, float(assumptions["phev"]["utility_factor"]))

    scenario = ET.Element("scenario")
    world = ET.SubElement(scenario, "world")

    for region in root.findall(".//region"):
        supplysector = region.find("./supplysector[@name='trn_pass_road_LDV_4W']")
        if supplysector is None:
            continue

        region_out = ET.SubElement(world, "region", {"name": region.get("name")})
        supply_out = ET.SubElement(region_out, "supplysector", {"name": "trn_pass_road_LDV_4W"})
        has_any = False

        for subsector_name in LDV_SUBSECTORS:
            subsector = supplysector.find(f"./tranSubsector[@name='{subsector_name}']")
            if subsector is None:
                continue
            stub_map = {stub.get("name"): stub for stub in subsector.findall("./stub-technology")}
            if "BEV" not in stub_map or "Hybrid Liquids" not in stub_map:
                continue

            sub_out = ET.SubElement(supply_out, "tranSubsector", {"name": subsector_name})
            has_any = True
            sub_out.append(build_existing_stub_tech(stub_map["BEV"], "BEV", future_years, cost_sched["BEV"], coef_sched["BEV"]))
            if "FCEV" in stub_map:
                sub_out.append(build_existing_stub_tech(stub_map["FCEV"], "FCEV", future_years, cost_sched["FCEV"], coef_sched["FCEV"]))
            sub_out.append(
                build_phev_stub_tech(
                    stub_map["BEV"],
                    stub_map["Hybrid Liquids"],
                    future_years,
                    uf_sched,
                    cost_sched["PHEV"],
                    coef_sched["PHEV"],
                    assumptions["phev"]["cost_blend"],
                    assumptions["phev"]["capital_coef_blend"]
                )
            )

        if not has_any:
            world.remove(region_out)

    gtd = ET.SubElement(world, "global-technology-database")
    core_root = ET.parse(gcam_root / "input" / "gcamdata" / "xml" / "transportation_UCD_CORE.xml").getroot()
    for subsector_name in LDV_SUBSECTORS:
        base_loc = find_base_location_info(core_root, subsector_name)
        if base_loc is None:
            continue
        loc = ET.SubElement(gtd, "location-info", {"sector-name": "trn_pass_road_LDV_4W", "subsector-name": subsector_name})
        for tech_name in ["BEV", "PHEV", "FCEV", "Hybrid Liquids", "Liquids", "NG"]:
            if tech_name not in share_sched:
                continue
            loc.append(build_tran_technology(tech_name, future_years, share_sched[tech_name]))

    return scenario


def build_query_subset(gcam_root: Path, assumptions):
    queries_path = gcam_root / "output" / "queries" / "Main_queries.xml"
    root = ET.parse(queries_path).getroot()
    wanted = set(assumptions["query_titles"])
    out = ET.Element("queries")
    group = ET.SubElement(out, "queryGroup", {"name": "ev-ssp"})
    seen = set()
    for elem in root.iter():
        title = elem.get("title")
        if title in wanted and title not in seen:
            group.append(deepcopy(elem))
            seen.add(title)
    return out


def parse_gcam_regions(gcam_root: Path):
    building_det = ET.parse(
        gcam_root / "input" / "gcamdata" / "xml" / "building_det.xml"
    ).getroot()
    return sorted(
        {
            region.get("name")
            for region in building_det.findall(".//region")
            if region.get("name")
        }
    )


def build_validation_query_file(gcam_root: Path, assumptions):
    main_queries = ET.parse(gcam_root / "output" / "queries" / "Main_queries.xml").getroot()
    diagnostics_queries = ET.parse(
        gcam_root / "output" / "gcam_diagnostics" / "batch_queries" / "Model_verification_queries.xml"
    ).getroot()

    out = ET.Element("queries")
    if assumptions["validation_region"] == "Global":
        region_names = parse_gcam_regions(gcam_root)
    else:
        region_names = [assumptions["validation_region"]]

    for title in assumptions["validation_query_titles"]:
        source = find_query_by_title(main_queries, title)
        if source is None:
            source = find_query_by_title(diagnostics_queries, title)
        if source is None:
            raise SystemExit(f"Could not find validation query titled '{title}'")

        for region_name in region_names:
            aquery = ET.SubElement(out, "aQuery")
            ET.SubElement(aquery, "region", {"name": region_name})
            aquery.append(deepcopy(source))

    return out


def build_batch_file(gcam_root: Path):
    batch_path = gcam_root / "exe" / "batch_SSP_REF.xml"
    root = ET.parse(batch_path).getroot()
    for fileset in root.findall("./ComponentSet/FileSet"):
        name = fileset.get("name")
        if name not in {"SSP1", "SSP2", "SSP3", "SSP4", "SSP5"}:
            continue
        rel = f"../input/gcamdata/xml/transportation_EV_{name}.xml"
        fileset.append(ET.Element("Value", {"name": "trn_ev"}))
        fileset[-1].text = rel
    return root


def build_config_file(gcam_root: Path):
    config_path = gcam_root / "exe" / "configuration_ssp.xml"
    root = ET.parse(config_path).getroot()
    ensure_batch_scenario_name(root)
    for value in root.findall("./Files/Value"):
        if value.get("name") == "BatchFileName":
            value.text = "batch_SSP_EV.xml"
        elif value.get("name") == "xmldb-location":
            value.text = "../output/database_basexdb_ev_ssp"
        elif value.get("name") == "batchCSVOutputFile":
            value.text = "batch-csv-out-ev-ssp.csv"
    return root


def build_baseline_config_file(gcam_root: Path):
    config_path = gcam_root / "exe" / "configuration_ssp.xml"
    root = ET.parse(config_path).getroot()
    ensure_batch_scenario_name(root)
    for value in root.findall("./Files/Value"):
        if value.get("name") == "xmldb-location":
            value.text = "../output/database_basexdb_ssp_baseline"
        elif value.get("name") == "batchCSVOutputFile":
            value.text = "batch-csv-out-ssp-baseline.csv"
    return root


def build_validation_batch_file():
    root = ET.Element("ModelInterfaceBatch")
    klass = ET.SubElement(root, "class", {"name": "ModelInterface.ModelGUI2.DbViewer"})

    scenarios = ["GCAM_SSP1", "GCAM_SSP2", "GCAM_SSP3", "GCAM_SSP4", "GCAM_SSP5"]
    commands = [
        ("../output/database_basexdb_ssp_baseline", "../output/ev_validation/baseline_validation.csv"),
        ("../output/database_basexdb_ev_ssp", "../output/ev_validation/ev_validation.csv"),
    ]

    for db_path, out_path in commands:
        cmd = ET.SubElement(klass, "command", {"name": "XMLDB Batch File"})
        for scenario_name in scenarios:
            ET.SubElement(cmd, "scenario", {"name": scenario_name})
        ET.SubElement(cmd, "queryFile").text = "../output/queries/EV_SSP_validation_queries.xml"
        ET.SubElement(cmd, "outFile").text = out_path
        ET.SubElement(cmd, "xmldbLocation").text = db_path
        ET.SubElement(cmd, "batchQueryResultsInDifferentSheets").text = "false"
        ET.SubElement(cmd, "batchQueryIncludeCharts").text = "false"
        ET.SubElement(cmd, "batchQuerySplitRunsInDifferentSheets").text = "false"
        ET.SubElement(cmd, "batchQueryReplaceResults").text = "true"
        ET.SubElement(cmd, "coresToUse").text = "2"

    return root


def build_run_script():
    return """#!/bin/sh

# Change to the appropriate working directory
DIR=`echo "'$0'" | xargs dirname`
DIR2=`echo "'$DIR'"`

eval cd $DIR2

JAVA_HOME=$(/usr/libexec/java_home 2>/dev/null)
if [ -z "$JAVA_HOME" ]
then
    for CANDIDATE in \\
        /usr/local/opt/openjdk/libexec/openjdk.jdk/Contents/Home \\
        /opt/homebrew/opt/openjdk/libexec/openjdk.jdk/Contents/Home
    do
        if [ -x "${CANDIDATE}/bin/java" ]
        then
            JAVA_HOME="${CANDIDATE}"
            break
        fi
    done
fi
if [ -z "$JAVA_HOME" ]
then
    >&2 echo "ERROR: Could not find Java install location."
    exit 1
elif [ ${JAVA_HOME#*1.6} != $JAVA_HOME ]
then
    >&2 echo "ERROR: GCAM now requires Java 1.7+"
    exit 1
elif [[ ${JAVA_HOME#*jdk1.7} != $JAVA_HOME || ${JAVA_HOME#*jdk1.8} != $JAVA_HOME ]]
then
    LIB_PATH=${JAVA_HOME}/jre/lib/server
else
    LIB_PATH=${JAVA_HOME}/lib/server
fi

if [ ! -h ../libs/java/lib ]
then
    ln -s ${LIB_PATH} ../libs/java/lib
fi

./gcam -C configuration_ssp_ev.xml
"""


def build_baseline_run_script():
    return """#!/bin/sh

# Change to the appropriate working directory
DIR=`echo "'$0'" | xargs dirname`
DIR2=`echo "'$DIR'"`

eval cd $DIR2

JAVA_HOME=$(/usr/libexec/java_home 2>/dev/null)
if [ -z "$JAVA_HOME" ]
then
    for CANDIDATE in \\
        /usr/local/opt/openjdk/libexec/openjdk.jdk/Contents/Home \\
        /opt/homebrew/opt/openjdk/libexec/openjdk.jdk/Contents/Home
    do
        if [ -x "${CANDIDATE}/bin/java" ]
        then
            JAVA_HOME="${CANDIDATE}"
            break
        fi
    done
fi
if [ -z "$JAVA_HOME" ]
then
    >&2 echo "ERROR: Could not find Java install location."
    exit 1
elif [ ${JAVA_HOME#*1.6} != $JAVA_HOME ]
then
    >&2 echo "ERROR: GCAM now requires Java 1.7+"
    exit 1
elif [[ ${JAVA_HOME#*jdk1.7} != $JAVA_HOME || ${JAVA_HOME#*jdk1.8} != $JAVA_HOME ]]
then
    LIB_PATH=${JAVA_HOME}/jre/lib/server
else
    LIB_PATH=${JAVA_HOME}/lib/server
fi

if [ ! -h ../libs/java/lib ]
then
    ln -s ${LIB_PATH} ../libs/java/lib
fi

./gcam -C configuration_ssp_baseline.xml
"""


def build_validation_run_script():
    return """#!/bin/sh

DIR=`echo "'$0'" | xargs dirname`
DIR2=`echo "'$DIR'"`

eval cd $DIR2

JAVA_HOME=$(/usr/libexec/java_home 2>/dev/null)
if [ -z "$JAVA_HOME" ]
then
    for CANDIDATE in \\
        /usr/local/opt/openjdk/libexec/openjdk.jdk/Contents/Home \\
        /opt/homebrew/opt/openjdk/libexec/openjdk.jdk/Contents/Home
    do
        if [ -x "${CANDIDATE}/bin/java" ]
        then
            JAVA_HOME="${CANDIDATE}"
            break
        fi
    done
fi
if [ -z "$JAVA_HOME" ]
then
    >&2 echo "ERROR: Could not find Java install location."
    exit 1
elif [ ${JAVA_HOME#*1.6} != $JAVA_HOME ]
then
    >&2 echo "ERROR: GCAM now requires Java 1.7+"
    exit 1
fi

mkdir -p ../output/ev_validation

"$JAVA_HOME/bin/java" -Xmx4g \\
  -cp "../ModelInterface/ModelInterface.app/Contents/Resources/Java/ModelInterface.jar:../ModelInterface/ModelInterface.app/Contents/Resources/Java/jars/*" \\
  ModelInterface.InterfaceMain \\
  -b xmldb_batch_ssp_vs_ev_validation.xml \\
  -l ../output/ev_validation/modelinterface_validation.log

python3 ../scripts/compare_ssp_ev_validation.py \\
  --baseline ../output/ev_validation/baseline_validation.csv \\
  --ev ../output/ev_validation/ev_validation.csv \\
  --out ../output/ev_validation/ev_minus_baseline.csv \\
  --summary ../output/ev_validation/ev_minus_baseline_summary.csv
"""


def main():
    args = parse_args()
    addon_root = Path(__file__).resolve().parents[1]
    generated_root = addon_root / "generated"
    assumptions = load_json(addon_root / "data" / "ev_ssp_assumptions.json")
    source_package = load_source_package(addon_root, assumptions)

    if not args.gcam_root.exists():
        raise SystemExit(f"GCAM root not found: {args.gcam_root}")

    for ssp_name in ["SSP1", "SSP2", "SSP3", "SSP4", "SSP5"]:
        overlay = build_transport_overlay(args.gcam_root, assumptions, source_package, ssp_name)
        write_xml(overlay, generated_root / "input" / "gcamdata" / "xml" / f"transportation_EV_{ssp_name}.xml")

    write_xml(build_query_subset(args.gcam_root, assumptions), generated_root / "output" / "queries" / "EV_SSP_queries.xml")
    write_xml(build_validation_query_file(args.gcam_root, assumptions), generated_root / "output" / "queries" / "EV_SSP_validation_queries.xml")
    write_xml(build_batch_file(args.gcam_root), generated_root / "exe" / "batch_SSP_EV.xml")
    write_xml(build_config_file(args.gcam_root), generated_root / "exe" / "configuration_ssp_ev.xml")
    write_xml(build_baseline_config_file(args.gcam_root), generated_root / "exe" / "configuration_ssp_baseline.xml")
    write_xml(build_validation_batch_file(), generated_root / "exe" / "xmldb_batch_ssp_vs_ev_validation.xml")
    write_text(generated_root / "exe" / "run-gcam-ssp-baseline.command", build_baseline_run_script(), executable=True)
    write_text(generated_root / "exe" / "run-gcam-ssp-ev.command", build_run_script(), executable=True)
    write_text(generated_root / "exe" / "run-validate-ssp-vs-ev.command", build_validation_run_script(), executable=True)
    copy_file(addon_root / "scripts" / "compare_ssp_ev_validation.py", generated_root / "scripts" / "compare_ssp_ev_validation.py", executable=True)

    print(f"Generated EV SSP add-on under {generated_root}")


if __name__ == "__main__":
    main()
