---
name: hermes-agent
description: "Configure, extend, or contribute to Hermes Agent."
version: 2.0.0
author: Hermes Agent + Teknium
license: MIT
metadata:
  hermes:
    tags: [hermes, setup, configuration, multi-agent, spawning, cli, gateway, development]
    homepage: https://github.com/NousResearch/hermes-agent
    related_skills: [claude-code, codex, opencode]
---

# Hermes Agent

Hermes Agent is an open-source AI agent framework by Nous Research that runs in your terminal, messaging platforms, and IDEs. It belongs to the same category as Claude Code (Anthropic), Codex (OpenAI), and OpenClaw — autonomous coding and task-execution agents that use tool calling to interact with your system. Hermes works with any LLM provider (OpenRouter, Anthropic, OpenAI, DeepSeek, local models, and 15+ others) and runs on Linux, macOS, and WSL.

What makes Hermes different:

- **Self-improving through skills** — Hermes learns from experience by saving reusable procedures as skills. When it solves a complex problem, discovers a workflow, or gets corrected, it can persist that knowledge as a skill document that loads into future sessions. Skills accumulate over time, making the agent better at your specific tasks and environment.
- **Persistent memory across sessions** — remembers who you are, your preferences, environment details, and lessons learned. Pluggable memory backends (built-in, Honcho, Mem0, and more) let you choose how memory works.
- **Multi-platform gateway** — the same agent runs on Telegram, Discord, Slack, WhatsApp, Signal, Matrix, Email, and 10+ other platforms with full tool access, not just chat.
- **Provider-agnostic** — swap models and providers mid-workflow without changing anything else. Credential pools rotate across multiple API keys automatically.
- **Profiles** — run multiple independent Hermes instances with isolated configs, sessions, skills, and memory.
- **Extensible** — plugins, MCP servers, custom tools, webhook triggers, cron scheduling, and the full Python ecosystem.

People use Hermes for software development, research, system administration, data analysis, content creation, home automation, and anything else that benefits from an AI agent with persistent context and full system access.

**This skill helps you work with Hermes Agent effectively** — setting it up, configuring features, spawning additional agent instances, troubleshooting issues, finding the right commands and settings, and understanding how the system works when you need to extend or contribute to it.

**Docs:** Preferred `/Volumes/WDBlack4TB/.hermes/docs/HERMES-AGENT.md`
**Docs:** Also available at https://hermes-agent.nousresearch.com/docs/

## Quick Start

```bash
# Install
curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash

# Interactive chat (default)
hermes

# Single query
hermes chat -q "What is the capital of France?"

# Setup wizard
hermes setup

# Change model/provider
hermes model

# Check health
hermes doctor
```

---

## CLI Reference

### Global Flags

```
hermes [flags] [command]

  --version, -V             Show version
  --resume, -r SESSION      Resume session by ID or title
  --continue, -c [NAME]     Resume by name, or most recent session
  --worktree, -w            Isolated git worktree mode (parallel agents)
  --skills, -s SKILL        Preload skills (comma-separate or repeat)
  --profile, -p NAME        Use a named profile
  --yolo                    Skip dangerous command approval
  --pass-session-id         Include session ID in system prompt
```

No subcommand defaults to `chat`.

### Chat

```
hermes chat [flags]
  -q, --query TEXT          Single query, non-interactive
  -m, --model MODEL         Model (e.g. anthropic/claude-sonnet-4)
  -t, --toolsets LIST       Comma-separated toolsets
  --provider PROVIDER       Force provider (openrouter, anthropic, nous, etc.)
  -v, --verbose             Verbose output
  -Q, --quiet               Suppress banner, spinner, tool previews
  --checkpoints             Enable filesystem checkpoints (/rollback)
  --source TAG              Session source tag (default: cli)
```

### Configuration

```
hermes setup [section]      Interactive wizard (model|terminal|gateway|tools|agent)
hermes model                Interactive model/provider picker
hermes config               View current config
hermes config edit          Open config.yaml in $EDITOR
hermes config set KEY VAL   Set a config value
hermes config path          Print config.yaml path
hermes config env-path      Print .env path
hermes config check         Check for missing/outdated config
hermes config migrate       Update config with new options
hermes login [--provider P] OAuth login (nous, openai-codex)
hermes logout               Clear stored auth
hermes doctor [--fix]       Check dependencies and config
hermes status [--all]       Show component status
```

### Tools & Skills

**Skill authoring lane:** for in-repo `SKILL.md` creation, validation, frontmatter, support-file layout, and generated host-skill docs, use this Hermes Agent skill as the umbrella. The former `hermes-agent-skill-authoring` package is preserved under `references/absorbed/hermes-agent-skill-authoring/` for detailed validator and external-skill-directory recipes.

```
hermes tools                Interactive tool enable/disable (curses UI)
hermes tools list           Show all tools and status
hermes tools enable NAME    Enable a toolset
hermes tools disable NAME   Disable a toolset

hermes skills list          List installed skills
hermes skills search QUERY  Search the skills hub
hermes skills install ID    Install a skill (ID can be a hub identifier OR a direct https://…/SKILL.md URL; pass --name to override when frontmatter has no name). It does NOT accept local filesystem paths; for a local SKILL.md, copy/import it into $HERMES_HOME/skills/<category>/<name>/SKILL.md or use the skill_manage tool.
hermes skills inspect ID    Preview without installing
hermes skills config        Enable/disable skills per platform
hermes skills check         Check for updates
hermes skills update        Update outdated skills
hermes skills uninstall N   Remove a hub skill
hermes skills publish PATH  Publish to registry
hermes skills browse        Browse all available skills
hermes skills tap add REPO  Add a GitHub repo as skill source
```

### MCP Servers

```
hermes mcp serve            Run Hermes as an MCP server
hermes mcp add NAME         Add an MCP server (--url or --command)
hermes mcp remove NAME      Remove an MCP server
hermes mcp list             List configured servers
hermes mcp test NAME        Test connection
hermes mcp configure NAME   Toggle tool selection

# Common add forms:
hermes mcp add SERVER --command CMD --args ARG1 ARG2
hermes mcp add SERVER --url https://example.com/mcp
hermes mcp add SERVER --url https://example.com/mcp --auth header
# For --auth header, pass JSON such as {"Authorization":"Bearer ..."} on stdin/interactively; redact token values in logs/UI.
```

**Pitfall: stdio args that begin with `-`.** `hermes mcp add ... --args` currently uses argparse `nargs="*"`; values like `-y` may be parsed as Hermes options instead of child-command arguments. For commands such as Chrome DevTools MCP (`npx -y chrome-devtools-mcp@latest`), prefer editing `mcp_servers` directly in `config.yaml`:

```yaml
mcp_servers:
  chrome-devtools:
    command: npx
    args:
      - -y
      - chrome-devtools-mcp@latest
```

Then run `/reload-mcp` or restart Hermes. Alternative: create an executable wrapper script that runs `exec npx -y chrome-devtools-mcp@latest`, and add that script as the MCP `--command` with no `--args`.

### Gateway (Messaging Platforms)

```
hermes gateway run          Start gateway foreground
hermes gateway install      Install as background service
hermes gateway start/stop   Control the service
hermes gateway restart      Restart the service
hermes gateway status       Check status
hermes gateway setup        Configure platforms
```

Supported platforms: Telegram, Discord, Slack, WhatsApp, Signal, Email, SMS, Matrix, Mattermost, Home Assistant, DingTalk, Feishu, WeCom, BlueBubbles (iMessage), Weixin (WeChat), API Server, Webhooks. Open WebUI / “office site” style frontends connect via the API Server adapter.

**Open WebUI / office URL field pitfall:** when a web frontend asks for a server URL, use the Hermes **API Server** endpoint with `/v1`, not the Hermes dashboard. Local browser/native frontend: `http://127.0.0.1:8642/v1`. Dockerized frontend reaching the host: `http://host.docker.internal:8642/v1`. The API key must match `API_SERVER_KEY`. Do not use dashboard URLs such as `http://127.0.0.1:9119` or the Tailscale dashboard URL; those are UI/dashboard endpoints, not OpenAI-compatible API endpoints. If a client configured with a bare origin (`http://127.0.0.1:8642`) gets `404 Not Found` on `/responses` or `/chat/completions`, first check for a `/v1` route mismatch; see `references/api-server-v1-bare-origin-404.md` for the reproduction, dual client/server fix, running-tree pitfall, and verification checklist.

**API Server `model` field pitfall:** for `/v1/chat/completions` and `/v1/responses`, the `model` field should be the advertised Hermes API-server model id (normally `hermes-agent`, or the id returned by `GET /v1/models`), not the underlying provider LLM. `API_SERVER_MODEL_NAME` can override the advertised id, and named profiles may advertise the profile name. The request model is primarily OpenAI-compatible metadata/echoing; the actual backing model/provider is resolved from Hermes gateway/runtime config. See `references/api-server-model-field.md`.

**Hermes Office / Claw3D gateway pitfall:** distinguish the Hermes API HTTP endpoint from the Claw3D/OpenClaw-compatible WebSocket gateway. `http://127.0.0.1:8642/v1` is correct for OpenAI-compatible API fields, but `ws://localhost:8642` is wrong for Claw3D gateway fields because port 8642 is HTTP. To connect Claw3D to Hermes Agent, run Hermes Office's `npm run hermes-adapter` and point Claw3D at that adapter, e.g. `ws://localhost:18790` if OpenClaw already uses `18789`. If the API is healthy but Claw3D cannot connect, prove `:18790` is listening and that Studio settings use `adapterType=hermes`; on Laurent's Mac the persistent adapter is LaunchAgent `fr.dubertrand.hermes-office-adapter`. When installing/building Hermes Office, if `npm run build` fails from `node_modules/.bin/next` with `Cannot find module '../server/require-hook'`, the `.bin/next` shim is a copied file instead of a symlink; run `npm rebuild next` in the Hermes Office checkout, then rebuild. See `references/hermes-office-claw3d-api-vs-gateway.md` for the diagnostic checklist, proxy verification, and Tailscale/OpenClaw allowlist pitfall; see `references/hermes-office-claw3d-adapter-persistence.md` for LaunchAgent persistence, settings repair, and end-to-end `chat.send` verification.

**API Server no-key 403 pitfall:** if an external/local app gets HTTP 403 while connecting without an API key, first prove whether `API_SERVER_KEY` is actually configured. A no-key gateway can still 403 because of feature gates on `X-Hermes-Session-Id` / `X-Hermes-Session-Key` or browser CORS preflight, not bearer auth. Do not add an API key when the requirement is no-key local use; instead allow local no-key session headers, configure `API_SERVER_CORS_ORIGINS`, include Hermes control headers in CORS, and verify with curl after gateway readiness. See `references/api-server-no-key-local-session-headers.md`.

**Dashboard/gateway auth diagnostics:** the former `hermes-dashboard-gateway-auth` skill is absorbed here as a Hermes-specific troubleshooting lane. For dashboard WebSocket/TUI gateway token mismatches, stale dashboard processes, host-proxy/Tailscale failures, or API-server vs dashboard auth confusion, start from this skill's Gateway and Troubleshooting sections, then consult the preserved package at `references/absorbed/hermes-dashboard-gateway-auth/README.md` for its focused diagnostic checklist and support references.

**TUI fast/priority verification pitfall:** for OpenAI-family models such as `gpt-5.5`, Hermes fast mode means the outbound API kwargs contain `service_tier: "priority"` — not a literal `fast` field. The TUI `config.get fast` / `session.info.fast` status only proves `agent.service_tier == "priority"` or `agent.service_tier` was read from config; it does not by itself prove the provider request includes the override. The definitive no-network check is to instantiate the TUI agent and run `agent.chat_completion_helpers.build_api_kwargs(...)`, then confirm `kwargs.get("service_tier") == "priority"` and/or `agent.request_overrides == {"service_tier": "priority"}`. If `agent.service_tier` is `priority` but `agent.request_overrides` is empty and built kwargs omit `service_tier`, the TUI is displaying fast mode but not sending Priority Processing for that path; live `config.set fast` updates request_overrides, but fresh-session config loading must also seed it.

Platform docs: https://hermes-agent.nousresearch.com/docs/user-guide/messaging/

### Sessions

```
hermes sessions list        List recent sessions
hermes sessions browse      Interactive picker
hermes sessions export OUT  Export to JSONL
hermes sessions rename ID T Rename a session
hermes sessions delete ID   Delete a session
hermes sessions prune       Clean up old sessions (--older-than N days)
hermes sessions stats       Session store statistics
```

### Cron Jobs

```
hermes cron list            List jobs (--all for disabled)
hermes cron create SCHED    Create: '30m', 'every 2h', '0 9 * * *'
hermes cron edit ID         Edit schedule, prompt, delivery
hermes cron pause/resume ID Control job state
hermes cron run ID          Trigger on next tick
hermes cron remove ID       Delete a job
hermes cron status          Scheduler status
```

**Wrapper/UI pitfall:** `hermes cron create` takes the prompt as an optional positional argument immediately after the schedule. When implementing schedule creation in Host Companion, desktop, mobile, or dashboard wrappers, build args as `create SCHEDULE PROMPT --name NAME --deliver TARGET`; do **not** append `-- PROMPT` after options, or argparse can fail with `unrecognized arguments: -- <prompt>`. See `references/hermes-runtime-schedules-cron-prompt-argument.md` for the reproduction, affected files, and smoke checks.

**Cron skill/provider pitfall:** Cron jobs load skills only from the installed Hermes skill registry under `$HERMES_HOME/skills`, not arbitrary project folders. For local Ollama/custom endpoints, avoid `provider: custom:<name>` unless that named custom provider exists; otherwise pin `provider: custom`, the actual model id, and `base_url`. See `references/cron-skill-provider-resolution.md` for the diagnostic and verification snippets.

### Webhooks

```
hermes webhook subscribe N  Create route at /webhooks/<name>
hermes webhook list         List subscriptions
hermes webhook remove NAME  Remove a subscription
hermes webhook test NAME    Send a test POST
```

### Profiles

```
hermes profile list         List all profiles
hermes profile create NAME  Create (--clone, --clone-all, --clone-from)
hermes profile use NAME     Set sticky default
hermes profile delete NAME  Delete a profile
hermes profile show NAME    Show details
hermes profile alias NAME   Manage wrapper scripts
hermes profile rename A B   Rename a profile
hermes profile export NAME  Export to tar.gz
hermes profile import FILE  Import from archive
```

### Credential Pools

```
hermes auth add             Interactive credential wizard
hermes auth list [PROVIDER] List pooled credentials
hermes auth remove P INDEX  Remove by provider + index
hermes auth reset PROVIDER  Clear exhaustion status
```

### Other

```
hermes insights [--days N]  Usage analytics
hermes update               Update to latest version
hermes pairing list/approve/revoke  DM authorization
hermes plugins list/install/remove  Plugin management
hermes honcho setup/status  Honcho memory integration (requires honcho plugin)
hermes memory setup/status/off  Memory provider config
hermes completion bash|zsh  Shell completions
hermes acp                  ACP server (IDE integration)
hermes claw migrate         Migrate from OpenClaw
hermes uninstall            Uninstall Hermes
```

---

## Slash Commands (In-Session)

Type these during an interactive chat session.

### Session Control
```
/new (/reset)        Fresh session
/clear               Clear screen + new session (CLI)
/retry               Resend last message
/undo                Remove last exchange
/title [name]        Name the session
/compress            Manually compress context
/stop                Kill background processes
/rollback [N]        Restore filesystem checkpoint
/background <prompt> Run prompt in background
/queue <prompt>      Queue for next turn
/resume [name]       Resume a named session
```

### Configuration
```
/config              Show config (CLI)
/model [name]        Show or change model
/personality [name]  Set personality
/reasoning [level]   Set reasoning (none|minimal|low|medium|high|xhigh|show|hide)
/verbose             Cycle: off → new → all → verbose
/voice [on|off|tts]  Voice mode
/yolo                Toggle approval bypass
/skin [name]         Change theme (CLI)
/statusbar           Toggle status bar (CLI)
```

### Tools & Skills
```
/tools               Manage tools (CLI)
/toolsets            List toolsets (CLI)
/skills              Search/install skills (CLI)
/skill <name>        Load a skill into session
/cron                Manage cron jobs (CLI)
/reload-mcp          Reload MCP servers
/plugins             List plugins (CLI)
```

### Gateway
```
/approve             Approve a pending command (gateway)
/deny                Deny a pending command (gateway)
/restart             Restart gateway (gateway)
/sethome             Set current chat as home channel (gateway)
/update              Update Hermes to latest (gateway)
/platforms (/gateway) Show platform connection status (gateway)
```

### Utility
```
/branch (/fork)      Branch the current session
/fast                Toggle priority/fast processing
/browser             Open CDP browser connection
/history             Show conversation history (CLI)
/save                Save conversation to file (CLI)
/paste               Attach clipboard image (CLI)
/image               Attach local image file (CLI)
```

### Info
```
/help                Show commands
/commands [page]     Browse all commands (gateway)
/usage               Token usage
/insights [days]     Usage analytics
/status              Session info (gateway)
/profile             Active profile info
```

### Exit
```
/quit (/exit, /q)    Exit CLI
```

---

## Key Paths & Config

```
~/.hermes/config.yaml       Main configuration
~/.hermes/.env              API keys and secrets
$HERMES_HOME/skills/        Installed skills
~/.hermes/sessions/         Session transcripts
~/.hermes/logs/             Gateway and error logs
~/.hermes/auth.json         OAuth tokens and credential pools
~/.hermes/hermes-agent/     Source code (if git-installed)
```

Profiles use `~/.hermes/profiles/<name>/` with the same layout.

### Config Sections

Edit with `hermes config edit` or `hermes config set section.key value`.

| Section | Key options |
|---------|-------------|
| `model` | `default`, `provider`, `base_url`, `api_key`, `context_length` |
| `agent` | `max_turns` (90), `tool_use_enforcement` |
| `terminal` | `backend` (local/docker/ssh/modal), `cwd`, `timeout` (180) |
| `compression` | `enabled`, `threshold` (0.50), `target_ratio` (0.20) |
| `display` | `skin`, `tool_progress`, `show_reasoning`, `show_cost` |
| `stt` | `enabled`, `provider` (local/groq/openai/mistral) |
| `tts` | `provider` (edge/elevenlabs/openai/minimax/mistral/neutts) |
| `memory` | `memory_enabled`, `user_profile_enabled`, `provider` |
| `security` | `tirith_enabled`, `website_blocklist` |
| `delegation` | `model`, `provider`, `base_url`, `api_key`, `max_iterations` (50), `reasoning_effort` |
| `checkpoints` | `enabled`, `max_snapshots` (50) |
| `auxiliary` | Per-side-task model routing: `vision`, `web_extract`, `compression`, `session_search`, `skills_hub`, `approval`, `mcp`, `title_generation`, `curator` |

Full config reference: https://hermes-agent.nousresearch.com/docs/user-guide/configuration

### Auxiliary Models

Hermes uses `auxiliary:` model slots for side-task LLM calls. When answering questions about config.yaml auxiliary models, check the live repo/default config if possible (`hermes_cli/config.py` → `DEFAULT_CONFIG["auxiliary"]`) because this list evolves.

Current class-level slots:

| Slot | Purpose / notes |
|------|-----------------|
| `vision` | Image, screenshot, browser-vision analysis. Includes `download_timeout` in addition to standard routing fields. |
| `web_extract` | Web page extraction and summarization. |
| `compression` | Context compression summaries. Summary model should have a context window large enough for the main model's compressed middle section. |
| `session_search` | Summaries for past-session search. Includes `max_concurrency` to avoid bursty 429s. |
| `skills_hub` | Skill hub search/selection helper reasoning. |
| `approval` | Smart command approval/risk judging (`approvals.mode: smart`). |
| `mcp` | MCP helper reasoning/routing. |
| `title_generation` | Automatic session title generation. |
| `curator` | Skill curator review/consolidation background task; default timeout is longer because reviews can take minutes. |

Standard per-slot shape:

```yaml
auxiliary:
  compression:
    provider: auto      # auto | main | openrouter | nous | anthropic | gemini | openai-codex | custom | named provider
    model: ""           # empty = provider's default auxiliary model
    base_url: ""        # direct OpenAI-compatible endpoint; takes precedence when set
    api_key: ""         # key for base_url, otherwise provider/env auth
    timeout: 120
    extra_body: {}
```

Useful commands:
```bash
hermes model                                      # includes Configure auxiliary models UI
hermes config set auxiliary.vision.provider openrouter
hermes config set auxiliary.vision.model google/gemini-2.5-flash
```

Auto-routing notes: `provider: auto` generally tries the user's main provider/model first, then configured/available fallbacks such as OpenRouter, Nous Portal, custom endpoints, Anthropic, and direct API-key providers depending on task capabilities. `provider: main` explicitly resolves to the current main provider. Codex OAuth is used for auxiliary tasks when it is the main provider or when explicitly configured with a model; it is not blindly tried in the generic fallback chain.

**Direct OpenAI API pitfall:** `openai` is not currently a valid `auxiliary.<task>.provider` id. For OpenAI API-key routing, configure the slot as `provider: custom` with `base_url: https://api.openai.com/v1` and an explicit OpenAI model (with `OPENAI_API_KEY` in `.env` or the environment). For ChatGPT/Codex OAuth, use `provider: openai-codex` and always set `auxiliary.<task>.model` explicitly because the Codex endpoint has no stable default allow-list.

### Providers

20+ providers supported. Set via `hermes model` or `hermes setup`.

| Provider | Auth | Key env var |
|----------|------|-------------|
| OpenRouter | API key | `OPENROUTER_API_KEY` |
| Anthropic | API key or Claude Pro/Max OAuth | `ANTHROPIC_API_KEY`, or `hermes auth add anthropic --type oauth` / `hermes model` |
| Nous Portal | OAuth | `hermes auth` |
| OpenAI Codex | OAuth | `hermes auth` |
| GitHub Copilot | Token | `COPILOT_GITHUB_TOKEN` |
| Google Gemini | API key | `GOOGLE_API_KEY` or `GEMINI_API_KEY` |
| DeepSeek | API key | `DEEPSEEK_API_KEY` |
| xAI / Grok | API key | `XAI_API_KEY` |
| Hugging Face | Token | `HF_TOKEN` |
| Z.AI / GLM | API key | `GLM_API_KEY` |
| MiniMax | API key | `MINIMAX_API_KEY` |
| MiniMax CN | API key | `MINIMAX_CN_API_KEY` |
| Kimi / Moonshot | API key | `KIMI_API_KEY` |
| Alibaba / DashScope | API key | `DASHSCOPE_API_KEY` |
| Xiaomi MiMo | API key | `XIAOMI_API_KEY` |
| Kilo Code | API key | `KILOCODE_API_KEY` |
| AI Gateway (Vercel) | API key | `AI_GATEWAY_API_KEY` |
| OpenCode Zen | API key | `OPENCODE_ZEN_API_KEY` |
| OpenCode Go | API key | `OPENCODE_GO_API_KEY` |
| Qwen OAuth | OAuth | `hermes login --provider qwen-oauth` |
| Custom endpoint | Config | `model.base_url` + `model.api_key` in config.yaml |
| GitHub Copilot ACP | External | `COPILOT_CLI_PATH` or Copilot CLI |

Full provider docs: https://hermes-agent.nousresearch.com/docs/integrations/providers

#### Anthropic / Claude Pro-Max subscription OAuth

Hermes can use Claude Pro/Max subscription credentials for the `anthropic` provider; it does not require an Anthropic API key. Prefer the interactive path for users asking how to configure this:

```bash
hermes model
# choose Anthropic / Claude
# choose "Claude Pro/Max subscription (OAuth login)"
# complete browser auth, then pick a model such as claude-sonnet-4-6
```

Direct credential-pool form:
```bash
hermes auth add anthropic --type oauth --label "Claude Max"
hermes model
```

If Claude Code is already installed/logged in, Hermes can reuse valid Claude Code credentials or run `claude setup-token` during the Anthropic model flow:
```bash
npm install -g @anthropic-ai/claude-code
claude auth login
hermes model
```

Resulting config should have `model.provider: anthropic` and `model.default: <claude-model>`. Do not set `model.base_url` for Anthropic; Hermes' adapter uses the correct Anthropic endpoint and auth headers automatically. Restart long-running gateway/API processes after changing the provider/model: `hermes gateway restart`.

### Toolsets

Enable/disable via `hermes tools` (interactive) or `hermes tools enable/disable NAME`.

| Toolset | What it provides |
|---------|-----------------|
| `web` | Web search and content extraction |
| `browser` | Browser automation (Browserbase, Camofox, or local Chromium) |
| `terminal` | Shell commands and process management |
| `file` | File read/write/search/patch |
| `code_execution` | Sandboxed Python execution |
| `vision` | Image analysis |
| `image_gen` | AI image generation |
| `tts` | Text-to-speech |
| `skills` | Skill browsing and management |
| `memory` | Persistent cross-session memory |
| `session_search` | Search past conversations |
| `delegation` | Subagent task delegation |
| `cronjob` | Scheduled task management |
| `clarify` | Ask user clarifying questions |
| `messaging` | Cross-platform message sending |
| `search` | Web search only (subset of `web`) |
| `todo` | In-session task planning and tracking |
| `rl` | Reinforcement learning tools (off by default) |
| `moa` | Mixture of Agents (off by default) |
| `homeassistant` | Smart home control (off by default) |

Tool changes take effect on `/reset` (new session). They do NOT apply mid-conversation to preserve prompt caching.

---

## Security & Privacy Toggles

Common "why is Hermes doing X to my output / tool calls / commands?" toggles — and the exact commands to change them. Most of these need a fresh session (`/reset` in chat, or start a new `hermes` invocation) because they're read once at startup.

### Secret redaction in tool output

Secret redaction is **off by default** — tool output (terminal stdout, `read_file`, web content, subagent summaries, etc.) passes through unmodified. If the user wants Hermes to auto-mask strings that look like API keys, tokens, and secrets before they enter the conversation context and logs:

```bash
hermes config set security.redact_secrets true       # enable globally
```

**Restart required.** `security.redact_secrets` is snapshotted at import time — toggling it mid-session (e.g. via `export HERMES_REDACT_SECRETS=true` from a tool call) will NOT take effect for the running process. Tell the user to run `hermes config set security.redact_secrets true` in a terminal, then start a new session. This is deliberate — it prevents an LLM from flipping the toggle on itself mid-task.

Disable again with:
```bash
hermes config set security.redact_secrets false
```

### PII redaction in gateway messages

Separate from secret redaction. When enabled, the gateway hashes user IDs and strips phone numbers from the session context before it reaches the model:

```bash
hermes config set privacy.redact_pii true    # enable
hermes config set privacy.redact_pii false   # disable (default)
```

### Command approval prompts

By default (`approvals.mode: manual`), Hermes prompts the user before running shell commands flagged as destructive (`rm -rf`, `git reset --hard`, etc.). The modes are:

- `manual` — always prompt (default)
- `smart` — use an auxiliary LLM to auto-approve low-risk commands, prompt on high-risk
- `off` — skip all approval prompts (equivalent to `--yolo`)

```bash
hermes config set approvals.mode smart       # recommended middle ground
hermes config set approvals.mode off         # bypass everything (not recommended)
```

Per-invocation bypass without changing config:
- `hermes --yolo …`
- `export HERMES_YOLO_MODE=1`

Note: YOLO / `approvals.mode: off` does NOT turn off secret redaction. They are independent.

### Shell hooks allowlist

Some shell-hook integrations require explicit allowlisting before they fire. Managed via `~/.hermes/shell-hooks-allowlist.json` — prompted interactively the first time a hook wants to run.

### Disabling the web/browser/image-gen tools

To keep the model away from network or media tools entirely, open `hermes tools` and toggle per-platform. Takes effect on next session (`/reset`). See the Tools & Skills section above.

---

## Voice & Transcription

### STT (Voice → Text)

Voice messages from messaging platforms are auto-transcribed.

Provider priority (auto-detected):
1. **Local faster-whisper** — free, no API key: `pip install faster-whisper`
2. **Groq Whisper** — free tier: set `GROQ_API_KEY`
3. **OpenAI Whisper** — paid: set `VOICE_TOOLS_OPENAI_KEY`
4. **Mistral Voxtral** — set `MISTRAL_API_KEY`

Config:
```yaml
stt:
  enabled: true
  provider: local        # local, groq, openai, mistral
  local:
    model: base          # tiny, base, small, medium, large-v3
```

### TTS (Text → Voice)

| Provider | Env var | Free? |
|----------|---------|-------|
| Edge TTS | None | Yes (default) |
| ElevenLabs | `ELEVENLABS_API_KEY` | Free tier |
| OpenAI | `VOICE_TOOLS_OPENAI_KEY` | Paid |
| MiniMax | `MINIMAX_API_KEY` | Paid |
| Mistral (Voxtral) | `MISTRAL_API_KEY` | Paid |
| NeuTTS (local) | None (`pip install neutts[all]` + `espeak-ng`) | Free |

Voice commands: `/voice on` (voice-to-voice), `/voice tts` (always voice), `/voice off`.

---

## Spawning Additional Hermes Instances

Run additional Hermes processes as fully independent subprocesses — separate sessions, tools, and environments.

### When to Use This vs delegate_task

| | `delegate_task` | Spawning `hermes` process |
|-|-----------------|--------------------------|
| Isolation | Separate conversation, shared process | Fully independent process |
| Duration | Minutes (bounded by parent loop) | Hours/days |
| Tool access | Subset of parent's tools | Full tool access |
| Interactive | No | Yes (PTY mode) |
| Use case | Quick parallel subtasks | Long autonomous missions |

### One-Shot Mode

```
terminal(command="hermes chat -q 'Research GRPO papers and write summary to ~/research/grpo.md'", timeout=300)

# Background for long tasks:
terminal(command="hermes chat -q 'Set up CI/CD for ~/myapp'", background=true)
```

### Interactive PTY Mode (via tmux)

Hermes uses prompt_toolkit, which requires a real terminal. Use tmux for interactive spawning:

```
# Start
terminal(command="tmux new-session -d -s agent1 -x 120 -y 40 'hermes'", timeout=10)

# Wait for startup, then send a message
terminal(command="sleep 8 && tmux send-keys -t agent1 'Build a FastAPI auth service' Enter", timeout=15)

# Read output
terminal(command="sleep 20 && tmux capture-pane -t agent1 -p", timeout=5)

# Send follow-up
terminal(command="tmux send-keys -t agent1 'Add rate limiting middleware' Enter", timeout=5)

# Exit
terminal(command="tmux send-keys -t agent1 '/exit' Enter && sleep 2 && tmux kill-session -t agent1", timeout=10)
```

### Multi-Agent Coordination

```
# Agent A: backend
terminal(command="tmux new-session -d -s backend -x 120 -y 40 'hermes -w'", timeout=10)
terminal(command="sleep 8 && tmux send-keys -t backend 'Build REST API for user management' Enter", timeout=15)

# Agent B: frontend
terminal(command="tmux new-session -d -s frontend -x 120 -y 40 'hermes -w'", timeout=10)
terminal(command="sleep 8 && tmux send-keys -t frontend 'Build React dashboard for user management' Enter", timeout=15)

# Check progress, relay context between them
terminal(command="tmux capture-pane -t backend -p | tail -30", timeout=5)
terminal(command="tmux send-keys -t frontend 'Here is the API schema from the backend agent: ...' Enter", timeout=5)
```

### Session Resume

```
# Resume most recent session
terminal(command="tmux new-session -d -s resumed 'hermes --continue'", timeout=10)

# Resume specific session
terminal(command="tmux new-session -d -s resumed 'hermes --resume 20260225_143052_a1b2c3'", timeout=10)
```

### Tips

- **Prefer `delegate_task` for quick subtasks** — less overhead than spawning a full process
- **Use `-w` (worktree mode)** when spawning agents that edit code — prevents git conflicts
- **Set timeouts** for one-shot mode — complex tasks can take 5-10 minutes
- **Use `hermes chat -q` for fire-and-forget** — no PTY needed
- **Use tmux for interactive sessions** — raw PTY mode has `\r` vs `\n` issues with prompt_toolkit
- **For scheduled tasks**, use the `cronjob` tool instead of spawning — handles delivery and retry

---

## Troubleshooting

### Voice not working
1. Check `stt.enabled: true` in config.yaml
2. Verify provider: `pip install faster-whisper` or set API key
3. In gateway: `/restart`. In CLI: exit and relaunch.

### Memory provider selected but shown unavailable/deactivated
1. Check config first: `hermes config` or `grep -A8 '^memory:' ~/.hermes/config.yaml`; `memory.provider: "supermemory"` means the provider selection persisted.
2. Run `hermes memory status`. If the provider is active but `Status: not available` and the missing checklist marks the API key as present, check the provider SDK import in the Hermes venv, not just `.env`.
3. For Supermemory specifically, `SUPERMEMORY_API_KEY` alone is insufficient: the Python package must import in the Hermes runtime venv. Verify with `~/.hermes/hermes-agent/venv/bin/python3 - <<'PY'\nimport supermemory\nprint('ok')\nPY`.
4. If the venv lacks pip, bootstrap and install: `~/.hermes/hermes-agent/venv/bin/python3 -m ensurepip --upgrade && ~/.hermes/hermes-agent/venv/bin/python3 -m pip install supermemory`.
5. Re-run `hermes memory status` and expect `Provider: supermemory`, `Plugin: installed ✓`, `Status: available ✓`. Restart any already-running gateway/app/runtime process so it sees the newly installed module.

### Tool not available
1. `hermes tools` — check if toolset is enabled for your platform
2. Some tools need env vars (check `.env`)
3. `/reset` after enabling tools

### Model/provider issues
1. `hermes doctor` — check config and dependencies
2. `hermes login` — re-authenticate OAuth providers
3. Check `.env` has the right API key
4. **Copilot 403**: `gh auth login` tokens do NOT work for Copilot API. You must use the Copilot-specific OAuth device code flow via `hermes model` → GitHub Copilot.

### Changes not taking effect
- **Tools/skills:** `/reset` starts a new session with updated toolset
- **Config changes:** In gateway: `/restart`. In CLI: exit and relaunch.
- **Code changes:** Restart the CLI or gateway process

### Skills not showing
1. `hermes skills list` — verify installed
2. `hermes skills config` — check platform enablement
3. Load explicitly: `/skill name` or `hermes -s name`

### Gateway issues
Check logs first:
```bash
grep -i "failed to send\|error" ~/.hermes/logs/gateway.log | tail -20
```

Common gateway problems:
- **`service "com.nous.hermesd" not found` when restarting the API/gateway on macOS**: Do not restart Hermes via a hardcoded `launchctl` service label. The supported command is `hermes gateway restart`. If the service has not been installed yet, run `hermes gateway install` first, then `hermes gateway start` or `hermes gateway restart`. The API Server adapter is controlled by the Hermes gateway service.
- **macOS LaunchAgent says loaded but gateway does not start**: Inspect launchd state and unified logs, not only `gateway.log`: `launchctl print gui/$(id -u)/ai.hermes.gateway` and `log show --last 10m --predicate 'eventMessage CONTAINS[c] "ai.hermes.gateway" OR eventMessage CONTAINS[c] "posix_spawn"' --style compact`. `EX_CONFIG 78` with `posix_spawn(.../venv/bin/python), Operation not permitted` can mean launchd refuses the Python executable behind the Hermes venv (observed with depot_tools Python on an external/dev volume). Recreate the venv with a trusted Homebrew/system Python rather than patching the generated plist by hand. See `references/hermes-macos-gateway-launchd.md`.
- **API Server adapter refuses to start on `0.0.0.0`**: If logs say binding to `0.0.0.0` requires `API_SERVER_KEY`, check the active `HERMES_HOME/.env` and profile env. Either set `API_SERVER_KEY` or bind to `127.0.0.1` for local-only use.
- **Gateway dies on SSH logout**: Enable linger: `sudo loginctl enable-linger $USER`
- **Gateway dies on WSL2 close**: WSL2 requires `systemd=true` in `/etc/wsl.conf` for systemd services to work. Without it, gateway falls back to `nohup` (dies when session closes).
- **Gateway crash loop**: Reset the failed state: `systemctl --user reset-failed hermes-gateway`

### Platform-specific issues
- **Discord bot silent**: Must enable **Message Content Intent** in Bot → Privileged Gateway Intents.
- **Slack bot only works in DMs**: Must subscribe to `message.channels` event. Without it, the bot ignores public channels.
- **Windows HTTP 400 "No models provided"**: Config file encoding issue (BOM). Ensure `config.yaml` is saved as UTF-8 without BOM.

### Auxiliary models not working
If `auxiliary` tasks (vision, compression, session_search) fail silently, the `auto` provider can't find a backend. Either set `OPENROUTER_API_KEY` or `GOOGLE_API_KEY`, or explicitly configure each auxiliary task's provider:
```bash
hermes config set auxiliary.vision.provider <your_provider>
hermes config set auxiliary.vision.model <model_name>
```

---

## Where to Find Things

| Looking for... | Location |
|----------------|----------|
| Config options | `hermes config edit` or [Configuration docs](https://hermes-agent.nousresearch.com/docs/user-guide/configuration) |
| Available tools | `hermes tools list` or [Tools reference](https://hermes-agent.nousresearch.com/docs/reference/tools-reference) |
| Slash commands | `/help` in session or [Slash commands reference](https://hermes-agent.nousresearch.com/docs/reference/slash-commands) |
| Skills catalog | `hermes skills browse` or [Skills catalog](https://hermes-agent.nousresearch.com/docs/reference/skills-catalog) |
| Provider setup | `hermes model` or [Providers guide](https://hermes-agent.nousresearch.com/docs/integrations/providers) |
| Platform setup | `hermes gateway setup` or [Messaging docs](https://hermes-agent.nousresearch.com/docs/user-guide/messaging/) |
| MCP servers | `hermes mcp list` or [MCP guide](https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp) |
| Profiles | `hermes profile list` or [Profiles docs](https://hermes-agent.nousresearch.com/docs/user-guide/profiles) |
| Cron jobs | `hermes cron list` or [Cron docs](https://hermes-agent.nousresearch.com/docs/user-guide/features/cron) |
| Memory | `hermes memory status` or [Memory docs](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory) |
| Env variables | `hermes config env-path` or [Env vars reference](https://hermes-agent.nousresearch.com/docs/reference/environment-variables) |
| CLI commands | `hermes --help` or [CLI reference](https://hermes-agent.nousresearch.com/docs/reference/cli-commands) |
| Gateway logs | `~/.hermes/logs/gateway.log` |
| Session files | `~/.hermes/sessions/` or `hermes sessions browse` |
| Source code | `~/.hermes/hermes-agent/` |

---

## Contributor Quick Reference

For occasional contributors and PR authors. Full developer docs: https://hermes-agent.nousresearch.com/docs/developer-guide/

### Project Layout

```
hermes-agent/
├── run_agent.py          # AIAgent — core conversation loop
├── model_tools.py        # Tool discovery and dispatch
├── toolsets.py           # Toolset definitions
├── cli.py                # Interactive CLI (HermesCLI)
├── hermes_state.py       # SQLite session store
├── agent/                # Prompt builder, context compression, memory, model routing, credential pooling, skill dispatch
├── hermes_cli/           # CLI subcommands, config, setup, commands
│   ├── commands.py       # Slash command registry (CommandDef)
│   ├── config.py         # DEFAULT_CONFIG, env var definitions
│   └── main.py           # CLI entry point and argparse
├── tools/                # One file per tool
│   └── registry.py       # Central tool registry
├── gateway/              # Messaging gateway
│   └── platforms/        # Platform adapters (telegram, discord, etc.)
├── cron/                 # Job scheduler
├── tests/                # ~3000 pytest tests
└── website/              # Docusaurus docs site
```

Config: `~/.hermes/config.yaml` (settings), `~/.hermes/.env` (API keys).

### Model catalog vs selected model

When answering questions about `models.json`, model picker contents, or what should be listed for models, distinguish three things:

- The documented **model catalog manifest** is `https://hermes-agent.nousresearch.com/docs/api/model-catalog.json`, sourced from `website/static/api/model-catalog.json` and cached at `~/.hermes/cache/model_catalog.json`.
- The catalog is a curated menu for `/model` and `hermes model` (currently especially OpenRouter and Nous), not the active runtime selection.
- The active runtime model/provider live in `~/.hermes/config.yaml` under `model` and are changed with `hermes model`, `/model`, or config edits.

Do not assume `~/.hermes/models.json` is authoritative; verify code/docs references first. See `references/hermes-model-catalog.md` for schema, fetch/fallback behavior, and config overrides.

### Adding a Tool (3 files)

**1. Create `tools/your_tool.py`:**
```python
import json, os
from tools.registry import registry

def check_requirements() -> bool:
    return bool(os.getenv("EXAMPLE_API_KEY"))

def example_tool(param: str, task_id: str = None) -> str:
    return json.dumps({"success": True, "data": "..."})

registry.register(
    name="example_tool",
    toolset="example",
    schema={"name": "example_tool", "description": "...", "parameters": {...}},
    handler=lambda args, **kw: example_tool(
        param=args.get("param", ""), task_id=kw.get("task_id")),
    check_fn=check_requirements,
    requires_env=["EXAMPLE_API_KEY"],
)
```

**2. Add to `toolsets.py`** → `_HERMES_CORE_TOOLS` list.

Auto-discovery: any `tools/*.py` file with a top-level `registry.register()` call is imported automatically — no manual list needed.

All handlers must return JSON strings. Use `get_hermes_home()` for paths, never hardcode `~/.hermes`.

### Adding a Slash Command

1. Add `CommandDef` to `COMMAND_REGISTRY` in `hermes_cli/commands.py`
2. Add handler in `cli.py` → `process_command()`
3. (Optional) Add gateway handler in `gateway/run.py`

All consumers (help text, autocomplete, Telegram menu, Slack mapping) derive from the central registry automatically.

### Agent Loop (High Level)

```
run_conversation():
  1. Build system prompt
  2. Loop while iterations < max:
     a. Call LLM (OpenAI-format messages + tool schemas)
     b. If tool_calls → dispatch each via handle_function_call() → append results → continue
     c. If text response → return
  3. Context compression triggers automatically near token limit
```

### Testing

```bash
python -m pytest tests/ -o 'addopts=' -q   # Full suite
python -m pytest tests/tools/ -q            # Specific area
```

### Hermes Desktop / Electron packaging

When `apps/desktop && npm run pack` fails on macOS with `codesign ... ambiguous` for a duplicate `Developer ID Application` identity, avoid mutating the user's keychain first. In electron-builder 26.8.x, keep/use a `build.mac.sign` custom hook that delegates to `@electron/osx-sign` with the prepared `configuration.identity` SHA-1 hash, then verify with `npm run pack` and `codesign --verify --deep --strict`. See `references/desktop-electron-builder-duplicate-codesign-identity.md`.

### HermesiOS / HermesHostCompanion UI extensions

When adding or rewriting iOS Agent Runtime accordion panels that mirror Hermes Desktop screens, first inspect the desktop renderer screen and main-process implementation, then implement the same actions through `HermesHostCompanion` WebSocket APIs rather than direct iOS file access. Add protocol Codable types, a focused host registry, server dispatch/capabilities, iOS client methods, and the SwiftUI panel. Verify with both `xcodebuild -project HermesiOS.xcodeproj -scheme HermesiOS -destination 'generic/platform=iOS Simulator' build` and `swiftc -parse HermesHostCompanion/*.swift` when no separate companion project/package exists. See `references/ios-companion-runtime-panels.md` for concrete patterns and pitfalls from Providers, Memory, Profiles, Gateway, and runtime model routing; for Agent Runtime → Models specifically, see `references/hermesios-runtime-models-panel.md`.

When debugging the Agent Runtime "Allowlisted Targets" panel, do not assume the path comes from Settings → Host Companion → Hermes workspace path. The target picker displays paths returned by Host Companion's persisted target registry (`~/Library/Application Support/HermesHostCompanion/targets.json`), and the current `list_targets` request does not send the workspace path. `CompanionTargetRegistry.seededDocument()` historically seeded `hermes-config` from the macOS home directory (`~/.hermes/config.toml`), which can be stale/outdated versus a configured workspace such as `/Volumes/WDBlack4TB/Code/HermesiOS/.hermes/config.yaml`. See `references/hermesios-companion-target-registry.md` for the investigation path and fix options.

When HermesiOS Host Companion enrollment fails with a generic TLS error, first verify URL/port ownership before changing cert logic. On Laurent's Mac, stale `wss://...:9113/enroll` values can hit Tailscale/IPNExtension, which presents a Let's Encrypt tailnet cert rather than the pinned HermesHostCompanion cert; the actual companion enrollment listener used `:9212` while API used `:9112`. Check `lsof`, `defaults read fr.dubertrand.HermesHostCompanion`, the PKI cert/fingerprint, and unified logs; migrate stale `:9113/enroll` settings/QR defaults to `:9212/enroll` if needed. See `references/hermesios-companion-enrollment-tls-port-conflict.md` for commands, evidence, and patch pattern.

When implementing YAML validation for Host Companion targets, do not use a naive native Swift fallback parser for real Hermes `config.yaml`; it can flag multiline valid YAML as broken. Prefer PyYAML from the target workspace venv, then default Hermes venv, then system Python; sanitize Xcode preview dynamic-loader environment variables before launching subprocesses; if PyYAML is unavailable everywhere, skip strict validation rather than fabricating syntax diagnostics. See `references/hermesios-companion-yaml-validation.md`.

When modifying HermesiOS Responses API or Chat Completions console bubbles, reuse shared bubble helpers for duplicated bubble visuals. For copy affordances, overlay a tiny bottom-right button that copies the adjacent bubble's real message content via `UIPasteboard`/`NSPasteboard`. For the current API tab selector, prefer Hermes **profile** selection over provider-model selection: populate from `GET /v1/profiles`, send the selected id as `X-Hermes-Profile` on every `/v1/chat/completions` and `/v1/responses` request, keep the request `model` as the API-server compatibility id (`hermes-agent` unless otherwise centralized), and lock the selected profile into session state (`activeProfile`) on first submit. If the user selects a different profile, start a fresh session/clear continuation state before subsequent calls. Use Host Companion `list_models` only for saved provider-model management, not for per-request API context. If `/v1/profiles` only returns `default` while `~/.hermes/profiles/` contains folders such as `Ollama`, check for legacy/manual mixed-case profile directory names; `list_profiles()`, `get_profile_dir()`, and `profile_exists()` should normalize the API id to lowercase while resolving the actual folder case-insensitively. If native Ask Hermes/Profile UI gets a 404 or missing model reasoning properties from the Hermes API, restore `/v1/profiles` metadata including `supported_parameters`, `supports_reasoning`, and a `reasoning` object; resolve support via `agent.models_dev.get_model_capabilities()` with conservative fallback heuristics, then restart the gateway before live verification. See `references/hermes-api-profile-reasoning-metadata.md`. See `references/hermes-profiles-legacy-case-folders.md`. The older model-selector behavior is documented historically in `references/hermesios-console-bubbles-and-model-selection.md`; use `references/hermesios-api-tabs-profile-selection.md` for the current profile-dropdown pattern, migration compatibility, server API changes, and verification checklist.

When HermesiOS cannot connect to `https://mac-studio.tail4d2ab4.ts.net:8642/v1`, first distinguish network reachability from API authentication: unauthenticated `GET /v1/models` returning `401 Invalid API key` means the route/backend is reachable; authenticated with `API_SERVER_KEY` should return `200`. If Tailscale Serve returns `502` while the local API server is healthy, inspect `tailscale serve status`; a backend of `http://localhost:8642` can be ambiguous when Hermes is not listening on `::1`. Repoint Serve explicitly to `http://127.0.0.1:8642` with `/Applications/Tailscale.app/Contents/MacOS/Tailscale serve --bg --https 8642 http://127.0.0.1:8642`, then verify `/v1/models` and a small `/v1/chat/completions` smoke test. See `references/hermesios-tailscale-api-server-reachability.md`.

When adding file attachments to HermesiOS Responses API or Chat Completions prompt composers, use a local `fileImporter` paperclip button immediately left of the prompt area, show a removable attachment chip, and pass a `HermesPromptAttachment` through the session submit/build-request path. Send images as inline base64 data URLs in the OpenAI/Hermes multimodal image shapes; for documents and text/source files, append filename/MIME/size metadata plus UTF-8 fenced content or a base64 data URL to prompt text, because the Hermes API server accepts inline images but currently rejects `file`/`input_file` parts. See `references/hermesios-api-tabs-file-attachments.md`.

When debugging or extending HermesiOS handling of generated-image output from Hermes Agent/API streams, support Laurent's JSON contract: rendered base64 image data is in `image_base64`, and that encoded image's MIME type is in `mime_type`; `original_mime_type` describes the original cached/source file and is only a fallback. Patch both structured API decoders and loose/raw assistant JSON extraction, because image payloads may arrive as parsed content parts, Responses final envelopes, or literal JSON text in the assistant bubble. See `references/hermesios-json-base64-image-output.md`.

When gateway delivery of generated images fails with platform text errors such as `Message too long`, do not assume the native file attachment size limit is too low. First compare the source file size with the expanded inline base64 payload: a small PNG can become millions of text characters if `image_base64` or `data:image/...;base64,...` reaches the streaming/text path. Decode embedded base64 images into `$HERMES_HOME/cache/images/`, redact the base64 from streamed/display text, and route the decoded file through normal native attachment delivery. See `references/gateway-base64-image-attachments.md`.

When extending `/v1/chat/completions` streaming for Hermes debug/observability UIs, keep OpenAI assistant text in normal unnamed SSE `data:` chunks and emit non-text debug information as named Hermes SSE events instead of `delta.content`. Current debug events include `hermes.tool.progress`, `Hermes.reasoning.summary`, and `Hermes.tool.output`; wire `reasoning_callback` through `_create_agent`/`_run_agent`, emit tool output from correlated non-internal `tool_complete_callback`, cap large outputs, advertise capability flags, and test that debug events never leak into `chat.completion.chunk` content. For context compression specifically, `run_agent.py` should emit a structured JSON reasoning callback and the API server should expose it on `Hermes.reasoning.summary` as a parsed `message` while preserving `delta`/`summary` strings; see `references/context-compression-reasoning-json.md`. For HermesiOS Chat, raw streamed JSON in the debug modal is not enough: decode named events into readable debug text for debug surfaces, but do not render tools/events/logs in the assistant chat bubble. The visible Chat tab should update the Status pill with short (≤40 char) labels for every streamed event, preferably before raw/debug log processing and with a `Task.yield()` if SwiftUI otherwise batches the repaint. See `references/chat-completions-debug-sse-events.md`.

When changing HermesiOS History search resume controls, treat "Resume in Responses" and "Resume in Chat" as destination-tab actions. Disable the Responses resume controls while `responseSession.isSending` (Ask Hermes streaming) and disable Chat resume controls while `chatSession.isSending` (Chat with Hermes streaming), including both expanded-row buttons and compact menu actions. Also add handler-level guards in `ContentView` to prevent races. See `references/hermesios-history-resume-controls.md`.

When adding iPad sidebar completion/attention indicators for HermesiOS tabs, keep notification state in `ContentView`, set it from the relevant completion signal, pass bindings into `WorkspaceSidebar`, and clear the green state from the sidebar row tap. For Ask Hermes/Chat, use `.onChange` of each session `connectionStatus == "Completed"`; for History search, use `.onChange(of: dashboardHistorySearchSession.isSearching)` and set unread when it transitions from `true` to `false` unless status is `"Cancelled"`. Preserve the existing selected row background; only the icon background should turn green. See `references/hermesios-sidebar-completion-indicators.md`.

When performing Hermes session-hygiene maintenance, such as deleting sessions with no agent/assistant response, scan live stores beyond the primary `state.db`: profile `state.db` files, transcript JSON files (including file-only transcripts absent from SQLite), and `response_store.db` rows whose JSON contains the deleted `session_id`. Skip the currently running cron job's own fresh active session so the maintenance task does not delete its still-open log. See `references/session-hygiene-no-agent-response.md` for the exact identification query, safe deletion order, and verification checklist.

When running Hermes maintenance scripts such as `scripts/backfill_session_titles.py`, prefer the Hermes runtime venv (`.venv`, `venv`, or `~/.hermes/hermes-agent/venv`) over system `python` so auxiliary providers/imports are available. If a direct run shows missing provider imports such as `No module named 'openai'`, rerun with the venv before diagnosing config. If title backfill is long-running, background it and poll until completion. If many `[SILENT]` cron sessions produce duplicate `Silent` titles, expect uniqueness failures after suffix exhaustion; treat this as a low-information-title collision, not necessarily a provider failure. In scheduled-job delivery contexts, report nonzero/partial outcomes succinctly; use `[SILENT]` only when the run genuinely produced nothing new. See `references/session-title-backfill-maintenance.md`.

When debugging HermesiOS Agent Runtime → Memory showing Supermemory as deactivated after startup, do not assume `memory.provider` failed to persist. Check the active workspace config, `.env` key presence without printing secrets, and `hermes memory status`; if it says provider `supermemory` is configured but `Status: not available` while `SUPERMEMORY_API_KEY` is present, verify `import supermemory` in the Hermes venv and install with that exact interpreter if needed. See `references/hermesios-memory-supermemory-availability.md` for the reproduction, fix, and pitfalls.

When debugging or changing HermesMacOS Ask Hermes / Chat with Hermes cancellation, distinguish client-side Swift `Task.cancel()` from actual Hermes Agent interruption. Current explicit-cancel pattern: HermesMacOS sends `X-Hermes-Request-Id` on `/v1/responses` and `/v1/chat/completions`, then posts `POST /v1/requests/{request_id}/cancel` before local cancellation; the API server tracks `agent_ref`/asyncio task, calls `agent.interrupt("Cancel requested via API")`, and cancels the task. Streaming disconnect handling remains useful, but non-streaming paths need this explicit request tracking to avoid invisible continued work. `/v1/runs/{run_id}/stop` remains the strongest structured control-plane API for future run-oriented UX. See `references/hermesmacos-api-cancellation-semantics.md`.

When adding dashboard History/search features or companion-app access to dashboard session data, remember that `SessionDB.search_messages()` is the underlying FTS API and dashboard routes live in `hermes_cli/web_server.py` (not the OpenAI-compatible API server adapter). For full-conversation search, wrap `search_messages()`, group matches by `session_id`, then expand each hit with `db.get_session()` and `db.get_messages()`. For a History/Search “Resume to chat” action, use the persisted Hermes `SessionDB` `session_id` as the universal resume key; do not resume by a TUI runtime id or a Responses API `resp_...` id. Responses-mode sessions can be continued in chat by resuming the stored Hermes `session_id`; chat sessions can be continued in Responses mode only via an explicit bridge (`X-Hermes-Session-Id` support on `/v1/responses`, a synthesized `response_store` row, or client-supplied `conversation_history`). When resuming into HermesiOS Chat or Responses, also propagate a defensive friendly title (`title`/`display_title`/`friendly_name`/`name`/`summary`, including metadata variants) into the destination tab's session pill before falling back to prompt/session-id labels. See `references/history-resume-cross-mode.md`. Dashboard `/api/*` routes require the injected `X-Hermes-Session-Token`; native iOS clients can fetch `/`, extract `window.__HERMES_SESSION_TOKEN__`, then call the JSON endpoint. For local simulator access on port `9119`, check for stale listeners with `lsof -nP -iTCP:9119 -sTCP:LISTEN`, kill the stale PID if needed, and verify the port/dashboard before debugging app code; stale dashboard processes can produce misleading token/API behavior. For Tailscale Serve/Funnel access, distinguish upstream failures (502 when `127.0.0.1:9119` is not serving) from Hermes Host-header protection (400 `Invalid Host header` when a reverse proxy preserves the tailnet hostname while Hermes is bound to loopback); prefer a Host-rewriting local proxy over `--host 0.0.0.0 --insecure`. On Laurent's Mac, `https://mac-studio.tail4d2ab4.ts.net:9119` is served by Tailscale to a Host-rewriting proxy on `127.0.0.1:9120`, installed as LaunchAgent `fr.dubertrand.hermes-dashboard-host-proxy`, forwarding to the Hermes dashboard on `127.0.0.1:9119`; see `references/hermesios-tailscale-dashboard-host-proxy.md` for the exact topology and verification commands. If 9120 returns `Hermes dashboard proxy error: [Errno 61] Connection refused` or HermesMacOS TUI Gateway says the server response is bad, first verify `lsof -nP -iTCP:9119 -sTCP:LISTEN`; on Laurent's Mac the direct dashboard should be kept alive by LaunchAgent `fr.dubertrand.hermes-dashboard` using local wrapper `/Users/laurent/Library/Application Support/HermesDashboard/run_dashboard.sh` and logs under `/Users/laurent/Library/Logs/Hermes/hermes-dashboard*.log`. If this LaunchAgent is loaded but will not start with `EX_CONFIG 78` / `posix_spawn(...), Operation not permitted`, move executable inputs and logs out of symlinked/external-drive `.hermes` paths into `~/Library/Application Support/HermesDashboardHostProxy/` and `~/Library/Logs/Hermes/`; see `references/dashboard-host-proxy-launchd-local-paths.md`. If dashboard search returns 500, reproduce `SessionDB().search_messages(...)` directly and check for SQLite `no such tokenizer: trigram`; some macOS/CI SQLite builds need a unicode61 fallback with the same `messages_fts_trigram` table name. See `references/dashboard-session-search-api.md` for endpoint shape, iOS access notes, stale-port cleanup, reverse-proxy pitfalls, trigram fallback, and test pitfalls. If asked to change the dashboard HTTP API timeout, patch the browser dashboard clients too: `web/src/lib/api.ts` REST `fetchJSON` needs an `AbortController` timeout and `web/src/lib/gatewayClient.ts` JSON-RPC has `DEFAULT_REQUEST_TIMEOUT_MS`; rebuild `web/` so `hermes_cli/web_dist` is updated. See `references/dashboard-api-timeout-2026-05.md`.

When changing or debugging Hermes dashboard API timeouts, distinguish browser/client-side timeouts from FastAPI/uvicorn server behavior. Generic dashboard REST calls are centralized in `web/src/lib/api.ts` (`fetchJSON`), and embedded Chat/TUI WebSocket JSON-RPC request timeouts are in `web/src/lib/gatewayClient.ts` (`DEFAULT_REQUEST_TIMEOUT_MS`). After frontend timeout changes, run `cd web && npm run build` so `hermes_cli/web_dist` is updated, then hard-refresh or restart the dashboard/gateway if an old bundle is still served. See `references/dashboard-api-timeouts.md` for the exact 5-minute timeout pattern and pitfalls.

When adding dashboard indicators for Hermes installation/update state, reuse the existing update-check primitives rather than inventing new git logic: `hermes_cli.banner.check_for_updates()` counts commits behind `origin/main` and writes `$HERMES_HOME/.update_check`. If the dashboard needs a different refresh cadence, extend the helper with an injectable cache window (default unchanged for CLI) and expose a small FastAPI endpoint from `hermes_cli/web_server.py`; keep browser API bindings in `web/src/lib/api.ts`, render in the relevant page, then run `cd web && npm run build` to update `hermes_cli/web_dist`. The dashboard left-panel system action links live in `web/src/App.tsx` in `SidebarSystemActions`; remove/update entries there and clean up now-unused Lucide imports rather than changing backend action handlers or i18n strings unless the action itself is being retired everywhere. Pitfall: `uv run` may rewrite `uv.lock` in this repo because `pyproject.toml` uses a relative `tool.uv.exclude-newer = "7 days"`; for focused local tests prefer the repo `.venv` or Laurent's shared `~/.hermes/hermes-agent/venv` and avoid committing lockfile churn from ad-hoc env creation.

When adding URL-driven Hermes dashboard theme behavior, treat `theme` as a first-class query parameter preserved across all internal page URLs. Read it in the React theme provider before localStorage/server defaults, canonicalize known theme names case-insensitively (`?theme=MONO` → `mono`), replace the current URL once the active theme is known, and update every `Link`/`NavLink`/`Navigate`/`navigate(...)` path including plugin tabs and existing query URLs such as chat resume. See `references/dashboard-theme-query-param.md`.

When adding a built-in Hermes Dashboard visual theme, update both frontend and backend registries: `web/src/themes/presets.ts` (`DashboardTheme` export plus `BUILTIN_THEMES`) and `hermes_cli/web_server.py` (`dashboard.theme` schema options plus `_BUILTIN_DASHBOARD_THEMES`). Then run `cd web && npm run build`, verify `hermes_cli/web_dist` contains the theme id/colors, and smoke-test `/api/dashboard/themes` plus the browser theme switcher. If aligning `solarized-light` with standalone HermesMacOS light mode, use a white canvas with pale blue/grey controls rather than classic warm Solarized paper, and remember `hermes_cli/web_dist` may be gitignored even though it is locally rebuilt; see `references/dashboard-solarized-light-hermesmacos-parity-2026-05.md`. See `references/dashboard-builtin-theme-addition.md`.

When adding HermesiOS Settings → Hermes Installation controls that operate on the host Hermes Agent checkout, route all actions through HermesHostCompanion protocol/client/server layers and isolate git operations in `CompanionGitRegistry`. For local-branch-safe official updates, auto-commit any dirty working-tree changes to the current local branch before fetching official main; require a non-detached branch if dirty, include the auto-commit hash/output in the UI operation result, then fetch `https://github.com/NousResearch/hermes-agent.git` directly into `refs/remotes/hermes-official/main`, probe conflicts with `git merge-tree --write-tree` without merging official main, persist pending review state in local git config, disable the update button while review is pending, and enable a separate merge-after-review action that merges the pinned official commit into the local branch after the working tree is clean. Verify Host Companion with `swiftc -typecheck HermesHostCompanion/*.swift`; verify iOS with an iPhone simulator SDK/target (iOS 26 if Speech APIs require it). See `references/hermesios-settings-installation-update-workflow.md` for protocol files, state keys, UI details, and verification commands.

When the TUI/dashboard resume-session flow appears to open a new chat instead of resuming, inspect `tui_gateway/server.py` `session.resume`: the frontend uses the returned `result.session_id` as the active chat key, so it must be the persisted target SessionDB id, not a fresh short runtime UUID. Keep `result.session_id`, `result.resumed`, `_sessions[...]`, and the agent's `session_id` aligned on the persisted id. See `references/tui-resume-session-id.md` for the root cause, patch pattern, and regression test.

- Tests auto-redirect `HERMES_HOME` to temp dirs — never touch real `~/.hermes/`
- Run full suite before pushing any change
- Use `-o 'addopts='` to clear any baked-in pytest flags

### Local branch convention for Laurent's Hermes Agent changes

Before modifying Hermes Agent source code for Laurent, check the repo branch/status and avoid editing directly on `main`. Create or reuse a local branch that was created after the latest Hermes Agent update, and keep using that branch for all Hermes Agent source changes until the next update. When touching HermesiOS Settings → Hermes Installation, make sure the current local Hermes Agent branch is visible there so Laurent can tell which local change branch is active.

### Commit Conventions

```
type: concise subject line

Optional body.
```

Types: `fix:`, `feat:`, `refactor:`, `docs:`, `chore:`

### Key Rules

- **Never break prompt caching** — don't change context, tools, or system prompt mid-conversation
- **Message role alternation** — never two assistant or two user messages in a row
- Use `get_hermes_home()` from `hermes_constants` for all paths (profile-safe)
- Config values go in `config.yaml`, secrets go in `.env`
- New tools need a `check_fn` so they only appear when requirements are met
