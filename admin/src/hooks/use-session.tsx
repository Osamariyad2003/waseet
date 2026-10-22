"use client";

/**
 * Session state: the bearer token and the signed-in user.
 *
 * Token storage, stated plainly because the SRS asks for assumptions to be
 * surfaced: the token is held in memory and mirrored into sessionStorage so
 * a page refresh does not sign the user out. sessionStorage is readable by
 * any script on the origin, so this is a demo-grade choice, not a
 * production one — a real deployment would use an httpOnly cookie set by
 * the backend. It is sessionStorage rather than localStorage so the token
 * dies with the tab.
 */

import { useRouter } from "next/navigation";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import { TOKEN_STORAGE_KEY, api, setAuthToken } from "@/lib/api";
import type { User } from "@/lib/types";

const TOKEN_KEY = TOKEN_STORAGE_KEY;
const USER_KEY = "waseet.user";

interface SessionValue {
  user: User | null;
  isLoading: boolean;
  signIn: (email: string, password: string) => Promise<User>;
  signOut: () => void;
}

const SessionContext = createContext<SessionValue | null>(null);

function readStored(): { token: string; user: User } | null {
  if (typeof window === "undefined") return null;
  try {
    const token = window.sessionStorage.getItem(TOKEN_KEY);
    const rawUser = window.sessionStorage.getItem(USER_KEY);
    if (!token || !rawUser) return null;
    return { token, user: JSON.parse(rawUser) as User };
  } catch {
    // Private mode, or storage disabled. Not an error — just no session.
    return null;
  }
}

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // Restore on mount, then confirm with the server: a token that looks
  // present may still be expired, and we would rather find out now than on
  // the user's first action.
  useEffect(() => {
    const stored = readStored();
    if (!stored) {
      setIsLoading(false);
      return;
    }

    setAuthToken(stored.token);
    setUser(stored.user);

    let cancelled = false;
    api
      .me()
      .then((confirmed) => {
        if (!cancelled) setUser(confirmed);
      })
      .catch(() => {
        if (cancelled) return;
        setAuthToken(null);
        setUser(null);
        clearStored();
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const signIn = useCallback(async (email: string, password: string) => {
    const result = await api.login(email, password);
    setAuthToken(result.access_token);
    setUser(result.user);
    try {
      window.sessionStorage.setItem(TOKEN_KEY, result.access_token);
      window.sessionStorage.setItem(USER_KEY, JSON.stringify(result.user));
    } catch {
      // Storage unavailable: the session still works for this page view.
    }
    return result.user;
  }, []);

  const signOut = useCallback(() => {
    setAuthToken(null);
    setUser(null);
    clearStored();
  }, []);

  const value = useMemo<SessionValue>(
    () => ({ user, isLoading, signIn, signOut }),
    [user, isLoading, signIn, signOut],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

function clearStored(): void {
  try {
    window.sessionStorage.removeItem(TOKEN_KEY);
    window.sessionStorage.removeItem(USER_KEY);
  } catch {
    // Nothing to clear.
  }
}

export function useSession(): SessionValue {
  const context = useContext(SessionContext);
  if (!context) throw new Error("useSession must be used inside a SessionProvider");
  return context;
}

/**
 * Gate a page on being signed in. Returns the user once known, or null
 * while resolving — callers render their own skeleton in that window
 * rather than flashing a redirect.
 */
export function useRequireSession(locale: string): { user: User | null; isLoading: boolean } {
  const { user, isLoading } = useSession();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && !user) router.replace(`/${locale}/login`);
  }, [isLoading, user, router, locale]);

  return { user, isLoading };
}
