---
sidebar_position: 4
title: "MCP (Model Context Protocol)"
description: "Connect Hermes Agent to external tool servers via MCP — and control exactly which MCP tools Hermes loads"
---

# MCP (Model Context Protocol)

Python dependency commands on this page use a
[PM-prepared source checkout](../../reference/package-management.md#developer-workflow).
After a dependency change, reactivate the checkout and restart Hermes.

MCP lets Hermes Agent connect to external tool servers so the agent can use tools that live outside Hermes itself — GitHub, databases, file systems, browser stacks, internal APIs, and more.

If you have ever wanted Hermes to use a tool that already exists somewhere else, MCP is usually the cleanest way to do it.

:::tip Coming from Claude Code?
The `mcpServers` block in your `~/.claude.json` maps to `mcp_servers` in Hermes' `config.yaml` — and `hermes import-agent claude-code` migrates it (along with skills and instructions) automatically. See [Import from Other Agents](../import-from-other-agents.md).
:::

## What MCP gives you

- Access to external tool ecosystems without writing a native Hermes tool first
- Local stdio servers and remote HTTP MCP servers in the same config
- Automatic tool discovery and registration at startup
- Utility wrappers for MCP resources and prompts when supported by the server
- Per-server filtering so you can expose only the MCP tools you actually want Hermes to see

## Quick start

1. MCP support ships with the standard install — no extra step needed.

2. Add an MCP server to `~/.hermes/config.yaml`:

```yaml
mcp_servers:
  filesystem:
    command: "npx"
    args: ["-y", "@modelcontextprotocol/server-filesystem", "/home/user/projects"]
```

3. Start Hermes:

```bash
hermes chat
```

4. Ask Hermes to use the MCP-backed capability.

For example:

```text
List the files in /home/user/projects and summarize the repo structure.
```

Hermes will discover the MCP server's tools and use them like any other tool.

## Catalog: one-click install for Nous-approved MCPs

Hermes ships a curated catalog of MCP servers that Nous staff has reviewed
and merged. They're disabled by default — install only what you actually
want.

You can also ask in chat: "add the Linear MCP". The agent calls
`manage_connections` with an `mcp: true` target and a setup card appears. The
card works the same way in the desktop app (a dialog), the terminal UI
(`hermes --tui`, a callout above the composer) and the classic CLI (a panel):

1. **Fields.** If the entry declares setup values, the card shows all of them
   at once. A plain value is prefilled with its default. A secret is masked.
   Nothing is saved while you type.
2. **Connect or Cancel.** Cancel skips that one server; other servers in the
   same request continue.
3. **Authorization.** For an OAuth entry the card shows the authorization link.
   Hermes never opens the browser by itself: click **Open in browser** on the
   desktop, or press Enter in the terminal. Over SSH the card tells you how to
   reach the callback port or paste the redirected URL.
4. **Save.** Hermes saves the server configuration, the tokens and your setup
   values together, once the server has accepted the new token and the first
   connection has returned. If the server rejects the token, or you cancel
   before that point, nothing from the attempt is kept, your earlier
   configuration and tokens stay as they were, and a failed form reopens with
   what you typed. A server that is already authorized connects with its saved
   tokens; Hermes asks you to authorize again only when they no longer work.
5. **Tools.** Hermes then lists the server's tools and registers them. The
   agent can call them in the same turn. If authorization worked and the tool
   list failed, the card says "Authorized. Tools unavailable." and the agent can
   run discovery again later without asking you to authorize again.

In messaging apps there is no card; the agent relays the commands below.

```bash
hermes mcp                   # interactive picker (default)
hermes mcp catalog           # plain-text list, scriptable
hermes mcp install deepwiki  # install a catalog entry by name
```

The picker shows each entry with its current status:

```
deepwiki     available              Ask questions about public GitHub repositories
linear       enabled                Linear issue/project management (remote OAuth)
github       installed (disabled)   GitHub repo + PR tools
```

Hit `Enter` on a row to install (and walk through any required credentials),
enable, disable, or uninstall. Catalog entries are stored under
`optional-mcps/` in the hermes-agent repo — presence in that directory means
Nous approval. There is no community submission tier; entries are added by
merging a PR.

The third-party n8n bridge is no longer available for catalog installation.
Existing installations keep their `mcp_servers` configuration, credentials,
installed files, and selected tools. They continue to load as configured MCP
servers and appear as custom entries in the picker, where you can still
configure tools or enable and disable them. Catalog reinstall is no longer
available. This change does not migrate existing connections to
[n8n's official MCP server](https://docs.n8n.io/connect/connect-to-n8n-mcp-server/).

Catalog entries can require:

- **API key** — Hermes prompts at install time and writes the value to
  `~/.hermes/.env`. Non-secret values (base URLs) go to the same file.
- **OAuth** (remote MCP) — written as `auth: oauth` in your config; the MCP
  client opens a browser on first connection.
- **OAuth** (third-party provider like Google/GitHub) — Hermes points you at
  `hermes auth <provider>` if you haven't authenticated already.

### n8n's official MCP server

The `n8n-official` catalog entry connects directly to your n8n Cloud or
self-hosted instance over HTTP with browser OAuth. No local bridge or n8n
API key is required.

1. Ask an owner or admin to enable **Settings > Instance-level MCP** in n8n.
2. Open **Connect** and copy the full **Server URL** ending in
   `/mcp-server/http`, not the editor URL. Older versions show the endpoint
   directly on the MCP settings page.
3. Run `hermes mcp install n8n-official` and enter that URL when prompted.
4. Complete browser OAuth. If needed, run `hermes mcp login n8n-official`
   or use **Authorize** on the configured server in Desktop or the dashboard.
5. Review tools with `hermes mcp configure n8n-official`, then start a new
   session or use `/reload-mcp`.

The Hermes backend must be able to reach the URL. n8n controls permissions
and workflow exposure; some tools modify or run workflows. See
[n8n's connection guide](https://docs.n8n.io/connect/connect-to-n8n-mcp-server/).

This entry uses the existing catalog setup and storage behavior. It is
separate from the retired `n8n` bridge, so existing connections, credentials,
installed files, and tool selections are not replaced.

### Tool selection at install time

After credentials are configured, Hermes probes the MCP server to list every
tool it exposes and presents a checklist:

```
Select tools for 'linear' (SPACE toggle, ENTER confirm)
  [x] find_issues       Find issues matching a query
  [x] get_issue         Get a single issue
  [x] create_issue      Create a new issue
  [ ] delete_workspace  Delete a Linear workspace
  ...
```

The pre-checked rows come from:

1. **Your prior selection** if you've installed this entry before (reinstalls
   preserve what you had — the manifest's defaults don't override it)
2. **The manifest's `tools.default_enabled`** if the entry declares one (some
   catalog entries pre-prune mutating or rarely-useful tools)
3. **Everything** if neither applies

Some entries with very large auto-generated surfaces (e.g. `cloudflare`,
~3,300 OpenAPI endpoint tools) instead declare `tools.default_excluded` — a
curated block-list of names and glob patterns. Installing one of these skips
the checklist entirely and writes `tools.exclude`; everything not matched
stays enabled, including tools the server adds later. Edit
`mcp_servers.<name>.tools.exclude` in config.yaml to re-enable a family.

Submit the checklist with ENTER. Only the checked tools end up in
`mcp_servers.<name>.tools.include`. If you select everything, no filter is
written (cleanest config shape, identical behavior).

**If the probe fails** (server unreachable, OAuth not yet completed,
backing service not running), the install still succeeds: the manifest's
`tools.default_enabled` is applied directly (if declared), or no filter is
written (if not). Re-run `hermes mcp configure <name>` once the server is
reachable to refine.

### Trust model

Installing a catalog entry runs whatever the manifest specifies — `git clone`,
the entry's `bootstrap` commands (`pip install`, `npm install`, etc.), and
ultimately the MCP server's own code. Manifests are gated by PR review into
the hermes-agent repo, so Nous has reviewed each entry before it shipped —
**but you should still read the manifest before installing**, especially the
`source:` field's repository, the `install.bootstrap:` commands, and any
`transport.command:` invocation.

Manifests live at
[`optional-mcps/<name>/manifest.yaml`](https://github.com/NousResearch/hermes-agent/tree/main/optional-mcps)
on GitHub. The picker also prints the manifest's `source:` URL at install
time so you can quickly verify the upstream repo. The web dashboard's MCP
page surfaces the same detail per catalog entry — transport, auth type, the
endpoint URL (HTTP) or command + args (stdio), the git install source/ref and
bootstrap commands, and setup notes — with the `source:` rendered as a
clickable link, so you can inspect exactly what an entry connects to or runs
before clicking Install.

### Manifest version compatibility

Manifests pin a `manifest_version`. The catalog is forward-compatible: if a
PR adds an entry with a newer `manifest_version` than your installed Hermes
understands, the picker will surface a warning (`⚠ '<name>' requires a newer
Hermes`) for that entry instead of silently hiding it. Run `hermes update`
to install the latest Hermes when you see that.

### Runtime `${ENV_VAR}` substitution

Inside an entry's `transport.command`, `transport.args`, `transport.url`,
and `headers`, `${VAR}` placeholders are resolved at server-connect time
from environment variables (which include everything in `~/.hermes/.env`).
This is useful when a catalog entry wants to reference a value the user
configured elsewhere — e.g. `${HOME}/foo` or `${MY_PROVIDER_TOKEN}`.

Cursor-style context variables are also substituted (case-sensitive):
`${userHome}` (home directory), `${workspaceFolder}` (session workspace
root), `${workspaceFolderBasename}`, and `${pathSeparator}` / `${/}`
(the OS path separator). See the
[MCP config reference](../../reference/mcp-config-reference.md) for details.

Note this is distinct from `${INSTALL_DIR}` in catalog manifests, which is
substituted at install-time with the path the catalog cloned the entry's
repo into.

### Entries that need your own OAuth app (no DCR)

Some vendors run their remote MCP behind OAuth but do **not** offer Dynamic
Client Registration — every client must be an app the user pre-registers in
the vendor's developer console. Asana's V2 server
(`https://mcp.asana.com/v2/mcp`) is the shipped example: the retired V1
`https://mcp.asana.com/sse` server accepted any client; V2 does not.

Such a manifest declares the credentials under `auth.env` and pins the
client under `auth.oauth`, so installing it (CLI picker, web dashboard or
Desktop) prompts for the Client ID / Client secret, stores them in the
profile's `.env`, and writes only `${VAR}` references to `config.yaml`:

```yaml
mcp_servers:
  asana:
    url: https://mcp.asana.com/v2/mcp
    auth: oauth
    oauth:
      client_id: "${ASANA_CLIENT_ID}"
      client_secret: "${ASANA_CLIENT_SECRET}"
      redirect_host: localhost      # the vendor matches the redirect URL exactly
      redirect_port: 27890          # register http://localhost:27890/callback on the app
```

Read the entry's `post_install` notes for the exact app type and redirect URL
to register, then run `hermes mcp login <name>` and restart (or
`/reload-mcp`) the session or gateway that should expose the tools. The
dashboard / Desktop **Authorize** button works too: because the client is
pre-registered with a pinned `redirect_port`, Hermes keeps the registered
loopback callback (`http://localhost:27890/callback`) instead of the
dashboard's own callback URL — so the browser you approve in must run on the
same machine as the Hermes process. For a remote host, use `hermes mcp login`
over SSH port-forwarding.

### Updating tool selection later

```bash
hermes mcp configure linear
```

Reopens the same checklist with your current selection pre-checked. Use this
when you want more tools enabled, or when the server has added new tools that
you want to opt into.

### Updating the catalog manifest

MCPs are never auto-updated. Re-run `hermes mcp install <name>` to refresh
after a Hermes update if a manifest version changed.

To add an MCP to the catalog, open a PR against
[`optional-mcps/`](https://github.com/NousResearch/hermes-agent/tree/main/optional-mcps).

### Suggestion metadata (`suggest:`)

A manifest may declare an optional `suggest:` block with `keywords:` and/or
`hosts:` lists. UI surfaces (currently the Desktop app's composer) use it to
offer a one-click "Add &lt;server&gt;" pill when your draft mentions one of the
keywords as a completed word, or contains a pasted link whose hostname ends
with one of the host suffixes. It is purely advisory — installs still flow
through the same validated catalog/config paths — and most hosted remote
entries (Atlassian, Sentry, Notion, Stripe, Vercel, Supabase, and friends)
declare it. Optional `applications:` (up to 16 app names), `requires_app: true`
(the MCP needs that local app; such entries are never offered as a one-click
pill) and `examples:` (up to six one-line outcomes) describe entries that drive
a desktop application.

GitHub is deliberately **not** in the catalog: its hosted MCP requires each
client to bring its own OAuth app (generic dynamic client registration is
rejected), and Hermes's bundled `github/*` skills driving the `gh` CLI are a
more capable integration. On Desktop, GitHub mentions instead offer the
`github-auth` skill when `gh` isn't signed in yet.

## External server transports

### Stdio servers

Stdio servers run as local subprocesses and talk over stdin/stdout.

```yaml
mcp_servers:
  github:
    command: "npx"
    args: ["-y", "@modelcontextprotocol/server-github"]
    env:
      GITHUB_PERSONAL_ACCESS_TOKEN: "***"
```

Use stdio servers when:
- the server is installed locally
- you want low-latency access to local resources
- you are following MCP server docs that show `command`, `args`, and `env`

### HTTP servers

HTTP MCP servers are remote endpoints Hermes connects to directly.

```yaml
mcp_servers:
  remote_api:
    url: "https://mcp.example.com/mcp"
    headers:
      Authorization: "Bearer ***"
```

Use HTTP servers when:
- the MCP server is hosted elsewhere
- your organization exposes internal MCP endpoints
- you do not want Hermes spawning a local subprocess for that integration


### REST OpenAPI servers

Some bridges, including [mcpo](https://github.com/open-webui/mcpo), expose an
MCP server as ordinary REST operations plus an OpenAPI 3.x document. These are
not native HTTP MCP endpoints. Select the OpenAPI transport explicitly so
Hermes fetches the schema, registers each operation as a tool, and executes the
operation over REST:

```bash
hermes mcp add XCodeMCP \
  --url http://127.0.0.1:8084 \
  --transport openapi \
  --openapi-url http://127.0.0.1:8084/openapi.json
```

Equivalent config:

```yaml
mcp_servers:
  XCodeMCP:
    transport: openapi
    url: http://127.0.0.1:8084
    openapi_url: http://127.0.0.1:8084/openapi.json  # optional default
    headers: {}                                      # optional
```

Hermes maps path, query, header, and cookie parameters into the tool input
schema using OpenAPI's standard serialization styles. Required JSON object-body
properties are flattened when their names are unambiguous; optional or
colliding bodies use a nested `body` input so conditional requirements are
preserved. Operations that require unsupported non-JSON request bodies are not
registered. Local component `$ref` values are resolved. For mcpo operation IDs
such as `tool_XcodeListWindows_post`, Hermes preserves the original MCP tool
name (`XcodeListWindows`) under the normal `mcp__<server>__<tool>` namespace.

Use `transport: openapi` only for REST/OpenAPI servers. Omit it for native
Streamable HTTP/SSE MCP endpoints. OpenAPI targets expose operations only;
MCP resources, prompts, sampling, elicitation, and OAuth negotiation do not
apply.
