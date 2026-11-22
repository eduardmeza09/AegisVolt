import { expect, type Page, test } from "@playwright/test";

// Flujo completo DESDE EL FRONTEND: el usuario opera la UI y se verifica el resultado de la SAGA
// (éxito, fondos insuficientes y fallo de hardware con compensación + reintento idempotente).
const ADMIN_TOKEN = process.env.ADMIN_TOKEN ?? "local-admin";
const FLAG_FAULT = "Fallo de hardware";

test.describe.configure({ mode: "serial" });

async function open(page: Page) {
  await page.goto("./");
  await expect(page.locator(".env-pill .led.on")).toBeVisible();
  await expect(page.locator(".station").first()).toBeVisible();
}

async function setFault(page: Page, on: boolean) {
  const flags = page.locator("#flags");
  await flags.scrollIntoViewIfNeeded();
  if (await flags.getByRole("button", { name: "Modo administrador" }).isVisible()) {
    await flags.getByRole("button", { name: "Modo administrador" }).click();
  }
  await flags.locator('input[type="password"]').fill(ADMIN_TOKEN);
  const card = flags.locator(".flag", { hasText: FLAG_FAULT });
  const wanted = on ? "ACTIVO" : "INACTIVO";
  if ((await card.locator(".flag-state b").textContent())?.trim() !== wanted) {
    await card.getByRole("button", { name: on ? "Activar" : "Desactivar" }).click();
  }
  await expect(card.locator(".flag-state b")).toHaveText(wanted);
  await page.waitForTimeout(6_000); // los servicios releen los flags cada 5 s (sin redespliegue)
}

async function reserve(page: Page, fleetId: string) {
  // Clic en un conector disponible del panel => queda preseleccionado en el formulario
  await page.locator(".conn-available").first().click();
  const form = page.locator("#reservar form");
  await form.locator("label", { hasText: "Flota" }).locator("select").selectOption(fleetId);
  await form.getByRole("button", { name: "Reservar y activar carga" }).click();
  await expect(page.locator("#reservar .result")).toBeVisible();
}

test("muestra estaciones, ambiente y flags del ambiente", async ({ page }) => {
  await open(page);
  await expect(page.locator(".env-pill")).not.toHaveText("…");
  await expect(page.locator("#flags .flag")).toHaveCount(3);
  await expect(page.locator(".conn-available").first()).toBeVisible();
});

test("éxito: reserva -> carga activa -> detener desde el historial", async ({ page }) => {
  await open(page);
  await setFault(page, false);
  await reserve(page, "fleet-rapido");
  await expect(page.locator("#reservar .result b")).toHaveText("Cargando");
  await expect(page.locator("#reservar .step.tone-ok")).toHaveCount(3);

  const row = page.locator("#historial .trow").first();
  await expect(row.locator(".badge")).toHaveText("Cargando");
  await row.locator(".trow-head").click();
  await row.getByRole("button", { name: "Detener carga" }).click();
  await expect(row.locator(".badge")).toHaveText("Finalizada");
});

test("fondos insuficientes: la SAGA libera el conector (compensación del paso 2)", async ({ page }) => {
  await open(page);
  await reserve(page, "fleet-sinfondos");
  await expect(page.locator("#reservar .result b")).toHaveText("Compensada");
  await expect(page.locator("#reservar .result")).toContainText("Fondos insuficientes");
  await expect(page.locator("#reservar .step h4")).toHaveText(["Reservar conector", "Retener saldo", "Activar cargador", "Liberar conector"]);
});

test("fallo de hardware (flag desde la UI): reembolso + liberación y reintento idempotente", async ({ page }) => {
  await open(page);
  await setFault(page, true);
  try {
    await reserve(page, "fleet-rapido");
    await expect(page.locator("#reservar .result b")).toHaveText("Compensada");
    await expect(page.locator("#reservar .result")).toContainText("Fallo físico del cargador");
    await expect(page.locator("#reservar .step h4")).toHaveText([
      "Reservar conector", "Retener saldo", "Activar cargador", "Reembolsar saldo", "Liberar conector",
    ]);
    await expect(page.locator("#reservar .step.tone-bad")).toHaveCount(1);

    const row = page.locator("#historial .trow").first();
    await row.locator(".trow-head").click();
    await row.getByRole("button", { name: "Reintentar compensación" }).click();
    await expect(row.locator(".tag", { hasText: "idempotente" })).toHaveCount(2);
  } finally {
    await setFault(page, false);
  }
});
