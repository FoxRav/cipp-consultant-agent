import { expect, test } from "@playwright/test";

test("frontend playground works with mock API", async ({ page }) => {
  await page.goto("/?mock=1");

  await expect(page.getByRole("heading", { name: "CIPP Consultant Agent" })).toBeVisible();
  await expect(page.getByText("api: ok")).toBeVisible();
  await expect(page.getByLabel("Auth prototype")).toBeVisible();
  await expect(page.getByText("Mock auth")).toBeVisible();
  await page.getByLabel("Auth email").fill("board@example.test");
  await page.getByLabel("Auth password").fill("local-password");
  await page.getByRole("button", { name: "Login" }).click();
  await expect(page.getByText("board@example.test")).toBeVisible();

  const expectedFields = [
    "Asuntoja",
    "Rakennuksia",
    "Porrashuoneita",
    "JV-pystyviemäreitä",
    "SV-pystyviemäreitä",
    "Pohjaviemäri m",
    "Tonttilinja m",
    "Sadevesilinjat m",
    "Kattokaivot"
  ];
  const caseBar = page.getByLabel("Taloyhtiön perustiedot");
  for (const label of expectedFields) {
    await expect(caseBar.getByText(label, { exact: true })).toBeVisible();
  }
  await expect(caseBar.getByText("Videotarkastus", { exact: true })).not.toBeVisible();
  await expect(caseBar.getByText("Yksikköhinnat / lisätyöt", { exact: true })).not.toBeVisible();
  await expect(page.getByRole("button", { name: "Videotarkastus" })).not.toBeVisible();
  await expect(page.getByRole("button", { name: "Lisätyöt" })).not.toBeVisible();

  await expect(page.getByLabel("Asuntoja")).toHaveValue("30");
  await expect(page.getByLabel("Rakennuksia")).toHaveValue("1");
  await expect(page.getByLabel("Porrashuoneita")).toHaveValue("3");
  await expect(page.getByLabel("JV-pystyviemäreitä")).toHaveValue("15");
  await expect(page.getByLabel("Pohjaviemäri m")).toHaveValue("50");
  await expect(page.getByLabel("Tonttilinja m")).toHaveValue("30");
  await expect(page.getByLabel("Sadevesilinjat m")).toHaveValue("30");

  const apartments = page.getByLabel("Asuntoja");
  await apartments.fill("42");
  await expect(apartments).toHaveValue("42");

  const jvVerticals = page.getByLabel("JV-pystyviemäreitä");
  await jvVerticals.fill("11");
  await expect(jvVerticals).toHaveValue("11");

  const svVerticals = page.getByLabel("SV-pystyviemäreitä");
  await expect(svVerticals).toHaveValue("4");

  const roofDrains = page.getByLabel("Kattokaivot");
  await expect(roofDrains).toHaveValue("4");
  await roofDrains.fill("6");
  await expect(roofDrains).toHaveValue("6");

  await page.getByRole("button", { name: "Reset defaults" }).click();
  await expect(svVerticals).toHaveValue("4");
  await expect(roofDrains).toHaveValue("4");

  await apartments.fill("42");
  await jvVerticals.fill("11");
  await roofDrains.fill("6");

  await page.getByLabel("Kysy CIPP-/sukitusurakasta").fill("Paljonko yllä kuvatun taloyhtiön urakka maksaa?");
  await page.getByLabel("Show debug packet").check();
  await page.getByRole("button", { name: "Lähetä" }).click();

  await expect(page.getByRole("heading", { name: "Vastaus" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Arviossa käytetty case" })).toBeVisible();
  const caseUsed = page.locator(".case-used");
  await expect(caseUsed.getByText("Kattokaivot")).toBeVisible();
  await expect(caseUsed.getByText("6", { exact: true })).toBeVisible();
  await expect(page.getByText("4 SV-pystyviemäriä ja 6 kattokaivoa")).toBeVisible();
  await expect(page.getByText("llm_used=false")).toBeVisible();
  const sourcesPanel = page.getByRole("heading", { name: "Lähteet" }).locator("..");
  await expect(page.getByRole("heading", { name: "Lähteet" })).toBeVisible();
  await expect(sourcesPanel.getByText("reference_001", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { level: 2, name: "Epävarmuudet" })).toBeVisible();
  await expect(page.locator("li").filter({ hasText: "includes_yard_line" })).toBeVisible();

  await expect(page.locator(".debug-panel summary")).toHaveText("Show debug packet");
  await page.locator(".debug-panel summary").click();
  await expect(page.getByText('"mock_api": true')).toBeVisible();

  const bodyText = await page.locator("body").innerText();
  expect(bodyText).not.toContain("F:\\");
  expect(bodyText).not.toContain("C:\\");
  expect(bodyText).not.toContain(".pdf");
  expect(bodyText).not.toContain(".docx");
  expect(bodyText).not.toContain(".xlsx");
  expect(bodyText).not.toContain(".csv");
  expect(bodyText).not.toContain("As Oy ");

  await page.getByRole("button", { name: "Logout" }).click();
  await expect(page.getByRole("button", { name: "Login" })).toBeVisible();
});

test("frontend shows actionable diagnostics when API is offline", async ({ page }) => {
  await page.goto("/?apiBase=http://127.0.0.1:9");

  await expect(page.getByRole("heading", { name: "CIPP Consultant Agent" })).toBeVisible();
  await expect(page.getByText("api: offline")).toBeVisible();
  await expect(page.getByText("API-yhteys epäonnistui.")).toBeVisible();
  await expect(page.getByText("cipp-run-dev-api --host 127.0.0.1 --port 8000")).toBeVisible();

  await page.getByLabel("Kysy CIPP-/sukitusurakasta").fill(
    "Mitä maksueristä kannattaa sopia CIPP-sukitusurakassa?"
  );
  await page.getByRole("button", { name: "Lähetä" }).click();

  await expect(page.getByText("Endpoint: /api/answer")).toBeVisible();
  await expect(page.getByText("API base URL: http://127.0.0.1:9")).toBeVisible();
  const bodyText = await page.locator("body").innerText();
  expect(bodyText).not.toContain("Failed to fetch");
  expect(bodyText).not.toContain("TypeError");
  expect(bodyText).not.toContain("Traceback");
});
