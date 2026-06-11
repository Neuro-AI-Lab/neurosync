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

import * as SecureStore from "expo-secure-store";

const ACCESS_KEY = "ns.auth.access";
const REFRESH_KEY = "ns.auth.refresh";
const USER_KEY = "ns.auth.user";

const STORE_OPTS: SecureStore.SecureStoreOptions = {
  keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
};

export type StoredUser = {
  userId: string;
  role: "patient";
  email: string;
};

export async function saveTokens(access: string, refresh: string): Promise<void> {
  await SecureStore.setItemAsync(ACCESS_KEY, access, STORE_OPTS);
  await SecureStore.setItemAsync(REFRESH_KEY, refresh, STORE_OPTS);
}

export async function saveAccessToken(access: string): Promise<void> {
  await SecureStore.setItemAsync(ACCESS_KEY, access, STORE_OPTS);
}

export async function getAccessToken(): Promise<string | null> {
  return SecureStore.getItemAsync(ACCESS_KEY, STORE_OPTS);
}

export async function getRefreshToken(): Promise<string | null> {
  return SecureStore.getItemAsync(REFRESH_KEY, STORE_OPTS);
}

export async function saveUser(user: StoredUser): Promise<void> {
  await SecureStore.setItemAsync(USER_KEY, JSON.stringify(user), STORE_OPTS);
}

export async function getUser(): Promise<StoredUser | null> {
  const raw = await SecureStore.getItemAsync(USER_KEY, STORE_OPTS);
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
    SecureStore.deleteItemAsync(ACCESS_KEY, STORE_OPTS),
    SecureStore.deleteItemAsync(REFRESH_KEY, STORE_OPTS),
    SecureStore.deleteItemAsync(USER_KEY, STORE_OPTS),
  ]);
}
