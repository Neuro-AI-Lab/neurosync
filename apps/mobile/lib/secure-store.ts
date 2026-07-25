/**
 * Token storage — expo-secure-store (iOS Keychain / Android EncryptedSharedPreferences).
 *
 * NEVER store tokens in AsyncStorage (plaintext). PRD §4.5.2 mandates AES-grade
 * at-rest; mobile-side equivalent is the OS-managed secure enclave.
 *
 * Keychain options:
 * - `WHEN_UNLOCKED_THIS_DEVICE_ONLY`: tokens are usable only while the device
 *   is unlocked AND never restored to another device via iCloud backup. PRD
 *   §4.5.2 PIPA: 민감정보 처리 최소화 + 백업으로 인한 권한 우회 방지.
 */

import { Platform } from "react-native";
import * as SecureStore from "expo-secure-store";

const ACCESS_KEY = "ns.auth.access";
const REFRESH_KEY = "ns.auth.refresh";
const USER_KEY = "ns.auth.user";

const STORE_OPTS: SecureStore.SecureStoreOptions = {
  keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
};

// Web dev-preview only: expo-secure-store has no web implementation. localStorage
// is NOT enclave-grade — release builds are native-only (config.ts guard), so
// this branch never ships to patients.
const isWeb = Platform.OS === "web";

// BUG-062/BUG-064 fix wave item 7 — formalize the dev-preview-only guarantee
// with an explicit runtime check (same defense-in-depth pattern as
// `config.ts`'s `__DEV__` production guards) instead of relying only on the
// comment above: a release (`__DEV__ === false`) build must never take the
// localStorage branch for token storage, even if someone builds for web by
// mistake — fail fast rather than silently store patient auth tokens in
// plaintext localStorage.
if (isWeb && !__DEV__) {
  throw new Error(
    "[neuro-sync] secure-store's web localStorage fallback is dev-preview-only " +
      "and must never run in a release build (Platform.OS === 'web' && !__DEV__)",
  );
}

async function storeGet(key: string): Promise<string | null> {
  if (isWeb) return globalThis.localStorage?.getItem(key) ?? null;
  return SecureStore.getItemAsync(key, STORE_OPTS);
}

async function storeSet(key: string, value: string): Promise<void> {
  if (isWeb) {
    globalThis.localStorage?.setItem(key, value);
    return;
  }
  await SecureStore.setItemAsync(key, value, STORE_OPTS);
}

async function storeDelete(key: string): Promise<void> {
  if (isWeb) {
    globalThis.localStorage?.removeItem(key);
    return;
  }
  await SecureStore.deleteItemAsync(key, STORE_OPTS);
}

export type StoredUser = {
  userId: string;
  role: "patient";
  email: string;
};

export async function saveTokens(access: string, refresh: string): Promise<void> {
  await storeSet(ACCESS_KEY, access);
  await storeSet(REFRESH_KEY, refresh);
}

export async function saveAccessToken(access: string): Promise<void> {
  await storeSet(ACCESS_KEY, access);
}

export async function getAccessToken(): Promise<string | null> {
  return storeGet(ACCESS_KEY);
}

export async function getRefreshToken(): Promise<string | null> {
  return storeGet(REFRESH_KEY);
}

export async function saveUser(user: StoredUser): Promise<void> {
  await storeSet(USER_KEY, JSON.stringify(user));
}

export async function getUser(): Promise<StoredUser | null> {
  const raw = await storeGet(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as StoredUser;
  } catch {
    // Corrupted entry — purge the entire partial state. Leaving orphan tokens
    // behind is a refresh-token reuse hazard. The user returns to the
    // anonymous flow and must log in again.
    await clearAll();
    return null;
  }
}

export async function clearAll(): Promise<void> {
  await Promise.all([
    storeDelete(ACCESS_KEY),
    storeDelete(REFRESH_KEY),
    storeDelete(USER_KEY),
  ]);
}
