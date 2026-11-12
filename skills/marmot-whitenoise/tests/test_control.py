import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT=Path(__file__).resolve().parents[1]/'scripts/wn_control.py'
spec=importlib.util.spec_from_file_location('control',SCRIPT);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class ControlTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.path=self.root/'text.json'
        self.value={'account_id_hex':'a'*64,'group_id_hex':'b'*32,'text':'Authorized test','idempotency_key':'synthetic-key'}
        self.write()

    def write(self):
        self.path.write_text(json.dumps(self.value));self.path.chmod(0o600)

    def invoke(self):
        with patch.object(sys,'argv',[str(SCRIPT),'--home',str(self.root),'--send-text',str(self.path)]),contextlib.redirect_stdout(io.StringIO()):m.main()

    def test_confirmed_send_reuses_receipt_and_rejects_changed_text(self):
        response={'type':'final_sent','message_ids_hex':['c'*64]}
        with patch.object(m,'rpc',return_value=response) as rpc:
            self.invoke();self.invoke();self.assertEqual(rpc.call_count,1)
            self.value['text']='Different text';self.write()
            with self.assertRaisesRegex(AssertionError,'different bytes'):
                self.invoke()
            self.assertEqual(rpc.call_count,1)

    def test_unknown_send_is_not_retried(self):
        with patch.object(m,'rpc',side_effect=TimeoutError) as rpc:
            with self.assertRaises(TimeoutError):self.invoke()
            with self.assertRaisesRegex(SystemExit,'pending/uncertain'):self.invoke()
            self.assertEqual(rpc.call_count,1)

    def test_python_optimization_cannot_disable_manifest_checks(self):
        p=subprocess.run([sys.executable,'-O',str(SCRIPT),'--help'],capture_output=True,text=True)
        self.assertNotEqual(p.returncode,0);self.assertIn('safety checks',p.stderr)


if __name__=='__main__':unittest.main()
