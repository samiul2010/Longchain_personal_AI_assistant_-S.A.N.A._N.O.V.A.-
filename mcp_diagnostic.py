"""
MCP GitHub Connection Diagnostic Script
=========================================
Run this directly (e.g. `python mcp_diagnostic.py`) in the SAME environment/container
as your HF Space (or add its content near the top of your app.py temporarily and
redeploy). It uses `logging` with a stdout StreamHandler + explicit flush so output
shows up in Hugging Face Space container logs, which sometimes swallow bare `print()`
calls when the main process is a Gradio/uvicorn server.

It checks, in order:
  1. Environment variables (PATH, HOME, GITHUB_PAT presence/length)
  2. Whether `node` / `npx` binaries are actually found on PATH
  3. Whether `npx -y @modelcontextprotocol/server-github` can be spawned directly
     as a raw subprocess (bypassing crewai/MCP entirely) and what it prints
  4. Whether crewai's MCPServerStdio can list tools, with full exception capture
  5. A summary verdict telling you exactly which layer is failing
"""

import os
import sys
import shutil
import subprocess
import logging
import traceback

# ---------------------------------------------------------------------------
# Logger setup — explicit stdout handler + immediate flush, so it shows up
# reliably in HF Space logs even inside a Gradio app process.
# ---------------------------------------------------------------------------
logger = logging.getLogger("mcp_diagnostic")
logger.setLevel(logging.DEBUG)
_handler = logging.StreamHandler(stream=sys.stdout)
_handler.setFormatter(logging.Formatter("[MCP-DIAG] %(message)s"))
logger.addHandler(_handler)
logger.propagate = False


def log(msg):
    logger.info(msg)
    sys.stdout.flush()


def section(title):
    log("")
    log("=" * 70)
    log(title)
    log("=" * 70)


# ---------------------------------------------------------------------------
# 1. Environment check
# ---------------------------------------------------------------------------
section("STEP 1: Environment Variables")

_GITHUB_PAT = os.getenv("GITHUB_PAT")
log(f"GITHUB_PAT present: {bool(_GITHUB_PAT)}")
log(f"GITHUB_PAT length:  {len(_GITHUB_PAT) if _GITHUB_PAT else 0}")
if _GITHUB_PAT:
    log(f"GITHUB_PAT prefix:  {_GITHUB_PAT[:7]}... (should look like 'ghp_' or 'github_pat_')")

log(f"PATH: {os.environ.get('PATH')}")
log(f"HOME: {os.environ.get('HOME')}")

# ---------------------------------------------------------------------------
# 2. Binary discovery
# ---------------------------------------------------------------------------
section("STEP 2: Binary Discovery (node / npx)")

node_path = shutil.which("node")
npx_path = shutil.which("npx")
log(f"node found at: {node_path}")
log(f"npx  found at: {npx_path}")

if not node_path or not npx_path:
    log("!!! node or npx not found on PATH. If this is the case, npx-based MCP")
    log("!!! servers can NEVER work in this container, regardless of Python code.")
    log("!!! Check your Dockerfile installs nodejs and that PATH includes it")
    log("!!! for the user account actually running the Python process.")

# ---------------------------------------------------------------------------
# 3. Raw subprocess spawn test (bypasses crewai and MCP client entirely)
# ---------------------------------------------------------------------------
section("STEP 3: Raw subprocess spawn of the MCP server")

if npx_path:
    try:
        env = {**os.environ, "GITHUB_PERSONAL_ACCESS_TOKEN": _GITHUB_PAT or ""}
        log("Spawning: npx -y @modelcontextprotocol/server-github")
        proc = subprocess.Popen(
            ["npx", "-y", "@modelcontextprotocol/server-github"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True,
        )
        # MCP servers speak JSON-RPC over stdio and expect an initialize
        # handshake. We just wait briefly to see if the process survives
        # startup or crashes immediately (e.g. missing token, network block).
        try:
            out, err = proc.communicate(timeout=5)
            log(f"Process exited early with code {proc.returncode}")
            log(f"STDOUT: {out[:2000]}")
            log(f"STDERR: {err[:2000]}")
        except subprocess.TimeoutExpired:
            log("Process is still running after 5s (this is actually a GOOD sign —")
            log("MCP stdio servers stay alive waiting for JSON-RPC input).")
            proc.kill()
            out, err = proc.communicate()
            if err:
                log(f"STDERR during startup (first 2000 chars): {err[:2000]}")
    except FileNotFoundError as e:
        log(f"!!! FileNotFoundError spawning npx: {e}")
    except Exception as e:
        log(f"!!! Unexpected error spawning npx subprocess: {repr(e)}")
        log(traceback.format_exc())
else:
    log("Skipping — npx not found (see Step 2).")

# ---------------------------------------------------------------------------
# 4. crewai MCPServerStdio tool-listing test
# ---------------------------------------------------------------------------
section("STEP 4: crewai MCPServerStdio tool listing")

try:
    import crewai
    log(f"crewai version: {getattr(crewai, '__version__', 'unknown')}")
except Exception as e:
    log(f"Could not import crewai: {repr(e)}")

try:
    from crewai.mcp import MCPServerStdio

    git_hub = MCPServerStdio(
        command="npx",
        args=["-y", "@modelcontextprotocol/server-github"],
        env={**os.environ, "GITHUB_PERSONAL_ACCESS_TOKEN": _GITHUB_PAT or ""},
        cache_tools_list=True,
        tool_filter=None,
    )
    log(f"MCPServerStdio object created: {git_hub!r}")

    # Try every plausible method name across crewai versions, since the API
    # for "give me the tool list synchronously" has changed between releases.
    tools = None
    for method_name in ("get_tools", "list_tools", "tools"):
        candidate = getattr(git_hub, method_name, None)
        if candidate is None:
            continue
        try:
            log(f"Trying git_hub.{method_name} ...")
            result = candidate() if callable(candidate) else candidate
            # handle async
            if hasattr(result, "__await__"):
                import asyncio
                result = asyncio.run(result)
            tools = result
            log(f"SUCCESS via {method_name}: got {len(tools) if tools else 0} tools")
            break
        except Exception as e:
            log(f"  {method_name} failed: {repr(e)}")

    if tools:
        for t in tools:
            log(f"  - TOOL: {getattr(t, 'name', t)}")
    else:
        log("!!! No tools could be retrieved through any known method.")
        log("!!! This confirms the MCP connection/tool-list step itself is failing,")
        log("!!! independent of any Agent/Crew/reasoning configuration.")

except Exception as e:
    log(f"!!! Failed to construct or query MCPServerStdio: {repr(e)}")
    log(traceback.format_exc())

# ---------------------------------------------------------------------------
# 5. Verdict
# ---------------------------------------------------------------------------
section("STEP 5: Verdict")

if not node_path or not npx_path:
    log("VERDICT: node/npx missing from PATH -> fix your Dockerfile / PATH setup.")
else:
    log("VERDICT: node/npx are present. Check Step 3 and Step 4 output above to see")
    log("whether the subprocess crashes on startup (auth/network issue) or whether")
    log("crewai's MCP client fails to retrieve tools even though the process runs")
    log("(a crewai/MCP integration bug or version mismatch).")

log("")
log("Diagnostic complete.")
