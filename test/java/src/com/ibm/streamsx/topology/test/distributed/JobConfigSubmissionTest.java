/*
# Licensed Materials - Property of IBM
# Copyright IBM Corp. 2015  
 */
package com.ibm.streamsx.topology.test.distributed;

import static org.junit.Assert.assertTrue;
import static org.junit.Assume.assumeTrue;

import java.util.List;
import java.util.concurrent.TimeUnit;

import org.junit.Test;

import com.ibm.streamsx.topology.TStream;
import com.ibm.streamsx.topology.Topology;
import com.ibm.streamsx.topology.jobconfig.JobConfig;
import com.ibm.streamsx.topology.spl.JavaPrimitive;
import com.ibm.streamsx.topology.spl.SPLSchemas;
import com.ibm.streamsx.topology.spl.SPLStream;
import com.ibm.streamsx.topology.test.TestTopology;
import com.ibm.streamsx.topology.test.api.JobPropertiesTest.JobPropertiesTestOp;
import com.ibm.streamsx.topology.tester.Condition;

/**
 * Test submission using JobConfig API
 */
public class JobConfigSubmissionTest extends TestTopology {

    @Test
    public void testGroupJobConfig() throws Exception {
        
        JobConfig config = new JobConfig();
        config.setJobGroup("default");
        testItDirect("testGroupJobConfig", config, "<jobId>", "<jobName>", "default", "<empty>");
    }
    @Test
    public void testNameJobConfig() throws Exception {
        
        JobConfig config = new JobConfig();
        config.setJobName("nameG");
        testItDirect("testNameJobConfig", config, "<jobId>", "nameG", "default", "<empty>");
    }
    
    @Test
    public void testDataDirJobConfig() throws Exception {
        
        JobConfig config = new JobConfig();
        config.setJobName("nameDD");
        config.setDataDirectory("/tmp/some/dir");
        testItDirect("testNameJobConfig", config, "<jobId>", "nameDD", "default", "/tmp/some/dir");
    }
    
    private void testItDirect(String topologyName, JobConfig config, String ...expected)
            throws Exception {
        
        // Uses a Java primitive operator directly.
        assumeTrue(hasStreamsInstall());

        // JobConfig only apply to DISTRIBUTED submit
        assumeTrue(isDistributedOrService());
        
        config.addToConfig(getConfig());

        Topology topology = newTopology(topologyName);
        topology.addClassDependency(JobPropertiesTestOp.class);
        SPLStream sourceSPL = JavaPrimitive.invokeJavaPrimitiveSource(topology, JobPropertiesTestOp.class,
                SPLSchemas.STRING, null);
        TStream<String> source = sourceSPL.toStringStream();

        Condition<Long> end = topology.getTester().tupleCount(source, 4);
        Condition<List<String>> result = topology.getTester().stringContents(source, expected);
        complete(topology.getTester(), end.and(result), 10, TimeUnit.SECONDS);
        
        
        assertTrue(result.valid());
        assertTrue(end.valid());
    }
    
}
