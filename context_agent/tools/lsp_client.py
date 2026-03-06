from __future__ import annotations

import json
import os
import select
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse


@dataclass(slots=True)
class LSPSymbolMatch:
    path: str
    symbol_name: str
    kind: str = ""


@dataclass(slots=True)
class LSPBackend:
    name: str
    command: list[str]


class LSPClient:
    """最小可用的 LSP workspace symbol 客户端。"""

    def __init__(self, warmup_seconds: float = 1.0, response_timeout_seconds: float = 5.0) -> None:
        self.warmup_seconds = warmup_seconds
        self.response_timeout_seconds = response_timeout_seconds

    def find_symbols(
        self,
        workspace_root: str | Path,
        symbols: list[str],
        limit: int = 8,
    ) -> list[LSPSymbolMatch]:
        root = Path(workspace_root).resolve()
        filtered_symbols = [symbol for symbol in symbols if symbol]
        if not filtered_symbols or limit <= 0:
            return []

        results: list[LSPSymbolMatch] = []
        seen: set[tuple[str, str, str]] = set()
        for backend in self._resolve_backends(root):
            remaining = limit - len(results)
            if remaining <= 0:
                break
            matches = self._find_symbols_from_backend(root, filtered_symbols, backend, remaining)
            for match in matches:
                key = (match.path, match.symbol_name, match.kind)
                if key in seen:
                    continue
                seen.add(key)
                results.append(match)
                if len(results) >= limit:
                    return results
        return results

    def _resolve_backends(self, workspace_root: Path) -> list[LSPBackend]:
        backends: list[LSPBackend] = []

        python_command = self._resolve_command(
            workspace_root,
            executable_name="basedpyright-langserver",
            fallback_paths=[
                Path(sys.executable).with_name("basedpyright-langserver"),
                workspace_root / ".venv" / "bin" / "basedpyright-langserver",
            ],
        )
        if python_command is not None:
            backends.append(LSPBackend(name="python", command=python_command))

        typescript_command = self._resolve_command(
            workspace_root,
            executable_name="typescript-language-server",
            fallback_paths=[
                workspace_root / "node_modules" / ".bin" / "typescript-language-server",
                Path(sys.executable).with_name("typescript-language-server"),
                workspace_root / ".venv" / "bin" / "typescript-language-server",
            ],
        )
        if typescript_command is not None:
            backends.append(LSPBackend(name="typescript", command=typescript_command))

        return backends

    def _resolve_command(
        self,
        workspace_root: Path,
        executable_name: str,
        fallback_paths: list[Path],
    ) -> list[str] | None:
        _ = workspace_root
        executable = shutil.which(executable_name)
        if executable:
            return [executable, "--stdio"]

        for candidate in fallback_paths:
            if candidate.exists():
                return [str(candidate), "--stdio"]
        return None

    def _find_symbols_from_backend(
        self,
        workspace_root: Path,
        symbols: list[str],
        backend: LSPBackend,
        limit: int,
    ) -> list[LSPSymbolMatch]:
        try:
            with subprocess.Popen(
                backend.command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=False,
            ) as process:
                if process.stdin is None or process.stdout is None:
                    return []
                if not self._initialize(process, workspace_root):
                    return []
                time.sleep(self.warmup_seconds)

                results: list[LSPSymbolMatch] = []
                request_id = 10
                for symbol in symbols:
                    matches = self._query_workspace_symbol(process, workspace_root, symbol, request_id)
                    request_id += 1
                    for match in matches:
                        results.append(match)
                        if len(results) >= limit:
                            return results
                return results
        except OSError:
            return []

    def _initialize(self, process: subprocess.Popen[bytes], workspace_root: Path) -> bool:
        workspace_uri = workspace_root.as_uri()
        self._send_message(
            process,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "processId": None,
                    "rootUri": workspace_uri,
                    "capabilities": {},
                    "workspaceFolders": [{"uri": workspace_uri, "name": workspace_root.name}],
                },
            },
        )
        response = self._read_until_response(process, 1)
        if response is None:
            return False
        self._send_message(process, {"jsonrpc": "2.0", "method": "initialized", "params": {}})
        return True

    def _query_workspace_symbol(
        self,
        process: subprocess.Popen[bytes],
        workspace_root: Path,
        symbol: str,
        request_id: int,
    ) -> list[LSPSymbolMatch]:
        self._send_message(
            process,
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": "workspace/symbol",
                "params": {"query": symbol},
            },
        )
        response = self._read_until_response(process, request_id)
        if response is None:
            return []

        raw_items = response.get("result")
        if not isinstance(raw_items, list):
            return []

        results: list[LSPSymbolMatch] = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            location = item.get("location")
            if not isinstance(location, dict):
                continue
            path = self._uri_to_relative_path(location.get("uri"), workspace_root)
            if path is None:
                continue
            results.append(
                LSPSymbolMatch(
                    path=path,
                    symbol_name=str(item.get("name") or symbol),
                    kind=str(item.get("kind") or ""),
                )
            )
        return results

    def _send_message(self, process: subprocess.Popen[bytes], message: dict[str, object]) -> None:
        if process.stdin is None:
            return
        payload = json.dumps(message).encode("utf-8")
        packet = f"Content-Length: {len(payload)}\r\n\r\n".encode("utf-8") + payload
        process.stdin.write(packet)
        process.stdin.flush()

    def _read_until_response(
        self,
        process: subprocess.Popen[bytes],
        expected_id: int,
    ) -> dict[str, object] | None:
        deadline = time.monotonic() + self.response_timeout_seconds
        while time.monotonic() < deadline:
            message = self._read_message(process, deadline)
            if message is None:
                return None
            if message.get("id") == expected_id:
                return message
        return None

    def _read_message(
        self,
        process: subprocess.Popen[bytes],
        deadline: float,
    ) -> dict[str, object] | None:
        if process.stdout is None:
            return None
        file_descriptor = process.stdout.fileno()

        header = bytearray()
        while b"\r\n\r\n" not in header:
            if not self._wait_for_bytes(file_descriptor, deadline):
                return None
            chunk = os.read(file_descriptor, 1)
            if not chunk:
                return None
            header.extend(chunk)

        header_bytes, _, body_prefix = bytes(header).partition(b"\r\n\r\n")
        content_length = 0
        for line in header_bytes.decode("utf-8").split("\r\n"):
            if line.lower().startswith("content-length:"):
                content_length = int(line.split(":", 1)[1].strip())
                break
        if content_length <= 0:
            return None

        body = bytearray(body_prefix)
        while len(body) < content_length:
            if not self._wait_for_bytes(file_descriptor, deadline):
                return None
            chunk = os.read(file_descriptor, content_length - len(body))
            if not chunk:
                return None
            body.extend(chunk)

        return json.loads(bytes(body[:content_length]).decode("utf-8"))

    def _wait_for_bytes(self, file_descriptor: int, deadline: float) -> bool:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        readable, _, _ = select.select([file_descriptor], [], [], remaining)
        return bool(readable)

    def _uri_to_relative_path(self, uri: object, workspace_root: Path) -> str | None:
        if not isinstance(uri, str):
            return None
        parsed = urlparse(uri)
        if parsed.scheme != "file":
            return None
        path = Path(unquote(parsed.path)).resolve()
        try:
            return str(path.relative_to(workspace_root))
        except ValueError:
            return None