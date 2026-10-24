// Browser-only loader. Never imports the native disk evaluator.
import { atom } from "nanostores";
import { $apiRequestScope, getApiRequestProfile } from "@/api/client";
import {
  createPluginContext,
  type HermesPlugin,
  type PluginContext,
} from "@/contrib/plugin";
import {
  $pluginRecords,
  dropPlugin,
  publishPlugin,
} from "@/contrib/plugins-store";
import { installPluginSdk, sdkImportMap } from "@/sdk/runtime";
import { BrowserPluginRuntime } from "./browser-plugin-runtime.mjs";
import { rewriteModule } from "./plugin-module.mjs";
export const $diskPluginsScanPending = atom(false);
const report = (error: unknown) =>
  window.dispatchEvent(
    new CustomEvent("hermes-capability-error", {
      detail: `Browser plugin: ${error instanceof Error ? error.message : String(error)}`,
    }),
  );
const scope = () => getApiRequestProfile() || "default";
let suspended = false;
const request = async (url: string) => {
  if (suspended) throw Error("Browser plugin host suspended until page reload");
  const response = await fetch(url, {
    credentials: "same-origin",
    cache: "no-store",
    redirect: "error",
    signal: AbortSignal.timeout(10000),
  });
  if (response.status === 401)
    window.dispatchEvent(new Event("hermes-auth-required"));
  if (!response.ok)
    throw Object.assign(Error(`Plugin delivery HTTP ${response.status}`), {
      status: response.status,
    });
  return response.json();
};
function guardContext(
  ctx: PluginContext,
  alive: () => boolean,
  namespace: string,
): PluginContext {
  const guard = (target: object): object =>
    new Proxy(target, {
      get(object, key) {
        const value = Reflect.get(object, key);
        if (typeof value === "function")
          return (...args: unknown[]) => {
            if (!alive())
              throw Error("Plugin context disposed or profile changed");
            return Reflect.apply(value, object, args);
          };
        return value && typeof value === "object" ? guard(value) : value;
      },
    });
  const storage: PluginContext["storage"] = {
    get: (key, fallback) => ctx.storage.get(namespace + key, fallback),
    set: (key, value) => ctx.storage.set(namespace + key, value),
    remove: (key) => ctx.storage.remove(namespace + key),
  };
  return guard({
    ...ctx,
    storage,
    os: {
      ...ctx.os,
      notify: () =>
        report("Native notifications are unavailable in the browser"),
      revealPath: async () => false,
      pickOpenPath: async () => null,
      pickSavePath: async () => null,
    },
  }) as PluginContext;
}
const runtime = new BrowserPluginRuntime({
  scope,
  request,
  reserved: (id: string) => !!$pluginRecords.get()[id],
  drop: (id: string) => dropPlugin(id),
  report,
  publish: (record: {
    id: string;
    name: string;
    description?: string;
    digest: string;
    approved: boolean;
    profile: string;
    status: "disabled" | "loaded" | "error";
    error?: string;
  }) =>
    publishPlugin(
      {
        id: record.id,
        name: record.name,
        description: `${record.description || ""} [Trusted app code · profile ${record.profile} · ${record.approved ? "owner approved" : "owner approval required"} · ${record.digest?.slice(0, 12) || "invalid bundle"}]`,
        kind: "runtime",
        status: record.status,
        error: record.error,
      },
      {
        activate: () => runtime.enable(record.id),
        deactivate: () => runtime.disable(record.id),
      },
    ),
  evaluate: async (
    source: string,
    record: { dispose: (() => void) | null },
    alive: () => boolean,
  ) => {
    installPluginSdk();
    const rewritten = rewriteModule(source, sdkImportMap());
    if (!alive()) throw Error("Plugin load cancelled");
    const url = URL.createObjectURL(
      new Blob([rewritten], { type: "text/javascript" }),
    );
    record.dispose = () => URL.revokeObjectURL(url);
    try {
      return await import(/* @vite-ignore */ url);
    } finally {
      URL.revokeObjectURL(url);
    }
  },
  activate: async (
    record: {
      id: string;
      principal: string;
      profile: string;
      dispose: (() => void) | null;
    },
    module: { default: HermesPlugin },
    alive: () => boolean,
  ) => {
    const disposers: (() => void)[] = [];
    const dispose = () => {
      for (const fn of disposers.splice(0).reverse()) {
        try {
          fn();
        } catch (error) {
          report(error);
        }
      }
    };
    record.dispose = dispose;
    const ctx = createPluginContext(record.id, (fn) => {
      if (alive()) disposers.push(fn);
      else fn();
    });
    try {
      await module.default.register(
        guardContext(ctx, alive, `${record.principal}.${record.profile}.`),
      );
      return dispose;
    } catch (error) {
      dispose();
      throw error;
    }
  },
});
export async function discoverRuntimePlugins(): Promise<void> {
  runtime.reset();
  await runtime.scan();
}
let watching = false;
export function watchRuntimePlugins(): void {
  if (watching) return;
  watching = true;
  $diskPluginsScanPending.set(true);
  void runtime.scan().finally(() => $diskPluginsScanPending.set(false));
  $apiRequestScope.listen(() => {
    runtime.reset();
    void runtime.scan();
  });
  window.addEventListener("hermes-auth-required", () => {
    suspended = true;
    runtime.reset();
  });
  window.addEventListener("hermes-browser-logout", () => {
    suspended = true;
    runtime.reset();
  });
  window.addEventListener("pagehide", () => runtime.reset());
  window.setInterval(() => void runtime.scan(), 2000);
}
export async function uninstallDiskPlugin(
  _pluginId: string,
): Promise<{ ok: boolean; error: string }> {
  return {
    ok: false,
    error:
      "Browser removal is owner-only: revoke approval with browser-plugin-owner.mjs; backend packages are never deleted.",
  };
}
