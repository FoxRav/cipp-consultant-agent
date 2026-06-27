import { expect, test } from "@playwright/test";

test("frontend playground works with mock API", async ({ page }) => {
  await page.goto("/?mock=1");

  await expect(page.getByRole("heading", { name: "CIPP Consultant Agent" })).toBeVisible();

  const expectedFields = [
    "Asuntoja",
    "Rakennuksia",
    "Porrashuoneita",
    "JV-pystyviemäreitä",
    "SV-pystyviemäreitä",
    "Pohjaviemäri m",
    "Tonttilinja m",
    "Sadevesilinjat m",
    "Kattokaivot",
    "Videotarkastus",
    "Yksikköhinnat / lisätyöt"
  ];
  const caseBar = page.getByLabel("Taloyhtiön perustiedot");
  for (const label of expectedFields) {
    await expect(caseBar.getByText(label, { exact: true })).toBeVisible();
  }

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

  await page.getByLabel("Kysy CIPP-/sukitusurakasta").fill(
    "Mitä pitää huomioida taloyhtiön JV-pystylinjojen ja pohjaviemärin sukituksessa?"
  );
  await page.getByLabel("Show debug packet").check();
  await page.getByRole("button", { name: "Lähetä" }).click();

  await expect(page.getByRole("heading", { name: "Vastaus" })).toBeVisible();
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
});
