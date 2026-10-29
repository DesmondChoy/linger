// Render every SVG in ../figures to a PNG at twice its size.
// Run from the repository root: node docs/report/revised/tools/render_svgs.mjs [name ...]
import { readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const figures = join(dirname(fileURLToPath(import.meta.url)), "..", "figures");
const only = new Set(process.argv.slice(2));
const names = readdirSync(figures)
  .filter((file) => file.endsWith(".svg"))
  .filter((file) => only.size === 0 || only.has(file.replace(/\.svg$/, "")));

const browser = await chromium.launch();
const page = await browser.newPage({ deviceScaleFactor: 2 });
for (const file of names) {
  const svg = readFileSync(join(figures, file), "utf8");
  await page.setContent(`<!doctype html><html><body style="margin:0;background:#fff">${svg}</body></html>`);
  await page.evaluate(() => document.fonts.ready);
  await page.locator("svg").first().screenshot({ path: join(figures, file.replace(/\.svg$/, ".png")) });
  console.log(`rendered ${file}`);
}
await browser.close();
