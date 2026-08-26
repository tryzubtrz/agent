import { NextRequest, NextResponse } from "next/server";
import { OWNER_SESSION_COOKIE, createOwnerSession, verifyOwnerAccessKey } from "@/lib/owner-session";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  try {
    const body = (await request.json()) as { token?: string };
    if (!body.token || !verifyOwnerAccessKey(body.token)) {
      return NextResponse.json({ authenticated: false }, { status: 401, headers: { "cache-control": "no-store" } });
    }

    const session = createOwnerSession();
    const response = NextResponse.json({ authenticated: true }, { headers: { "cache-control": "no-store" } });
    response.cookies.set(OWNER_SESSION_COOKIE, session.value, {
      httpOnly: true,
      secure: true,
      sameSite: "strict",
      path: "/",
      maxAge: session.maxAge,
    });
    return response;
  } catch {
    return NextResponse.json({ authenticated: false }, { status: 400, headers: { "cache-control": "no-store" } });
  }
}
