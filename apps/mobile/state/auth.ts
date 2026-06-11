/**
 * Auth Zustand store — accessToken/refreshToken + user, plus bootstrap
 * (hydrate from SecureStore) and logout. The role for mobile is fixed to
 * "patient" — the server returns 403 ROLE_MISMATCH for non-patient logins.
 */

import { create } from "zustand";

import {
  login as loginApi,
  refreshAccessTokenOnce,
  register as registerApi,
  RegisterInput,
  TokenPair,
} from "../lib/api";
import * as Store from "../lib/secure-store";

export type AuthState = {
  status: "hydrating" | "anonymous" | "authenticated";
  accessToken: string | null;
  refreshToken: string | null;
  user: Store.StoredUser | null;

  hydrate: () => Promise<void>;
  login: (email: string, password: string) => Promise<void>;
  register: (input: RegisterInput) => Promise<void>;
  logout: () => Promise<void>;
  /** Used by the WS client to refresh mid-stream. Returns the new token or null. */
  refreshAccessToken: () => Promise<string | null>;
};

function toStoredUser(email: string, pair: TokenPair): Store.StoredUser {
  return {
    userId: pair.userId,
    role: "patient",
    email,
  };
}

let hydrating: Promise<void> | null = null;

export const useAuth = create<AuthState>((set) => ({
  status: "hydrating",
  accessToken: null,
  refreshToken: null,
  user: null,

  hydrate: async () => {
    // Coalesce concurrent hydrate calls.
    if (hydrating !== null) return hydrating;
    hydrating = (async () => {
      try {
        const [access, refresh, user] = await Promise.all([
          Store.getAccessToken(),
          Store.getRefreshToken(),
          Store.getUser(),
        ]);
        if (access && refresh && user) {
          set({
            status: "authenticated",
            accessToken: access,
            refreshToken: refresh,
            user,
          });
        } else {
          set({
            status: "anonymous",
            accessToken: null,
            refreshToken: null,
            user: null,
          });
        }
      } finally {
        hydrating = null;
      }
    })();
    return hydrating;
  },

  login: async (email, password) => {
    const pair = await loginApi(email, password, "patient");
    const user = toStoredUser(email, pair);
    await Store.saveTokens(pair.accessToken, pair.refreshToken);
    await Store.saveUser(user);
    set({
      status: "authenticated",
      accessToken: pair.accessToken,
      refreshToken: pair.refreshToken,
      user,
    });
  },

  register: async (input) => {
    const pair = await registerApi(input);
    const user = toStoredUser(input.email, pair);
    await Store.saveTokens(pair.accessToken, pair.refreshToken);
    await Store.saveUser(user);
    set({
      status: "authenticated",
      accessToken: pair.accessToken,
      refreshToken: pair.refreshToken,
      user,
    });
  },

  logout: async () => {
    await Store.clearAll();
    set({
      status: "anonymous",
      accessToken: null,
      refreshToken: null,
      user: null,
    });
  },

  refreshAccessToken: async () => {
    const fresh = await refreshAccessTokenOnce();
    if (fresh === null) {
      // tryRefresh already cleared SecureStore on failure — reflect that.
      set({
        status: "anonymous",
        accessToken: null,
        refreshToken: null,
        user: null,
      });
      return null;
    }
    set({ accessToken: fresh });
    return fresh;
  },
}));
