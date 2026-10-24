import {
  loadConfig,
  snapshot,
  approve,
  revoke,
  remove,
} from "../plugin-host.mjs";
import fs from "node:fs/promises";
import path from "node:path";
const [command, configPath, profile, id, digest, ...extra] =
  process.argv.slice(2);
if (
  !["inspect", "approve", "revoke", "remove"].includes(command) ||
  !configPath ||
  !profile ||
  !id ||
  extra.length ||
  (command === "approve" ? !digest : !!digest)
) {
  console.error(
    "Usage: node scripts/browser-plugin-owner.mjs inspect|revoke|remove CONFIG PROFILE ID\n       node scripts/browser-plugin-owner.mjs approve CONFIG PROFILE ID REVIEWED_SHA256",
  );
  process.exit(2);
}
let lock;
try {
  const config = await loadConfig(configPath);
  if (command === "inspect") {
    const { files, ...metadata } = await snapshot(config, profile, id);
    console.log(
      JSON.stringify(
        {
          ...metadata,
          assets: files.map(({ name, sha256 }) => ({ name, sha256 })),
        },
        null,
        2,
      ),
    );
  } else {
    const lockPath = path.join(config.store, "owner.lock");
    lock = await fs.open(lockPath, "wx", 0o600);
    try {
      if (command === "approve") await approve(config, profile, id, digest);
      else if (command === "remove") await remove(config, profile, id);
      else await revoke(config, profile, id);
      console.log(
        command === "approve"
          ? "Exact bundle approval verified; enable explicitly in Capabilities → Plugins."
          : "Approval revocation verified. Backend package untouched. Existing trusted JS requires a full page reload for realm reset.",
      );
    } finally {
      await lock.close();
      lock = null;
      await fs.unlink(lockPath);
    }
  }
} catch (error) {
  console.error(error.message);
  process.exitCode = 1;
}
