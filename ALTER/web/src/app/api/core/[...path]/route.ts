import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
import { OWNER_SESSION_COOKIE, verifyOwnerSession } from "@/lib/owner-session";

export const dynamic = "force-dynamic";

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

async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const cookieStore = await cookies();
  if (!verifyOwnerSession(cookieStore.get(OWNER_SESSION_COOKIE)?.value)) {
    return NextResponse.json(
      { error: "Owner authentication required" },
      { status: 401, headers: { "cache-control": "no-store" } },
    );
  }

  try {
    const { path } = await context.params;
    const suffix = path.map(encodeURIComponent).join("/");
    const target = `${coreBaseUrl()}/api/${suffix}${request.nextUrl.search}`;

    const headers = new Headers();
    const contentType = request.headers.get("content-type");
    if (contentType) headers.set("content-type", contentType);
    headers.set("accept", "application/json");
    headers.set("authorization", `Bearer ${coreToken()}`);

    const method = request.method.toUpperCase();
    const body = method === "GET" || method === "HEAD" ? undefined : await request.text();

    const response = await fetch(target, {
      method,
      headers,
      body,
      cache: "no-store",
      redirect: "manual",
    });

    const text = await response.text();
    const responseHeaders = new Headers();
    const upstreamType = response.headers.get("content-type");
    if (upstreamType) responseHeaders.set("content-type", upstreamType);
    responseHeaders.set("cache-control", "no-store");

    return new NextResponse(text, {
      status: response.status,
      headers: responseHeaders,
    });
  } catch (error) {
    console.error("ALTER Core proxy error", error);
    return NextResponse.json(
      { error: "ALTER Core proxy is not configured or unavailable" },
      { status: 503, headers: { "cache-control": "no-store" } },
    );
  }
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
