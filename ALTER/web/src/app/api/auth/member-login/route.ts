import { NextRequest, NextResponse } from "next/server";
import { createMemberSession, MEMBER_SESSION_COOKIE, type MemberRole } from "@/lib/member-session";

export const dynamic = "force-dynamic";

const NO_STORE = { "cache-control": "no-store" };

function coreBaseUrl(): string {
  const value = process.env.ALTER_CORE_URL?.trim();
  if (!value) throw new Error("ALTER_CORE_URL is not configured");
  return value.replace(/\/$/, "");
}

function coreToken(): string {
  const value = process.env.ALTER_CORE_TOKEN?.trim();
  if (!value) throw new Error("ALTER_CORE_TOKEN is not configured");
  return value;
}

export async function POST(request: NextRequest) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400, headers: NO_STORE });
  }

  const code = typeof body === "object" && body && "code" in body
    ? String((body as { code?: unknown }).code || "").trim()
    : "";
  if (!code) {
    return NextResponse.json({ error: "Invitation code required" }, { status: 400, headers: NO_STORE });
  }

  try {
    const upstream = await fetch(`${coreBaseUrl()}/api/access/redeem`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "accept": "application/json",
        "authorization": `Bearer ${coreToken()}`,
      },
      body: JSON.stringify({ code }),
      cache: "no-store",
    });

    const data = await upstream.json().catch(() => null) as null | {
      id?: string;
      role?: MemberRole;
      capabilities?: string[];
      active?: boolean;
      detail?: unknown;
    };

    if (!upstream.ok) {
      if (upstream.status === 429) {
        return NextResponse.json({ error: "Too many login attempts" }, { status: 429, headers: NO_STORE });
      }
      if (upstream.status >= 500) {
        return NextResponse.json({ error: "Member login unavailable" }, { status: 503, headers: NO_STORE });
      }
      return NextResponse.json({ error: "Invitation is invalid, expired, or already used" }, { status: 401, headers: NO_STORE });
    }

    if (!data?.id || (data.role !== "operator" && data.role !== "viewer") || !Array.isArray(data.capabilities) || data.active === false) {
      return NextResponse.json({ error: "Invitation is invalid, expired, or already used" }, { status: 401, headers: NO_STORE });
    }

    const session = createMemberSession(data.id, data.role, data.capabilities);
    const response = NextResponse.json(
      { authenticated: true, role: data.role, capabilities: data.capabilities },
      { headers: NO_STORE },
    );
    response.cookies.set(MEMBER_SESSION_COOKIE, session.value, {
      httpOnly: true,
      secure: true,
      sameSite: "strict",
      path: "/",
      maxAge: session.maxAge,
    });
    return response;
  } catch (error) {
    console.error("ALTER member login error", error);
    return NextResponse.json({ error: "Member login unavailable" }, { status: 503, headers: NO_STORE });
  }
}
