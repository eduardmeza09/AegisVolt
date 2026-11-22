import { describe, expect, it } from "vitest";
import { plannedSteps, sagaTone, shortId, timeAgo } from "./lib";

// resolveGraphqlUrl vive en api.ts (usa window); se prueba la misma lógica aquí sin DOM.
function resolve(pathname: string) {
  const i = pathname.lastIndexOf("/web");
  return `${i >= 0 ? pathname.slice(0, i) : ""}/graphql`;
}

describe("endpoint por ambiente", () => {
  it("deriva GraphQL del path del API Gateway", () => {
    expect(resolve("/restapis/abc123/test/_user_request_/web/")).toBe("/restapis/abc123/test/_user_request_/graphql");
  });
  it("en desarrollo usa /graphql", () => {
    expect(resolve("/")).toBe("/graphql");
  });
});

describe("saga", () => {
  it("clasifica estados", () => {
    expect(sagaTone("COMPLETED")).toBe("ok");
    expect(sagaTone("COMPENSATED")).toBe("warn");
    expect(sagaTone("COMPENSATION_FAILED")).toBe("bad");
    expect(sagaTone("FUNDS_HELD")).toBe("info");
  });

  it("muestra los 3 pasos y añade compensaciones en orden", () => {
    const steps = [
      { name: "RESERVE_CONNECTOR", service: "s", status: "SUCCEEDED", detail: null, at: null, idempotentReplay: null },
      { name: "HOLD_FUNDS", service: "b", status: "FAILED", detail: null, at: null, idempotentReplay: null },
      { name: "COMPENSATE_RELEASE", service: "s", status: "COMPENSATED", detail: null, at: null, idempotentReplay: false },
    ];
    expect(plannedSteps(steps).map((p) => [p.name, p.step?.status ?? "PENDING"])).toEqual([
      ["RESERVE_CONNECTOR", "SUCCEEDED"],
      ["HOLD_FUNDS", "FAILED"],
      ["START_CHARGING", "PENDING"],
      ["COMPENSATE_RELEASE", "COMPENSATED"],
    ]);
  });
});

describe("formato", () => {
  it("acorta ids", () => expect(shortId("9cc09fa0-6d49-4a2c-9250-0da6db9ecfd5")).toBe("9cc09fa0…cfd5"));
  it("tiempo relativo", () => expect(timeAgo("2026-01-01T00:00:00Z", Date.parse("2026-01-01T00:00:30Z"))).toBe("hace 30 s"));
});
