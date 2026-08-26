import { createHmac, timingSafeEqual } from "crypto";

export const MEMBER_SESSION_COOKIE = "alter_member_session";
const TTL_SECONDS = 60 * 60 * 24 * 7;
export type MemberRole = "operator" | "viewer";
export type MemberSession = { memberId: string; role: MemberRole; capabilities: string[]; expiresAt: number };

function secret(): string {
  const value = process.env.ALTER_CORE_TOKEN?.trim();
  if (!value) throw new Error("ALTER_CORE_TOKEN is not configured");
  return value;
}

function encodedCapabilities(capabilities: string[]): string {
  return Buffer.from(JSON.stringify([...new Set(capabilities)].sort()), "utf8").toString("base64url");
}

function signature(memberId: string, role: string, capabilities: string, expiresAt: number): string {
  return createHmac("sha256", secret()).update(`member:${memberId}:${role}:${capabilities}:${expiresAt}`).digest("hex");
}

export function createMemberSession(memberId: string, role: MemberRole, capabilities: string[]) {
  const expiresAt = Math.floor(Date.now() / 1000) + TTL_SECONDS;
  const caps = encodedCapabilities(capabilities);
  const sig = signature(memberId, role, caps, expiresAt);
  return { value: `v1.${memberId}.${role}.${caps}.${expiresAt}.${sig}`, maxAge: TTL_SECONDS };
}

export function verifyMemberSession(value: string | undefined): MemberSession | null {
  if (!value) return null;
  const parts = value.split(".");
  if (parts.length !== 6 || parts[0] !== "v1") return null;
  const [, memberId, roleRaw, capsRaw, expiryRaw, supplied] = parts;
  if (!memberId || (roleRaw !== "operator" && roleRaw !== "viewer")) return null;
  const expiresAt = Number(expiryRaw);
  if (!Number.isFinite(expiresAt) || expiresAt < Math.floor(Date.now() / 1000)) return null;
  const expected = signature(memberId, roleRaw, capsRaw, expiresAt);
  const a = Buffer.from(supplied, "utf8");
  const b = Buffer.from(expected, "utf8");
  if (a.length !== b.length || !timingSafeEqual(a, b)) return null;
  try {
    const parsed = JSON.parse(Buffer.from(capsRaw, "base64url").toString("utf8"));
    if (!Array.isArray(parsed) || !parsed.every((item) => typeof item === "string")) return null;
    return { memberId, role: roleRaw, capabilities: parsed, expiresAt };
  } catch {
    return null;
  }
}
