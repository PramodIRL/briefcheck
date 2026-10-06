import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.request import urlopen, Request
import webui

class UITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root/'runs').mkdir()
        (self.root/'research_pack').mkdir()
        self.addCleanup(patch.stopall)
        patch.object(webui,'ROOT',self.root).start()
        patch.object(webui,'JOB',None).start()
        patch.dict(os.environ,{},clear=True).start()

    def data(self, **extra):
        return dict(provider='groq',key='synthetic-test-key',model='qwen/qwen3.8-27b',ticker='EXWIRE',date='2026-09-23',version='v3',files=[],**extra)

    def test_uploaded_documents_replace_pack_and_reach_cli(self):
        data=self.data();data['files']=[{'name':'results.md','content':'published: 2026-08-01\nExample Wires'}]
        name,cmd,env,key=webui.prepare_job(data)
        docs=Path(cmd[cmd.index('--docs')+1])
        self.assertEqual((docs/'results.md').read_text(), data['files'][0]['content'])
        self.assertEqual(env['LLM_REASONING_EFFORT'],'none')
        self.assertEqual(env['LLM_API_KEY'],key)
        self.assertNotIn(key,' '.join(cmd))
        self.assertNotEqual(docs,self.root/'research_pack')

    def test_v4_ui_runs_passage_engine_with_bounded_budget(self):
        data=self.data();data['version']='v4'
        name,cmd,env,key=webui.prepare_job(data)
        self.assertEqual(Path(cmd[2]).name,'v4.py')
        self.assertEqual(env['V4_MAX_OUTPUT_TOKENS'],'900')
        self.assertNotIn('--version',cmd)
        self.assertEqual(cmd[cmd.index('--as-of')+1],'2026-09-23')
        data['provider']='openrouter'
        self.assertEqual(webui.prepare_job(data)[2]['V4_MAX_OUTPUT_TOKENS'],'4000')
        data['model']='dots-studio/dots-3-note-preview:free'
        self.assertEqual(webui.prepare_job(data)[2]['V4_MAX_OUTPUT_TOKENS'],'8000')
        data['provider']='groq'
        data['model']='openai/gpt-oss-120b'
        self.assertEqual(webui.prepare_job(data)[2]['V4_MAX_OUTPUT_TOKENS'],'4000')

    def test_provider_key_is_matched_to_provider(self):
        os.environ.update(LLM_BASE_URL='https://api.groq.com/openai/v1',LLM_API_KEY='synthetic-groq')
        self.assertEqual(webui.provider_key('groq'),'synthetic-groq')
        self.assertEqual(webui.provider_key('openrouter'),'')
        os.environ['OPENROUTER_API_KEY']='synthetic-router'
        self.assertEqual(webui.provider_key('openrouter'),'synthetic-router')

    def test_dotenv_handles_export_and_quotes(self):
        p=self.root/'.env';p.write_text('export GROQ_API_KEY="synthetic-key"\nLLM_MODEL=model/name\n# comment\n')
        webui.load_env(p)
        self.assertEqual(os.environ['GROQ_API_KEY'],'synthetic-key')
        self.assertEqual(os.environ['LLM_MODEL'],'model/name')

    def test_failed_generation_is_preserved_without_accepting_report(self):
        with patch.object(webui.subprocess,'run',return_value=subprocess.CompletedProcess([],1,'','Rejected synthetic-test-key')):
            webui.worker('example',[],{},'synthetic-test-key')
        result=json.loads((self.root/'runs/example/ui-result.json').read_text())
        self.assertEqual(result['status'],'failed')
        self.assertEqual(result['error'],'Rejected [redacted]')
        self.assertFalse((self.root/'runs/example/brief.md').exists())

    def test_completed_generation_requires_report_artifact(self):
        p=self.root/'runs/example';p.mkdir();(p/'report.html').write_text('<h1>Example</h1>')
        with patch.object(webui.subprocess,'run',return_value=subprocess.CompletedProcess([],0,'','')):
            webui.worker('example',[],{},'synthetic-key')
        self.assertEqual(webui.JOB['status'],'completed')

    def test_http_state_and_exact_markdown_export(self):
        p=self.root/'runs/example';p.mkdir()
        (p/'manifest.json').write_text(json.dumps({'status':'completed','mode':'live-api','ticker':'EXWIRE','version':'v3'}))
        (p/'report.html').write_text('<h1>Example</h1>')
        original=b'# EXWIRE\n\nExact model text.\n';(p/'brief.md').write_bytes(original)
        server=webui.ThreadingHTTPServer(('127.0.0.1',0),webui.Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            base=f'http://127.0.0.1:{server.server_port}'
            with urlopen(base+'/api/state') as r: state=json.load(r)
            self.assertTrue(state['runs'][0]['report'])
            self.assertFalse(state['keys']['groq'])
            with urlopen(base+'/artifact?run=example&file=brief.md') as r: self.assertEqual(r.read(),original)
        finally:
            server.shutdown();server.server_close();thread.join()

if __name__=='__main__':unittest.main()
