import { Audio } from "expo-av";
import * as Haptics from "expo-haptics";
import { useEffect, useRef, useState } from "react";
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from "react-native";

import { APIException, transcribeAudio } from "../lib/api";
import { colors, fontSize, radius, spacing } from "../lib/tokens";

/**
 * Push-to-Talk mic (FR-033/035/037). Tap to start, tap to stop → transcribe.
 * The result fills the chat input via `onTranscript` — it is NEVER auto-sent
 * (FR-035). Failures (consent / low confidence / mic perm) fall back to the
 * keyboard with a short notice (FR-037).
 *
 * Records 16kHz mono PCM WAV (backend `encoding=pcm16`). iOS LinearPCM is the
 * verified path; Android WAV via expo-av is best-effort (the backend would
 * reject a non-WAV container — track per the chosen demo platform).
 */
const MIN_MS = 700;

const WAV_OPTIONS: Audio.RecordingOptions = {
  isMeteringEnabled: false,
  android: {
    extension: ".wav",
    outputFormat: Audio.AndroidOutputFormat.DEFAULT,
    audioEncoder: Audio.AndroidAudioEncoder.DEFAULT,
    sampleRate: 16000,
    numberOfChannels: 1,
    bitRate: 256000,
  },
  ios: {
    extension: ".wav",
    outputFormat: Audio.IOSOutputFormat.LINEARPCM,
    audioQuality: Audio.IOSAudioQuality.HIGH,
    sampleRate: 16000,
    numberOfChannels: 1,
    bitRate: 256000,
    linearPCMBitDepth: 16,
    linearPCMIsBigEndian: false,
    linearPCMIsFloat: false,
  },
  web: { mimeType: "audio/webm", bitsPerSecond: 128000 },
};

type Status = "idle" | "recording" | "processing";

type Props = {
  token: string | null;
  sessionId: string | null;
  disabled?: boolean;
  onTranscript: (text: string) => void;
  /** User-facing notice (keyboard fallback). reason ∈ permission/too_short/low_confidence/consent/error */
  onNotice: (reason: string, message: string) => void;
};

function fmt(ms: number): string {
  const s = Math.floor(ms / 1000);
  return `0:${String(s).padStart(2, "0")}`;
}

export function PushToTalk({ token, sessionId, disabled, onTranscript, onNotice }: Props) {
  const [status, setStatus] = useState<Status>("idle");
  const [elapsed, setElapsed] = useState(0);
  const recordingRef = useRef<Audio.Recording | null>(null);
  const startRef = useRef(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const canceledRef = useRef(false);

  const clearTimer = () => {
    if (timerRef.current !== null) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  };

  useEffect(() => {
    return () => {
      clearTimer();
      // Best-effort teardown if unmounted mid-recording.
      void recordingRef.current?.stopAndUnloadAsync().catch(() => undefined);
    };
  }, []);

  const start = async () => {
    if (disabled || status !== "idle" || !token || !sessionId) return;
    try {
      const perm = await Audio.requestPermissionsAsync();
      if (!perm.granted) {
        onNotice("permission", "마이크 권한이 필요해요. 설정에서 허용해 주세요.");
        return;
      }
      await Audio.setAudioModeAsync({
        allowsRecordingIOS: true,
        playsInSilentModeIOS: true,
      });
      const { recording } = await Audio.Recording.createAsync(WAV_OPTIONS);
      recordingRef.current = recording;
      canceledRef.current = false;
      startRef.current = Date.now();
      setElapsed(0);
      setStatus("recording");
      timerRef.current = setInterval(
        () => setElapsed(Date.now() - startRef.current),
        200,
      );
      void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    } catch {
      recordingRef.current = null;
      setStatus("idle");
      onNotice("error", "녹음을 시작할 수 없어요. 키보드로 입력해 주세요.");
    }
  };

  const stopRecording = async (): Promise<string | null> => {
    clearTimer();
    const rec = recordingRef.current;
    recordingRef.current = null;
    if (!rec) return null;
    try {
      await rec.stopAndUnloadAsync();
      return rec.getURI();
    } catch {
      return null;
    }
  };

  const cancel = async () => {
    canceledRef.current = true;
    await stopRecording();
    setStatus("idle");
    setElapsed(0);
  };

  const stopAndTranscribe = async () => {
    if (status !== "recording" || !token || !sessionId) return;
    const ms = Date.now() - startRef.current;
    setStatus("processing");
    const uri = await stopRecording();
    if (canceledRef.current) return;
    if (!uri || ms < MIN_MS) {
      setStatus("idle");
      setElapsed(0);
      if (ms < MIN_MS) onNotice("too_short", "너무 짧아요. 조금 더 길게 말씀해 주세요.");
      return;
    }
    try {
      const result = await transcribeAudio(token, sessionId, {
        uri,
        encoding: "pcm16",
        sampleRateHz: 16000,
      });
      onTranscript(result.text);
    } catch (e) {
      const code = e instanceof APIException ? e.body.code : "NETWORK";
      if (code === "VOICE_CONSENT_REQUIRED") {
        onNotice("consent", "음성 입력 동의가 필요해요. 설정에서 켜주세요.");
      } else if (code === "STT_LOW_CONFIDENCE") {
        onNotice("low_confidence", "잘 들리지 않았어요. 다시 말씀하거나 키보드로 입력해 주세요.");
      } else {
        onNotice("error", `음성 인식에 실패했어요. 키보드로 입력해 주세요 (${code}).`);
      }
    } finally {
      setStatus("idle");
      setElapsed(0);
    }
  };

  const onPress = () => {
    if (status === "idle") void start();
    else if (status === "recording") void stopAndTranscribe();
  };

  return (
    <View>
      {status === "recording" ? (
        <View style={styles.banner}>
          <View style={styles.dot} />
          <Text style={styles.bannerText}>{fmt(elapsed)} · 다시 누르면 인식</Text>
          <Pressable onPress={() => void cancel()} hitSlop={8} accessibilityRole="button">
            <Text style={styles.cancel}>취소</Text>
          </Pressable>
        </View>
      ) : null}

      <Pressable
        onPress={onPress}
        disabled={disabled || status === "processing" || !token || !sessionId}
        accessibilityRole="button"
        accessibilityLabel={status === "recording" ? "녹음 정지 및 인식" : "음성 입력 시작"}
        style={({ pressed }) => [
          styles.mic,
          status === "recording" && styles.micActive,
          { opacity: disabled || status === "processing" ? 0.4 : pressed ? 0.7 : 1 },
        ]}
      >
        {status === "processing" ? (
          <ActivityIndicator size="small" color={colors.textSecondary} />
        ) : (
          <Text style={styles.micIcon}>{status === "recording" ? "■" : "🎤"}</Text>
        )}
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  mic: {
    width: 44,
    height: 44,
    borderRadius: 22,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.surfaceElevated,
    borderWidth: 1,
    borderColor: colors.border,
  },
  micActive: { backgroundColor: "#FEF2F2", borderColor: colors.stateDanger },
  micIcon: { fontSize: fontSize.bodyLg },
  banner: {
    position: "absolute",
    bottom: "100%",
    right: 0,
    marginBottom: spacing.xs,
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radius.lg,
    backgroundColor: colors.textPrimary,
    minWidth: 200,
  },
  dot: { width: 10, height: 10, borderRadius: 5, backgroundColor: colors.stateDanger },
  bannerText: { flex: 1, color: "#FFFFFF", fontSize: fontSize.body },
  cancel: { color: "#FCA5A5", fontSize: fontSize.body, fontWeight: "600" },
});
