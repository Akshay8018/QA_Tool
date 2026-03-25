'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  Bot,
  Compass,
  Image as ImageIcon,
  LayoutGrid,
  MessageSquarePlus,
  Search,
  Settings,
  Sparkles,
  UserCircle2,
} from 'lucide-react';

type RunResponse = {
  json_report: Record<string, unknown>;
  human_report: Record<string, unknown>;
};

type IntakeQuestion = {
  id: string;
  label: string;
  placeholder?: string;
};

type IntakeResponse = {
  needs_clarification: boolean;
  normalized_prompt: string;
  detected: Record<string, unknown>;
  questions: IntakeQuestion[];
};

type Message = {
  id: string;
  role: 'user' | 'assistant' | 'system';
  text: string;
};

type FlowStage = 'idle' | 'clarifying' | 'confirm_generate' | 'review_cases' | 'confirm_execute' | 'executing';

type ChatSession = {
  id: string;
  title: string;
  updatedAt: number;
  status: string;
  messages: Message[];
  questions: IntakeQuestion[];
  answers: Record<string, string>;
  questionIndex: number;
  detected: Record<string, unknown>;
  promptDraft: string;
  basePrompt: string;
  report: RunResponse | null;
  stage: FlowStage;
  previewCases: Array<{ title?: string; objective?: string; steps?: Array<{ action?: string; target?: string; assertion?: string }> }>;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? 'http://127.0.0.1:8010';
/** When true (default), first message uses POST /v1/chat/message + session refetch; set NEXT_PUBLIC_USE_CHAT_API=false for legacy intake-only. */
const USE_CHAT_API = process.env.NEXT_PUBLIC_USE_CHAT_API !== 'false';

type ChatMessageResponse = {
  reply: string;
  session_id: string;
  context_summary: string;
  message_count: number;
  intake: IntakeResponse | null;
  suggested_next: string;
};

type SessionSummary = {
  session_id: string;
  title: string;
  updated_at: string;
};

type SessionMessageApi = {
  message_id: string;
  role: string;
  text: string;
};

function initialSession(): ChatSession {
  return {
    id: `chat-${Date.now()}`,
    title: 'New chat',
    updatedAt: Date.now(),
    status: 'Ready',
    messages: [],
    questions: [],
    answers: {},
    questionIndex: 0,
    detected: {},
    promptDraft: '',
    basePrompt: '',
    report: null,
    stage: 'idle',
    previewCases: [],
  };
}

function isYes(text: string): boolean {
  const t = text.trim().toLowerCase();
  return ['yes', 'y', 'ok', 'okay', 'proceed', 'confirm', 'approved'].includes(t);
}

function isNo(text: string): boolean {
  const t = text.trim().toLowerCase();
  return ['no', 'n', 'stop', 'cancel', 'reject'].includes(t);
}

export default function Dashboard() {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeId, setActiveId] = useState<string>('');
  const [engine, setEngine] = useState('playwright');
  const [watchExecution, setWatchExecution] = useState(true);

  const active = useMemo(() => sessions.find((s) => s.id === activeId) ?? sessions[0], [sessions, activeId]);

  async function createRemoteSession(title: string): Promise<SessionSummary> {
    const res = await fetch(`${API_BASE}/v1/tests/sessions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title }),
    });
    if (!res.ok) throw new Error(`Create session failed: ${res.status}`);
    return (await res.json()) as SessionSummary;
  }

  async function appendRemoteMessage(sessionId: string, role: Message['role'], text: string): Promise<void> {
    try {
      const res = await fetch(`${API_BASE}/v1/tests/sessions/${sessionId}/messages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ role, text }),
      });
      if (!res.ok) return;
    } catch {
      return;
    }
  }

  async function loadSession(sessionId: string): Promise<{ summary: SessionSummary; messages: SessionMessageApi[] }> {
    const res = await fetch(`${API_BASE}/v1/tests/sessions/${sessionId}`);
    if (!res.ok) throw new Error(`Load session failed: ${res.status}`);
    const data = (await res.json()) as SessionSummary & { messages: SessionMessageApi[] };
    return {
      summary: { session_id: data.session_id, title: data.title, updated_at: data.updated_at },
      messages: data.messages ?? [],
    };
  }

  async function loadSessions(): Promise<SessionSummary[]> {
    const res = await fetch(`${API_BASE}/v1/tests/sessions`);
    if (!res.ok) throw new Error(`List sessions failed: ${res.status}`);
    const data = (await res.json()) as { sessions: SessionSummary[] };
    return data.sessions ?? [];
  }

  function mapApiToChat(summary: SessionSummary, messages: SessionMessageApi[]): ChatSession {
    const mappedMessages: Message[] = messages.map((m) => ({
      id: m.message_id,
      role: (m.role === 'assistant' || m.role === 'system' ? m.role : 'user') as Message['role'],
      text: m.text,
    }));
    return {
      id: summary.session_id,
      title: summary.title || 'New chat',
      updatedAt: Date.parse(summary.updated_at) || Date.now(),
      status: 'Ready',
      messages: mappedMessages,
      questions: [],
      answers: {},
      questionIndex: 0,
      detected: {},
      promptDraft: '',
      basePrompt: '',
      report: null,
      stage: 'idle',
      previewCases: [],
    };
  }

  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const summaries = await loadSessions();
        if (!mounted) return;
        if (!summaries.length) {
          const created = await createRemoteSession('New chat');
          if (!mounted) return;
          const s = mapApiToChat(created, []);
          setSessions([s]);
          setActiveId(s.id);
          return;
        }
        const hydrated = await Promise.all(
          summaries.map(async (summary) => {
            const detail = await loadSession(summary.session_id);
            return mapApiToChat(detail.summary, detail.messages);
          })
        );
        if (!mounted) return;
        setSessions(hydrated);
        setActiveId(hydrated[0]?.id ?? '');
      } catch {
        if (!mounted) return;
        const local = initialSession();
        setSessions([local]);
        setActiveId(local.id);
      }
    })();
    return () => {
      mounted = false;
    };
  }, []);

  const updateActive = (updater: (s: ChatSession) => ChatSession) => {
    setSessions((prev) => prev.map((s) => (s.id === activeId ? updater(s) : s)));
  };

  const createChat = async () => {
    const created = await createRemoteSession('New chat');
    const s = mapApiToChat(created, []);
    setSessions((prev) => [s, ...prev]);
    setActiveId(s.id);
  };

  async function intakePrompt(prompt: string) {
    const res = await fetch(`${API_BASE}/v1/tests/intake`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ instruction: prompt }),
    });
    if (!res.ok) throw new Error(`Intake failed: ${res.status}`);
    return (await res.json()) as IntakeResponse;
  }

  /** Server-backed chat: persists user+assistant and runs intake / flow hints. */
  async function postChatMessage(sessionId: string, message: string, flowStage: FlowStage): Promise<ChatMessageResponse> {
    const res = await fetch(`${API_BASE}/v1/chat/message`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, message, flow_stage: flowStage }),
    });
    if (!res.ok) throw new Error(`Chat failed: ${res.status}`);
    return (await res.json()) as ChatMessageResponse;
  }

  function isRemoteSessionId(id: string): boolean {
    return id.length > 0 && !id.startsWith('chat-');
  }

  async function previewCases(basePrompt: string, answers: Record<string, string>) {
    const res = await fetch(`${API_BASE}/v1/tests/preview-cases`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        instruction: basePrompt,
        execution_engine: engine,
        watch_execution: watchExecution,
        clarification_answers: answers,
      }),
    });
    if (!res.ok) throw new Error(`Preview failed: ${res.status}`);
    return (await res.json()) as {
      scenario_count: number;
      scenarios: Array<{ title?: string; objective?: string; steps?: Array<{ action?: string; target?: string; assertion?: string }> }>;
    };
  }

  async function runExecution(basePrompt: string, answers: Record<string, string>) {
    const payload = {
      instruction: basePrompt,
      execution_engine: engine,
      watch_execution: watchExecution,
      clarification_answers: answers,
    };

    const res = await fetch(`${API_BASE}/v1/tests/run-stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (!res.ok) throw new Error(`Request failed: ${res.status}`);
    if (!res.body) throw new Error('No response stream from server');

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let newlineIndex = buffer.indexOf('\n');
      while (newlineIndex >= 0) {
        const line = buffer.slice(0, newlineIndex).trim();
        buffer = buffer.slice(newlineIndex + 1);
        newlineIndex = buffer.indexOf('\n');
        if (!line) continue;

        const chunk = JSON.parse(line) as
          | { type: 'log'; event: Record<string, unknown> }
          | { type: 'final'; json_report: Record<string, unknown>; human_report: Record<string, unknown> }
          | { type: 'error'; message: string };

        if (chunk.type === 'log') {
          const txt = `[${String(chunk.event.type)}] ${JSON.stringify(chunk.event)}`;
          await appendRemoteMessage(activeId, 'system', txt);
          updateActive((s) => ({
            ...s,
            updatedAt: Date.now(),
            messages: [...s.messages, { id: `log-${Date.now()}-${Math.random()}`, role: 'system', text: txt }],
          }));
        } else if (chunk.type === 'final') {
          await appendRemoteMessage(activeId, 'assistant', 'Execution finished. Summary is shown below.');
          updateActive((s) => ({
            ...s,
            updatedAt: Date.now(),
            status: 'Completed',
            report: { json_report: chunk.json_report, human_report: chunk.human_report },
            stage: 'idle',
            messages: [...s.messages, { id: `done-${Date.now()}`, role: 'assistant', text: 'Execution finished. Summary is shown below.' }],
          }));
        } else {
          await appendRemoteMessage(activeId, 'assistant', `Execution failed: ${chunk.message}`);
          updateActive((s) => ({
            ...s,
            updatedAt: Date.now(),
            status: 'Failed',
            stage: 'idle',
            messages: [...s.messages, { id: `err-${Date.now()}`, role: 'assistant', text: `Execution failed: ${chunk.message}` }],
          }));
        }
      }
    }
  }

  async function sendPrompt() {
    if (!active) return;
    const prompt = active.promptDraft.trim();
    if (!prompt) return;

    const useChatIdle =
      USE_CHAT_API && active.stage === 'idle' && isRemoteSessionId(activeId);
    const useChatManagedStage =
      USE_CHAT_API &&
      isRemoteSessionId(activeId) &&
      (active.stage === 'confirm_generate' || active.stage === 'review_cases' || active.stage === 'confirm_execute');
    let stageReplyAlreadyPersisted = false;

    if (useChatIdle) {
      try {
        const chat = await postChatMessage(activeId, prompt, 'idle');
        const detail = await loadSession(activeId);
        const merged = mapApiToChat(detail.summary, detail.messages);
        const intake = chat.intake;

        updateActive((s) => ({
          ...s,
          promptDraft: '',
          updatedAt: Date.now(),
          messages: merged.messages,
          basePrompt: prompt,
          answers: {},
          ...(intake && intake.needs_clarification
            ? {
                stage: 'clarifying' as FlowStage,
                questions: intake.questions,
                detected: intake.detected,
                questionIndex: 0,
                status: 'Need clarifications',
              }
            : {
                stage: 'confirm_generate' as FlowStage,
                questions: [],
                detected: intake?.detected ?? {},
                questionIndex: 0,
                status: 'Ready for testcase generation',
              }),
        }));
        return;
      } catch {
        /* fall through to legacy path */
      }
    }

    if (useChatManagedStage) {
      try {
        await postChatMessage(activeId, prompt, active.stage);
        const detail = await loadSession(activeId);
        const merged = mapApiToChat(detail.summary, detail.messages);
        updateActive((s) => ({
          ...s,
          promptDraft: '',
          updatedAt: Date.now(),
          messages: merged.messages,
        }));
        stageReplyAlreadyPersisted = true;
      } catch {
        stageReplyAlreadyPersisted = false;
      }
    }

    if (!stageReplyAlreadyPersisted) {
      await appendRemoteMessage(activeId, 'user', prompt);
    }
    if (!stageReplyAlreadyPersisted) {
      updateActive((s) => ({
        ...s,
        title: s.title === 'New chat' ? s.title : s.title,
        promptDraft: '',
        updatedAt: Date.now(),
        messages: [...s.messages, { id: `u-${Date.now()}`, role: 'user', text: prompt }],
      }));
    }

    try {
      if (active.stage === 'clarifying' && active.questions[active.questionIndex]) {
        const q = active.questions[active.questionIndex];
        const nextAnswers = { ...active.answers, [q.id]: prompt };
        const nextIndex = active.questionIndex + 1;

        if (nextIndex < active.questions.length) {
          const nextQ = active.questions[nextIndex];
          await appendRemoteMessage(activeId, 'assistant', nextQ.label);
          updateActive((s) => ({
            ...s,
            answers: nextAnswers,
            questionIndex: nextIndex,
            status: 'Clarification in progress',
            messages: [...s.messages, { id: `a-${Date.now()}`, role: 'assistant', text: nextQ.label }],
          }));
          return;
        }

        updateActive((s) => ({
          ...s,
          answers: nextAnswers,
          questionIndex: nextIndex,
          stage: 'confirm_generate',
          status: 'Waiting confirmation for testcase generation',
          messages: [
            ...s.messages,
            {
              id: `a-${Date.now()}`,
              role: 'assistant',
              text: 'Thanks. I have all required inputs. Should I now generate complete functional and non-functional test cases? Reply yes/no.',
            },
          ],
        }));
        return;
      }

      if (active.stage === 'confirm_generate') {
        if (isYes(prompt)) {
          updateActive((s) => ({ ...s, status: 'Generating test cases...' }));
          const preview = await previewCases(active.basePrompt, active.answers);
          const caseText = preview.scenarios
            .map((sc, i) => `${i + 1}. ${sc.title ?? 'Scenario'} - ${sc.objective ?? 'Objective not provided'}`)
            .join('\n');
          updateActive((s) => ({
            ...s,
            stage: 'review_cases',
            previewCases: preview.scenarios,
            status: 'Review generated test cases',
            messages: [
              ...s.messages,
              {
                id: `a-${Date.now()}`,
                role: 'assistant',
                text: `Generated ${preview.scenario_count} test cases:\n${caseText}\n\nAre these test cases correct? Reply yes/no and optionally mention corrections.`,
              },
            ],
          }));
          if (!stageReplyAlreadyPersisted) {
            await appendRemoteMessage(
              activeId,
              'assistant',
              `Generated ${preview.scenario_count} test cases. Are these test cases correct? Reply yes/no and optionally mention corrections.`
            );
          }
        } else {
          if (!stageReplyAlreadyPersisted) {
            await appendRemoteMessage(
              activeId,
              'assistant',
              'Okay. Please provide the missing or corrected details in your next messages. I will continue asking if needed.'
            );
          }
          updateActive((s) => ({
            ...s,
            stage: 'clarifying',
            status: 'Please provide additional details',
            messages: [
              ...s.messages,
              {
                id: `a-${Date.now()}`,
                role: 'assistant',
                text: 'Okay. Please provide the missing or corrected details in your next messages. I will continue asking if needed.',
              },
            ],
          }));
        }
        return;
      }

      if (active.stage === 'review_cases') {
        if (isYes(prompt)) {
          if (!stageReplyAlreadyPersisted) {
            await appendRemoteMessage(
              activeId,
              'assistant',
              'Great. Final confirmation: Do you approve starting test execution now? Reply yes/no.'
            );
          }
          updateActive((s) => ({
            ...s,
            stage: 'confirm_execute',
            status: 'Awaiting final execution approval',
            messages: [
              ...s.messages,
              {
                id: `a-${Date.now()}`,
                role: 'assistant',
                text: 'Great. Final confirmation: Do you approve starting test execution now? Reply yes/no.',
              },
            ],
          }));
        } else {
          if (!stageReplyAlreadyPersisted) {
            await appendRemoteMessage(activeId, 'assistant', 'Please provide corrections. I will regenerate test cases after your updates.');
          }
          updateActive((s) => ({
            ...s,
            stage: 'clarifying',
            status: 'Collecting corrections for testcase regeneration',
            messages: [
              ...s.messages,
              {
                id: `a-${Date.now()}`,
                role: 'assistant',
                text: 'Please provide corrections. I will regenerate test cases after your updates.',
              },
            ],
          }));
        }
        return;
      }

      if (active.stage === 'confirm_execute') {
        if (isYes(prompt)) {
          if (!stageReplyAlreadyPersisted) {
            await appendRemoteMessage(activeId, 'system', 'Execution started...');
          }
          updateActive((s) => ({
            ...s,
            stage: 'executing',
            status: 'Running tests...',
            report: null,
            messages: [...s.messages, { id: `sys-${Date.now()}`, role: 'system', text: 'Execution started...' }],
          }));
          await runExecution(active.basePrompt, active.answers);
        } else {
          if (!stageReplyAlreadyPersisted) {
            await appendRemoteMessage(activeId, 'assistant', 'Execution cancelled. You can continue refining the chat.');
          }
          updateActive((s) => ({
            ...s,
            stage: 'idle',
            status: 'Execution cancelled by user',
            messages: [...s.messages, { id: `a-${Date.now()}`, role: 'assistant', text: 'Execution cancelled. You can continue refining the chat.' }],
          }));
        }
        return;
      }

      // initial prompt processing
      updateActive((s) => ({ ...s, status: 'Analyzing prompt...', basePrompt: prompt, answers: {}, questions: [], questionIndex: 0 }));
      const data = await intakePrompt(prompt);

      if (data.needs_clarification) {
        const firstQ = data.questions[0]?.label ?? 'Please provide required details.';
        await appendRemoteMessage(activeId, 'assistant', firstQ);
        updateActive((s) => ({
          ...s,
          stage: 'clarifying',
          questions: data.questions,
          detected: data.detected,
          questionIndex: 0,
          status: 'Need clarifications',
          messages: [...s.messages, { id: `a-${Date.now()}`, role: 'assistant', text: firstQ }],
        }));
      } else {
        await appendRemoteMessage(
          activeId,
          'assistant',
          'I have enough context. Should I generate all relevant functional and non-functional test cases now? Reply yes/no.'
        );
        updateActive((s) => ({
          ...s,
          stage: 'confirm_generate',
          questions: [],
          detected: data.detected,
          status: 'Ready for testcase generation',
          messages: [
            ...s.messages,
            {
              id: `a-${Date.now()}`,
              role: 'assistant',
              text: 'I have enough context. Should I generate all relevant functional and non-functional test cases now? Reply yes/no.',
            },
          ],
        }));
      }
    } catch (error) {
      await appendRemoteMessage(activeId, 'assistant', `Could not continue: ${(error as Error).message}`);
      updateActive((s) => ({
        ...s,
        status: 'Failed',
        stage: 'idle',
        messages: [...s.messages, { id: `e-${Date.now()}`, role: 'assistant', text: `Could not continue: ${(error as Error).message}` }],
      }));
    }
  }

  const summary = active?.report?.json_report as { results?: Array<{ status?: string }> } | undefined;
  const total = summary?.results?.length ?? 0;
  const pass = summary?.results?.filter((r) => r.status === 'passed').length ?? 0;
  const fail = total - pass;

  return (
    <div className="gpt-shell">
      <aside className="gpt-sidebar">
        <div className="side-top-icons">
          <span><Bot size={15} /></span>
          <span><Compass size={15} /></span>
        </div>
        <button className="new-chat" onClick={() => { void createChat(); }}><MessageSquarePlus size={15} /> New chat</button>
        <div className="side-links">
          <button><Search size={14} /> Search chats</button>
          <button><ImageIcon size={14} /> Images</button>
          <button><LayoutGrid size={14} /> Apps</button>
          <button><Sparkles size={14} /> Codex</button>
        </div>
        <div className="session-list">
          {sessions.map((s) => (
            <button key={s.id} className={`session-item ${s.id === activeId ? 'active' : ''}`} onClick={() => setActiveId(s.id)}>
              <strong>{s.title === 'New chat' && s.messages.find((m) => m.role === 'user') ? s.messages.find((m) => m.role === 'user')!.text.slice(0, 36) : s.title}</strong>
              <span>{s.status}</span>
            </button>
          ))}
        </div>
      </aside>

      <main className="gpt-main">
        <header className="gpt-header">
          <div>QPilot GPT ?</div>
          <div className="head-icons"><UserCircle2 size={15} /> <Settings size={15} /></div>
        </header>

        {active && active.messages.length === 0 && (
          <section className="hero">
            <h2>Where should we begin?</h2>
          </section>
        )}

        <section className="thread">
          {active?.messages.map((m) => (
            <div key={m.id} className={`bubble-row ${m.role}`}>
              <div className="bubble">{m.text}</div>
            </div>
          ))}
        </section>

        <section className="composer-wrap">
          <div className="composer-input-wrap">
            <textarea
              rows={3}
              value={active?.promptDraft ?? ''}
              onChange={(e) => updateActive((s) => ({ ...s, promptDraft: e.target.value }))}
              placeholder="Type your response or next instruction here..."
            />
            <button className="send-inside" onClick={sendPrompt}>Send</button>
          </div>
          <div className="status-line">Status: {active?.status ?? 'Loading...'}</div>
        </section>

        {active?.report && (
          <section className="summary">
            <h3>Execution Summary</h3>
            <div className="stats">
              <div><strong>Total</strong><span>{total}</span></div>
              <div><strong>Passed</strong><span>{pass}</span></div>
              <div><strong>Failed</strong><span>{fail}</span></div>
            </div>
            <pre>{JSON.stringify(active.report.human_report, null, 2)}</pre>
          </section>
        )}
      </main>
    </div>
  );
}
