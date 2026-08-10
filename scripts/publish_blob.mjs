import { readdir, readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { put } from "@vercel/blob";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const source = path.join(root, "apps", "dashboard", "data");
const token = process.env.BLOB_READ_WRITE_TOKEN;

if (!token) {
  console.log("BLOB_READ_WRITE_TOKEN is not configured; skipping Blob publication.");
  process.exit(0);
}

async function filesIn(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const absolute = path.join(directory, entry.name);
    if (entry.isDirectory()) files.push(...(await filesIn(absolute)));
    else files.push(absolute);
  }
  return files;
}

const files = await filesIn(source);
let baseUrl = null;
for (const file of files) {
  const relative = path.relative(source, file).split(path.sep).join("/");
  const pathname = `hydrosl/${relative}`;
  const contentType = relative.endsWith(".json") ? "application/json; charset=utf-8" : undefined;
  const result = await put(pathname, await readFile(file), {
    access: "public",
    allowOverwrite: true,
    addRandomSuffix: false,
    cacheControlMaxAge: 300,
    contentType,
    token,
  });
  if (relative === "manifest.json") {
    baseUrl = result.url.slice(0, -"manifest.json".length);
  }
  console.log(`published ${relative}`);
}
if (baseUrl) console.log(`HYDROSL_DATA_BASE=${baseUrl}`);
