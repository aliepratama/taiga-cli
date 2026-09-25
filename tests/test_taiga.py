import importlib
import io
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

# Add scripts directory to path to import taiga module
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import taiga


class TestToonEncoder(unittest.TestCase):
    def test_encode_tabular_array(self):
        items = [
            {"ref": 101, "status": "New", "subject": "Fix login crash", "version": 1},
            {"ref": 102, "status": "In Progress", "subject": "Update docs", "version": 3},
        ]
        result = taiga.encode_toon("issues", items)
        expected = (
            "issues[2]{ref,status,subject,version}:\n"
            "  101,New,Fix login crash,1\n"
            "  102,In Progress,Update docs,3"
        )
        self.assertEqual(result, expected)

    def test_encode_tabular_with_selected_fields(self):
        items = [
            {"ref": 1, "status": "Open", "subject": "Bug", "ignored_field": "ignore_me"},
            {"ref": 2, "status": "Closed", "subject": "Feature", "ignored_field": "ignore_me"},
        ]
        result = taiga.encode_toon("issues", items, fields=["ref", "status", "subject"])
        expected = (
            "issues[2]{ref,status,subject}:\n"
            "  1,Open,Bug\n"
            "  2,Closed,Feature"
        )
        self.assertEqual(result, expected)

    def test_encode_quoting_and_escapes(self):
        items = [
            {"id": 1, "title": "Hello, world", "note": "line1\nline2"},
            {"id": 2, "title": 'He said "hi"', "note": "simple"},
        ]
        result = taiga.encode_toon("items", items)
        expected = (
            'items[2]{id,title,note}:\n'
            '  1,"Hello, world","line1\\nline2"\n'
            '  2,"He said \\"hi\\"",simple'
        )
        self.assertEqual(result, expected)

    def test_encode_empty_array(self):
        result = taiga.encode_toon("issues", [])
        self.assertEqual(result, "issues[0]:")

    def test_encode_single_object(self):
        obj = {
            "ref": 42,
            "status": "Ready",
            "subject": "Deploy to production",
            "assignee": None,
            "is_closed": False,
        }
        result = taiga.encode_toon(None, obj)
        expected = (
            "ref: 42\n"
            "status: Ready\n"
            "subject: Deploy to production\n"
            "assignee: -\n"
            "is_closed: false"
        )
        self.assertEqual(result, expected)

    def test_encode_nested_object_or_list(self):
        obj = {
            "ref": 10,
            "tags": ["bug", "ui"],
            "owner": {"username": "admin"},
        }
        result = taiga.encode_toon(None, obj)
        expected = (
            "ref: 10\n"
            "tags: bug,ui\n"
            "owner:\n"
            "  username: admin"
        )
        self.assertEqual(result, expected)

    def test_prepare_compact_issues(self):
        raw_issues = [
            {
                "id": 10,
                "ref": 1,
                "subject": "Crash on startup",
                "type_extra_info": {"name": "Bug"},
                "status_extra_info": {"name": "New"},
                "assigned_to_extra_info": {"full_name_display": "Alice"},
                "version": 2,
            }
        ]
        compact = taiga.prepare_compact_issues(raw_issues)
        self.assertEqual(len(compact), 1)
        self.assertEqual(compact[0]["ref"], 1)
        self.assertEqual(compact[0]["type"], "Bug")
        self.assertEqual(compact[0]["status"], "New")
        self.assertEqual(compact[0]["assigned"], "Alice")
        self.assertEqual(compact[0]["subject"], "Crash on startup")
        self.assertEqual(compact[0]["version"], 2)

    def test_prepare_compact_stories_tasks_epics(self):
        stories = [
            {
                "id": 20,
                "ref": 5,
                "subject": "Implement TOON format",
                "status_extra_info": {"name": "In Progress"},
                "total_points": 5,
                "assigned_to_extra_info": {"full_name_display": "Bob"},
                "version": 3,
            }
        ]
        comp_s = taiga.prepare_compact_stories(stories)
        self.assertEqual(comp_s[0]["ref"], 5)
        self.assertEqual(comp_s[0]["points"], 5)
        self.assertEqual(comp_s[0]["status"], "In Progress")

        tasks = [
            {
                "id": 30,
                "ref": 8,
                "subject": "Write unit tests",
                "user_story_extra_info": {"ref": 5},
                "status_extra_info": {"name": "Closed"},
                "assigned_to_extra_info": {"full_name_display": "Bob"},
                "version": 1,
            }
        ]
        comp_t = taiga.prepare_compact_tasks(tasks)
        self.assertEqual(comp_t[0]["story"], "#5")
        self.assertEqual(comp_t[0]["status"], "Closed")

        epics = [
            {
                "id": 40,
                "ref": 2,
                "subject": "Core Engine V2",
                "status_extra_info": {"name": "Active"},
                "color": "#ffaa00",
                "version": 4,
            }
        ]
        comp_e = taiga.prepare_compact_epics(epics)
        self.assertEqual(comp_e[0]["color"], "#ffaa00")

    def test_parse_fields_arg(self):
        self.assertIsNone(taiga.parse_fields_arg(None))
        self.assertIsNone(taiga.parse_fields_arg(""))
        self.assertEqual(
            taiga.parse_fields_arg("ref, status, subject"),
            ["ref", "status", "subject"]
        )

    def test_parser_has_fields_arguments(self):
        parser = taiga.build_parser()
        args = parser.parse_args(["issues", "list", "--fields", "ref,status"])
        self.assertEqual(args.fields, "ref,status")

    def test_parser_version_flag(self):
        parser = taiga.build_parser()
        with mock.patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            with self.assertRaises(SystemExit) as ctx:
                parser.parse_args(["--version"])
        self.assertEqual(ctx.exception.code, 0)
        self.assertIn("taiga-cli 0.1.0", mock_out.getvalue())

    def test_none_type_extra_info_handling(self):
        raw_issues = [
            {
                "id": 10,
                "ref": 1,
                "subject": "Null extra info issue",
                "type_extra_info": None,
                "status_extra_info": None,
                "assigned_to_extra_info": None,
                "version": 1,
            }
        ]
        compact_i = taiga.prepare_compact_issues(raw_issues)
        self.assertEqual(compact_i[0]["type"], "-")
        self.assertEqual(compact_i[0]["status"], "-")
        self.assertEqual(compact_i[0]["assigned"], "-")

        raw_stories = [
            {
                "id": 20,
                "ref": 2,
                "subject": "Null extra info story",
                "status_extra_info": None,
                "total_points": None,
                "assigned_to_extra_info": None,
                "version": 1,
            }
        ]
        compact_s = taiga.prepare_compact_stories(raw_stories)
        self.assertEqual(compact_s[0]["status"], "-")
        self.assertEqual(compact_s[0]["assigned"], "-")

        raw_tasks = [
            {
                "id": 30,
                "ref": 3,
                "subject": "Null extra info task",
                "user_story_extra_info": None,
                "user_story": None,
                "status_extra_info": None,
                "assigned_to_extra_info": None,
                "version": 1,
            }
        ]
        compact_t = taiga.prepare_compact_tasks(raw_tasks)
        self.assertEqual(compact_t[0]["story"], "-")
        self.assertEqual(compact_t[0]["status"], "-")
        self.assertEqual(compact_t[0]["assigned"], "-")

    def test_endpoint_normalizer(self):
        self.assertEqual(taiga.normalize_endpoint("/user-stories"), "userstories")
        self.assertEqual(taiga.normalize_endpoint("user_stories"), "userstories")
        self.assertEqual(taiga.normalize_endpoint("/user-stories/by_ref"), "userstories/by_ref")
        self.assertEqual(taiga.normalize_endpoint("issue-types/"), "issue-types")
        self.assertEqual(taiga.normalize_endpoint("/userstory_statuses"), "userstory-statuses")

    def test_parser_project_flag_positions(self):
        parser = taiga.build_parser()
        args1 = parser.parse_args(["stories", "get", "88", "--project", "1799125"])
        self.assertEqual(args1.project, "1799125")

        args2 = parser.parse_args(["issues", "list", "-p", "my-slug"])
        self.assertEqual(args2.project, "my-slug")

        args3 = parser.parse_args(["--project", "99", "tasks", "list"])
        self.assertEqual(args3.project, "99")

    def test_client_get_item_fallback_403_and_404(self):
        client = taiga.TaigaClient(base_url="https://fake.taiga.io", token="fake")

        calls = []

        def mock_request(method, path, **kwargs):
            calls.append((method, path))
            if path == "userstories/88":
                raise taiga.TaigaAPIError(403, "Permission Denied")
            if path == "userstories/by_ref?ref=88&project=123":
                return {"id": 999, "ref": 88, "subject": "Found by ref"}
            raise taiga.TaigaAPIError(404, "Not Found")

        client.request = mock_request
        item = client.get_item_by_id_or_ref("userstories", "88", project_arg=123)
        self.assertEqual(item["ref"], 88)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0], ("GET", "userstories/88"))
        self.assertEqual(calls[1], ("GET", "userstories/by_ref?ref=88&project=123"))

    def test_get_current_user_id(self):
        client = taiga.TaigaClient(base_url="https://fake.taiga.io", token="fake")

        def mock_request(method, path, **kwargs):
            if path == "users/me":
                return {"id": 909057, "username": "alice"}
            raise taiga.TaigaAPIError(404, "Not Found")

        client.request = mock_request
        user_id = client.get_current_user_id()
        self.assertEqual(user_id, 909057)


class TestAtomicStorage(unittest.TestCase):
    def test_atomic_write_creates_file_with_0600_permissions(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target_file = Path(tmpdir) / "test_session.json"
            data = {"token": "secret_token_123", "user_id": 99}

            taiga.atomic_write_json(target_file, data)

            self.assertTrue(target_file.is_file())
            # Check file permissions on POSIX
            if os.name != "nt":
                file_stat = target_file.stat()
                mode = stat.S_IMODE(file_stat.st_mode)
                self.assertEqual(mode, 0o600)

            # Check content
            loaded = taiga.load_json_file(target_file)
            self.assertEqual(loaded, data)

    def test_atomic_write_temp_file_cleanup_on_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target_file = Path(tmpdir) / "sub" / "error_file.json"
            # Attempt to write an un-serializable object to trigger exception in json.dump
            with self.assertRaises(TypeError):
                taiga.atomic_write_json(target_file, object())

            # Verify no temporary files remain in the target directory
            temp_files = list(target_file.parent.glob("tmp*"))
            self.assertEqual(temp_files, [])
            self.assertFalse(target_file.exists())


class TestSecurityHardening(unittest.TestCase):
    def test_cross_origin_request_forbidden(self):
        client = taiga.TaigaClient(base_url="https://api.taiga.io", token="dummy-token")
        with self.assertRaises(ValueError) as ctx:
            client.request("GET", "https://evil.com/api/v1/data")
        self.assertIn("Cross-origin requests forbidden: evil.com", str(ctx.exception))

    def test_insecure_http_protection(self):
        # Insecure HTTP to remote host raises ValueError
        with self.assertRaises(ValueError) as ctx:
            taiga.TaigaClient(base_url="http://remote.taiga.example.com", token="dummy")
        self.assertIn("Insecure HTTP protocol", str(ctx.exception))

        # Localhost is allowed without allow_insecure
        client_localhost = taiga.TaigaClient(base_url="http://localhost:8000", token="dummy")
        self.assertEqual(client_localhost.base_url, "http://localhost:8000")

        client_127 = taiga.TaigaClient(base_url="http://127.0.0.1:8000", token="dummy")
        self.assertEqual(client_127.base_url, "http://127.0.0.1:8000")

        # Remote host allowed when allow_insecure=True
        client_insecure = taiga.TaigaClient(
            base_url="http://remote.taiga.example.com", token="dummy", allow_insecure=True
        )
        self.assertEqual(client_insecure.base_url, "http://remote.taiga.example.com")

    def test_authorization_uses_unredirected_header(self):
        client = taiga.TaigaClient(base_url="https://api.taiga.io", token="secret_token_123")
        captured_req = []

        class MockResp:
            status = 200

            def read(self):
                return b'{"ok": true}'

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_val, exc_tb):
                pass

        def mock_urlopen(req):
            captured_req.append(req)
            return MockResp()

        with mock.patch("urllib.request.urlopen", side_effect=mock_urlopen):
            client.request("GET", "projects")

        self.assertEqual(len(captured_req), 1)
        req = captured_req[0]
        self.assertEqual(req.unredirected_hdrs.get("Authorization"), "Bearer secret_token_123")
        self.assertNotIn("Authorization", req.headers)

    def test_token_cache_collision_prevention(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            session_file = Path(tmpdir) / "session.json"
            taiga.atomic_write_json(
                session_file,
                {"base_url": "https://api.taiga.io", "token": "bob_token", "username": "bob"},
            )
            with mock.patch.object(taiga, "SESSION_FILE", session_file):
                # When client username is alice, bob's token must be ignored
                client_alice = taiga.TaigaClient(
                    base_url="https://api.taiga.io",
                    username="alice",
                )
                self.assertIsNone(client_alice._load_cached_token())
                self.assertIsNone(client_alice.token)

                # When client username is bob, bob's token is loaded
                client_bob = taiga.TaigaClient(
                    base_url="https://api.taiga.io",
                    username="bob",
                )
                self.assertEqual(client_bob._load_cached_token(), "bob_token")
                self.assertEqual(client_bob.token, "bob_token")

    def test_xdg_base_directory_support(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            custom_config = str(Path(tmpdir) / "custom_config")
            custom_cache = str(Path(tmpdir) / "custom_cache")
            with mock.patch.dict(
                os.environ,
                {
                    "XDG_CONFIG_HOME": custom_config,
                    "XDG_CACHE_HOME": custom_cache,
                },
            ):
                importlib.reload(taiga)
                self.assertEqual(taiga.CONFIG_DIR, Path(custom_config) / "taiga")
                self.assertEqual(taiga.CACHE_DIR, Path(custom_cache) / "taiga")
                self.assertEqual(taiga.CONFIG_FILE, Path(custom_config) / "taiga" / "config.json")
                self.assertEqual(taiga.SESSION_FILE, Path(custom_cache) / "taiga" / "session.json")
            # Reload module after test to restore default environment state
            importlib.reload(taiga)


if __name__ == "__main__":
    unittest.main()
