import { expect, test } from "@playwright/test";

const pages = ["/", "/votacoes", "/presenca", "/partidos", "/metodologia"];

test.describe("static pages", () => {
  for (const path of pages) {
    test(`${path} renders with visible content`, async ({ page }) => {
      const consoleErrors: string[] = [];
      page.on("console", (message) => {
        if (message.type() === "error") {
          consoleErrors.push(message.text());
        }
      });
      await page.goto(path);
      await expect(page.locator("main")).toBeVisible();
      await expect(page.getByRole("heading", { name: /404|not found/i })).toHaveCount(0);
      const screenshot = await page.locator("main").screenshot();
      expect(screenshot.length).toBeGreaterThan(12_000);
      expect(consoleErrors).toEqual([]);
    });
  }
});

test("screens fit the viewport without page scroll", async ({ page }) => {
  for (const path of pages) {
    await page.goto(path);
    await page.waitForLoadState("networkidle");
    const [scrollHeight, viewport] = await page.evaluate(() => [document.documentElement.scrollHeight, window.innerHeight]);
    expect(scrollHeight, `${path} deve caber na tela`).toBeLessThanOrEqual(viewport);
  }
});

test("a vereador's votes load on demand", async ({ page }) => {
  await page.goto("/");
  await page.waitForLoadState("networkidle");
  await expect.poll(async () => page.locator("table.ruled tbody tr").count(), { timeout: 15_000 }).toBeGreaterThan(0);
});

test("a votação lists who voted how", async ({ page }) => {
  await page.goto("/votacoes");
  await page.waitForLoadState("networkidle");
  await expect.poll(async () => page.locator("main ul li a").count(), { timeout: 15_000 }).toBeGreaterThan(10);
});

test("hotkeys switch screens", async ({ page }) => {
  await page.goto("/");
  await page.waitForLoadState("networkidle");
  await page.keyboard.press("2");
  await expect(page).toHaveURL(/\/votacoes/);
});
