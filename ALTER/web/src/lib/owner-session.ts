import { createHmac, timingSafeEqual } from "crypto";

export const OWNER_SESSION_COOKIE = "alter_owner_session";
const SESSION_TTL_SECONDS = 60 * 60 * 24 * 7;

function secret(): string {
  const value = process.env.ALTER_CORE_TOKEN?.trim();
  if (!value) throw new Error("ALTER_CORE_TOKEN is not configured");
  return value;
}

function signature(expiresAt: number): string {
  return createHmac("sha256", secret()).update(`owner:${expiresAt}`).digest("hex");
}

export function createOwnerSession(): { value: string; maxAge: number } {
  const expiresAt = Math.floor(Date.now() / 1000) + SESSION_TTL_SECONDS;
  return { value: `v1.${expiresAt}.${signature(expiresAt)}`, maxAge: SESSION_TTL_SECONDS };
}

export function verifyOwnerSession(value: string | undefined): boolean {
  if (!value) return false;
  const [version, rawExpiry, rawSignature] = value.split(".");
  if (version !== "v1" || !rawExpiry || !rawSignature) return false;
  const expiresAt = Number(rawExpiry);
  if (!Number.isFinite(expiresAt) || expiresAt < Math.floor(Date.now() / 1000)) return false;
  const expected = signature(expiresAt);
  const actualBuffer = Buffer.from(rawSignature, "utf8");
  const expectedBuffer = Buffer.from(expected, "utf8");
  return actualBuffer.length === expectedBuffer.length && timingSafeEqual(actualBuffer, expectedBuffer);
}

export function verifyOwnerAccessKey(candidate: string): boolean {
  const expected = (process.env.ALTER_WEB_PIN || process.env.ALTER_CORE_TOKEN || "").trim();
  const actual = candidate.trim();
  if (!expected || !actual) return false;
  const actualBuffer = Buffer.from(actual, "utf8");
  const expectedBuffer = Buffer.from(expected, "utf8");
  return actualBuffer.length === expectedBuffer.length && timingSafeEqual(actualBuffer, expectedBuffer);
}
