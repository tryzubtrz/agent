import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const userAgent = request.headers.get("user-agent") || "";
  if (!userAgent.toLowerCase().includes("vercel-cron")) {
    return NextResponse.json({ error: "Not found" }, { status: 404, headers: { "cache-control": "no-store" } });
  }

  const base = process.env.ALTER_CORE_URL?.trim().replace(/\/$/, "");
  const token = process.env.ALTER_CORE_TOKEN?.trim();
  if (!base || !token) return NextResponse.json({ error: "ALTER Core is not configured" }, { status: 503 });

  try {
    const response = await fetch(`${base}/api/automations/tick`, {
      method: "POST",
      headers: { authorization: `Bearer ${token}`, accept: "application/json", "content-type": "application/json" },
      body: "{}",
      cache: "no-store",
    });
    const text = await response.text();
    return new NextResponse(text, { status: response.status, headers: { "content-type": response.headers.get("content-type") || "application/json", "cache-control": "no-store" } });
  } catch {
    return NextResponse.json({ error: "Automation tick failed" }, { status: 502, headers: { "cache-control": "no-store" } });
  }
}
