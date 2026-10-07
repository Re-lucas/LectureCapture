import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

spec = importlib.util.spec_from_file_location(
    'publication_check', Path(__file__).resolve().parents[1] / 'scripts' / 'check_publication.py')
publication = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publication)


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.git('init', '-b', 'main')
        self.git('config', 'user.name', 'Example contributor')
        self.git('config', 'user.email', 'contributor@example.com')
        self.git('config', 'commit.gpgsign', 'false')
        self.git('config', 'core.hooksPath', str(self.root / 'unused-hooks'))

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.root), *args],
                              capture_output=True, check=True).stdout

    def commit(self, files, message='Synthetic change'):
        for name, text in files.items():
            (self.root / name).write_text(text, encoding='utf-8')
        self.git('add', '.')
        self.git('commit', '-m', message)

    def test_clean_public_tree_passes(self):
        self.commit({'README.md': 'A generic local caption tool.'})
        self.assertEqual([], publication.inspect(self.root)['issues'])

    def test_private_local_settings_fail_allowlist(self):
        self.commit({'README.md': 'Example', 'settings.json': '{}'})
        self.assertTrue(any(item[2] == 'outside-public-allowlist'
                            for item in publication.inspect(self.root)['issues']))

    def test_github_noreply_metadata_passes(self):
        self.git('config', 'user.email', 'noreply@github.com')
        self.commit({'README.md': 'Example'})
        self.assertEqual([], publication.inspect(self.root)['issues'])

    def test_token_removed_in_latest_commit_still_fails_history(self):
        token = 'gh' + 'p_' + 'x' * 36  # Invented fixture; not a credential.
        self.commit({'README.md': token})
        self.commit({'README.md': 'Clean now'})
        full = publication.inspect(self.root)
        self.assertEqual(2, full['commits'])
        self.assertTrue(any(item[2] == 'github-token' for item in full['issues']))
        self.assertFalse(any(token in str(item) for item in full['issues']))
        self.assertEqual([], publication.inspect(self.root, snapshot=True)['issues'])

    def test_personal_author_email_is_detected(self):
        self.git('config', 'user.email', 'someone' + '@' + 'private.invalid')
        self.commit({'README.md': 'Example'})
        self.assertTrue(any(item[1:] == ('<commit metadata>', 'personal-email')
                            for item in publication.inspect(self.root)['issues']))

    def test_machine_path_and_private_key_are_detected(self):
        path = 'C:' + chr(92) + 'Users' + chr(92) + 'Example'
        private_key = '-' * 5 + 'BEGIN PRIVATE KEY' + '-' * 5
        self.commit({'README.md': path + '\n' + private_key})
        categories = {item[2] for item in publication.inspect(self.root)['issues']}
        self.assertIn('machine-path', categories)
        self.assertIn('private-key', categories)
