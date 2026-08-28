import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";

function config() {
  const coreUrl = process.env.ALTER_CORE_URL?.trim().replace(/\/$/, "");
  const coreToken = process.env.ALTER_CORE_TOKEN?.trim();
  if (!coreUrl || !coreToken) return null;
  return { coreUrl, coreToken };
}

export async function GET() {
  const runtime = config();
  if (!runtime) {
    return NextResponse.json(
      { ready: false, core: "not_configured" },
      { status: 503, headers: { "cache-control": "no-store" } },
    );
  }

  try {
    const headers = {
      accept: "application/json",
      authorization: `Bearer ${runtime.coreToken}`,
    };
    const [healthResponse, principalResponse] = await Promise.all([
      fetch(`${runtime.coreUrl}/api/health`, { headers, cache: "no-store" }),
      fetch(`${runtime.coreUrl}/api/auth/me`, { headers, cache: "no-store" }),
    ]);
    if (!healthResponse.ok || !principalResponse.ok) {
      return NextResponse.json(
        { ready: false, core: "authentication_or_health_failed" },
        { status: 503, headers: { "cache-control": "no-store" } },
      );
    }

    const health = (await healthResponse.json()) as { status?: string; storage?: string; version?: string };
    const principal = (await principalResponse.json()) as { actor_role?: string };
    const ready = health.status === "ok" && principal.actor_role === "owner";
    return NextResponse.json(
      {
        ready,
        core: ready ? "connected" : "degraded",
        storage: health.storage ?? "unknown",
        version: health.version ?? "unknown",
        owner_auth: principal.actor_role === "owner",
      },
      { status: ready ? 200 : 503, headers: { "cache-control": "no-store" } },
    );
  } catch {
    return NextResponse.json(
      { ready: false, core: "unreachable" },
      { status: 503, headers: { "cache-control": "no-store" } },
    );
  }
}
