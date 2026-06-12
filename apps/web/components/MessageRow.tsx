import type { MessageOut } from "../lib/api";

const roleLabel: Record<MessageOut["role"], string> = {
  user: "환자",
  ai: "AI",
  system: "시스템",
};

export function MessageRow({ msg }: { msg: MessageOut }) {
  const isUser = msg.role === "user";
  return (
    <div className="flex gap-3 py-3 border-b border-border last:border-0">
      <div className="w-16 text-sm font-medium text-text-secondary shrink-0">
        {roleLabel[msg.role]}
      </div>
      <div className="flex-1">
        <p className={isUser ? "text-text-primary" : "text-text-secondary"}>
          {msg.content}
        </p>
        <p className="text-xs text-text-secondary mt-1">
          {new Date(msg.createdAt).toLocaleString("ko-KR")}
          {msg.inputModality === "voice" ? " · 🎤 음성" : ""}
        </p>
      </div>
    </div>
  );
}
