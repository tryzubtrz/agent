import { createHash, createHmac, timingSafeEqual } from "crypto";

export const OWNER_SESSION_COOKIE = "alter_owner_session";
const SESSION_TTL_SECONDS = 60 * 60 * 24 * 7;
const BOOTSTRAP_ACCESS_KEY_SHA256 = "a3275edca2646c9e271ef59c22f3cda66019e7410b4434032a6418de7b03341c";

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

function matches(candidate: string, expected: string): boolean {
  const actualBuffer = Buffer.from(candidate, "utf8");
  const expectedBuffer = Buffer.from(expected, "utf8");
  return actualBuffer.length === expectedBuffer.length && timingSafeEqual(actualBuffer, expectedBuffer);
}

export function verifyOwnerAccessKey(candidate: string): boolean {
  const actual = candidate.trim();
  if (!actual) return false;

  const configured = (process.env.ALTER_WEB_PIN || process.env.ALTER_CORE_TOKEN || "").trim();
  if (configured && matches(actual, configured)) return true;

  // Emergency/bootstrap credential: only its SHA-256 digest is committed.
  // The raw key is never bundled into the browser and can be rotated by replacing this digest.
  const digest = createHash("sha256").update(actual).digest("hex");
  return matches(digest, BOOTSTRAP_ACCESS_KEY_SHA256);
}
