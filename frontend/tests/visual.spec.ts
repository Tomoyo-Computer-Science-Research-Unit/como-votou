import { expect, test, type Page, type TestInfo } from "@playwright/test";

const pages = ["/", "/votacoes", "/presenca", "/partidos", "/metodologia"];
type Meta = { slug: string; prefix: string; nome: string; nivel: number };

function meta(info: TestInfo): Meta {
  return info.project.metadata as Meta;
}

/** Endereço da tela na cidade do projeto ("" = Rio, "/sp", "/rj/<slug>"). */
function at(info: TestInfo, path: string): string {
  return `${meta(info).prefix}${path === "/" ? "/" : `${path}/`}`;
}

// O Discord flutuante vem da raiz do g0v em produção; aqui não existe.
test.beforeEach(async ({ page }) => {
  await page.route("**/discord-float.js", (route) => route.fulfill({ status: 200, contentType: "text/javascript", body: "" }));
});

async function ready(page: Page) {
  await page.waitForLoadState("networkidle");
  await expect(page.locator("main")).not.toContainText("CARREGANDO");
}

test.describe("static pages", () => {
  for (const path of pages) {
    test(`${path} renders with visible content`, async ({ page }, info) => {
      const consoleErrors: string[] = [];
      page.on("console", (message) => {
        if (message.type() === "error") {
          consoleErrors.push(message.text());
        }
      });
      await page.goto(at(info, path));
      await ready(page);
      await expect(page.getByRole("heading", { name: /404|not found/i })).toHaveCount(0);
      const screenshot = await page.locator("main").screenshot();
      expect(screenshot.length).toBeGreaterThan(meta(info).nivel === 0 ? 5_000 : 12_000);
      expect(consoleErrors).toEqual([]);
    });
  }
});

test("screens fit the viewport without page scroll", async ({ page }, info) => {
  for (const path of pages) {
    await page.goto(at(info, path));
    await ready(page);
    const [scrollHeight, viewport] = await page.evaluate(() => [document.documentElement.scrollHeight, window.innerHeight]);
    expect(scrollHeight, `${path} deve caber na tela`).toBeLessThanOrEqual(viewport);
  }
});

test("a vereador's votes load on demand", async ({ page }, info) => {
  test.skip(meta(info).nivel < 3, "sem votos nominais");
  await page.goto(at(info, "/"));
  await ready(page);
  await expect.poll(async () => page.locator("table.ruled tbody tr").count(), { timeout: 15_000 }).toBeGreaterThan(0);
});

test("a votação lists who voted how", async ({ page }, info) => {
  test.skip(meta(info).nivel < 3, "sem votos nominais");
  await page.goto(at(info, "/votacoes"));
  await ready(page);
  await expect.poll(async () => page.locator("main ul li a").count(), { timeout: 15_000 }).toBeGreaterThan(3);
});

test("level 0 lists the TSE vereadores and says once that votes are not published", async ({ page }, info) => {
  test.skip(meta(info).nivel > 0, "só nível 0");
  await page.goto(at(info, "/"));
  await ready(page);
  await expect.poll(async () => page.getByRole("listbox", { name: "Vereadores" }).getByRole("option").count()).toBeGreaterThan(5);
  await page.goto(at(info, "/votacoes"));
  await ready(page);
  await expect(page.locator("main")).toContainText("Esta câmara não publica votações em formato legível.");
});

test("hotkeys switch screens within the city", async ({ page }, info) => {
  await page.goto(at(info, "/"));
  await ready(page);
  await page.keyboard.press("2");
  await expect(page).toHaveURL(new RegExp(`${meta(info).prefix}/votacoes/$`));
});

test("the city search sits left of the theme button; typing a name opens the same screen there", async ({ page }, info) => {
  await page.goto(at(info, "/presenca"));
  await ready(page);
  const search = page.getByRole("combobox", { name: "Cidade" });
  await expect(search).toHaveValue(meta(info).nome);
  const searchBox = await search.boundingBox();
  const themeBox = await page.getByRole("button", { name: /Usar tema/ }).boundingBox();
  expect(searchBox && themeBox && searchBox.x + searchBox.width <= themeBox.x).toBeTruthy();
  const target = meta(info).slug === "macuco" ? { nome: "Volta Redonda", url: "/rj/volta-redonda/presenca/$" } : { nome: "Macuco", url: "/rj/macuco/presenca/$" };
  await search.click();
  await search.fill(target.nome.slice(0, 5).toLowerCase());
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(new RegExp(target.url));
});

test("u goes to the next city on the same screen", async ({ page }, info) => {
  await page.goto(at(info, "/votacoes"));
  await ready(page);
  const before = page.url();
  await page.keyboard.press("u");
  await expect(page).not.toHaveURL(before);
  await expect(page).toHaveURL(/\/votacoes\/$/);
});
