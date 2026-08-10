import { cp, mkdir, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const source = path.join(root, "apps", "dashboard");
const destination = path.join(root, "dist");

await rm(destination, { recursive: true, force: true });
await mkdir(destination, { recursive: true });

for (const file of ["index.html", "app.js", "styles.css"]) {
  await cp(path.join(source, file), path.join(destination, file));
}

const apiBase = process.env.HYDROSL_API_BASE || "";
const dataBase = process.env.HYDROSL_DATA_BASE || "./data";
await writeFile(
  path.join(destination, "config.js"),
  `window.HYDROSL_API_BASE = ${JSON.stringify(apiBase)};\n` +
    `window.HYDROSL_DATA_BASE = ${JSON.stringify(dataBase)};\n`,
  "utf8",
);
