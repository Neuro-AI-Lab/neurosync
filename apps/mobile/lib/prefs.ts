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

import * as SecureStore from "expo-secure-store";

const ONBOARDING_KEY = "ns.pref.seenOnboarding";

export async function getSeenOnboarding(): Promise<boolean> {
  try {
    return (await SecureStore.getItemAsync(ONBOARDING_KEY)) === "1";
  } catch {
    return false;
  }
}

export async function setSeenOnboarding(): Promise<void> {
  await SecureStore.setItemAsync(ONBOARDING_KEY, "1");
}
