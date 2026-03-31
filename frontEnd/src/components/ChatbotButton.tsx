import { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router';
import { MessageCircle, X, Send, RotateCcw } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeRaw from 'rehype-raw';
import { Button } from './ui/button';
import { Input } from './ui/input';

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  isError?: boolean;
}

const SESSION_KEY = 'palantiny_session_id';
const MESSAGES_KEY = 'palantiny_chat_messages';
const DEFAULT_MESSAGES: ChatMessage[] = [
  {
    role: 'assistant',
    content: '안녕하세요! Palantiny 고객지원입니다.\n궁금하신 한약재나 주문 관련 문의사항이 있으시면 언제든 말씀해주세요.',
  },
];

export function ChatbotButton() {
  const navigate = useNavigate();
  const [isChatbotOpen, setIsChatbotOpen] = useState(false);
  const [frontendContext, setFrontendContext] = useState<'PRICE' | 'ORDER' | null>(null);
  const [message, setMessage] = useState('');
  
  const [sessionId, setSessionId] = useState(() => {
    const saved = sessionStorage.getItem(SESSION_KEY);
    if (saved) return saved;
    const newId = `user_${Date.now()}_${Math.random().toString(36).substring(7)}`;
    sessionStorage.setItem(SESSION_KEY, newId);
    return newId;
  });

  const [messages, setMessages] = useState<ChatMessage[]>(() => {
    const saved = sessionStorage.getItem(MESSAGES_KEY);
    if (saved) {
      try {
        return JSON.parse(saved);
      } catch (e) {
        console.error('Failed to parse saved messages', e);
      }
    }
    return DEFAULT_MESSAGES;
  });

  const [isStreaming, setIsStreaming] = useState(false);

  // Sync messages to sessionStorage automatically whenever they change
  useEffect(() => {
    sessionStorage.setItem(MESSAGES_KEY, JSON.stringify(messages));
  }, [messages]);

  // Handle resetting the chat (Start new conversation)
  const handleResetChat = async () => {
    if (isStreaming) return;
    
    // Attempt to delete DB history for the current user
    try {
      await fetch(`http://localhost:8000/api/v1/chat/${sessionId}/history?user_id=user`, {
        method: 'DELETE',
      });
    } catch (e) {
      console.warn('Failed to clear backend chat history:', e);
    }

    const newId = `user_${Date.now()}_${Math.random().toString(36).substring(7)}`;
    setSessionId(newId);
    sessionStorage.setItem(SESSION_KEY, newId);
    setMessages(DEFAULT_MESSAGES);
  };
  
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll when messages update
  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, isChatbotOpen]);

  // Typing simulator for frontend auto-replies
  const simulateTyping = async (text: string) => {
    setIsStreaming(true);
    setMessages((prev: ChatMessage[]) => [...prev, { role: 'assistant', content: '' }]);
    
    for (let i = 0; i < text.length; i++) {
      await new Promise(resolve => setTimeout(resolve, 30));
      setMessages((prev: ChatMessage[]) => {
        const newArr = [...prev];
        newArr[newArr.length - 1].content = text.slice(0, i + 1);
        return newArr;
      });
    }
    setIsStreaming(false);
  };

  // Handle message sending logic
  const handleSendMessage = async (textFallback?: string) => {
    const userMessage = typeof textFallback === 'string' ? textFallback : message;
    if (!userMessage.trim() || isStreaming) return;

    setMessage('');

    // --- Frontend Intercept Logic ---
    if (userMessage === '약재 가격 확인하고 싶어요.') {
      setFrontendContext('PRICE');
      setMessages((prev: ChatMessage[]) => [...prev, { role: 'user', content: userMessage }]);
      simulateTyping('어떤 약재 가격을 알고 싶으신가요?');
      return;
    }
    
    if (userMessage === '약재 주문하고 싶어요.') {
      setFrontendContext('ORDER');
      setMessages((prev: ChatMessage[]) => [...prev, { role: 'user', content: userMessage }]);
      simulateTyping('어떤 약재를 주문하고 싶으신가요?');
      return;
    }
    // --------------------------------

    // Prepend hidden context to backend request if active
    let backendPayloadMessage = userMessage;
    if (frontendContext === 'PRICE') {
      backendPayloadMessage = `[약재 가격 확인] ${userMessage}`;
      setFrontendContext(null);
    } else if (frontendContext === 'ORDER') {
      backendPayloadMessage = `[약재 주문] ${userMessage}`;
      setFrontendContext(null);
    }

    setMessages((prev: ChatMessage[]) => [...prev, { role: 'user', content: userMessage }]);
    setIsStreaming(true);

    const abortController = new AbortController();

    try {
      // 1. Prepare stream listener connection
      const streamPromise = fetch(`http://localhost:8000/api/v1/chat/${sessionId}/stream`, {
        signal: abortController.signal,
      });

      // 2. Send POST message to backend queue
      const postResponse = await fetch(`http://localhost:8000/api/v1/chat/${sessionId}/message`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: backendPayloadMessage, user_id: 'user' }), // Send the intercepted message
      });
      
      if (!postResponse.ok) {
        throw new Error('메시지 전송에 실패했습니다.');
      }

      // 3. Connect to stream and read SSE
      const response = await streamPromise;
      if (!response.body) throw new Error('스트림을 연결할 수 없습니다.');
      
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      
      // Add empty assistant message to append chunks to
      setMessages((prev: ChatMessage[]) => [...prev, { role: 'assistant', content: '' }]);

      let done = false;
      let buffer = '';

      while (!done) {
        const { value, done: readerDone } = await reader.read();
        if (readerDone) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        
        // Keep the last incomplete line in buffer
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.trim() === '') continue;
          
          if (line.startsWith('data: ')) {
            const jsonStr = line.replace('data: ', '');
            try {
              const data = JSON.parse(jsonStr);
              
              if (data.type === 'end') {
                done = true;
                break;
              } else if (data.type === 'error') {
                setMessages((prev: ChatMessage[]) => {
                  const newArr = [...prev];
                  newArr[newArr.length - 1].content = `[오류] ${data.content}`;
                  newArr[newArr.length - 1].isError = true;
                  return newArr;
                });
              } else if (data.type === 'token' && data.content) {
                setMessages((prev: ChatMessage[]) => {
                  const newArr = [...prev];
                  newArr[newArr.length - 1].content += data.content;
                  return newArr;
                });
              } else if (data.type === 'status') {
                // Ignore status updates or show them visually (currently just logging)
                // console.log("Status update from backend:", data.content);
              }
            } catch (e) {
              console.error('JSON parse error:', e, 'Line:', line);
            }
          }
        }
      }
    } catch (error) {
      console.error('Chat error:', error);
      setMessages((prev: ChatMessage[]) => [
        ...prev,
        { role: 'assistant', content: '응답을 받는 중 문제가 발생했습니다.', isError: true },
      ]);
    } finally {
      setIsStreaming(false);
      abortController.abort(); // Cleanup connection
    }
  };

  return (
    <>
      {/* Chatbot Floating Button */}
      <button
        onClick={() => setIsChatbotOpen(!isChatbotOpen)}
        className="fixed bottom-6 right-6 w-16 h-16 bg-[#059669] hover:bg-[#047857] text-white rounded-full shadow-lg hover:shadow-xl transition-all duration-300 flex items-center justify-center z-50"
        aria-label="챗봇 열기"
      >
        {isChatbotOpen ? (
          <X className="w-6 h-6" />
        ) : (
          <MessageCircle className="w-6 h-6" />
        )}
      </button>

      {/* Chatbot Window */}
      {isChatbotOpen && (
        <div className="fixed bottom-24 right-6 w-[500px] h-[650px] bg-white rounded-[12px] shadow-2xl border border-gray-200 z-50 flex flex-col">
          {/* Chatbot Header */}
          <div className="bg-[#059669] text-white px-4 py-3 rounded-t-[12px] flex items-center justify-between">
            <div className="flex items-center gap-2">
              <MessageCircle className="w-5 h-5" />
              <h3 className="font-semibold text-lg">Palantiny 고객지원</h3>
            </div>
            <div className="flex items-center gap-1">
              <button
                onClick={handleResetChat}
                disabled={isStreaming}
                className={`hover:bg-[#047857] rounded p-1 transition-colors ${isStreaming ? 'opacity-50 cursor-not-allowed' : ''}`}
                aria-label="새로 고침"
                title="대화 새로 시작"
              >
                <RotateCcw className="w-4 h-4" />
              </button>
              <button
                onClick={() => setIsChatbotOpen(false)}
                className="hover:bg-[#047857] rounded p-1 transition-colors"
                aria-label="닫기"
                title="닫기"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Chatbot Messages Area */}
          <div className="flex-1 p-4 overflow-y-auto bg-gray-50 flex flex-col">
            <div className="space-y-4">
              {messages.map((msg: ChatMessage, idx: number) => (
                <div 
                  key={idx} 
                  className={`flex items-start gap-2 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}
                >
                  {/* Avatar only for assistant */}
                  {msg.role === 'assistant' && (
                    <div className="w-8 h-8 rounded-full bg-[#059669] flex items-center justify-center flex-shrink-0">
                      <MessageCircle className="w-4 h-4 text-white" />
                    </div>
                  )}
                  {/* Message Bubble */}
                  <div 
                    className={`rounded-lg p-3 shadow-sm max-w-[80%] text-base ${
                      msg.role === 'user' 
                        ? 'bg-[#059669] text-white whitespace-pre-wrap' 
                        : msg.isError 
                          ? 'bg-red-50 text-red-600 border border-red-200 whitespace-pre-wrap'
                          : 'bg-white text-gray-700'
                    }`}
                  >
                    {msg.role === 'assistant' && !msg.isError ? (
                      <div className="[&_p]:mb-2 [&_p:last-child]:mb-0 [&_strong]:font-bold [&_ul]:list-disc [&_ul]:ml-4 [&_ul]:mb-2 [&_ol]:list-decimal [&_ol]:ml-4 [&_ol]:mb-2 [&_a]:underline [&_table]:w-full [&_table]:my-3 [&_table]:border-collapse [&_th]:border [&_th]:border-[#059669]/20 [&_th]:bg-[#059669]/10 [&_th]:p-2 [&_th]:text-left [&_th]:text-base [&_th]:text-[#059669] [&_th]:whitespace-nowrap [&_td]:border [&_td]:border-gray-200 [&_td]:p-2 [&_td]:text-base [&_td]:whitespace-nowrap [&_tbody>tr]:cursor-pointer [&_tbody>tr:hover]:bg-gray-100 [&_tbody>tr]:transition-colors break-words overflow-x-auto">
                        <ReactMarkdown 
                          remarkPlugins={[remarkGfm]}
                          rehypePlugins={[rehypeRaw]}
                          components={{
                            a: ({ node, href, children, ...props }) => {
                              if (href?.startsWith('/product/')) {
                                return (
                                  <button
                                    data-product="true"
                                    onClick={(e) => { e.stopPropagation(); navigate(href); }}
                                    className="text-left bg-transparent border-none text-[#059669] hover:text-[#047857] hover:underline cursor-pointer transition-colors p-0 m-0 font-semibold"
                                  >
                                    {children}
                                  </button>
                                );
                              }
                              return <a href={href} className="text-[#059669] hover:underline" {...props}>{children}</a>;
                            },
                            tr: (props) => {
                              return (
                                <tr
                                  {...props}
                                  onClick={(e) => {
                                    if (e.currentTarget.querySelector('th')) return; // Ignore header rows
                                    const btn = e.currentTarget.querySelector('[data-product="true"]');
                                    if (btn) {
                                      (btn as HTMLButtonElement).click();
                                    }
                                  }}
                                >
                                  {props.children}
                                </tr>
                              );
                            }
                          }}
                        >
                          {msg.content}
                        </ReactMarkdown>
                      </div>
                    ) : (
                      msg.content
                    )}
                  </div>
                </div>
              ))}
              
              {/* Reference to scroll to latest messages */}
              <div ref={messagesEndRef} />
              
              {/* Quick Questions (only show if few messages or initially) */}
              {messages.length === 1 && (
                <div className="space-y-2 mt-4">
                  <p className="text-sm text-gray-500 px-2 text-center">자주 묻는 질문</p>
                  <div className="space-y-2">
                    {['약재 가격 확인하고 싶어요.', '약재 주문하고 싶어요.'].map((q) => (
                      <button 
                        key={q}
                        onClick={() => handleSendMessage(q)}
                        disabled={isStreaming}
                        className="w-full text-center bg-white hover:bg-gray-50 rounded-lg p-3 shadow-sm text-base text-gray-700 transition-colors border"
                      >
                        {q}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Chatbot Input Area */}
          <div className="p-4 border-t border-gray-200 bg-white rounded-b-[12px]">
            <div className="flex gap-2">
              <Input
                placeholder="메시지를 입력하세요..."
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                onKeyPress={(e) => {
                  if (e.key === 'Enter') {
                    handleSendMessage();
                  }
                }}
                disabled={isStreaming}
                className="flex-1 h-12 text-base rounded-[8px] border-gray-300"
              />
              <Button
                onClick={() => handleSendMessage()}
                disabled={!message.trim() || isStreaming}
                className={`h-12 px-5 rounded-[8px] transition-colors ${
                  message.trim() && !isStreaming 
                    ? 'bg-[#059669] hover:bg-[#047857] text-white' 
                    : 'bg-gray-200 text-gray-400 cursor-not-allowed'
                }`}
              >
                <Send className="w-4 h-4" />
              </Button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}