// Firebase Auth in the browser. Locally it talks to the Auth emulator (make emulator), which signs in
// with fake accounts; set NEXT_PUBLIC_AUTH_EMULATOR=off and the NEXT_PUBLIC_FIREBASE_* values on Google Cloud.
import { getApps, initializeApp } from "firebase/app";
import { connectAuthEmulator, getAuth, type Auth } from "firebase/auth";

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
