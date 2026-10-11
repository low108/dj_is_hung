"use client";

import {
  GoogleAuthProvider,
  getRedirectResult,
  onAuthStateChanged,
  signInWithRedirect,
  signOut,
  type User,
} from "firebase/auth";
import Link from "next/link";
import { useEffect, useState } from "react";
import { firebaseAuth } from "../firebase";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001";

/** GET /me/onboarding: where the user is, so they can resume where they left off. */
type Progress = {
  consent: { version: string; at: string } | null;
  consent_text: string;
  consent_version: string;
  total: number;
  answered: number;
  complete: boolean;
  current: { id: string; theme: string; text: string; followup: string | null; number: number } | null;
  max_chars: number;
};

export default function Onboarding() {
  const [user, setUser] = useState<User | null | undefined>(undefined); // undefined: still checking
  const [progress, setProgress] = useState<Progress | null>(null);
  const [draft, setDraft] = useState("");
  const [agreed, setAgreed] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function call(path: string, body?: unknown, who: User | null | undefined = user): Promise<Progress> {
    const token = await who!.getIdToken();
    const res = await fetch(`${API_URL}${path}`, {
      method: body === undefined ? "GET" : "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!res.ok) {
      const detail = await res.json().catch(() => null);
      throw new Error(detail?.detail ?? `API returned ${res.status}`);
    }
    return res.json();
  }

  /** Runs one API step; true if it worked (the error is shown otherwise). */
  async function run(step: () => Promise<Progress>): Promise<boolean> {
    setBusy(true);
    setError(null);
    try {
      setProgress(await step());
      return true;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      return false;
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    getRedirectResult(firebaseAuth()).catch((e) => setError(`Sign-in failed: ${e.message}`));
    return onAuthStateChanged(firebaseAuth(), setUser);
  }, []);

  useEffect(() => {
    // A new account starts clean, and a slow load for the previous one is ignored.
    setProgress(null);
    setDraft("");
    setAgreed(false);
    setError(null);
    if (!user) return;
    let stale = false;
    call("/me/onboarding", undefined, user)
      .then((p) => !stale && setProgress(p))
      .catch((e) => !stale && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      stale = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reload only when the signed-in user changes
  }, [user]);

  const current = progress?.current;

  async function submit() {
    if (!current || !draft.trim()) return;
    if (await run(() => call("/me/answers", { question_id: current.id, text: draft }))) setDraft("");
  }

  return (
    <main className="page onboarding">
      <p className="meta">
        <Link href="/">← The Garden</Link>
      </p>
      <h1>Build your twin</h1>

      {user === undefined && <p className="meta">Checking sign-in…</p>}

      {user === null && (
        <section className="result">
          <p>Sign in to answer a few questions. Your twin is built from your answers.</p>
          {/* A redirect rather than a popup: works on phones and in embedded browsers. */}
          <button onClick={() => signInWithRedirect(firebaseAuth(), new GoogleAuthProvider()).catch((e) => setError(e.message))}>
            Sign in with Google
          </button>
        </section>
      )}

      {user && progress && !progress.consent && (
        <section className="result" data-testid="consent">
          <h2>Before we start</h2>
          <p>{progress.consent_text}</p>
          <label className="check">
            <input type="checkbox" checked={agreed} onChange={(e) => setAgreed(e.target.checked)} /> I agree
          </label>
          <button
            disabled={!agreed || busy}
            onClick={() => run(() => call("/me/consent", { agree: true, version: progress.consent_version }))}
          >
            Continue
          </button>
        </section>
      )}

      {user && progress?.consent && current && (
        <section className="result question" data-testid="question">
          <p className="meta">
            {current.theme} · question {current.number} of {progress.total}
          </p>
          <progress value={progress.answered} max={progress.total} />
          <h2>{current.text}</h2>
          {current.followup && <p className="followup">{current.followup}</p>}
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            rows={5}
            maxLength={progress.max_chars}
            aria-label={current.followup ?? current.text}
            placeholder="Take your time. A few sentences is perfect."
          />
          <button onClick={submit} disabled={busy || !draft.trim()}>
            {busy ? "Saving…" : "Next"}
          </button>
        </section>
      )}

      {user && progress?.complete && (
        <section className="result" data-testid="done">
          <h2>That&apos;s everything</h2>
          <p>Thank you. Your answers are saved; next we build your twin from them.</p>
        </section>
      )}

      {error && <p className="error">{error}</p>}

      {user && (
        <p className="meta">
          Signed in as {user.email ?? "a guest"} ·{" "}
          <button className="link" onClick={() => signOut(firebaseAuth())}>
            Sign out
          </button>
        </p>
      )}
    </main>
  );
}
