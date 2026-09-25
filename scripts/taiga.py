#!/usr/bin/env python3
"""Taiga Universal CLI & API Client.

A lightweight, zero-dependency CLI tool to interact with Taiga.io REST API.
Handles auto-authentication, session caching, optimistic concurrency control (versioning),
and provides both ergonomic shortcuts and a 100% generic REST passthrough.
"""

import argparse
import getpass
import json
import os
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

__version__ = "0.1.0"

DEFAULT_TAIGA_URL = "https://api.taiga.io"
CONFIG_DIR = Path(os.getenv("XDG_CONFIG_HOME", Path.home() / ".config")) / "taiga"
CACHE_DIR = Path(os.getenv("XDG_CACHE_HOME", Path.home() / ".cache")) / "taiga"
SESSION_FILE = CACHE_DIR / "session.json"
CONFIG_FILE = CONFIG_DIR / "config.json"


def atomic_write_json(file_path: Union[str, Path], data: Any, mode: int = 0o600) -> None:
    path = Path(file_path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temp_dir = path.parent
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile("w", dir=temp_dir, delete=False, encoding="utf-8") as tf:
            temp_name = tf.name
            json.dump(data, tf, indent=2)
        if os.name != "nt":
            try:
                os.chmod(temp_name, mode)
            except OSError:
                pass
        os.replace(temp_name, path)
        temp_name = None
    finally:
        if temp_name is not None and os.path.exists(temp_name):
            try:
                os.unlink(temp_name)
            except OSError:
                pass


def load_json_file(file_path: Union[str, Path]) -> Dict[str, Any]:
    path = Path(file_path)
    if not path.is_file():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def encode_toon_value(val: Any) -> str:
    if val is None:
        return "-"
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, list):
        return ",".join(encode_toon_value(x) for x in val)
    s = str(val)
    if "," in s or '"' in s or "\n" in s or "\r" in s or s.strip() != s:
        escaped = s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r")
        return f'"{escaped}"'
    return s


def encode_toon(name: Optional[str], data: Any, fields: Optional[List[str]] = None) -> str:
    if isinstance(data, list):
        if not data:
            return f"{name}[0]:" if name else "[]"
        if all(isinstance(x, dict) for x in data):
            if not fields:
                seen = set()
                fields = []
                for item in data:
                    for k in item.keys():
                        if k not in seen:
                            seen.add(k)
                            fields.append(k)
            header_name = name or "items"
            header = f"{header_name}[{len(data)}]{{{','.join(fields)}}}:"
            rows = [
                f"  {','.join(encode_toon_value(item.get(f)) for f in fields)}"
                for item in data
            ]
            return "\n".join([header] + rows)
        encoded_items = [encode_toon_value(x) for x in data]
        return f"{name}[{len(data)}]: {','.join(encoded_items)}" if name else ",".join(encoded_items)

    if isinstance(data, dict):
        lines = []
        for k, v in data.items():
            if isinstance(v, dict):
                lines.append(f"{k}:")
                for sub_k, sub_v in v.items():
                    lines.append(f"  {sub_k}: {encode_toon_value(sub_v)}")
            else:
                lines.append(f"{k}: {encode_toon_value(v)}")
        return "\n".join(lines)

    return encode_toon_value(data)


class TaigaAPIError(Exception):
    """Exception raised when Taiga API returns an error response."""

    def __init__(self, status_code: int, message: str, response_data: Any = None):
        super().__init__(f"HTTP {status_code}: {message}")
        self.status_code = status_code
        self.message = message
        self.response_data = response_data


class TaigaClient:
    """HTTP Client for Taiga REST API with session caching and auto-reauth."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        token: Optional[str] = None,
        default_project: Optional[str] = None,
        allow_insecure: bool = False,
    ):
        config = self._load_config()
        self.base_url = (
            base_url
            or os.getenv("TAIGA_API_URL")
            or config.get("url")
            or DEFAULT_TAIGA_URL
        ).rstrip("/")
        if not self.base_url.endswith("/api/v1"):
            self.api_url = f"{self.base_url}/api/v1"
        else:
            self.api_url = self.base_url
            self.base_url = self.base_url[:-7]

        self.allow_insecure = (
            allow_insecure
            or os.getenv("TAIGA_INSECURE", "").lower() in ("1", "true", "yes")
        )
        parsed_url = urllib.parse.urlparse(self.base_url)
        hostname = (parsed_url.hostname or "").lower()
        if (
            parsed_url.scheme == "http"
            and hostname not in ("localhost", "127.0.0.1", "::1")
            and not self.allow_insecure
        ):
            raise ValueError(
                f"Insecure HTTP protocol '{self.base_url}' rejected for remote host. Use HTTPS or pass --insecure (or TAIGA_INSECURE=1)."
            )

        self.username = username or os.getenv("TAIGA_USERNAME") or config.get("username")
        self.password = password or os.getenv("TAIGA_PASSWORD")
        self.token = token or os.getenv("TAIGA_AUTH_TOKEN") or config.get("token")
        self.default_project = (
            default_project
            or os.getenv("TAIGA_PROJECT_ID")
            or config.get("default_project")
        )

        if not self.token:
            self.token = self._load_cached_token()

    def _load_config(self) -> Dict[str, Any]:
        return load_json_file(CONFIG_FILE)

    def _load_cached_token(self) -> Optional[str]:
        data = load_json_file(SESSION_FILE)
        if data.get("base_url") == self.base_url and data.get("token"):
            cached_username = data.get("username")
            if self.username and cached_username and cached_username != self.username:
                return None
            return data.get("token")
        return None

    def _save_cached_token(self, token: str, user_id: Optional[int] = None):
        data = {
            "base_url": self.base_url,
            "token": token,
            "username": self.username,
            "user_id": user_id,
        }
        atomic_write_json(SESSION_FILE, data)

    def login(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        save_config: bool = False,
    ) -> Dict[str, Any]:
        """Authenticate with Taiga using username and password."""
        user = username or self.username
        pwd = password or self.password
        if not user or not pwd:
            raise ValueError(
                "Missing credentials. Set TAIGA_USERNAME & TAIGA_PASSWORD or pass --username and --password."
            )

        endpoint = f"{self.api_url}/auth"
        payload = {
            "type": "normal",
            "username": user,
            "password": pwd,
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            endpoint,
            data=data,
            headers={
                "Content-Type": "application/json",
                "User-Agent": f"Taiga-CLI/{__version__}",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                token = result.get("auth_token")
                user_id = result.get("id")
                if not token:
                    raise TaigaAPIError(500, "Auth token not present in login response")

                self.token = token
                self.username = user
                self.password = pwd
                self._save_cached_token(token, user_id)

                if save_config:
                    cfg = {
                        "url": self.base_url,
                        "username": user,
                        "default_project": self.default_project,
                    }
                    atomic_write_json(CONFIG_FILE, cfg)

                return result
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(err_body)
                msg = parsed.get("_error_message") or parsed.get("detail") or err_body
            except Exception:
                msg = err_body
            raise TaigaAPIError(e.code, msg)

    def request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Union[Dict[str, Any], List[Any]]] = None,
        retry_on_401: bool = True,
    ) -> Any:
        """Perform an HTTP request with automatic token header and 401 retry."""
        if not self.token:
            if self.username and self.password:
                self.login()
            else:
                raise ValueError(
                    "Not authenticated. Run 'taiga login' or set TAIGA_USERNAME and TAIGA_PASSWORD."
                )

        if path.startswith(("http://", "https://")):
            parsed_target = urllib.parse.urlparse(path)
            parsed_base = urllib.parse.urlparse(self.base_url)
            if (parsed_target.scheme, parsed_target.netloc) != (parsed_base.scheme, parsed_base.netloc):
                raise ValueError(f"Cross-origin requests forbidden: {parsed_target.netloc}")
            url = path
        else:
            clean_path = path.lstrip("/")
            if not clean_path.startswith("api/v1/"):
                url = f"{self.api_url}/{clean_path}"
            else:
                url = f"{self.base_url}/{clean_path}"

        if params:
            clean_params = {k: v for k, v in params.items() if v is not None}
            if clean_params:
                encoded = urllib.parse.urlencode(clean_params)
                url = f"{url}?{encoded}" if "?" not in url else f"{url}&{encoded}"

        headers = {
            "Content-Type": "application/json",
            "User-Agent": f"Taiga-CLI/{__version__}",
            "x-disable-pagination": "True",
        }

        body = None
        if data is not None:
            body = json.dumps(data).encode("utf-8")

        req = urllib.request.Request(url, data=body, headers=headers, method=method.upper())
        req.add_unredirected_header("Authorization", f"Bearer {self.token}")

        try:
            with urllib.request.urlopen(req) as resp:
                if resp.status == 204:
                    return {"status": "success", "message": "No Content (204)"}
                resp_text = resp.read().decode("utf-8")
                if not resp_text:
                    return None
                try:
                    return json.loads(resp_text)
                except json.JSONDecodeError:
                    return resp_text
        except urllib.error.HTTPError as e:
            if e.code == 401 and retry_on_401 and self.username and self.password:
                self.login()
                return self.request(method, path, params=params, data=data, retry_on_401=False)

            err_body = e.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(err_body)
                msg = (
                    parsed.get("_error_message")
                    or parsed.get("detail")
                    or parsed.get("message")
                    or json.dumps(parsed)
                )
            except Exception:
                msg = err_body
            raise TaigaAPIError(e.code, msg, response_data=err_body)

    def resolve_project_id(self, project_arg: Optional[Union[str, int]]) -> int:
        """Resolve a project ID from argument, default_project, or slug lookup."""
        target = project_arg or self.default_project
        if not target:
            raise ValueError(
                "Project ID required. Pass --project <id_or_slug> or set TAIGA_PROJECT_ID."
            )

        if isinstance(target, int) or (isinstance(target, str) and target.isdigit()):
            return int(target)

        proj = self.request("GET", "projects/by_slug", params={"slug": target})
        if not proj or "id" not in proj:
            raise ValueError(f"Project with slug '{target}' not found.")
        return proj["id"]

    def get_current_user_id(self) -> Optional[int]:
        session_data = load_json_file(SESSION_FILE)
        cached_id = session_data.get("user_id")
        if cached_id:
            return int(cached_id)
        try:
            user = self.request("GET", "users/me")
            user_id = user.get("id")
            if user_id:
                session_data["user_id"] = user_id
                atomic_write_json(SESSION_FILE, session_data)
                return int(user_id)
        except Exception:
            return None
        return None

    def get_item_by_id_or_ref(
        self,
        entity_endpoint: str,
        target: Union[str, int],
        project_arg: Optional[Union[str, int]] = None,
        by_ref: bool = False,
    ) -> Dict[str, Any]:
        target_str = str(target).lstrip("#")
        if not target_str.isdigit():
            raise ValueError(f"Invalid target: {target}")

        if by_ref:
            project_id = self.resolve_project_id(project_arg)
            return self.request("GET", f"{entity_endpoint}/by_ref?ref={target_str}&project={project_id}")

        try:
            return self.request("GET", f"{entity_endpoint}/{target_str}")
        except TaigaAPIError as e:
            if e.status_code in (403, 404):
                try:
                    project_id = self.resolve_project_id(project_arg)
                    return self.request("GET", f"{entity_endpoint}/by_ref?ref={target_str}&project={project_id}")
                except Exception:
                    raise e
            raise e


def parse_fields_arg(fields_arg: Optional[str]) -> Optional[List[str]]:
    if not fields_arg:
        return None
    return [f.strip() for f in fields_arg.split(",") if f.strip()]


def normalize_endpoint(endpoint: str) -> str:
    ep = endpoint.strip().strip("/")
    replacements = {
        "user-stories": "userstories",
        "user_stories": "userstories",
        "userstory-statuses": "userstory-statuses",
        "userstory_statuses": "userstory-statuses",
        "issue-types": "issue-types",
        "issue_types": "issue-types",
        "issue-statuses": "issue-statuses",
        "issue_statuses": "issue-statuses",
        "task-statuses": "task-statuses",
        "task_statuses": "task-statuses",
    }
    parts = ep.split("/")
    if parts and parts[0] in replacements:
        parts[0] = replacements[parts[0]]
    return "/".join(parts)


def prepare_compact_issues(issues: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {
            "ref": i.get("ref"),
            "id": i.get("id"),
            "type": (i.get("type_extra_info") or {}).get("name") or i.get("type") or "-",
            "status": (i.get("status_extra_info") or {}).get("name") or i.get("status") or "-",
            "assigned": (i.get("assigned_to_extra_info") or {}).get("full_name_display") or i.get("assigned_to") or "-",
            "subject": i.get("subject"),
            "version": i.get("version"),
        }
        for i in issues
    ]


def prepare_compact_stories(stories: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {
            "ref": s.get("ref"),
            "id": s.get("id"),
            "status": (s.get("status_extra_info") or {}).get("name") or s.get("status") or "-",
            "points": s.get("total_points") if s.get("total_points") is not None else "-",
            "assigned": (s.get("assigned_to_extra_info") or {}).get("full_name_display") or s.get("assigned_to") or "-",
            "subject": s.get("subject"),
            "version": s.get("version"),
        }
        for s in stories
    ]


def prepare_compact_tasks(tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {
            "ref": t.get("ref"),
            "id": t.get("id"),
            "story": f"#{(t.get('user_story_extra_info') or {}).get('ref')}" if (t.get("user_story_extra_info") or {}).get("ref") else (f"#{t.get('user_story')}" if t.get("user_story") else "-"),
            "status": (t.get("status_extra_info") or {}).get("name") or t.get("status") or "-",
            "assigned": (t.get("assigned_to_extra_info") or {}).get("full_name_display") or t.get("assigned_to") or "-",
            "subject": t.get("subject"),
            "version": t.get("version"),
        }
        for t in tasks
    ]


def prepare_compact_epics(epics: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {
            "ref": e.get("ref"),
            "id": e.get("id"),
            "status": (e.get("status_extra_info") or {}).get("name") or e.get("status") or "-",
            "color": e.get("color") or "-",
            "subject": e.get("subject"),
            "version": e.get("version"),
        }
        for e in epics
    ]


def cmd_login(client: TaigaClient, args: argparse.Namespace):
    pwd = getattr(args, "password", None) or os.getenv("TAIGA_PASSWORD")
    if not pwd and sys.stdin.isatty():
        args.password = getpass.getpass("Taiga Password: ")
    res = client.login(username=args.username, password=args.password, save_config=args.save)
    print(encode_toon(None, {"login": "success", "username": res.get("username", client.username)}))


def cmd_whoami(client: TaigaClient, args: argparse.Namespace):
    user = client.request("GET", "users/me")
    if args.json:
        print(json.dumps(user, indent=2))
    else:
        profile = {
            "id": user.get("id"),
            "username": user.get("username"),
            "full_name": user.get("full_name"),
            "email": user.get("email"),
            "theme": user.get("theme", "default"),
        }
        print(encode_toon(None, profile))


def cmd_config(client: TaigaClient, args: argparse.Namespace):
    project_target = getattr(args, "project", None) or client.default_project
    project_id = client.resolve_project_id(project_target)
    project = client.request("GET", f"projects/{project_id}")

    issue_types = client.request("GET", "issue-types", params={"project": project_id})
    severities = client.request("GET", "severities", params={"project": project_id})
    priorities = client.request("GET", "priorities", params={"project": project_id})
    issue_statuses = client.request("GET", "issue-statuses", params={"project": project_id})
    us_statuses = client.request("GET", "userstory-statuses", params={"project": project_id})
    task_statuses = client.request("GET", "task-statuses", params={"project": project_id})

    config_data = {
        "project": {
            "id": project.get("id"),
            "name": project.get("name"),
            "slug": project.get("slug"),
        },
        "issue_types": {item["name"]: item["id"] for item in issue_types},
        "severities": {item["name"]: item["id"] for item in severities},
        "priorities": {item["name"]: item["id"] for item in priorities},
        "issue_statuses": {item["name"]: item["id"] for item in issue_statuses},
        "user_story_statuses": {item["name"]: item["id"] for item in us_statuses},
        "task_statuses": {item["name"]: item["id"] for item in task_statuses},
    }

    if args.json:
        print(json.dumps(config_data, indent=2))
    else:
        print(encode_toon(None, config_data))


def cmd_projects(client: TaigaClient, args: argparse.Namespace):
    action = args.action
    if action == "list":
        params = {}
        if not getattr(args, "all", False):
            if getattr(args, "member", None):
                params["member"] = args.member
            else:
                user_id = client.get_current_user_id()
                if user_id:
                    params["member"] = user_id

        projs = client.request("GET", "projects", params=params if params else None)
        fields = parse_fields_arg(getattr(args, "fields", None)) or ["id", "slug", "name", "is_private"]
        if args.json:
            print(json.dumps(projs, indent=2))
        else:
            compact = [
                {
                    "id": p.get("id"),
                    "slug": p.get("slug"),
                    "name": p.get("name"),
                    "is_private": p.get("is_private", False),
                }
                for p in projs
            ]
            print(encode_toon("projects", compact, fields=fields))
    elif action == "get":
        target = args.target
        if str(target).isdigit():
            p = client.request("GET", f"projects/{target}")
        else:
            p = client.request("GET", "projects/by_slug", params={"slug": target})
        if args.json:
            print(json.dumps(p, indent=2))
        else:
            data = {
                "id": p.get("id"),
                "name": p.get("name"),
                "slug": p.get("slug"),
                "is_private": p.get("is_private", False),
                "members_count": len(p.get("members", [])),
                "description": p.get("description") or "-",
            }
            fields = parse_fields_arg(getattr(args, "fields", None))
            if fields:
                data = {k: v for k, v in data.items() if k in fields}
            print(encode_toon(None, data))


def cmd_issues(client: TaigaClient, args: argparse.Namespace):
    action = args.action
    if action == "list":
        project_id = client.resolve_project_id(args.project)
        params = {"project": project_id}
        if args.status:
            params["status"] = args.status
        if args.assigned:
            params["assigned_to"] = args.assigned
        if args.type:
            params["type"] = args.type
        if args.severity:
            params["severity"] = args.severity
        if args.priority:
            params["priority"] = args.priority

        issues = client.request("GET", "issues", params=params)
        if args.limit and len(issues) > args.limit:
            issues = issues[: args.limit]

        compact = prepare_compact_issues(issues)
        fields = parse_fields_arg(getattr(args, "fields", None)) or ["ref", "id", "type", "status", "assigned", "subject", "version"]

        if args.full:
            print(json.dumps(issues, indent=2))
        elif args.json:
            print(json.dumps(compact, indent=2))
        else:
            print(encode_toon("issues", compact, fields=fields))

    elif action == "get":
        issue = client.get_item_by_id_or_ref("issues", args.target, project_arg=args.project, by_ref=args.by_ref)

        details = {
            "ref": issue.get("ref"),
            "id": issue.get("id"),
            "subject": issue.get("subject"),
            "status": (issue.get("status_extra_info") or {}).get("name") or issue.get("status"),
            "status_id": issue.get("status"),
            "type": (issue.get("type_extra_info") or {}).get("name") or issue.get("type"),
            "type_id": issue.get("type"),
            "severity": (issue.get("severity_extra_info") or {}).get("name") or issue.get("severity"),
            "priority": (issue.get("priority_extra_info") or {}).get("name") or issue.get("priority"),
            "assigned": (issue.get("assigned_to_extra_info") or {}).get("full_name_display") if issue.get("assigned_to_extra_info") else (issue.get("assigned_to") or "-"),
            "version": issue.get("version"),
            "created_date": issue.get("created_date"),
            "description": issue.get("description") or "-",
        }
        fields = parse_fields_arg(getattr(args, "fields", None))
        if fields:
            details = {k: v for k, v in details.items() if k in fields}

        if args.full:
            print(json.dumps(issue, indent=2))
        elif args.json:
            print(json.dumps(details, indent=2))
        else:
            print(encode_toon(None, details))

    elif action == "create":
        project_id = client.resolve_project_id(args.project)
        if not args.subject:
            raise ValueError("Subject is required. Pass --subject 'Issue title'")

        type_id = args.type
        status_id = args.status
        sev_id = args.severity
        prio_id = args.priority

        if not (type_id and status_id and sev_id and prio_id):
            proj_conf = client.request("GET", f"projects/{project_id}")
            if not type_id and proj_conf.get("default_issue_type"):
                type_id = proj_conf["default_issue_type"]
            if not status_id and proj_conf.get("default_issue_status"):
                status_id = proj_conf["default_issue_status"]
            if not sev_id and proj_conf.get("default_severity"):
                sev_id = proj_conf["default_severity"]
            if not prio_id and proj_conf.get("default_priority"):
                prio_id = proj_conf["default_priority"]

        payload = {
            "project": project_id,
            "subject": args.subject,
            "description": args.desc or "",
            "type": type_id,
            "status": status_id,
            "severity": sev_id,
            "priority": prio_id,
        }
        if args.assigned:
            payload["assigned_to"] = args.assigned
        if args.tags:
            payload["tags"] = [t.strip() for t in args.tags.split(",") if t.strip()]

        created = client.request("POST", "issues", data=payload)
        res = {
            "created": "issue",
            "ref": created.get("ref"),
            "id": created.get("id"),
            "subject": created.get("subject"),
            "version": created.get("version"),
        }
        if args.json:
            print(json.dumps(created if args.full else res, indent=2))
        else:
            print(encode_toon(None, res))

    elif action == "update":
        target = args.id
        current = client.request("GET", f"issues/{target}")
        version = current.get("version")

        payload = {"version": version}
        if args.data:
            payload.update(json.loads(args.data))
        if args.subject:
            payload["subject"] = args.subject
        if args.status:
            payload["status"] = args.status
        if args.assigned:
            payload["assigned_to"] = args.assigned
        if args.desc:
            payload["description"] = args.desc
        if args.comment:
            payload["comment"] = args.comment

        updated = client.request("PATCH", f"issues/{target}", data=payload)
        res = {
            "updated": "issue",
            "ref": updated.get("ref"),
            "version": updated.get("version"),
        }
        if args.json:
            print(json.dumps(updated if args.full else res, indent=2))
        else:
            print(encode_toon(None, res))

    elif action == "delete":
        target = args.id
        client.request("DELETE", f"issues/{target}")
        res = {"deleted": "issue", "id": target}
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print(encode_toon(None, res))


def cmd_stories(client: TaigaClient, args: argparse.Namespace):
    action = args.action
    if action == "list":
        project_id = client.resolve_project_id(args.project)
        params = {"project": project_id}
        if args.milestone:
            params["milestone"] = args.milestone
        if args.status:
            params["status"] = args.status
        if args.assigned:
            params["assigned_to"] = args.assigned
        if args.epic:
            params["epic"] = args.epic

        stories = client.request("GET", "userstories", params=params)
        if args.limit and len(stories) > args.limit:
            stories = stories[: args.limit]

        compact = prepare_compact_stories(stories)
        fields = parse_fields_arg(getattr(args, "fields", None)) or ["ref", "id", "status", "points", "assigned", "subject", "version"]

        if args.full:
            print(json.dumps(stories, indent=2))
        elif args.json:
            print(json.dumps(compact, indent=2))
        else:
            print(encode_toon("stories", compact, fields=fields))

    elif action == "get":
        story = client.get_item_by_id_or_ref("userstories", args.target, project_arg=args.project, by_ref=args.by_ref)

        details = {
            "ref": story.get("ref"),
            "id": story.get("id"),
            "subject": story.get("subject"),
            "status": (story.get("status_extra_info") or {}).get("name") or story.get("status"),
            "status_id": story.get("status"),
            "points": story.get("total_points") if story.get("total_points") is not None else "-",
            "assigned": (story.get("assigned_to_extra_info") or {}).get("full_name_display") if story.get("assigned_to_extra_info") else (story.get("assigned_to") or "-"),
            "milestone": story.get("milestone") or "-",
            "version": story.get("version"),
            "description": story.get("description") or "-",
        }
        fields = parse_fields_arg(getattr(args, "fields", None))
        if fields:
            details = {k: v for k, v in details.items() if k in fields}

        if args.full or args.json:
            print(json.dumps(story if args.full else details, indent=2))
        else:
            print(encode_toon(None, details))

    elif action == "create":
        project_id = client.resolve_project_id(args.project)
        if not args.subject:
            raise ValueError("Subject is required. Pass --subject 'Story title'")

        payload = {
            "project": project_id,
            "subject": args.subject,
            "description": args.desc or "",
        }
        if args.status:
            payload["status"] = args.status
        if args.milestone:
            payload["milestone"] = args.milestone
        if args.assigned:
            payload["assigned_to"] = args.assigned
        if args.tags:
            payload["tags"] = [t.strip() for t in args.tags.split(",") if t.strip()]

        created = client.request("POST", "userstories", data=payload)
        res = {
            "created": "story",
            "ref": created.get("ref"),
            "id": created.get("id"),
            "subject": created.get("subject"),
            "version": created.get("version"),
        }
        if args.json:
            print(json.dumps(created if args.full else res, indent=2))
        else:
            print(encode_toon(None, res))

    elif action == "update":
        target = args.id
        current = client.request("GET", f"userstories/{target}")
        version = current.get("version")

        payload = {"version": version}
        if args.data:
            payload.update(json.loads(args.data))
        if args.subject:
            payload["subject"] = args.subject
        if args.status:
            payload["status"] = args.status
        if args.assigned:
            payload["assigned_to"] = args.assigned
        if args.desc:
            payload["description"] = args.desc
        if args.comment:
            payload["comment"] = args.comment

        updated = client.request("PATCH", f"userstories/{target}", data=payload)
        res = {
            "updated": "story",
            "ref": updated.get("ref"),
            "version": updated.get("version"),
        }
        if args.json:
            print(json.dumps(updated if args.full else res, indent=2))
        else:
            print(encode_toon(None, res))

    elif action == "delete":
        target = args.id
        client.request("DELETE", f"userstories/{target}")
        res = {"deleted": "story", "id": target}
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print(encode_toon(None, res))


def cmd_tasks(client: TaigaClient, args: argparse.Namespace):
    action = args.action
    if action == "list":
        project_id = client.resolve_project_id(args.project)
        params = {"project": project_id}
        if args.story:
            params["user_story"] = args.story
        if args.milestone:
            params["milestone"] = args.milestone
        if args.status:
            params["status"] = args.status
        if args.assigned:
            params["assigned_to"] = args.assigned

        tasks = client.request("GET", "tasks", params=params)
        if args.limit and len(tasks) > args.limit:
            tasks = tasks[: args.limit]

        compact = prepare_compact_tasks(tasks)
        fields = parse_fields_arg(getattr(args, "fields", None)) or ["ref", "id", "story", "status", "assigned", "subject", "version"]

        if args.full:
            print(json.dumps(tasks, indent=2))
        elif args.json:
            print(json.dumps(compact, indent=2))
        else:
            print(encode_toon("tasks", compact, fields=fields))

    elif action == "get":
        task = client.get_item_by_id_or_ref("tasks", args.target, project_arg=args.project, by_ref=args.by_ref)

        details = {
            "ref": task.get("ref"),
            "id": task.get("id"),
            "subject": task.get("subject"),
            "story": f"#{(task.get('user_story_extra_info') or {}).get('ref')}" if (task.get("user_story_extra_info") or {}).get("ref") else (f"#{task.get('user_story')}" if task.get("user_story") else "-"),
            "status": (task.get("status_extra_info") or {}).get("name") or task.get("status"),
            "status_id": task.get("status"),
            "assigned": (task.get("assigned_to_extra_info") or {}).get("full_name_display") if task.get("assigned_to_extra_info") else (task.get("assigned_to") or "-"),
            "version": task.get("version"),
            "description": task.get("description") or "-",
        }
        fields = parse_fields_arg(getattr(args, "fields", None))
        if fields:
            details = {k: v for k, v in details.items() if k in fields}

        if args.full or args.json:
            print(json.dumps(task if args.full else details, indent=2))
        else:
            print(encode_toon(None, details))

    elif action == "create":
        project_id = client.resolve_project_id(args.project)
        if not args.subject:
            raise ValueError("Subject is required. Pass --subject 'Task title'")

        payload = {
            "project": project_id,
            "subject": args.subject,
            "description": args.desc or "",
        }
        if args.story:
            payload["user_story"] = args.story
        if args.status:
            payload["status"] = args.status
        if args.milestone:
            payload["milestone"] = args.milestone
        if args.assigned:
            payload["assigned_to"] = args.assigned

        created = client.request("POST", "tasks", data=payload)
        res = {
            "created": "task",
            "ref": created.get("ref"),
            "id": created.get("id"),
            "subject": created.get("subject"),
            "version": created.get("version"),
        }
        if args.json:
            print(json.dumps(created if args.full else res, indent=2))
        else:
            print(encode_toon(None, res))

    elif action == "update":
        target = args.id
        current = client.request("GET", f"tasks/{target}")
        version = current.get("version")

        payload = {"version": version}
        if args.data:
            payload.update(json.loads(args.data))
        if args.subject:
            payload["subject"] = args.subject
        if args.status:
            payload["status"] = args.status
        if args.assigned:
            payload["assigned_to"] = args.assigned
        if args.desc:
            payload["description"] = args.desc
        if args.comment:
            payload["comment"] = args.comment

        updated = client.request("PATCH", f"tasks/{target}", data=payload)
        res = {
            "updated": "task",
            "ref": updated.get("ref"),
            "version": updated.get("version"),
        }
        if args.json:
            print(json.dumps(updated if args.full else res, indent=2))
        else:
            print(encode_toon(None, res))

    elif action == "delete":
        target = args.id
        client.request("DELETE", f"tasks/{target}")
        res = {"deleted": "task", "id": target}
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print(encode_toon(None, res))


def cmd_epics(client: TaigaClient, args: argparse.Namespace):
    action = args.action
    if action == "list":
        project_id = client.resolve_project_id(args.project)
        epics = client.request("GET", "epics", params={"project": project_id})
        if args.limit and len(epics) > args.limit:
            epics = epics[: args.limit]

        compact = prepare_compact_epics(epics)
        fields = parse_fields_arg(getattr(args, "fields", None)) or ["ref", "id", "status", "color", "subject", "version"]

        if args.full or args.json:
            print(json.dumps(compact if args.json else epics, indent=2))
        else:
            print(encode_toon("epics", compact, fields=fields))

    elif action == "get":
        target = str(args.target).lstrip("#")
        epic = client.request("GET", f"epics/{target}")
        details = {
            "ref": epic.get("ref"),
            "id": epic.get("id"),
            "subject": epic.get("subject"),
            "status": (epic.get("status_extra_info") or {}).get("name") or epic.get("status"),
            "color": epic.get("color") or "-",
            "version": epic.get("version"),
            "description": epic.get("description") or "-",
        }
        fields = parse_fields_arg(getattr(args, "fields", None))
        if fields:
            details = {k: v for k, v in details.items() if k in fields}

        if args.full or args.json:
            print(json.dumps(epic if args.full else details, indent=2))
        else:
            print(encode_toon(None, details))

    elif action == "create":
        project_id = client.resolve_project_id(args.project)
        if not args.subject:
            raise ValueError("Subject is required. Pass --subject 'Epic title'")

        payload = {
            "project": project_id,
            "subject": args.subject,
            "description": args.desc or "",
        }
        if args.color:
            payload["color"] = args.color
        created = client.request("POST", "epics", data=payload)
        res = {
            "created": "epic",
            "ref": created.get("ref"),
            "id": created.get("id"),
            "subject": created.get("subject"),
            "version": created.get("version"),
        }
        if args.json:
            print(json.dumps(created if args.full else res, indent=2))
        else:
            print(encode_toon(None, res))

    elif action == "update":
        target = args.id
        current = client.request("GET", f"epics/{target}")
        payload = {"version": current.get("version")}
        if args.data:
            payload.update(json.loads(args.data))
        if args.subject:
            payload["subject"] = args.subject
        if args.color:
            payload["color"] = args.color
        if args.comment:
            payload["comment"] = args.comment

        updated = client.request("PATCH", f"epics/{target}", data=payload)
        res = {
            "updated": "epic",
            "ref": updated.get("ref"),
            "version": updated.get("version"),
        }
        if args.json:
            print(json.dumps(updated if args.full else res, indent=2))
        else:
            print(encode_toon(None, res))

    elif action == "delete":
        target = args.id
        client.request("DELETE", f"epics/{target}")
        res = {"deleted": "epic", "id": target}
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print(encode_toon(None, res))


def cmd_api(client: TaigaClient, args: argparse.Namespace):
    method = args.method.upper()
    endpoint = normalize_endpoint(args.endpoint)

    params = {}
    if args.params:
        for p in args.params:
            if "=" in p:
                k, v = p.split("=", 1)
                params[k] = v

    data = None
    if args.data:
        data = json.loads(args.data)

    res = client.request(method, endpoint, params=params if params else None, data=data)
    print(json.dumps(res, indent=2))


def build_parser() -> argparse.ArgumentParser:
    common_opts = argparse.ArgumentParser(add_help=False)
    common_opts.add_argument("--url", default=argparse.SUPPRESS, help="Taiga API base URL (env: TAIGA_API_URL)")
    common_opts.add_argument("--username", default=argparse.SUPPRESS, help="Taiga username (env: TAIGA_USERNAME)")
    common_opts.add_argument("--password", default=argparse.SUPPRESS, help="Taiga password (discouraged on CLI, prefer TAIGA_PASSWORD or interactive prompt)")
    common_opts.add_argument("--token", default=argparse.SUPPRESS, help="Taiga auth token (env: TAIGA_AUTH_TOKEN)")
    common_opts.add_argument("--project", "-p", default=argparse.SUPPRESS, help="Target project ID or slug (env: TAIGA_PROJECT_ID)")
    common_opts.add_argument("--insecure", action="store_true", help="Allow unencrypted HTTP connection to remote host (env: TAIGA_INSECURE)")

    parser = argparse.ArgumentParser(
        prog="taiga",
        description="Taiga.io Universal CLI & REST API Client. Unofficial community project, not affiliated with or endorsed by Kaleidos Open Source SL or Taiga Agile LLC.",
        parents=[common_opts],
    )
    parser.add_argument("--version", action="version", version=f"taiga-cli {__version__}")

    subparsers = parser.add_subparsers(dest="command", help="Command category")

    p_login = subparsers.add_parser("login", parents=[common_opts], help="Authenticate and cache session token")
    p_login.add_argument("--save", action="store_true", help="Save URL and username to ~/.config/taiga/config.json")

    p_whoami = subparsers.add_parser("whoami", parents=[common_opts], help="Show currently authenticated user")
    p_whoami.add_argument("--json", action="store_true", help="Output as JSON")

    p_conf = subparsers.add_parser("config", parents=[common_opts], help="Get project configurations (types, severities, statuses)")
    p_conf.add_argument("project", nargs="?", default=argparse.SUPPRESS, help="Project ID or slug (optional if -p or TAIGA_PROJECT_ID set)")
    p_conf.add_argument("--json", action="store_true", help="Output as JSON")

    p_proj = subparsers.add_parser("projects", parents=[common_opts], help="Manage projects")
    p_proj.add_argument("action", choices=["list", "get"], help="Project action")
    p_proj.add_argument("target", nargs="?", help="Project ID or slug for 'get'")
    p_proj.add_argument("--all", action="store_true", help="List all public projects across server (may be slow/504)")
    p_proj.add_argument("--member", type=int, help="Filter projects by member user ID")
    p_proj.add_argument("--fields", help="Comma-separated fields to display in output")
    p_proj.add_argument("--json", action="store_true", help="Output as JSON")

    p_iss = subparsers.add_parser("issues", parents=[common_opts], help="Manage issues")
    p_iss.add_argument("action", choices=["list", "get", "create", "update", "delete"])
    p_iss.add_argument("target", nargs="?", help="Issue ID or #ref for 'get'")
    p_iss.add_argument("--id", type=int, help="Issue ID for update/delete")
    p_iss.add_argument("--subject", "-s", help="Issue subject/title")
    p_iss.add_argument("--desc", "-d", help="Issue description")
    p_iss.add_argument("--type", type=int, help="Type ID")
    p_iss.add_argument("--status", type=int, help="Status ID")
    p_iss.add_argument("--severity", type=int, help="Severity ID")
    p_iss.add_argument("--priority", type=int, help="Priority ID")
    p_iss.add_argument("--assigned", type=int, help="Assigned user ID")
    p_iss.add_argument("--tags", help="Comma-separated tags")
    p_iss.add_argument("--comment", help="Comment note when updating")
    p_iss.add_argument("--data", help="Raw JSON payload for update")
    p_iss.add_argument("--by-ref", action="store_true", help="Look up target by #ref explicitly")
    p_iss.add_argument("--limit", type=int, default=30, help="Max results for list")
    p_iss.add_argument("--fields", help="Comma-separated fields to display in output")
    p_iss.add_argument("--json", action="store_true", help="Compact JSON output")
    p_iss.add_argument("--full", action="store_true", help="Raw full Taiga payload")

    p_us = subparsers.add_parser("stories", parents=[common_opts], help="Manage user stories")
    p_us.add_argument("action", choices=["list", "get", "create", "update", "delete"])
    p_us.add_argument("target", nargs="?", help="Story ID or #ref for 'get'")
    p_us.add_argument("--id", type=int, help="Story ID for update/delete")
    p_us.add_argument("--subject", "-s", help="Story subject/title")
    p_us.add_argument("--desc", "-d", help="Story description")
    p_us.add_argument("--status", type=int, help="Status ID")
    p_us.add_argument("--milestone", type=int, help="Milestone/Sprint ID")
    p_us.add_argument("--epic", type=int, help="Epic ID")
    p_us.add_argument("--assigned", type=int, help="Assigned user ID")
    p_us.add_argument("--tags", help="Comma-separated tags")
    p_us.add_argument("--comment", help="Comment note when updating")
    p_us.add_argument("--data", help="Raw JSON payload for update")
    p_us.add_argument("--by-ref", action="store_true", help="Look up target by #ref explicitly")
    p_us.add_argument("--limit", type=int, default=30, help="Max results for list")
    p_us.add_argument("--fields", help="Comma-separated fields to display in output")
    p_us.add_argument("--json", action="store_true", help="Compact JSON output")
    p_us.add_argument("--full", action="store_true", help="Raw full Taiga payload")

    p_tsk = subparsers.add_parser("tasks", parents=[common_opts], help="Manage tasks")
    p_tsk.add_argument("action", choices=["list", "get", "create", "update", "delete"])
    p_tsk.add_argument("target", nargs="?", help="Task ID or #ref for 'get'")
    p_tsk.add_argument("--id", type=int, help="Task ID for update/delete")
    p_tsk.add_argument("--subject", "-s", help="Task subject/title")
    p_tsk.add_argument("--desc", "-d", help="Task description")
    p_tsk.add_argument("--story", type=int, help="Parent user story ID")
    p_tsk.add_argument("--milestone", type=int, help="Milestone ID")
    p_tsk.add_argument("--status", type=int, help="Status ID")
    p_tsk.add_argument("--assigned", type=int, help="Assigned user ID")
    p_tsk.add_argument("--comment", help="Comment note when updating")
    p_tsk.add_argument("--data", help="Raw JSON payload for update")
    p_tsk.add_argument("--by-ref", action="store_true", help="Look up target by #ref explicitly")
    p_tsk.add_argument("--limit", type=int, default=30, help="Max results for list")
    p_tsk.add_argument("--fields", help="Comma-separated fields to display in output")
    p_tsk.add_argument("--json", action="store_true", help="Compact JSON output")
    p_tsk.add_argument("--full", action="store_true", help="Raw full Taiga payload")

    p_epc = subparsers.add_parser("epics", parents=[common_opts], help="Manage epics")
    p_epc.add_argument("action", choices=["list", "get", "create", "update", "delete"])
    p_epc.add_argument("target", nargs="?", help="Epic ID or #ref for 'get'")
    p_epc.add_argument("--id", type=int, help="Epic ID for update/delete")
    p_epc.add_argument("--subject", "-s", help="Epic subject/title")
    p_epc.add_argument("--desc", "-d", help="Epic description")
    p_epc.add_argument("--color", help="Epic hex color (#E4405F)")
    p_epc.add_argument("--comment", help="Comment note when updating")
    p_epc.add_argument("--data", help="Raw JSON payload for update")
    p_epc.add_argument("--limit", type=int, default=30, help="Max results for list")
    p_epc.add_argument("--fields", help="Comma-separated fields to display in output")
    p_epc.add_argument("--json", action="store_true", help="Compact JSON output")
    p_epc.add_argument("--full", action="store_true", help="Raw full Taiga payload")

    p_api = subparsers.add_parser("api", parents=[common_opts], help="Direct Full REST API Passthrough (GET, POST, PATCH, DELETE)")
    p_api.add_argument("method", choices=["GET", "POST", "PATCH", "PUT", "DELETE", "get", "post", "patch", "put", "delete"])
    p_api.add_argument("endpoint", help="API path (e.g. 'wiki-pages', 'memberships', 'milestones')")
    p_api.add_argument("--data", help="Request body JSON string")
    p_api.add_argument("--params", nargs="*", help="Query parameters in KEY=VALUE format")

    return parser


def main():
    parser = build_parser()
    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)

    args = parser.parse_args()
    for attr in ("url", "username", "password", "token", "project", "fields", "insecure"):
        if not hasattr(args, attr):
            setattr(args, attr, None)

    try:
        client = TaigaClient(
            base_url=args.url,
            username=args.username,
            password=args.password,
            token=args.token,
            default_project=args.project,
            allow_insecure=getattr(args, "insecure", False),
        )

        if args.command == "login":
            cmd_login(client, args)
        elif args.command == "whoami":
            cmd_whoami(client, args)
        elif args.command == "config":
            cmd_config(client, args)
        elif args.command == "projects":
            cmd_projects(client, args)
        elif args.command == "issues":
            cmd_issues(client, args)
        elif args.command == "stories":
            cmd_stories(client, args)
        elif args.command == "tasks":
            cmd_tasks(client, args)
        elif args.command == "epics":
            cmd_epics(client, args)
        elif args.command == "api":
            cmd_api(client, args)
        else:
            parser.print_help()
            sys.exit(1)
    except TaigaAPIError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
