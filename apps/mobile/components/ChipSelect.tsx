/**
 * 단일 선택 칩 그룹 (선택 해제 가능). 인적사항 등 범주형 입력에 쓴다.
 * 색은 위험에만 쓰는 모노크롬 규칙에 따라 선택 상태는 ink 채움으로 표시한다.
 */

import { Pressable, StyleSheet, Text, View } from "react-native";

import type { Option } from "../lib/demographics";
import { colors } from "../lib/tokens";

export function ChipSelect<T extends string>({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: Option<T>[];
  value: T | null;
  onChange: (v: T | null) => void;
}) {
  return (
    <View style={styles.wrap}>
      <Text style={styles.label}>{label}</Text>
      <View style={styles.chips}>
        {options.map((opt) => {
          const on = value === opt.code;
          return (
            <Pressable
              key={opt.code}
              // 다시 누르면 선택 해제 — 선택 항목이므로 되돌릴 수 있어야 한다.
              onPress={() => onChange(on ? null : opt.code)}
              style={[styles.chip, on && styles.chipOn]}
              accessibilityRole="radio"
              accessibilityState={{ selected: on }}
            >
              <Text style={[styles.chipText, on && styles.chipTextOn]}>{opt.label}</Text>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: 7 },
  label: { fontSize: 12.5, fontWeight: "500", color: colors.muted, paddingLeft: 2 },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: 7 },
  chip: {
    paddingHorizontal: 13,
    height: 38,
    borderWidth: 1,
    borderColor: colors.lineStrong,
    borderRadius: 10,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.surface,
  },
  chipOn: { backgroundColor: colors.ink, borderColor: colors.ink },
  chipText: { fontSize: 13.5, color: colors.ink },
  chipTextOn: { color: colors.onInk, fontWeight: "600" },
});
