// Render each Section 3 SVG figure to a 2x PNG for pasting into documents.
import { readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { createRequire } from "node:module";

const { chromium } = createRequire(import.meta.url)("playwright");
const dir = dirname(fileURLToPath(import.meta.url));
const browser = await chromium.launch();
const page = await browser.newPage({ deviceScaleFactor: 2 });
for (const name of readdirSync(dir).filter((f) => f.endsWith(".svg"))) {
  await page.goto(pathToFileURL(join(dir, name)).href);
  await page.locator("svg").screenshot({ path: join(dir, name.replace(/\.svg$/, ".png")) });
}
await browser.close();
