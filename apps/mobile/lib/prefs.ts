/**
 * Non-sensitive local preferences.
 *
 * Spec §S-13 logout keeps `hasSeenOnboarding` across sessions. We reuse
 * expo-secure-store (already a dependency) rather than pulling in AsyncStorage
 * for a single boolean — the value is non-sensitive, but co-locating it in the
 * secure store keeps storage to one mechanism.
 *
 * NOTE: kept separate from secure-store.ts (tokens) so `clearAll()` on logout
 * does NOT wipe the onboarding flag.
 */

import { Platform } from "react-native";
import * as SecureStore from "expo-secure-store";

const ONBOARDING_KEY = "ns.pref.seenOnboarding";

// Web dev-preview only: expo-secure-store has no web implementation.
const isWeb = Platform.OS === "web";

// BUG-062/BUG-064 fix wave item 7 — same formalized dev-preview-only guard
// as `secure-store.ts` (non-sensitive, but kept consistent so both web
// fallbacks fail the same way in a release build by mistake).
if (isWeb && !__DEV__) {
  throw new Error(
    "[neuro-sync] prefs' web localStorage fallback is dev-preview-only " +
      "and must never run in a release build (Platform.OS === 'web' && !__DEV__)",
  );
}

export async function getSeenOnboarding(): Promise<boolean> {
  try {
    if (isWeb) return globalThis.localStorage?.getItem(ONBOARDING_KEY) === "1";
    return (await SecureStore.getItemAsync(ONBOARDING_KEY)) === "1";
  } catch {
    return false;
  }
}

export async function setSeenOnboarding(): Promise<void> {
  if (isWeb) {
    globalThis.localStorage?.setItem(ONBOARDING_KEY, "1");
    return;
  }
  await SecureStore.setItemAsync(ONBOARDING_KEY, "1");
}
