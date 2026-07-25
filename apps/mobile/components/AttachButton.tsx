/**
 * 대화 입력바의 [+] 첨부 버튼 (v3 FR-048).
 *
 * 처방전/진단서를 촬영하거나 앨범에서 골라 OCR 확인 화면으로 넘긴다. 업로드·인식은
 * 확인 화면이 담당하고, 여기서는 파일을 고르기만 한다. expo-image-picker는 Expo Go에
 * 내장돼 있어 네이티브 빌드가 필요 없다.
 */

import * as ImagePicker from "expo-image-picker";
import { Alert, Pressable, StyleSheet } from "react-native";

import { colors } from "../lib/tokens";

export type PickedDocument = { uri: string; name: string; mime: string };

function fromAsset(asset: ImagePicker.ImagePickerAsset): PickedDocument {
  const uri = asset.uri;
  const guessedExt = uri.split(".").pop()?.toLowerCase();
  const ext = guessedExt === "png" ? "png" : "jpg";
  const mime = asset.mimeType ?? (ext === "png" ? "image/png" : "image/jpeg");
  return { uri, name: asset.fileName ?? `document.${ext}`, mime };
}

export function AttachButton({
  onPick,
  disabled,
}: {
  onPick: (doc: PickedDocument) => void;
  disabled?: boolean;
}) {
  const launchCamera = async () => {
    const perm = await ImagePicker.requestCameraPermissionsAsync();
    if (!perm.granted) {
      Alert.alert("카메라 권한 필요", "설정에서 카메라 접근을 허용해 주세요.");
      return;
    }
    const res = await ImagePicker.launchCameraAsync({
      mediaTypes: "images",
      quality: 0.8,
    });
    if (!res.canceled && res.assets[0]) onPick(fromAsset(res.assets[0]));
  };

  const launchLibrary = async () => {
    const res = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: "images",
      quality: 0.8,
    });
    if (!res.canceled && res.assets[0]) onPick(fromAsset(res.assets[0]));
  };

  const choose = () => {
    Alert.alert("처방전·진단서 첨부", "어떻게 올릴까요?", [
      { text: "촬영하기", onPress: () => void launchCamera() },
      { text: "앨범에서 선택", onPress: () => void launchLibrary() },
      { text: "취소", style: "cancel" },
    ]);
  };

  return (
    <Pressable
      onPress={choose}
      disabled={disabled}
      accessibilityRole="button"
      accessibilityLabel="문서 첨부"
      style={({ pressed }) => [styles.btn, { opacity: disabled ? 0.4 : pressed ? 0.7 : 1 }]}
    >
      {/* + 아이콘 (두 획) */}
      <Plus />
    </Pressable>
  );
}

function Plus() {
  return (
    <>
      <Pressable pointerEvents="none" style={styles.hbar} />
      <Pressable pointerEvents="none" style={styles.vbar} />
    </>
  );
}

const styles = StyleSheet.create({
  btn: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: colors.fill,
    alignItems: "center",
    justifyContent: "center",
  },
  hbar: {
    position: "absolute",
    width: 16,
    height: 2,
    borderRadius: 1,
    backgroundColor: colors.ink,
  },
  vbar: {
    position: "absolute",
    width: 2,
    height: 16,
    borderRadius: 1,
    backgroundColor: colors.ink,
  },
});
