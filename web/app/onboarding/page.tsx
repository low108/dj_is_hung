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
import { ApiError, STATIC, authedFetch, firebaseAuth } from "../firebase";
import TwinReview, { type TwinSummary } from "./TwinReview";
import AboutYou, { type About } from "./AboutYou";
import { facts, type AboutRules } from "./aboutLocal";

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
  return STATIC ? <AboutYouDemo /> : <BuildYourTwin />;
}

/** The public demo has no API: the About you forms alone, worked out in the browser and never saved. */
function AboutYouDemo() {
  const [rules, setRules] = useState<AboutRules | null>(null);
  const [about, setAbout] = useState<About["about"]>({});
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    fetch("/demo/about.json")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`about.json returned ${r.status}`))))
      .then(setRules)
      .catch((e) => setError(e.message));
  }, []);
  const status = { profile: !!about.profile, personality: !!about.personality, preferences: !!about.preferences };
  return (
    <main className="page onboarding">
      <p className="meta">
        <Link href="/">← The Garden</Link>
      </p>
      <h1>Tell your twin about you</h1>
      <p className="meta">A demo: nothing leaves your browser. Signing in and the full interview need the live server.</p>
      {rules && (
        <AboutYou
          about={{ form: rules.form, about, status, facts: facts(about, rules) }}
          busy={false}
          onSave={(part, body) => setAbout((a) => ({ ...a, [part]: body }))}
        />
      )}
      {error && <p className="error">{error}</p>}
    </main>
  );
}

function BuildYourTwin() {
  const [user, setUser] = useState<User | null | undefined>(undefined); // undefined: still checking
  const [progress, setProgress] = useState<Progress | null>(null);
  const [draft, setDraft] = useState("");
  const [agreed, setAgreed] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [twin, setTwin] = useState<TwinSummary | null>(null);
  const [about, setAbout] = useState<About | null>(null);

  /** Runs one API step and stores its reply with `keep`; true if it worked (the error is shown otherwise). */
  async function run<T>(step: () => Promise<T>, keep: (value: T) => void): Promise<boolean> {
    setBusy(true);
    setError(null);
    try {
      keep(await step());
      return true;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      return false;
    } finally {
      setBusy(false);
    }
  }
  const progressStep = (path: string, body?: unknown) =>
    run(() => authedFetch<Progress>(user!, path, { body }), setProgress);
  const twinStep = (path: string, opts: { method?: string; body?: unknown }) =>
    run(() => authedFetch<TwinSummary>(user!, path, opts), setTwin);

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
    setTwin(null);
    setAbout(null);
    if (!user) return;
    let stale = false;
    const shown = (e: unknown) => !stale && setError(e instanceof Error ? e.message : String(e));
    authedFetch<Progress>(user, "/me/onboarding")
      .then((p) => !stale && setProgress(p))
      .catch(shown);
    authedFetch<About>(user, "/me/about")
      .then((a) => !stale && setAbout(a))
      .catch(shown);
    authedFetch<TwinSummary>(user, "/me/twin")
      .then((t) => !stale && setTwin(t))
      .catch((e) => !(e instanceof ApiError && e.status === 404) && shown(e)); // 404: no twin yet
    return () => {
      stale = true;
    };
  }, [user]);

  const current = progress?.current;

  async function submit() {
    if (!current || !draft.trim()) return;
    if (await progressStep("/me/answers", { question_id: current.id, text: draft })) setDraft("");
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
            onClick={() => progressStep("/me/consent", { agree: true, version: progress.consent_version })}
          >
            Continue
          </button>
        </section>
      )}

      {user && progress?.consent && about?.form && (
        <AboutYou
          about={about}
          busy={busy}
          onSave={(part, body) =>
            run(
              () => authedFetch<About>(user, `/me/about/${part}`, { method: "PUT", body }),
              (saved) => setAbout({ ...about, ...saved }),
            )
          }
        />
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
          <p>Thank you. Your answers are saved.</p>
          <button disabled={busy} onClick={() => twinStep("/me/twin", { body: {} })}>
            {busy ? "Building your twin…" : twin ? "Rebuild my twin from my answers" : "Build my twin"}
          </button>
          {twin?.reviewed && (
            <p className="meta">
              Your twin can now date in the <Link href="/">Garden</Link>: pick &ldquo;My twin&rdquo; as the pool.
            </p>
          )}
        </section>
      )}

      {user && twin && (
        <TwinReview
          key={twin.version} // a rebuilt or changed twin starts with nothing half-edited
          twin={twin}
          busy={busy}
          onSave={(section, text) => twinStep(`/me/twin/sections/${section}`, { method: "PUT", body: { text } })}
          onTraits={(traits) => twinStep("/me/twin/traits", { method: "PUT", body: traits })}
          onConfirm={() => twinStep("/me/twin/review", { body: {} })}
        />
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
