import copy
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import v4

class V4Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.docs=self.root/'docs';self.docs.mkdir()
        self.raw='---\r\nsource: Example Wires IR\r\nurl: https://example.test/results\r\npublished: 2026-08-01\r\ntype: filing\r\n---\r\n\r\nExample Wires makes cables.\r\n\r\n| Metric | Current | Prior |\r\n| Revenue | 200 | 100 |\r\n| Profit | 20 | 10 |\r\n\r\nManagement expects capacity growth of 30 percent.\r\n\r\nDebt was 40 crore. Receivable days were 90, up from 70.\r\n'
        (self.docs/'results.md').write_bytes(self.raw.encode())
        self.sources=v4.load_sources(self.docs,'2026-09-23')
        self.triage={'entity_name':'Example Wires','decisions':[{'source_id':'S01','disposition':'use','reason':'Relevant issuer results','refs':['S01:P01']}]}
        self.growth={'Snapshot':[
          {'text':'Example Wires makes cables.','kind':'fact','refs':['S01:P01']},
          {'text':'Revenue was 200, versus 100.','kind':'fact','refs':['S01:P02']},
          {'text':'Profit was 20, versus 10.','kind':'fact','refs':['S01:P02']}],
          'Bull case':[{'text':'Management expects capacity growth of 30 percent.','kind':'management_view','refs':['S01:P03']},
          {'text':'Revenue increased from 100 to 200.','kind':'fact','refs':['S01:P02']}]}
        self.risks={'Bear case':[
          {'text':'Debt was 40 crore.','kind':'fact','refs':['S01:P04']},
          {'text':'Receivable days rose from 70 to 90.','kind':'fact','refs':['S01:P04']},
          {'text':'Management’s capacity growth expectation remains a forecast.','kind':'management_view','refs':['S01:P03']}],
          'Open questions':[{'text':'What is the current valuation?','kind':'question','refs':[]},
          {'text':'When will the 40 crore debt mature?','kind':'question','refs':['S01:P04']}]}
    def part(self,wire,**kwargs):
        return v4.part_value({'claims':[dict(c,section=k) for k,items in wire.items() for c in items]},self.triage,list(wire),self.sources,as_of='2026-09-23',**kwargs)
    def full(self):return v4.assemble([self.part(self.growth),self.part(self.risks)],self.triage)

    def test_passages_preserve_original_crlf_and_table_context(self):
        for p in self.sources[0]['passages']:self.assertIn(p['text'],self.raw)
        quote=v4.passage_map(self.sources)['S01:P02'][1]
        self.assertIn('| Metric | Current | Prior |\r\n',quote)
        self.assertIn('| Revenue | 200 | 100 |',quote)

    def test_future_document_body_is_not_in_catalogue(self):
        (self.docs/'future.md').write_bytes(self.raw.replace('2026-08-01','2027-08-01').replace('Example Wires','FUTURE_ONLY').encode())
        sources=v4.load_sources(self.docs,'2026-09-23')
        self.assertNotIn('FUTURE_ONLY',v4.encoded(v4.catalogue(sources)))
        self.assertEqual(len(sources),2)

    def test_keyed_triage_requires_each_document_and_its_own_passage(self):
        wire={'entity_name':'Example Wires','decisions':{'S01':{'disposition':'use','reason':'Issuer data','ref':'S01:P02'}}}
        self.assertEqual(v4.triage_value(wire,self.sources)['decisions'][0]['refs'],['S01:P02'])
        wire['decisions']['S01']['ref']='S99:P01'
        with self.assertRaises(v4.Invalid):v4.triage_value(wire,self.sources)

    def test_complete_claims_render_once_with_exact_source_registry(self):
        value=self.full();v4.validate(value,'draft',self.sources,as_of='2026-09-23')
        text=v4.markdown(value,self.sources,'EXWIRE','2026-09-23')
        self.assertEqual(text.count('## Sources'),1)
        self.assertIn('Revenue was 200, versus 100. [S01]',text)
        self.assertEqual(text.count('results.md'),1)

    def test_question_label_cannot_bypass_forecast_checks_on_assertions(self):
        self.growth['Bull case'][0]['kind']='question'
        with self.assertRaises(v4.Invalid):self.part(self.growth)
        self.risks['Open questions'][0]['text']='The company has no financial risks.'
        with self.assertRaisesRegex(v4.Invalid,'actual question'):self.part(self.risks)

    def test_unknown_reference_is_rejected(self):
        self.growth['Snapshot'][0]['refs']=['S01:P99']
        with self.assertRaises(v4.Invalid):self.part(self.growth)

    def test_wrong_number_and_uncited_numeric_question_are_rejected(self):
        self.growth['Snapshot'][1]['text']='Revenue was 999 crore.'
        with self.assertRaisesRegex(v4.Invalid,'numeric'):self.part(self.growth)
        self.risks['Open questions'][1]['refs']=[]
        with self.assertRaisesRegex(v4.Invalid,'numeric'):self.part(self.risks)

    def test_excluded_source_cannot_ground_report(self):
        self.triage['decisions'][0]['disposition']='exclude'
        with self.assertRaisesRegex(v4.Invalid,'excluded'):self.part(self.growth)

    def test_writer_cannot_introduce_new_passage(self):
        previous=self.full();previous['claims']=[c for c in previous['claims'] if 'S01:P03' not in c['refs']]
        with self.assertRaises(v4.Invalid):self.part(self.growth,previous=previous)

    def test_no_automatic_rewrite_of_model_citation_or_control_character(self):
        self.growth['Snapshot'][0]['text']='Example Wires makes cables. [S01]'
        with self.assertRaisesRegex(v4.Invalid,'plain sentences'):self.part(self.growth)
        self.growth['Snapshot'][0]['text']='Example\u200b Wires makes cables.'
        with self.assertRaisesRegex(v4.Invalid,'readable'):self.part(self.growth)

    def test_audit_requires_each_claim_once(self):
        draft=self.full();spec=v4.small_audit_schema(draft,self.sources)
        self.assertEqual(set(spec['properties']['claim_reviews']['properties']),{f'C{i}' for i in range(1,11)})
        wire={'summary':'Reviewed','claim_reviews':{},'source_changes':[],'instructions':[]}
        with self.assertRaises(v4.Invalid):v4.audit_value(wire,self.triage,draft,self.sources)

    def test_source_can_does_not_become_expects(self):
        self.sources[0]['passages'][2]['text']='Management thinks capacity can double.'
        self.growth['Bull case']=[{'text':'Management expects capacity to double.','kind':'management_view','refs':['S01:P03']}]
        with self.assertRaisesRegex(v4.Invalid,'strengthens'):self.part(self.growth)
        self.growth['Bull case'][0]['text']='Management is expecting capacity to double.'
        with self.assertRaisesRegex(v4.Invalid,'strengthens'):self.part(self.growth)
        self.growth['Bull case'][0]['text']='Management plans to double capacity.'
        with self.assertRaisesRegex(v4.Invalid,'strengthens'):self.part(self.growth)
        self.risks['Open questions'][0]={'text':'Can capacity double as management expects?','kind':'question','refs':['S01:P03']}
        with self.assertRaisesRegex(v4.Invalid,'strengthens'):self.part(self.risks)
        self.growth['Bull case'][0]['text']='Management thinks capacity can double.'
        self.part(self.growth)

    def test_forecast_is_not_a_reported_fact(self):
        self.growth['Bull case'][0]['kind']='fact'
        with self.assertRaisesRegex(v4.Invalid,'classified'):self.part(self.growth)

    def test_repeated_cross_section_claim_has_actionable_error(self):
        self.risks['Bear case'][0]=copy.deepcopy(self.growth['Snapshot'][0])
        with self.assertRaisesRegex(v4.Invalid,'Example Wires makes cables'):
            v4.validate(self.full(),'draft',self.sources,as_of='2026-09-23')

    def test_complete_offline_execution_and_replay_use_exact_raw_outputs(self):
        def fake(client,stage,system,payload,schema,attempt):
            if stage=='triage':wire={'entity_name':'Example Wires','decisions':{'S01':{'disposition':'use','reason':'Relevant issuer','ref':'S01:P01'}}}
            elif stage=='audit':wire={'summary':'All supported','claim_reviews':{f'C{i}':{'verdict':'supported','reason':'Matches source'} for i in range(1,11)},'source_changes':[],'instructions':[]}
            else:
                if stage.endswith('risks'):self.assertIn('already_written_sections',payload)
                self.assertEqual(schema['properties']['claims']['maxItems'],7)
                if stage.startswith('revise'):
                    self.assertTrue(all(c['section'] in payload['sections'] for c in payload['draft']['claims']))
                    self.assertEqual({c['id'] for c in payload['draft']['claims']},{r['id'] for r in payload['audit']['claim_reviews']})
                parts=copy.deepcopy(self.growth if stage.endswith('growth') else self.risks)
                wire={'claims':[dict(c,section=k) for k,items in parts.items() for c in items]}
            (client.folder/'responses'/f'{stage}-{attempt:02d}.txt').write_text(json.dumps(wire))
            return wire
        with patch.dict(os.environ,{'LLM_API_KEY':'synthetic-key','LLM_BASE_URL':'https://api.groq.com/openai/v1'},clear=True),patch.object(v4.Client,'call',fake):
            run=self.root/'run';v4.run('EXWIRE',self.docs,'2026-09-23',run)
        self.assertEqual(v4.verify(run)['model_calls'],0)
        (run/'brief.md').write_text('altered')
        with self.assertRaisesRegex(v4.Invalid,'Archive mismatch'):v4.verify(run)

    def test_question_section_cannot_be_mislabelled_as_management_statement(self):
        self.risks['Open questions'][0]['kind']='management_view'
        with self.assertRaisesRegex(v4.Invalid,'kind question'):self.part(self.risks)
        schema=v4.part_schema(['Open questions'],self.sources)
        self.assertEqual(schema['properties']['claims']['items']['properties']['section']['enum'],['Open questions'])

    def test_publication_year_is_not_mistaken_for_a_financial_amount(self):
        self.growth['Snapshot'][0]['text']='The company makes cables, as reported in 2026.'
        self.part(self.growth)
        for text in ['The company makes cables, as reported in 2025.','Revenue was 2026 crore.','Revenue was reported in 2026 crore.']:
            self.growth['Snapshot'][0]['text']=text
            with self.assertRaisesRegex(v4.Invalid,'numeric'):self.part(self.growth)

    def test_context_document_cannot_be_only_basis_of_report_item(self):
        self.triage['decisions'][0]['disposition']='context'
        with self.assertRaisesRegex(v4.Invalid,'Context-only'):self.part(self.growth)

    def test_scheduled_plan_is_qualified_but_bare_assertion_is_not(self):
        self.growth['Bull case'][0]['text']='The new facility is slated for commercial production.'
        self.part(self.growth)
        self.growth['Bull case'][0]['text']='The new facility is on track for commercial production.'
        self.part(self.growth)
        self.growth['Bull case'][0]['text']='The Managing Director says the new facility can add capacity.'
        self.part(self.growth)
        self.growth['Bull case'][0]['text']='The new facility is producing goods.'
        with self.assertRaisesRegex(v4.Invalid,'qualify'):self.part(self.growth)

    def test_repair_feedback_identifies_multiple_bad_claims(self):
        self.growth['Snapshot'][1]['text']='Revenue was 999 crore.'
        self.growth['Bull case'][0]['kind']='fact'
        with self.assertRaises(v4.Invalid) as caught:self.part(self.growth)
        message=str(caught.exception)
        self.assertIn('Revenue was 999 crore.',message)
        self.assertIn('Management expects capacity growth',message)
        self.assertIn('numeric',message)
        self.assertIn('classified',message)

    def test_provider_schema_rejection_is_distinct_from_quota_error(self):
        run=self.root/'transport';run.mkdir()
        for folder in ('requests','responses'): (run/folder).mkdir()
        manifest={'calls':[]}
        def failed(*args,**kwargs):
            payload={'error':{'code':'json_validate_failed','message':'Schema failed for org_private synthetic-key','failed_generation':'{invalid'}}
            raise urllib.error.HTTPError('https://api.groq.com',400,'Bad request',{},io.BytesIO(json.dumps(payload).encode()))
        opener=type('Opener',(),{'open':failed})()
        with patch.dict(os.environ,{'LLM_API_KEY':'synthetic-key','LLM_BASE_URL':'https://api.groq.com/openai/v1'},clear=True),patch.object(v4.urllib.request,'build_opener',return_value=opener):
            client=v4.Client(run,manifest)
            with self.assertRaises(v4.GenerationError):client.call('test','Return JSON',{},v4.obj({}),1)
        self.assertEqual(manifest['calls'][0]['provider_error_code'],'json_validate_failed')
        self.assertNotIn('synthetic-key',(run/'manifest.json').read_text())
        self.assertNotIn('org_private',(run/'manifest.json').read_text())
        self.assertEqual((run/'responses/test-01-transport-1-rejected.txt').read_text(),'{invalid')

    def test_quota_retries_stop_after_three_transport_attempts(self):
        run=self.root/'transport';run.mkdir()
        for folder in ('requests','responses'): (run/folder).mkdir()
        manifest={'calls':[]}
        def failed(*args,**kwargs):
            raise urllib.error.HTTPError('https://api.groq.com',429,'Limited',{},io.BytesIO(b'{"error":{"message":"Rate limit"}}'))
        opener=type('Opener',(),{'open':failed})()
        with patch.dict(os.environ,{'LLM_API_KEY':'synthetic-key','LLM_BASE_URL':'https://api.groq.com/openai/v1'},clear=True),patch.object(v4.urllib.request,'build_opener',return_value=opener),patch.object(v4.time,'sleep'):
            client=v4.Client(run,manifest)
            with self.assertRaisesRegex(v4.Invalid,'HTTP 429'):client.call('test','Return JSON',{},v4.obj({}),1)
        self.assertEqual(len(manifest['calls']),3)

    def test_reasoning_model_has_its_own_budget_and_medium_reasoning(self):
        run=self.root/'transport';run.mkdir()
        for folder in ('requests','responses'): (run/folder).mkdir()
        manifest={'calls':[]}
        payload={'choices':[{'finish_reason':'stop','message':{'content':'{}'}}]}
        opener=type('Opener',(),{'open':lambda *_args,**_kw:io.BytesIO(json.dumps(payload).encode())})()
        with patch.dict(os.environ,{'LLM_API_KEY':'synthetic-key','LLM_BASE_URL':'https://api.groq.com/openai/v1','LLM_MODEL':'openai/gpt-oss-20b'},clear=True),patch.object(v4.urllib.request,'build_opener',return_value=opener):
            client=v4.Client(run,manifest);client.call('test','Return JSON',{},v4.obj({}),1)
        request=json.loads((run/'requests/test-01.json').read_text())
        self.assertEqual(request['max_completion_tokens'],4000)
        self.assertEqual(request['reasoning_effort'],'medium')

    def test_openrouter_requires_schema_support_and_reasoning_budget(self):
        run=self.root/'transport';run.mkdir()
        for folder in ('requests','responses'): (run/folder).mkdir()
        manifest={'calls':[]}
        payload={'choices':[{'finish_reason':'stop','message':{'content':'{}'}}]}
        captured=[]
        def respond(_self,request,**kwargs):
            captured.append(request)
            return io.BytesIO(json.dumps(payload).encode())
        opener=type('Opener',(),{'open':respond})()
        with patch.dict(os.environ,{'OPENROUTER_API_KEY':'synthetic-router','GROQ_API_KEY':'synthetic-wrong-provider','LLM_BASE_URL':'https://openrouter.ai/api/v1','LLM_MODEL':'openai/gpt-oss-20b'},clear=True),patch.object(v4.urllib.request,'build_opener',return_value=opener):
            client=v4.Client(run,manifest);client.call('test','Return JSON',{},v4.obj({}),1)
        request=json.loads(captured[0].data)
        self.assertEqual(captured[0].get_header('Authorization'),'Bearer synthetic-router')
        self.assertEqual(request['provider'],{'require_parameters':True})
        self.assertEqual(request['max_tokens'],4000)
        self.assertEqual(request['reasoning'],{'effort':'medium','exclude':True})
        self.assertNotIn('max_completion_tokens',request)
        self.assertNotIn('temperature',request)
        self.assertNotIn('synthetic-router',(run/'requests/test-01.json').read_text())

    def test_repair_dialogue_preserves_bad_answer_and_places_errors_last(self):
        run=self.root/'transport';run.mkdir()
        for folder in ('requests','responses'): (run/folder).mkdir()
        answer={'claims':[]};payload={'sections':['Snapshot'],'previous_rejected_output':answer,'validation_error':'Missing required claims.'}
        response={'choices':[{'finish_reason':'stop','message':{'content':'{}'}}]}
        opener=type('Opener',(),{'open':lambda *_args,**_kw:io.BytesIO(json.dumps(response).encode())})()
        with patch.dict(os.environ,{'LLM_API_KEY':'synthetic-key'},clear=True),patch.object(v4.urllib.request,'build_opener',return_value=opener):
            v4.Client(run,{'calls':[]}).call('test','JSON',payload,v4.obj({}),2)
        messages=json.loads((run/'requests/test-02.json').read_text())['messages']
        self.assertEqual([m['role'] for m in messages],['system','user','assistant','user'])
        self.assertEqual(json.loads(messages[2]['content']),answer)
        self.assertIn('Missing required claims.',messages[-1]['content'])
        self.assertNotIn('previous_rejected_output',json.loads(messages[1]['content']))

    def test_free_preset_enforces_zero_price_and_controls_reasoning(self):
        run=self.root/'transport';run.mkdir()
        for folder in ('requests','responses'): (run/folder).mkdir()
        payload={'choices':[{'finish_reason':'stop','message':{'content':'{}'}}]}
        opener=type('Opener',(),{'open':lambda *_args,**_kw:io.BytesIO(json.dumps(payload).encode())})()
        env={'OPENROUTER_API_KEY':'synthetic-key','LLM_BASE_URL':'https://openrouter.ai/api/v1','LLM_MODEL':'dots-studio/dots-3-note-preview:free'}
        with patch.dict(os.environ,env,clear=True),patch.object(v4.urllib.request,'build_opener',return_value=opener):
            v4.Client(run,{'calls':[]}).call('test','JSON',{},v4.obj({}),1)
        request=json.loads((run/'requests/test-01.json').read_text())
        self.assertEqual(request['provider']['max_price'],{'prompt':0,'completion':0})
        self.assertEqual(request['reasoning'],{'enabled':True,'exclude':True})
        self.assertEqual(request['max_tokens'],8000)

    def test_invalid_json_is_preserved_and_eligible_for_bounded_repair(self):
        run=self.root/'transport';run.mkdir()
        for folder in ('requests','responses'): (run/folder).mkdir()
        manifest={'calls':[]}
        payload={'choices':[{'finish_reason':'stop','message':{'content':'{invalid'}}]}
        opener=type('Opener',(),{'open':lambda *_args,**_kw:io.BytesIO(json.dumps(payload).encode())})()
        with patch.dict(os.environ,{'LLM_API_KEY':'synthetic-key'},clear=True),patch.object(v4.urllib.request,'build_opener',return_value=opener):
            with self.assertRaises(v4.GenerationError):v4.Client(run,manifest).call('test','JSON',{},v4.obj({}),1)
        self.assertEqual((run/'responses/test-01.txt').read_text(),'{invalid')

    def test_stage_stops_after_two_repairs_and_keeps_failure(self):
        out=self.root/'failed-run'
        with patch.dict(os.environ,{'LLM_API_KEY':'synthetic-key'},clear=True),patch.object(v4.Client,'call',side_effect=v4.GenerationError('Synthetic schema failure')) as call:
            with self.assertRaises(v4.GenerationError):v4.run('EXWIRE',self.docs,'2026-09-23',out)
        self.assertEqual(call.call_count,3)
        self.assertEqual(json.loads((out/'manifest.json').read_text())['status'],'failed')
        self.assertTrue((out/'responses/triage-03-rejection.json').exists())
        self.assertFalse((out/'brief.md').exists())

    def test_transport_uses_small_budget_archives_truncation_and_does_not_accept_it(self):
        run=self.root/'transport';run.mkdir()
        for folder in ('requests','responses'): (run/folder).mkdir()
        manifest={'calls':[]}
        payload={'choices':[{'finish_reason':'length','message':{'content':'partial'}}]}
        opener=type('Opener',(),{'open':lambda *_args,**_kw:io.BytesIO(json.dumps(payload).encode())})()
        with patch.dict(os.environ,{'LLM_API_KEY':'synthetic-key','LLM_BASE_URL':'https://api.groq.com/openai/v1'},clear=True),patch.object(v4.urllib.request,'build_opener',return_value=opener):
            client=v4.Client(run,manifest)
            with self.assertRaisesRegex(v4.Invalid,'truncated'):client.call('test','Return JSON',{},v4.obj({}),1)
        request=json.loads((run/'requests/test-01.json').read_text())
        self.assertEqual(request['max_completion_tokens'],900)
        self.assertTrue((run/'responses/test-01-provider.json').exists())
        self.assertNotIn('synthetic-key',(run/'manifest.json').read_text())

if __name__=='__main__':unittest.main()
