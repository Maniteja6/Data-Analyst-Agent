import { create } from 'zustand'
import type { Message, Conversation } from '@/types/conversation'

interface ChatState {
  conversation: Conversation | null
  messages: Message[]
  streamingContent: string
  isStreaming: boolean
  isLoading: boolean
  setConversation: (conv: Conversation | null) => void
  addMessage: (msg: Message) => void
  updateStreamingContent: (token: string) => void
  finaliseStreamingMessage: (messageId: string, finalContent: string) => void
  setStreaming: (streaming: boolean) => void
  setLoading: (loading: boolean) => void
  reset: () => void
}

export const useChatStore = create<ChatState>((set) => ({
  conversation: null,
  messages: [],
  streamingContent: '',
  isStreaming: false,
  isLoading: false,

  setConversation: (conversation) =>
    set({ conversation, messages: conversation?.messages ?? [] }),

  addMessage: (msg) =>
    set((s) => ({ messages: [...s.messages, msg] })),

  updateStreamingContent: (token) =>
    set((s) => ({ streamingContent: s.streamingContent + token, isStreaming: true })),

  finaliseStreamingMessage: (messageId, finalContent) =>
    set((s) => ({
      messages: s.messages.map((m) =>
        m.id === messageId ? { ...m, content: finalContent, isStreaming: false } : m,
      ),
      streamingContent: '',
      isStreaming: false,
    })),

  setStreaming: (isStreaming) => set({ isStreaming }),
  setLoading: (isLoading) => set({ isLoading }),
  reset: () =>
    set({ conversation: null, messages: [], streamingContent: '', isStreaming: false }),
}))