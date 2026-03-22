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

PLOT_PYTHON=""
for CANDIDATE in "${GCAM_PLOT_PYTHON}" /Users/sekiyamitsuna/miniconda3/bin/python python3 python
do
    if [ -z "$CANDIDATE" ]
    then
        continue
    fi
    if env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
        "$CANDIDATE" -c "import matplotlib" >/dev/null 2>&1
    then
        PLOT_PYTHON="$CANDIDATE"
        break
    fi
done

if [ -z "$PLOT_PYTHON" ]
then
    >&2 echo "ERROR: Could not find a Python interpreter with matplotlib."
    exit 1
fi

mkdir -p ../output/three_way_validation/plots

"$JAVA_HOME/bin/java" -Xmx4g \
  -cp "../ModelInterface/ModelInterface.app/Contents/Resources/Java/ModelInterface.jar:../ModelInterface/ModelInterface.app/Contents/Resources/Java/jars/*" \
  ModelInterface.InterfaceMain \
  -b xmldb_batch_ssp_baseline_for_three_way_validation.xml \
  -l ../output/three_way_validation/modelinterface_baseline.log

"$JAVA_HOME/bin/java" -Xmx4g \
  -cp "../ModelInterface/ModelInterface.app/Contents/Resources/Java/ModelInterface.jar:../ModelInterface/ModelInterface.app/Contents/Resources/Java/jars/*" \
  ModelInterface.InterfaceMain \
  -b xmldb_batch_ssp_ev_for_three_way_validation.xml \
  -l ../output/three_way_validation/modelinterface_ev.log

"$JAVA_HOME/bin/java" -Xmx4g \
  -cp "../ModelInterface/ModelInterface.app/Contents/Resources/Java/ModelInterface.jar:../ModelInterface/ModelInterface.app/Contents/Resources/Java/jars/*" \
  ModelInterface.InterfaceMain \
  -b xmldb_batch_ssp_ev_dc_for_three_way_validation.xml \
  -l ../output/three_way_validation/modelinterface_ev_dc.log

env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  "$PLOT_PYTHON" ../scripts/compare_ssp_three_way_validation.py \
  --baseline ../output/three_way_validation/baseline_validation.csv \
  --ev ../output/three_way_validation/ev_validation.csv \
  --ev-dc ../output/three_way_validation/ev_dc_validation.csv \
  --out ../output/three_way_validation/three_way_detail.csv \
  --summary ../output/three_way_validation/three_way_summary.csv

env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  "$PLOT_PYTHON" ../scripts/plot_three_way_validation_results.py \
  --detail ../output/three_way_validation/three_way_detail.csv \
  --summary ../output/three_way_validation/three_way_summary.csv \
  --out-dir ../output/three_way_validation/plots
