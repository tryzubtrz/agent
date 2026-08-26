import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";
import { OWNER_SESSION_COOKIE, verifyOwnerSession } from "@/lib/owner-session";
import { MEMBER_SESSION_COOKIE, verifyMemberSession, type MemberSession } from "@/lib/member-session";

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

function can(member: MemberSession, path: string[], method: string): boolean {
  const top = path[0] || "";
  const route = path.join("/");
  const capabilities = new Set(member.capabilities);
  if (["vault", "policies", "access", "gateway", "actions", "approvals", "settings"].includes(top)) return false;
  if (route.includes("/approve") || route.includes("/reject")) return false;

  const readCapability: Record<string, string> = {
    tasks: "tasks.read", memory: "memory.read", audit: "audit.read", connectors: "connectors.read", models: "models.read",
    system: "connectors.read", market: "models.read", calendar: "calendar.read", contacts: "contacts.read", notifications: "notifications.read",
    conversation: "conversation", documents: "documents", knowledge: "knowledge", research: "knowledge", automations: "automations",
  };
  if (method === "GET" || method === "HEAD") {
    const required = readCapability[top];
    return Boolean(required && (capabilities.has(required) || capabilities.has(top)));
  }

  if ((top === "knowledge" || top === "research") && method === "POST") return capabilities.has("knowledge");
  if (member.role !== "operator") return false;
  const writeCapability: Record<string, string> = {
    tasks: "tasks.write", conversation: "conversation", documents: "documents", calendar: "calendar", contacts: "contacts",
    automations: "automations", notifications: "notifications",
  };
  const required = writeCapability[top];
  return Boolean(required && capabilities.has(required));
}

async function memberStillActive(member: MemberSession): Promise<boolean> {
  try {
    const response = await fetch(`${coreBaseUrl()}/api/access/members/${encodeURIComponent(member.memberId)}`, {
      headers: { "accept": "application/json", "authorization": `Bearer ${coreToken()}` }, cache: "no-store",
    });
    if (!response.ok) return false;
    const data = await response.json() as { active?: boolean };
    return data.active === true;
  } catch { return false; }
}

async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const cookieStore = await cookies();
  const owner = verifyOwnerSession(cookieStore.get(OWNER_SESSION_COOKIE)?.value);
  const member = owner ? null : verifyMemberSession(cookieStore.get(MEMBER_SESSION_COOKIE)?.value);
  if (!owner && !member) return NextResponse.json({ error: "Authentication required" }, { status: 401, headers: { "cache-control": "no-store" } });

  try {
    const { path } = await context.params;
    const method = request.method.toUpperCase();
    if (member) {
      if (!can(member, path, method)) return NextResponse.json({ error: "This role cannot perform this action" }, { status: 403, headers: { "cache-control": "no-store" } });
      if (!(await memberStillActive(member))) return NextResponse.json({ error: "Member session is inactive" }, { status: 401, headers: { "cache-control": "no-store" } });
    }

    const suffix = path.map(encodeURIComponent).join("/");
    const target = `${coreBaseUrl()}/api/${suffix}${request.nextUrl.search}`;
    const headers = new Headers();
    const contentType = request.headers.get("content-type");
    if (contentType) headers.set("content-type", contentType);
    headers.set("accept", "application/json");
    headers.set("authorization", `Bearer ${coreToken()}`);
    headers.set("x-alter-actor-role", owner ? "owner" : member!.role);
    headers.set("x-alter-actor-id", owner ? "owner" : member!.memberId);

    const body = method === "GET" || method === "HEAD" ? undefined : await request.text();
    const response = await fetch(target, { method, headers, body, cache: "no-store", redirect: "manual" });
    const text = await response.text();
    const responseHeaders = new Headers();
    const upstreamType = response.headers.get("content-type");
    if (upstreamType) responseHeaders.set("content-type", upstreamType);
    responseHeaders.set("cache-control", "no-store");
    return new NextResponse(text, { status: response.status, headers: responseHeaders });
  } catch (error) {
    console.error("ALTER Core proxy error", error);
    return NextResponse.json({ error: "ALTER Core proxy is not configured or unavailable" }, { status: 503, headers: { "cache-control": "no-store" } });
  }
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
