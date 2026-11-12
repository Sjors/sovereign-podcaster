import importlib.util
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch,Mock

spec=importlib.util.spec_from_file_location('setup',Path(__file__).with_name('setup.py'))
s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)


class AliasTests(unittest.TestCase):
    def test_ppq_install_needs_no_openai_project_keys_or_codex_executable(self):
        with tempfile.TemporaryDirectory() as directory:
            home=Path(directory);marmot=home/'marmot';config=home/'.config/sovereign-podcaster';config.mkdir(parents=True)
            key=config/'api.key';key.write_text('fixture-secret');key.chmod(0o600)
            settings=config/'llm.json';s.save(settings,dict(provider='ppq',model='gpt-6.1-sol',reasoning_effort='high',api_key_file=str(key)))
            installer=b'fixture installer';downloader=Mock()
            downloader.open.side_effect=[io.BytesIO(installer),io.BytesIO(hashlib.sha256(installer).hexdigest().encode())]
            commands=[]
            def run(command,**kwargs):
                commands.append(command)
                if command[0]=='bash':s.save(marmot/'bootstrap.json',dict(npub='npub-fixture',account_id_hex='a'*64,welcomer_account_ids_hex=['b'*64]))
            with patch.object(s.Path,'home',return_value=home),patch.dict(s.LOCK,installer_sha256=hashlib.sha256(installer).hexdigest()),patch.object(s.urllib.request,'build_opener',return_value=downloader),patch.object(s.subprocess,'run',side_effect=run),patch.object(s,'skill_links') as skills,patch.object(s.sys,'argv',['setup.py','--home',str(marmot),'--trusted-npub','npub1'+'q'*58,'--llm-config',str(settings),'--allow-timeout-only']):
                s.main()
            skills.assert_not_called()
            self.assertFalse((home/'.local/bin/codex').exists());self.assertFalse((config/'openai').exists())
            instance=json.loads((marmot/'podcaster-instance.json').read_text());self.assertIsNone(instance['project_id']);self.assertEqual(instance['llm_config'],str(settings))
            self.assertFalse(any(any('codex'==Path(str(arg)).name for arg in command) for command in commands))

    def test_wrapper_has_room_for_the_longest_backend_turn_and_cleanup(self):
        import runtime_limits
        self.assertGreaterEqual(s.HARNESS_TIMEOUT_SECONDS,
            runtime_limits.MAX_MODEL_TURN_SECONDS+runtime_limits.HARNESS_CLEANUP_SECONDS)

    def test_short_alias_is_repeatable_and_never_replaces_other_workspace(self):
        with tempfile.TemporaryDirectory() as directory:
            home=Path(directory);repo=home/'checkout';repo.mkdir()
            with patch.object(s.Path,'home',return_value=home),patch.object(s,'REPO',repo):
                alias=s.workspace_alias()
                self.assertEqual(alias,home/'src/podcast')
                self.assertEqual(s.workspace_alias().resolve(),repo)
                alias.unlink();alias.mkdir();(alias/'keep').write_text('existing work')
                with self.assertRaisesRegex(RuntimeError,'already points elsewhere'):s.workspace_alias()
                self.assertEqual((alias/'keep').read_text(),'existing work')


if __name__=='__main__':unittest.main()
