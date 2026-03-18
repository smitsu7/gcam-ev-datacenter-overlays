#!/bin/sh

# Change to the appropriate working directory
DIR=`echo "'$0'" | xargs dirname`
DIR2=`echo "'$DIR'"`

eval cd $DIR2

JAVA_HOME=$(/usr/libexec/java_home 2>/dev/null)
if [ -z "$JAVA_HOME" ]
then
    for CANDIDATE in \
        /usr/local/opt/openjdk/libexec/openjdk.jdk/Contents/Home \
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
