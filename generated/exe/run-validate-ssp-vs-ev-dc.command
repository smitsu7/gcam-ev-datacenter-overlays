#!/bin/sh

DIR=`echo "'$0'" | xargs dirname`
DIR2=`echo "'$DIR'"`

eval cd $DIR2

JAVA_HOME=$(/usr/libexec/java_home 2>/dev/null)
if [ -z "$JAVA_HOME" ]
then
    for CANDIDATE in \
        /usr/local/opt/openjdk/libexec/openjdk.jdk/Contents/Home \
        /opt/homebrew/opt/openjdk/libexec/openjdk.jdk/Contents/Home \
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

mkdir -p ../output/ev_dc_validation

"$JAVA_HOME/bin/java" -Xmx4g \
  -cp "../ModelInterface/ModelInterface.app/Contents/Resources/Java/ModelInterface.jar:../ModelInterface/ModelInterface.app/Contents/Resources/Java/jars/*" \
  ModelInterface.InterfaceMain \
  -b xmldb_batch_ssp_baseline_for_dc_validation.xml \
  -l ../output/ev_dc_validation/modelinterface_baseline_validation.log

"$JAVA_HOME/bin/java" -Xmx4g \
  -cp "../ModelInterface/ModelInterface.app/Contents/Resources/Java/ModelInterface.jar:../ModelInterface/ModelInterface.app/Contents/Resources/Java/jars/*" \
  ModelInterface.InterfaceMain \
  -b xmldb_batch_ssp_ev_dc_validation.xml \
  -l ../output/ev_dc_validation/modelinterface_validation.log

python3 ../scripts/compare_ssp_overlay_validation.py \
  --baseline ../output/dc_validation/baseline_validation.csv \
  --overlay ../output/ev_dc_validation/ev_dc_validation.csv \
  --out ../output/ev_dc_validation/ev_dc_minus_baseline.csv \
  --summary ../output/ev_dc_validation/ev_dc_minus_baseline_summary.csv
