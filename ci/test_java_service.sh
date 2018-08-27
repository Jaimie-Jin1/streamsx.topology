. ${WORKSPACE:?}/ci/setup

# 3.5 environment is assumed to be conda environment created from 3.6
source ${ANACONDA36_HOME:?}/bin/activate `basename ${ANACONDA35_HOME}`
export PYTHONHOME=${ANACONDA35_HOME:?}
. ${WORKSPACE}/ci/pysetup

unset STREAMS_DOMAIN_ID
unset STREAMS_INSTANCE_ID

echo 'Testing Java Streaming Analytics service'
cd $WORKSPACE/test/java
ant -Dtopology.test.haltonfailure=no -Dtopology.test.threads=${CI_TEST_THREADS:-8} unittest.streaminganalytics
