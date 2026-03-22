#!/usr/bin/env python3
import argparse
import json
import math
import shutil
import xml.etree.ElementTree as ET
from copy import deepcopy
from pathlib import Path


TWH_TO_EJ = 0.0036
SSP_NAMES = [f"SSP{i}" for i in range(1, 6)]
SCENARIO_NAMES = [f"GCAM_SSP{i}" for i in range(1, 6)]


def parse_args():
    script_dir = Path(__file__).resolve().parent
    addon_root = script_dir.parent
    default_gcam = addon_root.parent / "gcam-v7.0-Mac_arm64-Release-Package"
    parser = argparse.ArgumentParser(
        description="Generate data center SSP overlay files for GCAM."
    )
    parser.add_argument("--gcam-root", type=Path, default=default_gcam)
    return parser.parse_args()


def load_json(path: Path):
    return json.loads(path.read_text())


def load_source_package(addon_root: Path, assumptions):
    return load_json(addon_root / assumptions["source_package"])


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


def format_num(value: float) -> str:
    return f"{value:.15g}"


def interpolate_piecewise(anchor_map, years):
    anchors = sorted((int(year), float(value)) for year, value in anchor_map.items())
    out = {}
    for year in years:
        if year <= anchors[0][0]:
            out[year] = anchors[0][1]
            continue
        if year >= anchors[-1][0]:
            out[year] = anchors[-1][1]
            continue
        for (left_year, left_value), (right_year, right_value) in zip(anchors[:-1], anchors[1:]):
            if left_year <= year <= right_year:
                if year == left_year:
                    out[year] = left_value
                elif year == right_year:
                    out[year] = right_value
                else:
                    slope = (right_value - left_value) / (right_year - left_year)
                    out[year] = left_value + slope * (year - left_year)
                break
    return out


def twh_to_ej(value_twh: float) -> float:
    return value_twh * TWH_TO_EJ


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


def append_fileset_value(fileset: ET.Element, name: str, text: str):
    value = ET.SubElement(fileset, "Value", {"name": name})
    value.text = text


def parse_region_weights_source(gcam_root: Path):
    building_det = ET.parse(
        gcam_root / "input" / "gcamdata" / "xml" / "building_det.xml"
    ).getroot()
    region_data = {}
    for region in building_det.findall(".//region"):
        region_name = region.get("name")
        stub_tech = region.find(
            "./supplysector[@name='comm others']/subsector[@name='electricity']/stub-technology[@name='electricity']"
        )
        if stub_tech is None:
            raise SystemExit(f"Missing comm others electricity template for region {region_name}")

        calibrated_2015 = None
        for period in stub_tech.findall("./period"):
            if int(period.get("year")) != 2015:
                continue
            calibrated_text = period.findtext(
                "./minicam-energy-input[@name='elect_td_bld']/calibrated-value"
            )
            if calibrated_text is not None:
                calibrated_2015 = float(calibrated_text)
            break

        if calibrated_2015 is None or calibrated_2015 <= 0:
            raise SystemExit(
                f"Could not find positive 2015 commercial electricity calibration for region {region_name}"
            )
        region_data[region_name] = {"comm_electricity_2015": calibrated_2015}
    return region_data


def parse_datacenter_gtd_template(gcam_root: Path, sector_name: str):
    building_det = ET.parse(
        gcam_root / "input" / "gcamdata" / "xml" / "building_det.xml"
    ).getroot()
    location = building_det.find(
        ".//global-technology-database/location-info[@sector-name='comm others'][@subsector-name='electricity']"
    )
    if location is None:
        raise SystemExit("Could not find comm others electricity GTD template.")
    copied = deepcopy(location)
    copied.set("sector-name", sector_name)
    return copied


def parse_gdp_paths(gcam_root: Path, ssp_name: str, model_years):
    root = ET.parse(
        gcam_root / "input" / "gcamdata" / "xml" / f"socioeconomics_{ssp_name}.xml"
    ).getroot()
    gdp_paths = {}
    model_years = set(model_years)
    for region in root.findall(".//region"):
        region_name = region.get("name")
        year_map = {}
        for acct in region.findall("./nationalAccountContainer/nationalAccount"):
            year = int(acct.get("year"))
            if year in model_years:
                year_map[year] = float(acct.findtext("GDP"))
        missing = sorted(model_years - set(year_map))
        if missing:
            raise SystemExit(
                f"Missing GDP years for region {region_name} in {ssp_name}: {missing}"
            )
        gdp_paths[region_name] = year_map
    return gdp_paths


def normalize_weights(weights):
    total = sum(weights.values())
    if total <= 0:
        raise SystemExit("Regional weight normalization failed because the sum of weights is not positive.")
    return {key: value / total for key, value in weights.items()}


def build_group_member_splits(region_data, assumptions):
    group_members = {
        group_name: list(members)
        for group_name, members in assumptions["regional_group_members"].items()
    }
    assigned_regions = {region for members in group_members.values() for region in members}
    rest_members = sorted(set(region_data) - assigned_regions)
    if not rest_members:
        raise SystemExit("Rest-of-world datacenter group is empty.")

    group_members[assumptions["rest_of_world_group_name"]] = rest_members

    splits = {}
    for group_name, members in group_members.items():
        weights = {
            region: region_data[region]["comm_electricity_2015"]
            for region in members
        }
        splits[group_name] = normalize_weights(weights)
    return group_members, splits


def build_group_twh_series(assumptions, source_package, ssp_name: str):
    years = [int(year) for year in assumptions["model_years"] if int(year) >= 2020]
    case_name = assumptions["scenario_to_case"][ssp_name]

    global_2020 = float(assumptions["global_twh_anchors"]["2020"])
    global_2024 = float(assumptions["global_twh_anchors"]["2024"])
    global_2030 = float(assumptions["global_twh_anchors"]["2030"])
    global_2035 = float(assumptions["global_twh_anchors"]["2035_case"][case_name])

    shares_2024 = assumptions["regional_anchor_shares_2024"]
    group_2024 = {
        group_name: global_2024 * float(share)
        for group_name, share in shares_2024.items()
    }
    rest_name = assumptions["rest_of_world_group_name"]
    group_2024[rest_name] = global_2024 - sum(group_2024.values())

    group_2020 = {
        group_name: global_2020 * (value / global_2024)
        for group_name, value in group_2024.items()
    }

    usa_2030 = group_2024["USA"] + float(
        assumptions["regional_anchor_adjustments_2030_twh"]["USA_increment_from_2024"]
    )
    remaining_2030 = global_2030 - usa_2030
    if remaining_2030 <= 0:
        raise SystemExit("Derived 2030 non-USA datacenter demand is non-positive.")

    non_usa_weights = {
        group_name: value
        for group_name, value in group_2024.items()
        if group_name != "USA"
    }
    non_usa_total = sum(non_usa_weights.values())
    group_2030 = {"USA": usa_2030}
    for group_name, value in non_usa_weights.items():
        group_2030[group_name] = remaining_2030 * (value / non_usa_total)

    scale_2035 = global_2035 / global_2030
    group_2035 = {
        group_name: value * scale_2035
        for group_name, value in group_2030.items()
    }

    out = {}
    for group_name in group_2030:
        anchor_map = {
            2020: group_2020[group_name],
            2024: group_2024[group_name],
            2030: group_2030[group_name],
            2035: group_2035[group_name],
        }
        pre_2035 = interpolate_piecewise(anchor_map, [year for year in years if year <= 2035])
        for year in years:
            if year > 2035:
                pre_2035[year] = group_2035[group_name]
        out[group_name] = pre_2035
    return out


def build_regional_energy_paths(region_data, assumptions, group_twh_series):
    group_members, group_splits = build_group_member_splits(region_data, assumptions)
    regional_paths = {}
    for group_name, members in group_members.items():
        splits = group_splits[group_name]
        for region in members:
            regional_paths[region] = {
                year: twh_to_ej(group_twh_series[group_name][year] * splits[region])
                for year in group_twh_series[group_name]
            }
    return regional_paths


def solve_income_elasticity(prev_demand, curr_demand, prev_gdp, curr_gdp):
    if prev_demand <= 0 or curr_demand <= 0:
        return 0.0
    gdp_ratio = curr_gdp / prev_gdp
    demand_ratio = curr_demand / prev_demand
    if gdp_ratio <= 0 or math.isclose(gdp_ratio, 1.0):
        return 0.0 if math.isclose(demand_ratio, 1.0) else 0.0
    return math.log(demand_ratio) / math.log(gdp_ratio)


def build_historical_and_future_paths(assumptions, regional_targets, gdp_paths):
    seed_year = int(assumptions["historical_seed_year"])
    seed_fraction = float(assumptions["historical_seed_fraction_of_2020"])
    future_years = [int(year) for year in assumptions["model_years"] if int(year) >= 2020]
    historic_zero_years = [int(year) for year in assumptions["historic_zero_years"]]

    regional_paths = {}
    for region, future_targets in regional_targets.items():
        seed_value = future_targets[2020] * seed_fraction
        base_service = {year: 0.0 for year in historic_zero_years}
        base_service[seed_year] = seed_value

        elasticities = {}
        prev_year = seed_year
        prev_demand = seed_value
        for year in future_years:
            curr_demand = future_targets[year]
            elasticities[year] = solve_income_elasticity(
                prev_demand,
                curr_demand,
                gdp_paths[region][prev_year],
                gdp_paths[region][year],
            )
            prev_year = year
            prev_demand = curr_demand

        regional_paths[region] = {
            "base_service": base_service,
            "future_targets": future_targets,
            "income_elasticities": elasticities,
        }
    return regional_paths


def build_supplysector(region_name: str, assumptions, region_path):
    supplysector = ET.Element("supplysector", {"name": assumptions["validation_sector_name"]})
    sector_logit = ET.SubElement(supplysector, "relative-cost-logit")
    ET.SubElement(
        sector_logit, "logit-exponent", {"fillout": "1", "year": "1975"}
    ).text = "-3"
    ET.SubElement(supplysector, "output-unit").text = "EJ"
    ET.SubElement(supplysector, "input-unit").text = "EJ"
    ET.SubElement(supplysector, "price-unit").text = "1975$/GJ"
    ET.SubElement(supplysector, "keyword", {"final-energy": "building"})

    subsector = ET.SubElement(supplysector, "subsector", {"name": "electricity"})
    subsector_logit = ET.SubElement(subsector, "relative-cost-logit")
    ET.SubElement(
        subsector_logit, "logit-exponent", {"fillout": "1", "year": "1975"}
    ).text = "-6"
    ET.SubElement(subsector, "share-weight", {"fillout": "1", "year": "1975"}).text = "1"
    interpolation = ET.SubElement(
        subsector,
        "interpolation-rule",
        {"apply-to": "share-weight", "from-year": "2015", "to-year": "2100"},
    )
    ET.SubElement(interpolation, "interpolation-function", {"name": "fixed"})

    stub = ET.SubElement(subsector, "stub-technology", {"name": "electricity"})
    for year in assumptions["model_years"]:
        period = ET.SubElement(stub, "period", {"year": str(year)})
        energy_input = ET.SubElement(period, "minicam-energy-input", {"name": "elect_td_bld"})
        ET.SubElement(energy_input, "coefficient").text = "1"
        ET.SubElement(energy_input, "market-name").text = region_name
        ET.SubElement(period, "share-weight").text = "1"
        if year <= 2015:
            cal_output = region_path["base_service"].get(year, 0.0)
            caldata = ET.SubElement(period, "CalDataOutput")
            ET.SubElement(caldata, "calOutputValue").text = format_num(cal_output)

    for year in [1975, 1990, 2005, 2010, 2015]:
        ET.SubElement(subsector, "share-weight", {"year": str(year)}).text = "1"
    return supplysector


def build_final_demand(assumptions, region_path):
    final_demand = ET.Element("energy-final-demand", {"name": assumptions["validation_sector_name"]})
    ET.SubElement(final_demand, "perCapitaBased").text = "0"
    ET.SubElement(final_demand, "final-energy-consumer")
    for year in assumptions["model_years"]:
        if year > 2015:
            continue
        ET.SubElement(final_demand, "base-service", {"year": str(year)}).text = format_num(
            region_path["base_service"].get(year, 0.0)
        )
    for year in assumptions["model_years"]:
        if year < 2020:
            continue
        ET.SubElement(final_demand, "income-elasticity", {"year": str(year)}).text = format_num(
            region_path["income_elasticities"][year]
        )
        ET.SubElement(final_demand, "price-elasticity", {"year": str(year)}).text = "0"
    return final_demand


def build_overlay(gcam_root: Path, assumptions, source_package, ssp_name: str):
    region_data = parse_region_weights_source(gcam_root)
    gdp_paths = parse_gdp_paths(gcam_root, ssp_name, assumptions["model_years"])
    group_twh_series = build_group_twh_series(assumptions, source_package, ssp_name)
    regional_targets = build_regional_energy_paths(region_data, assumptions, group_twh_series)
    regional_paths = build_historical_and_future_paths(assumptions, regional_targets, gdp_paths)

    scenario = ET.Element("scenario")
    world = ET.SubElement(scenario, "world")
    for region_name in sorted(region_data):
        region = ET.SubElement(world, "region", {"name": region_name})
        region_path = regional_paths[region_name]
        region.append(build_supplysector(region_name, assumptions, region_path))
        region.append(build_final_demand(assumptions, region_path))
    gtd = ET.SubElement(world, "global-technology-database")
    gtd.append(parse_datacenter_gtd_template(gcam_root, assumptions["validation_sector_name"]))
    return scenario


def build_query_subset(gcam_root: Path, assumptions):
    queries_path = gcam_root / "output" / "queries" / "Main_queries.xml"
    root = ET.parse(queries_path).getroot()
    wanted = set(assumptions["query_titles"])
    out = ET.Element("queries")
    group = ET.SubElement(out, "queryGroup", {"name": "ev-dc-ssp"})
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
    main_queries = ET.parse(
        gcam_root / "output" / "queries" / "Main_queries.xml"
    ).getroot()

    out = ET.Element("queries")
    if assumptions["validation_region"] == "Global":
        region_names = parse_gcam_regions(gcam_root)
    else:
        region_names = [assumptions["validation_region"]]

    for title in assumptions["validation_query_titles"]:
        source = find_query_by_title(main_queries, title)
        if source is None:
            raise SystemExit(f"Could not find validation query titled '{title}'")

        for region_name in region_names:
            aquery = ET.SubElement(out, "aQuery")
            ET.SubElement(aquery, "region", {"name": region_name})
            aquery.append(deepcopy(source))
    return out


def build_dc_batch_file(gcam_root: Path):
    root = ET.parse(gcam_root / "exe" / "batch_SSP_REF.xml").getroot()
    for fileset in root.findall("./ComponentSet/FileSet"):
        name = fileset.get("name")
        if name in SSP_NAMES:
            append_fileset_value(
                fileset,
                "sec_dc",
                f"../input/gcamdata/xml/datacenter_sector_{name}.xml",
            )
    return root


def build_ev_dc_batch_file(gcam_root: Path):
    root = ET.parse(gcam_root / "exe" / "batch_SSP_REF.xml").getroot()
    for fileset in root.findall("./ComponentSet/FileSet"):
        name = fileset.get("name")
        if name in SSP_NAMES:
            append_fileset_value(
                fileset,
                "trn_ev",
                f"../input/gcamdata/xml/transportation_EV_{name}.xml",
            )
            append_fileset_value(
                fileset,
                "sec_dc",
                f"../input/gcamdata/xml/datacenter_sector_{name}.xml",
            )
    return root


def build_config_file(gcam_root: Path, batch_file: str, db_path: str, batch_csv: str):
    root = ET.parse(gcam_root / "exe" / "configuration_ssp.xml").getroot()
    ensure_batch_scenario_name(root)
    for value in root.findall("./Files/Value"):
        if value.get("name") == "BatchFileName":
            value.text = batch_file
        elif value.get("name") == "xmldb-location":
            value.text = db_path
        elif value.get("name") == "batchCSVOutputFile":
            value.text = batch_csv
    return root


def build_validation_batch_file(database_path: str, output_path: str, query_file: str):
    root = ET.Element("ModelInterfaceBatch")
    klass = ET.SubElement(root, "class", {"name": "ModelInterface.ModelGUI2.DbViewer"})
    command = ET.SubElement(klass, "command", {"name": "XMLDB Batch File"})
    for scenario_name in SCENARIO_NAMES:
        ET.SubElement(command, "scenario", {"name": scenario_name})
    ET.SubElement(command, "queryFile").text = query_file
    ET.SubElement(command, "outFile").text = output_path
    ET.SubElement(command, "xmldbLocation").text = database_path
    ET.SubElement(command, "batchQueryResultsInDifferentSheets").text = "false"
    ET.SubElement(command, "batchQueryIncludeCharts").text = "false"
    ET.SubElement(command, "batchQuerySplitRunsInDifferentSheets").text = "false"
    ET.SubElement(command, "batchQueryReplaceResults").text = "true"
    ET.SubElement(command, "coresToUse").text = "2"
    return root


def build_run_script(config_name: str):
    return f"""#!/bin/sh

DIR=`echo "'$0'" | xargs dirname`
DIR2=`echo "'$DIR'"`

eval cd $DIR2

JAVA_HOME=$(/usr/libexec/java_home 2>/dev/null)
if [ -z "$JAVA_HOME" ]
then
    for CANDIDATE in \\
        /usr/local/opt/openjdk/libexec/openjdk.jdk/Contents/Home \\
        /opt/homebrew/opt/openjdk/libexec/openjdk.jdk/Contents/Home \\
        /Users/sekiyamitsuna/CodexCLI/GCAM/.jdk/jdk-17.0.17+10/Contents/Home
    do
        if [ -x "${{CANDIDATE}}/bin/java" ]
        then
            JAVA_HOME="${{CANDIDATE}}"
            break
        fi
    done
fi
if [ -z "$JAVA_HOME" ]
then
    >&2 echo "ERROR: Could not find Java install location."
    exit 1
elif [ ${{JAVA_HOME#*1.6}} != $JAVA_HOME ]
then
    >&2 echo "ERROR: GCAM now requires Java 1.7+"
    exit 1
elif [[ ${{JAVA_HOME#*jdk1.7}} != $JAVA_HOME || ${{JAVA_HOME#*jdk1.8}} != $JAVA_HOME ]]
then
    LIB_PATH=${{JAVA_HOME}}/jre/lib/server
else
    LIB_PATH=${{JAVA_HOME}}/lib/server
fi

if [ ! -h ../libs/java/lib ]
then
    ln -s ${{LIB_PATH}} ../libs/java/lib
fi

./gcam -C {config_name}
"""


def build_three_way_validation_run_script():
    return """#!/bin/sh

DIR=`echo "'$0'" | xargs dirname`
DIR2=`echo "'$DIR'"`

eval cd $DIR2

JAVA_HOME=$(/usr/libexec/java_home 2>/dev/null)
if [ -z "$JAVA_HOME" ]
then
    for CANDIDATE in \\
        /usr/local/opt/openjdk/libexec/openjdk.jdk/Contents/Home \\
        /opt/homebrew/opt/openjdk/libexec/openjdk.jdk/Contents/Home \\
        /Users/sekiyamitsuna/CodexCLI/GCAM/.jdk/jdk-17.0.17+10/Contents/Home
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
fi

mkdir -p ../output/three_way_validation/plots

"$JAVA_HOME/bin/java" -Xmx4g \\
  -cp "../ModelInterface/ModelInterface.app/Contents/Resources/Java/ModelInterface.jar:../ModelInterface/ModelInterface.app/Contents/Resources/Java/jars/*" \\
  ModelInterface.InterfaceMain \\
  -b xmldb_batch_ssp_baseline_for_three_way_validation.xml \\
  -l ../output/three_way_validation/modelinterface_baseline.log

"$JAVA_HOME/bin/java" -Xmx4g \\
  -cp "../ModelInterface/ModelInterface.app/Contents/Resources/Java/ModelInterface.jar:../ModelInterface/ModelInterface.app/Contents/Resources/Java/jars/*" \\
  ModelInterface.InterfaceMain \\
  -b xmldb_batch_ssp_ev_for_three_way_validation.xml \\
  -l ../output/three_way_validation/modelinterface_ev.log

"$JAVA_HOME/bin/java" -Xmx4g \\
  -cp "../ModelInterface/ModelInterface.app/Contents/Resources/Java/ModelInterface.jar:../ModelInterface/ModelInterface.app/Contents/Resources/Java/jars/*" \\
  ModelInterface.InterfaceMain \\
  -b xmldb_batch_ssp_ev_dc_for_three_way_validation.xml \\
  -l ../output/three_way_validation/modelinterface_ev_dc.log

python3 ../scripts/compare_ssp_three_way_validation.py \\
  --baseline ../output/three_way_validation/baseline_validation.csv \\
  --ev ../output/three_way_validation/ev_validation.csv \\
  --ev-dc ../output/three_way_validation/ev_dc_validation.csv \\
  --out ../output/three_way_validation/three_way_detail.csv \\
  --summary ../output/three_way_validation/three_way_summary.csv

python3 ../scripts/plot_three_way_validation_results.py \\
  --detail ../output/three_way_validation/three_way_detail.csv \\
  --summary ../output/three_way_validation/three_way_summary.csv \\
  --out-dir ../output/three_way_validation/plots
"""


def main():
    args = parse_args()
    addon_root = Path(__file__).resolve().parents[1]
    generated_root = addon_root / "generated"
    assumptions = load_json(addon_root / "data" / "datacenter_ssp_assumptions.json")
    source_package = load_source_package(addon_root, assumptions)

    if not args.gcam_root.exists():
        raise SystemExit(f"GCAM root not found: {args.gcam_root}")

    for ssp_name in SSP_NAMES:
        overlay = build_overlay(args.gcam_root, assumptions, source_package, ssp_name)
        write_xml(
            overlay,
            generated_root / "input" / "gcamdata" / "xml" / f"datacenter_sector_{ssp_name}.xml",
        )

    write_xml(
        build_query_subset(args.gcam_root, assumptions),
        generated_root / "output" / "queries" / "DC_SSP_queries.xml",
    )
    write_xml(
        build_validation_query_file(args.gcam_root, assumptions),
        generated_root / "output" / "queries" / "EV_DC_SSP_validation_queries.xml",
    )
    write_xml(
        build_dc_batch_file(args.gcam_root),
        generated_root / "exe" / "batch_SSP_DC.xml",
    )
    write_xml(
        build_ev_dc_batch_file(args.gcam_root),
        generated_root / "exe" / "batch_SSP_EV_DC.xml",
    )
    write_xml(
        build_config_file(
            args.gcam_root,
            "batch_SSP_DC.xml",
            "../output/database_basexdb_dc_ssp",
            "batch-csv-out-dc-ssp.csv",
        ),
        generated_root / "exe" / "configuration_ssp_dc.xml",
    )
    write_xml(
        build_config_file(
            args.gcam_root,
            "batch_SSP_EV_DC.xml",
            "../output/database_basexdb_ev_dc_ssp",
            "batch-csv-out-ev-dc-ssp.csv",
        ),
        generated_root / "exe" / "configuration_ssp_ev_dc.xml",
    )

    validation_query_path = "../output/queries/EV_DC_SSP_validation_queries.xml"
    write_xml(
        build_validation_batch_file(
            "../output/database_basexdb_ssp_baseline",
            "../output/three_way_validation/baseline_validation.csv",
            validation_query_path,
        ),
        generated_root / "exe" / "xmldb_batch_ssp_baseline_for_three_way_validation.xml",
    )
    write_xml(
        build_validation_batch_file(
            "../output/database_basexdb_ev_ssp",
            "../output/three_way_validation/ev_validation.csv",
            validation_query_path,
        ),
        generated_root / "exe" / "xmldb_batch_ssp_ev_for_three_way_validation.xml",
    )
    write_xml(
        build_validation_batch_file(
            "../output/database_basexdb_ev_dc_ssp",
            "../output/three_way_validation/ev_dc_validation.csv",
            validation_query_path,
        ),
        generated_root / "exe" / "xmldb_batch_ssp_ev_dc_for_three_way_validation.xml",
    )

    write_text(
        generated_root / "exe" / "run-gcam-ssp-dc.command",
        build_run_script("configuration_ssp_dc.xml"),
        executable=True,
    )
    write_text(
        generated_root / "exe" / "run-gcam-ssp-ev-dc.command",
        build_run_script("configuration_ssp_ev_dc.xml"),
        executable=True,
    )
    write_text(
        generated_root / "exe" / "run-validate-ssp-three-way.command",
        build_three_way_validation_run_script(),
        executable=True,
    )
    copy_file(
        addon_root / "scripts" / "compare_ssp_three_way_validation.py",
        generated_root / "scripts" / "compare_ssp_three_way_validation.py",
        executable=True,
    )
    copy_file(
        addon_root / "scripts" / "plot_three_way_validation_results.py",
        generated_root / "scripts" / "plot_three_way_validation_results.py",
        executable=True,
    )

    print(f"Generated data center SSP add-on under {generated_root}")


if __name__ == "__main__":
    main()
