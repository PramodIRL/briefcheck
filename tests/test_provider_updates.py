import io
import json
import unittest
from unittest.mock import patch
import briefcheck

class ProviderUpdateTests(unittest.TestCase):
    def test_reasoning_setting_and_application_header_reach_transport(self):
        envelope={'choices':[{'finish_reason':'stop','message':{'content':'{}'}}]}
        with patch.object(briefcheck,'open_http',return_value=io.BytesIO(json.dumps(envelope).encode())) as transport:
            _,meta=briefcheck.call_api({'system':'Return JSON','user':'Example'},'example-model','synthetic-key','https://provider.example/v1',20,reasoning_effort='none')
        request=transport.call_args.args[0]
        self.assertEqual(request.get_header('User-agent'),'BriefCheck/1.1')
        self.assertEqual(json.loads(request.data)['reasoning_effort'],'none')
        self.assertEqual(meta['api_settings']['reasoning_effort'],'none')

    def test_invalid_reasoning_setting_stops_before_transport(self):
        with self.assertRaises(briefcheck.BriefCheckError):
            briefcheck.effective_api_settings('model','https://provider.example/v1',20,None,'bearer','json_object','max_tokens','invalid')
