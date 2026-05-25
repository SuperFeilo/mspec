import { useRef, useEffect } from 'react'

export function useTask(taskId) {
  const taskData = useRef(null)
  const eventSource = useRef(null)

  useEffect(() => {
    if (!taskId) return

    const es = new EventSource(`/api/tasks/${taskId}/stream`)
    eventSource.current = es

    es.onmessage = (event) => {
      try {
        taskData.current = JSON.parse(event.data)
      } catch (e) {
        console.error('SSE parse error', e)
      }
    }

    es.onerror = () => {
      es.close()
    }

    return () => {
      es.close()
    }
  }, [taskId])

  return taskData.current
}
