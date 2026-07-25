import type { MessageOut } from "../lib/api";

const roleLabel: Record<MessageOut["role"], string> = {
  user: "환자",
  ai: "AI",
  system: "시스템",
};

export function MessageRow({ msg }: { msg: MessageOut }) {
  const isUser = msg.role === "user";
  return (
    <div className="flex gap-4 py-3.5 border-b border-sep last:border-0">
      <div className="w-14 shrink-0 pt-0.5">
        <span
          className={`text-[10px] font-semibold uppercase tracking-wider ${
            isUser ? "text-ink2" : "text-faint"
          }`}
        >
          {roleLabel[msg.role]}
        </span>
      </div>
      <div className="flex-1 min-w-0">
        <p className={`leading-relaxed ${isUser ? "text-text-primary" : "text-text-secondary"}`}>
          {msg.content}
        </p>
        <p className="text-xs text-faint mt-1 tabular-nums">
          {new Date(msg.createdAt).toLocaleString("ko-KR")}
          {msg.inputModality === "voice" ? " · 🎤 음성" : ""}
        </p>
      </div>
    </div>
  );
}
