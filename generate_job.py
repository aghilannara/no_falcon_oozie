#!/usr/bin/env python

import sys
import json
import argparse
from collections import OrderedDict
import os
import shutil
from datetime import datetime, timedelta
from dateutil.parser import parse as parse_date
import pdb

hive_create_template = '''
CREATE DATABASE IF NOT EXISTS INGEST_%(targetdb)s;

CREATE TABLE IF NOT EXISTS INGEST_%(targetdb)s.%(schema)s_%(table)s_SCHEMA
   ROW FORMAT SERDE
   'org.apache.hadoop.hive.serde2.avro.AvroSerDe'
STORED AS AVRO
TBLPROPERTIES (
   'avro.schema.url'='hdfs://%(prefix)s/source/%(source_name)s/%(schema)s_%(table)s/CURRENT/.metadata/schema.avsc'
);

CREATE EXTERNAL TABLE IF NOT EXISTS INGEST_%(targetdb)s.%(schema)s_%(table)s_CURRENT
LIKE INGEST_%(targetdb)s.%(schema)s_%(table)s_SCHEMA
STORED AS PARQUET LOCATION '%(prefix)s/source/%(source_name)s/%(schema)s_%(table)s/CURRENT';
'''

oozie_properties = OrderedDict([
    ('resourceManager','hdpmaster1.dev.dl.tm.com.my:8050'),
    ('jobTracker','hdpmaster1.dev.dl.tm.com.my:8050'),
    ('nameNode','hdfs://hdpmaster1.dev.dl.tm.com.my:8020'),
#    ('hivejdbc', 'jdbc:hive2://hdpmaster1.dev.dl.tm.com.my:10000/default'),
    ('oozie.bundle.application.path',None),#'/user/trace/workflows/bundle/%(workflow)s/'),
    ('oozie.use.system.libpath','true'),
    ('prefix', None),
    ('jdbc_uri','jdbc:oracle:thin:@%(host)s:%(port)s/%(tns)s'),
    ('username', None),
    ('password',None),
    ('source_name', None),
    ('direct', None),
    ('targetdb', None),
    ('stagingdb', None),
    ('backdate', '7'),
    ('retention', '7'),
    ('schema', None),
    ('table', None),
    ('mapper', None),
    ('split_by', None),
    ('merge_column', None),
    ('check_column', None),
    ('queueName',None),
    ('ingeststartTime',None),
    ('transformstartTime',None),
    ('initialinstanceTime',None),
    ('ingestendTime','2099-12-31T16:00Z'),
    ('transformendTime','2099-12-31T16:00Z'),
#    ('columns', None),
#    ('columns_create', None),
    ('columns_java', None),
])

JAVA_TYPE_MAP = {
#    'VARCHAR2': 'String',
    'DATE': 'String',
#    'NUMBER': 'String',
#    'CHAR': 'String',
#    'LONG': 'Long',
}

STAGES = {
   'dev': {
      'prefix': '/user/trace/development/',
      'targetdb': '%(source_name)s_DEV',
      'stagingdb': 'staging_dev',
   },
   'test': {
      'prefix': '/user/trace/test/',
      'targetdb': '%(source_name)s',
      'stagingdb': 'staging_test',
   },
   'prod': {
      'prefix': '/user/trace/',
      'targetdb': '%(source_name)s',
      'stagingdb': 'staging',
   }
}

PROCESSES = {
    'ingest-full': {
        'workflow': 'ingest-full',
        'out_feeds': ['full'],
        'condition': lambda x: x['merge_column'] and x['check_column'],
    },
    'ingest-increment': {
        'workflow': 'ingest-increment',
        'out_feeds': ['increment'],
    },
    'transform-full': {
        'in_feeds': ['full'],
        'workflow': 'transform-full',
    },
    'transform-increment': {
        'in_feeds': ['increment'],
        'workflow': 'transform-increment',
    },
    'incremental-ingest-frozen': {
        'workflow': 'incremental-ingest-frozen',
    },
    'data-retention-hdfs': {
        'workflow': 'data-retention-hdfs',
    }
}

EXEC_TIME = {
    'CPC': {
        'ingest-full': '00:01',
        'ingest-increment': '00:01',
        'transform-full': '00:30',
        'transform-increment': '00:30',
        'data-retention-hdfs': '14:30'
    },
    'SIEBEL_NOVA': {
        'ingest-full': '03:00',
        'ingest-increment': '03:00',
        'transform-full': '05:00',
        'transform-increment': '05:00',
        'data-retention-hdfs': '14:30'
    },
    'BRM_NOVA': {
        'ingest-full': '03:01',
        'ingest-increment': '03:01',
        'transform-full': '05:00',
        'transform-increment': '05:00',
        'data-retention-hdfs': '14:30'
    },
    'GRANITE': {
        'ingest-full': '03:01',
        'ingest-increment': '03:01',
        'transform-full': '05:00',
        'transform-increment': '05:00',
        'data-retention-hdfs': '14:30'
    },
    'NIS': {
        'ingest-full': '03:01',
        'ingest-increment': '03:01',
        'transform-full': '05:00',
        'transform-increment': '05:00',
        'data-retention-hdfs': '14:30'
    },
    'PORTAL': {
        'ingest-full': '03:01',
        'ingest-increment': '03:01',
        'transform-full': '05:00',
        'transform-increment': '05:00',
        'data-retention-hdfs': '14:30'
    },
    'SDP_ICP': {
        'ingest-full': '03:01',
        'ingest-increment': '03:01',
        'transform-full': '05:00',
        'transform-increment': '05:00',
        'data-retention-hdfs': '14:30'
    },
    'RESELLER_PORTAL_NOVA': {
        'ingest-full': '03:01',
        'ingest-increment': '03:01',
        'transform-full': '05:00',
        'transform-increment': '05:00',
        'data-retention-hdfs': '14:30'
    },
    'RESELLER_PORTAL_ICP': {
        'ingest-full': '03:01',
        'ingest-increment': '03:01',
        'transform-full': '05:00',
        'transform-increment': '05:00',
        'data-retention-hdfs': '14:30'
    },
    'CIP': {
        'ingest-full': '03:01',
        'ingest-increment': '03:01',
        'transform-full': '05:00',
        'transform-increment': '05:00',
        'data-retention-hdfs': '14:30'
    },
    'SWIFT': {
        'ingest-full': '03:01',
        'ingest-increment': '03:01',
        'transform-full': '05:00',
        'transform-increment': '05:00',
        'data-retention-hdfs': '14:30'
    },
    'SIEBEL_ICP': {
        'ingest-full': '03:00',
        'ingest-increment': '03:00',
        'transform-full': '05:00',
        'transform-increment': '05:00',
        'data-retention-hdfs': '14:30'
    },
    'BRM_ICP': {
        'ingest-full': '03:00',
        'ingest-increment': '03:00',
        'transform-full': '05:00',
        'transform-increment': '05:00',
        'data-retention-hdfs': '14:30'
    },
    'EAI_ICP': {
        'ingest-full': '03:00',
        'ingest-increment': '03:00',
        'transform-full': '05:00',
        'transform-increment': '05:00',
        'data-retention-hdfs': '14:30'
    }
}

FEEDS = {
   'full-retention': {
       'path': '%(prefix)s/source/%(source_name)s/%(schema)s_%(table)s/ingest_date=${YEAR}-${MONTH}-${DAY}',
       'format': 'parquet',
       'exec_time': '00:00',
       'retention': 7
   },
   'increment-retention': {
        'path': '%(prefix)s/source/%(source_name)s/%(schema)s_%(table)s/INCREMENT/ingest_date=${YEAR}-${MONTH}-${DAY}',
        'format': 'parquet',
        'exec_time': '00:00',
        'retention': 7
   },
   'full': {
       'path': '%(prefix)s/source/%(source_name)s/%(schema)s_%(table)s/CURRENT/',
       'format': 'parquet',
       'exec_time': '00:00',
   },
   'increment': {
        'path': '%(prefix)s/source/%(source_name)s/%(schema)s_%(table)s/INCREMENT/CURRENT',
        'format': 'parquet',
        'exec_time': '00:00'
   },
}

HIVE_FEEDS = {
    'hive-retention' : {
        'path': 'catalog:%(targetdb)s_HISTORY:%(schema)s_%(table)s#ingest_date=${YEAR}-${MONTH}-${DAY}',
        'format': 'orc',
        'exec_time': '00:00',
        'retention': 365
    }
}

ARTIFACTS='artifacts/'

FOREVER=36135

def get_exec_time(source, process):
    return EXEC_TIME.get(source, {}).get(process, '03:01')

def generate_utc_time(t, dayoffset=0):
    tt = (datetime.now() + timedelta(days=dayoffset)).strftime('%Y-%m-%d')
    dt = tt + ' %s' % t
    start_dt = parse_date(dt)
    return (start_dt - timedelta(hours=8)).strftime('%Y-%m-%dT%H:%MZ')

def default_feed_name(stage, properties, feed):
    return (stage +
        '-%(source_name)s-%(schema)s-%(table)s-' % properties +
        feed
    ).replace('_','')

def default_process_name(stage, properties):
    return (
        stage +
        '-%(source_name)s-%(schema)s-%(table)s-%(workflow)s' % properties
    ).replace('_','')

def write_oozie_config(storedir, properties):
    filename = '%(source_name)s-%(schema)s-%(table)s.properties' % properties
    if not os.path.exists(storedir):
        os.makedirs(storedir)
    with open('%s/%s' % (storedir, filename), 'w') as f:
        job = '\n'.join([
            '%s=%s' % (k,v) for k,v in oozie_config(properties).items()
        ])
        f.write(job)

def oozie_config(properties):
    prop = oozie_properties.copy()
    prop['jdbc_uri'] = prop['jdbc_uri'] % properties
    prop['oozie.bundle.application.path'] = properties['wfpath']
    for k,v in prop.items():
        if k in properties.keys():
            prop[k] = properties[k]
    prop['appName'] = (
        properties.get('appName', None) or
        '%(workflow)s-%(source_name)s-%(schema)s-%(table)s' % properties
    )
    return prop

def write_falcon_process(storedir, stage, properties, in_feeds=None,
        out_feeds=None, process_time='05:00'):
    filename = '%(source_name)s-%(schema)s-%(table)s.xml' % properties
    if not os.path.exists(storedir):
        os.makedirs(storedir)
    with open('%s/%s' % (storedir, filename), 'w') as f:
        params, job = falcon_process(stage, properties, in_feeds, out_feeds,
                process_time)
        f.write(job)



def falcon_process(stage, properties, in_feeds=None, out_feeds=None,
        process_time='05:00'):
    inputs = [
        default_feed_name(stage, properties,
            i) for  i in (in_feeds or [])
        ]
    outputs = [
        default_feed_name(stage, properties,
            i) for  i in (out_feeds or [])
        ]
    inputs_xml = '\n        '.join(
            ['<input name="input%s" feed="%s" start="today(8,0)" end="today(9,30)"/>' %
                (t,i) for t,i in enumerate(inputs)])
    inputs_xml = '<inputs>%s</inputs>' % inputs_xml if inputs_xml else ''
    outputs_xml = '\n        '.join(
            ['<output name="output%s" feed="%s" instance="today(8,0)"/>' %
                (t,i) for t,i in enumerate(outputs)])
    outputs_xml = '<outputs>%s</outputs>' % outputs_xml if outputs_xml else ''

    prop = oozie_config(properties)
    params = {
        'schema': properties['schema'],
        'table': properties['table'],
        'workflow': properties['workflow'],
        'source_name': properties['source_name'],
        'start_utc': generate_utc_time(process_time, dayoffset=1),
        'should_end_hours': 5,
        'frequency_hours': 24,
        'process_name': default_process_name(stage, properties),
        'workflow_path': prop['oozie.bundle.application.path'],
        'workflow_name': prop['appName'].replace('_',''),
        'stage' : stage,
        'properties': '\n       '.join(
            ['<property name="%s" value="%s"/>' % (k,v) for (k,v) in prop.items() if '.' not in k]),
        'outputs': outputs_xml,
        'inputs': inputs_xml,
    }
    job = falcon_process_template % params
    return params, job


def write_falcon_feed(storedir, stage, properties, feed, feed_path,
        feed_format, exec_time='00:00', retention=FOREVER):
    filename = '%(source_name)s-%(schema)s-%(table)s.xml' % properties
    if not os.path.exists(storedir):
        os.makedirs(storedir)
    with open('%s/%s' % (storedir, filename), 'w') as f:
        params, job = falcon_feed(stage, properties, feed,
                    feed_path, feed_format, exec_time, retention)
        f.write(job)

def falcon_feed(stage, properties, feed, feed_path, feed_format,
            exec_time='00:00', retention=FOREVER):
    if retention is not None:
        rt = "<retention limit='days(%s)' action='delete'/>" % retention
    else:
        rt = ''
    params = {
       'schema': properties['schema'],
       'table': properties['table'],
       'source_name': properties['source_name'],
       'start_utc': generate_utc_time(exec_time),
       'feed_name': default_feed_name(stage, properties, feed),
       'feed_path': feed_path % properties,
       'feed_type': feed,
       'feed_format': feed_format,
       'stage': stage,
       'retention': rt
    }
    job = falcon_feed_template % params
    return params, job

def write_falcon_hivefeed(storedir, stage, properties, feed, feed_path,
        feed_format, exec_time='00:00', retention=FOREVER):
    filename = '%(source_name)s-%(schema)s-%(table)s.xml' % properties
    if not os.path.exists(storedir):
        os.makedirs(storedir)
    with open('%s/%s' % (storedir, filename), 'w') as f:
        params, job = falcon_hivefeed(stage, properties, feed,
                    feed_path, feed_format, exec_time, retention)
        f.write(job)

def falcon_hivefeed(stage, properties, feed, feed_path, feed_format,
            exec_time='00:00', retention=FOREVER):
    if retention is not None:
        rt = "<retention limit='days(%s)' action='delete'/>" % retention
    else:
        rt = ''
    params = {
       'schema': properties['schema'],
       'table': properties['table'],
       'source_name': properties['source_name'],
       'start_utc': generate_utc_time(exec_time),
       'feed_name': default_feed_name(stage, properties, feed),
       'feed_path': feed_path % properties,
       'feed_type': feed,
       'feed_format': feed_format,
       'stage': stage,
       'retention': rt
    }
    job = falcon_hivefeed_template % params
    return params, job


def main():
    argparser = argparse.ArgumentParser(description='Generate oozie and falcon configurations for ingestion')
    argparser.add_argument('profilerjson', help='JSON output from oracle_profiler.py')
    opts = argparser.parse_args()
    hive_create = []
    import csv
    p1_tables = ['%s-%s-%s' % (i['Data Source'],i['Schema'],i['Tables']) for i in
        csv.DictReader(open('dataset/phase1_tables.tsv'),delimiter='\t')]

    if os.path.exists(ARTIFACTS):
        shutil.rmtree(ARTIFACTS)
    for ds in json.loads(open(opts.profilerjson).read()):
        for table in ds['tables']:

            mapper = int((table['estimated_size'] or 0) / 1024 / 1024 / 1024) or 2
            if mapper < 8:
                queueSize = 'small'
            if 7<mapper<14:
                queueSize = 'medium'
            if 13<mapper<20:
                queueSize = 'large'
            if mapper > 19:
                queueSize = 'xlarge'

            if mapper < 2:
                mapper = 2
            if mapper > 25:
                mapper = 25

            columns = [c['field'] for c in table['columns']]
            columns_create = []
            columns_java = []
            for c in table['columns']:
                if JAVA_TYPE_MAP.get(c['type'], None):
                    columns_java.append('%s=%s' % (c['field'], JAVA_TYPE_MAP[c['type']]))

            source_name = ds['datasource']['name'].replace(' ','_')
            username = ds['datasource']['login']
            password = ds['datasource']['password']

            if source_name=='BRM_NOVA' or source_name=='SIEBEL_NOVA':
                queueName = 'siebel_brm_%s'%(queueSize)
            else:
                queueName = '%s_%s'%(source_name.lower(),queueSize)

            if (
                '%s-%s-%s' % (source_name, table['schema'],
                    table['table']) not in p1_tables):
                continue
		
            ingest_time = EXEC_TIME['%s'%(source_name)].get('ingest-full')
	    ingest_time = datetime.strptime(ingest_time,'%H:%M').time()
	    dt = datetime.now()
	    ingest_time = datetime.combine(dt.date(),ingest_time) + timedelta(hours=16)
	    ingest_time = ingest_time.strftime('%Y-%m-%dT%H:%MZ') 

	    transform_time = EXEC_TIME['%s'%(source_name)].get('transform-full')
	    transform_time = datetime.strptime(transform_time,'%H:%M').time()
	    dt = datetime.now()
	    transform_time = datetime.combine(dt.date(),transform_time) + timedelta(hours=16)
	    transform_time = transform_time.strftime('%Y-%m-%dT%H:%MZ') 
	    
	    dt2 = dt.date() - timedelta(days=1)
	    instance_time = dt2.__str__() + 'T16:00Z'
	    #pdb.set_trace()
	    #if workflow == 'ingest-increment'
	    #   app_path = '/user/trace'
	    #pdb.set_trace()
            params = {
                'mapper': mapper,
		#'oozie.bundle.application.path': app_path,
                'queueName': queueName,
                'ingeststartTime': ingest_time,
		'transformstartTime': transform_time,
		'initialinstanceTime': instance_time,
                'source_name': source_name,
                'host': ds['datasource']['ip'],
                'port': ds['datasource']['port'],
                'username': username, # ds['datasource']['login'],
                'password': password,
                'tns': ds['datasource']['tns'],
                'schema': ds['datasource']['schema'],
                'table': table['table'],
                'split_by': table['split_by'],
                'columns_java': ','.join(columns_java),
                'columns_create': ','.join(columns_create),
                'columns_create_newline': ',\n    '.join(columns_create),
                'columns': ','.join(['`%s`' % c['field'] for c in table['columns']]),
                'merge_column': table['merge_key'],
                'check_column': table['check_column'],
                'direct': ds['direct']
            }

            for stage, conf in STAGES.items():

                if stage in ['prod']:
                    opts = params.copy()
                    opts['stagingdb'] = conf['stagingdb']
                    opts['targetdb'] = conf['targetdb'] % params
                    opts['prefix'] = conf['prefix']
                    hive_create.append(
                        hive_create_template % opts
                    )

                for process, proc_opts in PROCESSES.items():
                    opts = params.copy()
                    opts['prefix'] = conf['prefix']
                    opts['targetdb'] = conf['targetdb'] % params
                    opts['stagingdb'] = conf['stagingdb']

                    wf = proc_opts['workflow']
                    opts['workflow'] = wf
		    #new addition 
		    wf2 = wf.replace('ingest-','').replace('transform-','') + '/workflow.xml'
		    
                    opts['wfpath'] = os.path.join(conf['prefix'],'workflows/bundle', wf2)
                    if not proc_opts.get('condition', lambda x: True):
                        continue

                    storedir = '%s/%s-oozie-%s' % (ARTIFACTS, stage, wf)
                    write_oozie_config(storedir, opts)

    open('hive-create.sql', 'w').write('\n'.join(hive_create))

if __name__ == '__main__':
    main()
