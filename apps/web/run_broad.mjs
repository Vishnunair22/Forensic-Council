// Sequentially runs the full flow on every broad-set image, resilient to a
// single failure, and prints a one-line verdict summary per image.
import { readdirSync } from "node:fs";
import { spawnSync } from "node:child_process";

const DIR = "d:/Forensic Council/test-images-broad";
const files = readdirSync(DIR).filter((f) => !f.endsWith(".json"));
console.log("BROAD SET:", files.length, "images\n");

for (const f of files) {
  const label = "b_" + f.replace(/\.[^.]+$/, "").replace(/[^a-zA-Z0-9]/g, "_");
  process.stdout.write(`=== ${label} ... `);
  const r = spawnSync("node", ["browser_full_flow.mjs", `${DIR}/${f}`, label], {
    cwd: "d:/Forensic Council/apps/web",
    encoding: "utf8",
    timeout: 400000,
  });
  const out = (r.stdout || "") + (r.stderr || "");
  if (r.status !== 0 || /ERROR:/.test(out)) {
    const errLine = (out.match(/ERROR:[^\n]*/) || ["(unknown error)"])[0];
    console.log(`FAILED — ${errLine.slice(0, 80)}`);
  } else {
    console.log("done");
  }
}
console.log("\nBATCH COMPLETE");
