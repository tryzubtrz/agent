import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { OWNER_SESSION_COOKIE, verifyOwnerSession } from "@/lib/owner-session";
import { MEMBER_SESSION_COOKIE, verifyMemberSession } from "@/lib/member-session";

export const dynamic = "force-dynamic";

export async function GET() {
  const store = await cookies();
  if (verifyOwnerSession(store.get(OWNER_SESSION_COOKIE)?.value)) {
    return NextResponse.json({ authenticated: true, role: "owner", capabilities: ["*"] }, { status: 200, headers: { "cache-control": "no-store" } });
  }
  const member = verifyMemberSession(store.get(MEMBER_SESSION_COOKIE)?.value);
  if (member) {
    return NextResponse.json({ authenticated: true, role: member.role, member_id: member.memberId, capabilities: member.capabilities }, { status: 200, headers: { "cache-control": "no-store" } });
  }
  return NextResponse.json({ authenticated: false }, { status: 401, headers: { "cache-control": "no-store" } });
}
