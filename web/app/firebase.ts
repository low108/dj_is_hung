// Firebase Auth in the browser. Locally it talks to the Auth emulator (make emulator), which signs in
// with fake accounts; set NEXT_PUBLIC_AUTH_EMULATOR=off and the NEXT_PUBLIC_FIREBASE_* values on Google Cloud.
import { getApps, initializeApp } from "firebase/app";
import { connectAuthEmulator, getAuth, type Auth, type User } from "firebase/auth";

const EMULATOR = process.env.NEXT_PUBLIC_AUTH_EMULATOR ?? "http://localhost:9099";

let cached: Auth | null = null;

export function firebaseAuth(): Auth {
  if (cached) return cached;
  const app =
    getApps()[0] ??
    initializeApp({
      apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY ?? "demo-api-key",
      authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN ?? "demo-dj-is-hung.firebaseapp.com",
      projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID ?? "demo-dj-is-hung",
    });
  cached = getAuth(app);
  if (EMULATOR !== "off") connectAuthEmulator(cached, EMULATOR, { disableWarnings: true });
  return cached;
}

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001";

/** An API error with its HTTP status (e.g. 404 = "nothing yet"). */
export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

/** Calls the API as the signed-in user and returns the JSON reply (ApiError on failure). */
export async function authedFetch<T>(
  user: User,
  path: string,
  { method, body }: { method?: string; body?: unknown } = {},
): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    method: method ?? (body === undefined ? "GET" : "POST"),
    headers: { Authorization: `Bearer ${await user.getIdToken()}`, "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new ApiError(res.status, detail?.detail ?? `API returned ${res.status}`);
  }
  return res.json();
}
