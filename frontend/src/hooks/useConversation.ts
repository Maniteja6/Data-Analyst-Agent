import { useCallback } from 'react'
import { conversationsApi } from '@/api/conversations'
import { useChatStore } from '@/store/chatStore'
import type { Message } from '@/types/conversation'

export function useConversation() {
  const {
    conversation, messages, isStreaming, isLoading,
    setConversation, addMessage, setLoading,
  } = useChatStore()

  const startConversation = useCallback(async (datasetId: string) => {
    setLoading(true)
    try {
      const conv = await conversationsApi.create(datasetId)
      setConversation(conv)
    } finally {
      setLoading(false)
    }
  }, [setConversation, setLoading])

  const sendMessage = useCallback(async (content: string) => {
    if (!conversation) return
    const userMsg: Message = {
      id: `user-${Date.now()}`,
      role: 'user',
      content,
      createdAt: new Date().toISOString(),
    }
    addMessage(userMsg)
    setLoading(true)
    try {
      const assistantMsg = await conversationsApi.sendMessage(conversation.id, content)
      addMessage(assistantMsg)
    } finally {
      setLoading(false)
    }
  }, [conversation, addMessage, setLoading])

  return { conversation, messages, isStreaming, isLoading, startConversation, sendMessage }
}