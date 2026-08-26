import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { OWNER_SESSION_COOKIE, verifyOwnerSession } from "@/lib/owner-session";

export const dynamic = "force-dynamic";

export async function GET() {
  const store = await cookies();
  const authenticated = verifyOwnerSession(store.get(OWNER_SESSION_COOKIE)?.value);
  return NextResponse.json({ authenticated }, { status: authenticated ? 200 : 401, headers: { "cache-control": "no-store" } });
}
