import { Mail, MessageSquare, Mic, Smartphone } from "lucide-react";
import { CHANNEL_LABEL } from "../lib/format";

export const CHANNEL_ICON = { chat: MessageSquare, sms: Smartphone, email: Mail, voice: Mic };

export function ChannelTag({ channel }: { channel: string }) {
  const Icon = CHANNEL_ICON[channel as keyof typeof CHANNEL_ICON] ?? MessageSquare;
  return <span className="inline-flex items-center gap-1.5 text-slate-600"><Icon className="h-4 w-4" />{CHANNEL_LABEL[channel] ?? channel}</span>;
}
