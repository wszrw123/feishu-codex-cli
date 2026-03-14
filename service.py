import json
import logging
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
RUNTIME_DIR = ROOT / ".runtime"
RUNTIME_DIR.mkdir(parents=True, exist_ok=True)

CONFIG_PATH = ROOT / ".feishu-codex-cli.config.local.json"
LOG_PATH = RUNTIME_DIR / "service.log"
CONVERSATION_LOG_PATH = RUNTIME_DIR / "conversation.jsonl"
CHAT_CONTEXT_PATH = RUNTIME_DIR / "chat_context.json"
SESSION_STORE_PATH = RUNTIME_DIR / "chat_session.json"
CODEX_HOME_PATH = RUNTIME_DIR / "codex-home"


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_json_file(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def _write_json_file(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        raise RuntimeError(f"missing config file: {CONFIG_PATH}")
    payload = _read_json_file(CONFIG_PATH, {})
    if not isinstance(payload, dict):
        raise RuntimeError(f"invalid config json: {CONFIG_PATH}")
    return payload


CONFIG = _load_config()

FEISHU_APP_ID = str(CONFIG.get("feishuAppId", "") or "").strip()
FEISHU_APP_SECRET = str(CONFIG.get("feishuAppSecret", "") or "").strip()
FEISHU_CHAT_ID = str(CONFIG.get("feishuChatId", "") or "").strip()
FEISHU_API_BASE = str(CONFIG.get("feishuApiBase", "https://open.feishu.cn/open-apis") or "").strip().rstrip("/")
CODEX_CLI_PATH = str(CONFIG.get("codexCliPath", "") or "").strip() or "codex"
CODEX_WORKDIR = str(CONFIG.get("codexWorkdir", "") or "").strip() or str(ROOT)
CODEX_SANDBOX_MODE = str(CONFIG.get("codexSandboxMode", "danger-full-access") or "").strip()
CODEX_TIMEOUT_SECONDS = int(CONFIG.get("codexTimeoutSeconds", 900) or 900)
CODEX_SKIP_GIT_REPO_CHECK = bool(CONFIG.get("codexSkipGitRepoCheck", True))
OPENAI_BASE_URL = str(CONFIG.get("openaiBaseUrl", "") or "").strip()
OPENAI_API_KEY = str(CONFIG.get("openaiApiKey", "") or "").strip()
CHAT_SUMMARY_MAX_CHARS = int(CONFIG.get("chatSummaryMaxChars", 2500) or 2500)
CHAT_SUMMARY_MAX_EVENTS = int(CONFIG.get("chatSummaryMaxEvents", 10) or 10)
CHAT_SESSION_MAX_INPUT_TOKENS = int(CONFIG.get("chatSessionMaxInputTokens", 150000) or 150000)
CHAT_SESSION_MAX_ELAPSED_SECONDS = int(CONFIG.get("chatSessionMaxElapsedSeconds", 120) or 120)
CHAT_SESSION_IDLE_SUMMARY_SECONDS = int(CONFIG.get("chatSessionIdleSummarySeconds", 900) or 900)
CHAT_SESSION_PREEMPTIVE_ROTATE_RATIO = float(CONFIG.get("chatSessionPreemptiveRotateRatio", 0.8) or 0.8)
POLL_INTERVAL_SECONDS = float(CONFIG.get("pollIntervalSeconds", 2.5) or 2.5)
HISTORY_PAGE_SIZE = int(CONFIG.get("historyPageSize", 20) or 20)
REPLY_MAX_CHARS = int(CONFIG.get("replyMaxChars", 4000) or 4000)
STARTUP_MESSAGE = str(CONFIG.get("startupMessage", "feishu-codex-cli 已上线。") or "").strip()

TOKEN_CACHE: dict[str, Any] = {"token": "", "expires_at": 0.0}


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger("feishu_codex_cli")


DIAGNOSTIC_HINTS = (
    "日志",
    "log",
    "排查",
    "检查",
    "诊断",
    "trace",
    "timeout",
    "超时",
    "报错",
    "错误",
    "失败",
    "status",
    "状态",
    "gateway",
    "allowlist",
    "whitelist",
    "heartbeat",
    "openclaw",
)


def _is_diagnostic_request(text: str) -> bool:
    lowered = (text or "").strip().lower()
    return bool(lowered) and any(item in lowered for item in DIAGNOSTIC_HINTS)


def _clip_text(text: str, limit: int) -> str:
    value = (text or "").strip()
    if len(value) <= limit:
        return value
    return value[:limit] + "...(truncated)"


def _parse_json_object(raw: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _feishu_parse_api_response(raw: str) -> dict[str, Any]:
    parsed = _parse_json_object(raw)
    code_raw = parsed.get("code", parsed.get("statusCode", parsed.get("StatusCode", None)))
    code = -1
    if code_raw is not None and str(code_raw).strip() != "":
        try:
            code = int(code_raw)
        except Exception:
            code = -1
    elif parsed.get("tenant_access_token") or isinstance(parsed.get("data"), dict):
        code = 0
    if code != 0:
        raise RuntimeError(f"feishu api error code={code} msg={str(parsed.get('msg', raw))[:300]}")
    return parsed


def _feishu_api_request(
    method: str,
    path: str,
    *,
    bearer_token: str = "",
    params: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
    timeout: float = 12.0,
) -> dict[str, Any]:
    query = "?" + urllib.parse.urlencode(params) if params else ""
    endpoint = f"{FEISHU_API_BASE}{path}{query}"
    payload = None
    if body is not None:
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(endpoint, data=payload, method=method.upper())
    req.add_header("Content-Type", "application/json; charset=utf-8")
    if bearer_token:
        req.add_header("Authorization", f"Bearer {bearer_token}")
    with urllib.request.urlopen(req, timeout=timeout) as response:
        raw = response.read().decode("utf-8", errors="ignore")
    return _feishu_parse_api_response(raw)


def _feishu_tenant_access_token() -> str:
    now = time.time()
    cached = str(TOKEN_CACHE.get("token", "") or "").strip()
    expires_at = float(TOKEN_CACHE.get("expires_at", 0.0) or 0.0)
    if cached and expires_at - now > 30:
        return cached
    parsed = _feishu_api_request(
        "POST",
        "/auth/v3/tenant_access_token/internal",
        body={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET},
        timeout=10.0,
    )
    token = str(parsed.get("tenant_access_token", "") or "").strip()
    expire = int(parsed.get("expire", 0) or 0)
    if not token:
        raise RuntimeError("feishu tenant access token missing")
    TOKEN_CACHE["token"] = token
    TOKEN_CACHE["expires_at"] = now + max(60, expire)
    return token


def _feishu_send_text(chat_id: str, text: str) -> None:
    token = _feishu_tenant_access_token()
    _feishu_api_request(
        "POST",
        "/im/v1/messages",
        bearer_token=token,
        params={"receive_id_type": "chat_id"},
        body={
            "receive_id": chat_id,
            "msg_type": "text",
            "content": json.dumps({"text": _clip_text(text, REPLY_MAX_CHARS)}, ensure_ascii=False),
        },
        timeout=10.0,
    )


def _feishu_list_chat_messages(chat_id: str) -> list[dict[str, Any]]:
    token = _feishu_tenant_access_token()
    parsed = _feishu_api_request(
        "GET",
        "/im/v1/messages",
        bearer_token=token,
        params={
            "container_id_type": "chat",
            "container_id": chat_id,
            "sort_type": "ByCreateTimeDesc",
            "page_size": str(HISTORY_PAGE_SIZE),
        },
        timeout=10.0,
    )
    data = parsed.get("data", {})
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        return [item for item in data["items"] if isinstance(item, dict)]
    return []


def _feishu_message_from_bot(message: dict[str, Any]) -> bool:
    sender = message.get("sender", {})
    if not isinstance(sender, dict):
        return False
    sender_type = str(sender.get("sender_type", "") or "").strip().lower()
    if sender_type == "app":
        return True
    sender_id = sender.get("sender_id", {})
    if isinstance(sender_id, dict) and str(sender_id.get("app_id", "") or "").strip() == FEISHU_APP_ID:
        return True
    return False


def _feishu_message_id(message: dict[str, Any]) -> str:
    return str(message.get("message_id", "") or "").strip()


def _feishu_message_time_ms(message: dict[str, Any]) -> int:
    try:
        return int(str(message.get("create_time", "") or "").strip())
    except Exception:
        return 0


def _feishu_message_text(message: dict[str, Any]) -> str:
    msg_type = str(message.get("msg_type", "") or "").strip().lower()
    content_obj = _parse_json_object(str(message.get("body", {}).get("content", "") or ""))
    if msg_type == "text":
        return str(content_obj.get("text", "") or "").strip()
    return ""


def _session_store() -> dict[str, Any]:
    payload = _read_json_file(SESSION_STORE_PATH, {})
    return payload if isinstance(payload, dict) else {}


def _context_store() -> dict[str, Any]:
    payload = _read_json_file(CHAT_CONTEXT_PATH, {})
    return payload if isinstance(payload, dict) else {}


def _append_conversation_event(trace_id: str, role: str, text: str, status: str) -> None:
    payload = {
        "at": _utc_now_text(),
        "chat_id": FEISHU_CHAT_ID,
        "trace_id": trace_id,
        "role": role,
        "status": status,
        "text": _clip_text(text, 4000),
    }
    with CONVERSATION_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _read_recent_conversation_events(limit: int) -> list[dict[str, Any]]:
    if not CONVERSATION_LOG_PATH.exists():
        return []
    items: list[dict[str, Any]] = []
    with CONVERSATION_LOG_PATH.open("r", encoding="utf-8") as handle:
        lines = handle.readlines()
    for raw in reversed(lines):
        line = raw.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except Exception:
            continue
        if str(event.get("chat_id", "") or "") != FEISHU_CHAT_ID:
            continue
        items.append(event)
        if len(items) >= limit:
            break
    items.reverse()
    return items


def _build_summary(reason: str) -> str:
    events = _read_recent_conversation_events(CHAT_SUMMARY_MAX_EVENTS)
    if not events:
        return ""
    lines = [
        "以下是该聊天的轻量摘要，优先保留已确认事实、未完成事项和最近失败信息。",
        f"触发原因: {_clip_text(reason, 240)}",
    ]
    for event in events[-CHAT_SUMMARY_MAX_EVENTS:]:
        role = str(event.get("role", "") or "")
        text = _clip_text(str(event.get("text", "") or "").replace("\n", " | "), 320 if role == "user" else 480)
        if not text:
            continue
        label = "用户" if role == "user" else "助手"
        lines.append(f"- {label}: {text}")
    return _clip_text("\n".join(lines), CHAT_SUMMARY_MAX_CHARS)


def _current_context() -> dict[str, Any]:
    payload = _context_store()
    return payload if isinstance(payload, dict) else {}


def _store_context(**updates: Any) -> dict[str, Any]:
    current = _current_context()
    current.update(updates)
    current["updated_at"] = _utc_now_text()
    _write_json_file(CHAT_CONTEXT_PATH, current)
    return current


def _stored_session_id() -> str:
    payload = _session_store()
    return str(payload.get("session_id", "") or "").strip()


def _store_session_id(session_id: str) -> None:
    _write_json_file(
        SESSION_STORE_PATH,
        {
            "session_id": session_id,
            "updated_at": _utc_now_text(),
        },
    )


def _clear_session_id() -> None:
    _write_json_file(SESSION_STORE_PATH, {"session_id": "", "updated_at": _utc_now_text()})


def _build_prompt(user_text: str, trace_id: str, summary_text: str = "") -> str:
    parts = [
        "来自 Feishu 的远程消息，请按正常用户消息处理。",
        "如果本轮是在排查/看日志，请先用最小必要读取范围收集证据，优先精确 rg 和小窗口 tail/sed，避免一次性读取大文件或整份 jsonl。",
    ]
    if summary_text:
        parts.extend([
            "以下是压缩上下文，请仅把它当成背景：",
            f"```text\n{summary_text}\n```",
        ])
    parts.append(f"[trace_id={trace_id} chat_id={FEISHU_CHAT_ID} at {_utc_now_text()}] {user_text}")
    return "\n".join(parts)


def _prepare_codex_env() -> dict[str, str] | None:
    if not OPENAI_BASE_URL and not OPENAI_API_KEY:
        return None
    env = os.environ.copy()
    CODEX_HOME_PATH.mkdir(parents=True, exist_ok=True)
    config_lines = [
        'model_provider = "openai"',
        "",
        "[model_providers.openai]",
        'name = "OpenAI"',
    ]
    if OPENAI_BASE_URL:
        config_lines.append(f"base_url = {json.dumps(OPENAI_BASE_URL)}")
    config_lines.extend([
        'env_key = "OPENAI_API_KEY"',
        'wire_api = "responses"',
        "",
        f"[projects.{json.dumps(CODEX_WORKDIR)}]",
        'trust_level = "trusted"',
    ])
    (CODEX_HOME_PATH / "config.toml").write_text("\n".join(config_lines) + "\n", encoding="utf-8")
    if OPENAI_API_KEY:
        (CODEX_HOME_PATH / "auth.json").write_text(
            json.dumps({"auth_mode": "apikey", "OPENAI_API_KEY": OPENAI_API_KEY}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    env["CODEX_HOME"] = str(CODEX_HOME_PATH)
    if OPENAI_BASE_URL:
        env["OPENAI_BASE_URL"] = OPENAI_BASE_URL
    if OPENAI_API_KEY:
        env["OPENAI_API_KEY"] = OPENAI_API_KEY
    return env


def _extract_thread_id(stdout_text: str) -> str:
    for raw in stdout_text.splitlines():
        line = raw.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except Exception:
            continue
        for key in ("thread_id", "session_id"):
            value = str(event.get(key, "") or "").strip()
            if value:
                return value
        payload = event.get("payload", {})
        if isinstance(payload, dict):
            value = str(payload.get("thread_id", "") or payload.get("session_id", "") or "").strip()
            if value:
                return value
    return ""


def _extract_usage(stdout_text: str) -> dict[str, int]:
    usage: dict[str, int] = {}
    for raw in stdout_text.splitlines():
        line = raw.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except Exception:
            continue
        if event.get("type") != "turn.completed":
            continue
        payload = event.get("usage", {})
        if not isinstance(payload, dict):
            continue
        for key in ("input_tokens", "cached_input_tokens", "output_tokens"):
            value = payload.get(key)
            if isinstance(value, int):
                usage[key] = value
    return usage


def _extract_agent_text(stdout_text: str) -> str:
    chunks: list[str] = []
    for raw in stdout_text.splitlines():
        line = raw.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except Exception:
            continue
        if event.get("type") == "event_msg":
            payload = event.get("payload", {})
            if isinstance(payload, dict) and payload.get("type") == "agent_message":
                message = str(payload.get("message", "") or "").strip()
                if message:
                    chunks.append(message)
        if event.get("type") == "response_item":
            payload = event.get("payload", {})
            if isinstance(payload, dict) and payload.get("type") == "message":
                for item in payload.get("content", []):
                    if isinstance(item, dict) and item.get("type") == "output_text":
                        text = str(item.get("text", "") or "").strip()
                        if text:
                            chunks.append(text)
    return "\n\n".join(chunks).strip()


def _run_codex(prompt: str, mode: str, session_id: str) -> tuple[int, str, dict[str, int], float, str]:
    cmd = [
        CODEX_CLI_PATH,
        "-C",
        CODEX_WORKDIR,
        "exec",
        "--sandbox",
        CODEX_SANDBOX_MODE,
    ]
    if CODEX_SKIP_GIT_REPO_CHECK:
        cmd.append("--skip-git-repo-check")
    if mode == "resume_session" and session_id:
        cmd.extend(["resume", session_id, prompt, "--json"])
    else:
        cmd.extend([prompt, "--json"])
    started = time.monotonic()
    completed = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=CODEX_TIMEOUT_SECONDS,
        check=False,
        env=_prepare_codex_env() or None,
    )
    elapsed = time.monotonic() - started
    stdout_text = completed.stdout or ""
    usage = _extract_usage(stdout_text)
    thread_id = _extract_thread_id(stdout_text)
    return completed.returncode, stdout_text + (completed.stderr or ""), usage, elapsed, thread_id


def _should_rotate(usage: dict[str, int], elapsed: float) -> bool:
    input_tokens = int(usage.get("input_tokens", 0) or 0)
    if input_tokens >= CHAT_SESSION_MAX_INPUT_TOKENS:
        return True
    return elapsed >= CHAT_SESSION_MAX_ELAPSED_SECONDS


def _should_preemptive_rotate(context: dict[str, Any]) -> bool:
    ratio = max(0.0, min(1.0, CHAT_SESSION_PREEMPTIVE_ROTATE_RATIO))
    input_tokens = int(context.get("last_input_tokens", 0) or 0)
    elapsed = float(context.get("last_elapsed_seconds", 0.0) or 0.0)
    if CHAT_SESSION_MAX_INPUT_TOKENS > 0 and input_tokens >= int(CHAT_SESSION_MAX_INPUT_TOKENS * ratio):
        return True
    return CHAT_SESSION_MAX_ELAPSED_SECONDS > 0 and elapsed >= CHAT_SESSION_MAX_ELAPSED_SECONDS * ratio


def _handle_message(text: str) -> None:
    trace_id = uuid.uuid4().hex[:8]
    logger.info("message in trace_id=%s text=%s", trace_id, _clip_text(text, 200))
    _append_conversation_event(trace_id, "user", text, "ok")

    if text.strip() in {"/status", "/relay_status"}:
        context = _current_context()
        status_text = (
            f"workdir={CODEX_WORKDIR}\n"
            f"session_id={_stored_session_id() or '-'}\n"
            f"summary_chars={len(str(context.get('summary_text', '') or ''))}\n"
            f"last_input_tokens={context.get('last_input_tokens', '-')}\n"
            f"last_elapsed_seconds={context.get('last_elapsed_seconds', '-')}"
        )
        _feishu_send_text(FEISHU_CHAT_ID, status_text)
        return

    context = _current_context()
    session_id = _stored_session_id()
    use_resume = bool(session_id) and not _is_diagnostic_request(text)
    if session_id and _should_preemptive_rotate(context):
        use_resume = False
    summary_text = ""
    if not use_resume:
        summary_reason = "diagnostic_exec_new" if _is_diagnostic_request(text) else "summary_exec_new"
        summary_text = _build_summary(summary_reason)
        if summary_text:
            _store_context(summary_text=summary_text, summary_reason=summary_reason)

    prompt = _build_prompt(text, trace_id, summary_text=summary_text)
    mode = "resume_session" if use_resume else "exec_new"
    _feishu_send_text(FEISHU_CHAT_ID, "已收到，正在处理...")

    try:
        rc, output_text, usage, elapsed, thread_id = _run_codex(prompt, mode, session_id)
    except subprocess.TimeoutExpired:
        _clear_session_id()
        _append_conversation_event(trace_id, "assistant", f"转发超时(trace_id={trace_id})", "error")
        _feishu_send_text(FEISHU_CHAT_ID, f"转发超时(trace_id={trace_id}, timeout={CODEX_TIMEOUT_SECONDS}s)")
        return
    except Exception as exc:
        _clear_session_id()
        detail = f"转发失败(trace_id={trace_id}): {str(exc)[:300]}"
        _append_conversation_event(trace_id, "assistant", detail, "error")
        _feishu_send_text(FEISHU_CHAT_ID, detail)
        return

    message_text = _extract_agent_text(output_text).strip()
    if rc != 0:
        detail = message_text or _clip_text(output_text, 600) or f"codex exit={rc}"
        _clear_session_id()
        _append_conversation_event(trace_id, "assistant", detail, "error")
        _feishu_send_text(FEISHU_CHAT_ID, f"转发失败(trace_id={trace_id}): {_clip_text(detail, REPLY_MAX_CHARS)}")
        return

    if thread_id and not _should_rotate(usage, elapsed):
        _store_session_id(thread_id)
    else:
        _clear_session_id()

    _store_context(
        last_input_tokens=int(usage.get("input_tokens", 0) or 0),
        last_cached_input_tokens=int(usage.get("cached_input_tokens", 0) or 0),
        last_output_tokens=int(usage.get("output_tokens", 0) or 0),
        last_elapsed_seconds=round(elapsed, 2),
        last_session_id=thread_id,
        last_trace_id=trace_id,
        last_activity_at=_utc_now_text(),
    )

    reply_text = message_text or "消息已处理，但未提取到文本回复。"
    _append_conversation_event(trace_id, "assistant", reply_text, "ok")
    _feishu_send_text(FEISHU_CHAT_ID, _clip_text(reply_text, REPLY_MAX_CHARS))
    logger.info(
        "codex done trace_id=%s mode=%s elapsed=%.2fs input_tokens=%s cached_input_tokens=%s output_tokens=%s",
        trace_id,
        mode,
        elapsed,
        usage.get("input_tokens", "-"),
        usage.get("cached_input_tokens", "-"),
        usage.get("output_tokens", "-"),
    )


def main() -> None:
    if not FEISHU_APP_ID or not FEISHU_APP_SECRET or not FEISHU_CHAT_ID:
        raise RuntimeError("missing feishuAppId / feishuAppSecret / feishuChatId in config")

    seen_ids: set[str] = set()
    seen_order: list[str] = []
    max_seen = 200
    last_seen_ms = int(time.time() * 1000)

    logger.info("service starting workdir=%s cli=%s base_url=%s", CODEX_WORKDIR, CODEX_CLI_PATH, OPENAI_BASE_URL or "(inherit)")
    if STARTUP_MESSAGE:
        _feishu_send_text(FEISHU_CHAT_ID, STARTUP_MESSAGE)

    while True:
        try:
            items = _feishu_list_chat_messages(FEISHU_CHAT_ID)
        except Exception as exc:
            logger.warning("feishu pull failed error=%s", str(exc)[:300])
            time.sleep(POLL_INTERVAL_SECONDS)
            continue

        for item in items:
            message_id = _feishu_message_id(item)
            created_ms = _feishu_message_time_ms(item)
            if message_id and message_id in seen_ids:
                continue
            if created_ms and created_ms <= last_seen_ms:
                continue
            if _feishu_message_from_bot(item):
                continue
            text = _feishu_message_text(item)
            if not text:
                continue

            if message_id:
                seen_ids.add(message_id)
                seen_order.append(message_id)
                if len(seen_order) > max_seen:
                    dropped = seen_order.pop(0)
                    if dropped not in seen_order:
                        seen_ids.discard(dropped)
            if created_ms > last_seen_ms:
                last_seen_ms = created_ms

            _handle_message(text.strip())

        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
