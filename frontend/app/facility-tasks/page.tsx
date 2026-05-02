'use client';

import { FormEvent, useEffect, useMemo, useState } from 'react';

type TaskCategory = 'statutory' | 'regular' | 'safety' | 'fire' | 'mechanical' | 'other';
type RecurrenceType = 'none' | 'daily' | 'weekly' | 'monthly' | 'quarterly' | 'half_yearly' | 'yearly' | 'custom_days';
type Priority = 'statutory' | 'high' | 'normal';

type FacilityTask = {
  id: number;
  title: string;
  category: TaskCategory;
  category_label: string;
  description: string | null;
  assignee: string | null;
  priority: Priority;
  priority_label: string;
  due_date: string;
  recurrence_type: RecurrenceType;
  recurrence_label: string;
  recurrence_interval_days: number | null;
  reminder_days: number[];
  evidence_required: boolean;
  active: boolean;
  last_completed_at: string | null;
  completion_count: number;
  computed_status: 'overdue' | 'today' | 'week' | 'month' | 'later' | 'paused';
  d_day: number;
};

type Summary = {
  total: number;
  overdue: number;
  today: number;
  week: number;
  month: number;
  statutory: number;
  evidence_required: number;
};

type FormState = {
  title: string;
  category: TaskCategory;
  description: string;
  assignee: string;
  priority: Priority;
  due_date: string;
  recurrence_type: RecurrenceType;
  recurrence_interval_days: string;
  reminder_days: string;
  evidence_required: boolean;
};

const CATEGORY_OPTIONS: { value: TaskCategory; label: string }[] = [
  { value: 'statutory', label: '법정점검' },
  { value: 'regular', label: '정기점검' },
  { value: 'safety', label: '시설안전점검' },
  { value: 'fire', label: '소방점검' },
  { value: 'mechanical', label: '기계설비유지' },
  { value: 'other', label: '기타' },
];

const RECURRENCE_OPTIONS: { value: RecurrenceType; label: string }[] = [
  { value: 'none', label: '반복 없음' },
  { value: 'daily', label: '매일' },
  { value: 'weekly', label: '매주' },
  { value: 'monthly', label: '매월' },
  { value: 'quarterly', label: '분기' },
  { value: 'half_yearly', label: '반기' },
  { value: 'yearly', label: '매년' },
  { value: 'custom_days', label: '사용자 지정' },
];

const PRIORITY_OPTIONS: { value: Priority; label: string }[] = [
  { value: 'statutory', label: '법정' },
  { value: 'high', label: '중요' },
  { value: 'normal', label: '일반' },
];

function getApiBase() {
  const configuredApiBase = process.env.NEXT_PUBLIC_API_BASE?.trim();
  if (configuredApiBase) return configuredApiBase;
  if (typeof window !== 'undefined') {
    const hostname = window.location.hostname;
    if (hostname.endsWith('.onrender.com') && hostname.includes('frontend')) {
      return `https://${hostname.replace('frontend', 'backend')}`;
    }
    if (hostname.endsWith('.app.github.dev')) {
      return `https://${hostname.replace(/-3000\.app\.github\.dev$/, '-8000.app.github.dev')}`;
    }
    if (hostname && hostname !== 'localhost' && hostname !== '127.0.0.1') {
      return `${window.location.protocol}//${hostname}:8000`;
    }
  }
  return 'http://localhost:8000';
}

function formatDateInput(date: Date) {
  const year = date.getFullYear();
  const month = `${date.getMonth() + 1}`.padStart(2, '0');
  const day = `${date.getDate()}`.padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function blankForm(): FormState {
  return {
    title: '',
    category: 'regular',
    description: '',
    assignee: '시설과장',
    priority: 'normal',
    due_date: formatDateInput(new Date()),
    recurrence_type: 'monthly',
    recurrence_interval_days: '',
    reminder_days: '30,7,1,0',
    evidence_required: false,
  };
}

async function responseMessage(res: Response) {
  const body = await res.json().catch(() => null);
  if (body && typeof body.detail === 'string') return body.detail;
  return `요청 실패: ${res.status}`;
}

function parseReminderDays(value: string) {
  return value
    .split(',')
    .map(item => Number(item.trim()))
    .filter(item => Number.isFinite(item) && item >= 0);
}

function statusLabel(task: FacilityTask) {
  if (task.computed_status === 'overdue') return `${Math.abs(task.d_day)}일 지연`;
  if (task.computed_status === 'today') return '오늘';
  if (task.computed_status === 'week') return `D-${task.d_day}`;
  if (task.computed_status === 'month') return `D-${task.d_day}`;
  if (task.computed_status === 'paused') return '중지';
  return `D-${task.d_day}`;
}

function statusTone(task: FacilityTask) {
  if (task.computed_status === 'overdue') return 'border-rose-300 bg-rose-50 text-rose-950';
  if (task.computed_status === 'today') return 'border-amber-300 bg-amber-50 text-amber-950';
  if (task.computed_status === 'week') return 'border-sky-300 bg-sky-50 text-sky-950';
  if (task.priority === 'statutory') return 'border-indigo-200 bg-indigo-50 text-indigo-950';
  return 'border-slate-200 bg-white text-slate-700';
}

function taskSortValue(task: FacilityTask) {
  const statusWeight = task.computed_status === 'overdue' ? 0 : task.computed_status === 'today' ? 1 : task.computed_status === 'week' ? 2 : 3;
  const priorityWeight = task.priority === 'statutory' ? 0 : task.priority === 'high' ? 1 : 2;
  return `${statusWeight}-${priorityWeight}-${task.due_date}-${task.id}`;
}

export default function FacilityTasksPage() {
  const [tasks, setTasks] = useState<FacilityTask[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [form, setForm] = useState<FormState>(() => blankForm());
  const [scope, setScope] = useState('attention');
  const [query, setQuery] = useState('');
  const [notice, setNotice] = useState('');
  const [loading, setLoading] = useState(false);
  const [completionNotes, setCompletionNotes] = useState<Record<number, string>>({});
  const [completionFiles, setCompletionFiles] = useState<Record<number, File | null>>({});

  const sortedTasks = useMemo(() => [...tasks].sort((a, b) => taskSortValue(a).localeCompare(taskSortValue(b))), [tasks]);
  const overdueTasks = useMemo(() => sortedTasks.filter(task => task.computed_status === 'overdue'), [sortedTasks]);
  const todayTasks = useMemo(() => sortedTasks.filter(task => task.computed_status === 'today'), [sortedTasks]);
  const weekTasks = useMemo(() => sortedTasks.filter(task => task.computed_status === 'week'), [sortedTasks]);

  async function loadData(nextScope = scope) {
    const params = new URLSearchParams({ scope: nextScope, limit: '250' });
    if (query.trim()) params.set('q', query.trim());
    const [tasksRes, summaryRes] = await Promise.all([
      fetch(`${getApiBase()}/api/facility-tasks?${params.toString()}`),
      fetch(`${getApiBase()}/api/facility-tasks/summary`),
    ]);
    if (!tasksRes.ok) throw new Error(await responseMessage(tasksRes));
    if (!summaryRes.ok) throw new Error(await responseMessage(summaryRes));
    setTasks(await tasksRes.json());
    setSummary(await summaryRes.json());
  }

  useEffect(() => {
    loadData().catch(err => setNotice(err instanceof Error ? err.message : '업무를 불러오지 못했습니다.'));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function updateField<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm(current => ({ ...current, [key]: value }));
  }

  async function submitTask(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!form.title.trim()) {
      setNotice('업무명을 입력해 주세요.');
      return;
    }
    setLoading(true);
    try {
      const payload = {
        ...form,
        recurrence_interval_days: form.recurrence_type === 'custom_days' ? Number(form.recurrence_interval_days || 0) : null,
        reminder_days: parseReminderDays(form.reminder_days),
      };
      const res = await fetch(`${getApiBase()}/api/facility-tasks`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error(await responseMessage(res));
      setForm(blankForm());
      await loadData();
      setNotice('필수업무를 등록했습니다.');
    } catch (err) {
      setNotice(err instanceof Error ? err.message : '업무 등록 중 오류가 발생했습니다.');
    } finally {
      setLoading(false);
    }
  }

  async function completeTask(task: FacilityTask) {
    setLoading(true);
    try {
      const body = new FormData();
      body.append('note', completionNotes[task.id] || '');
      const file = completionFiles[task.id];
      if (file) body.append('evidence', file);
      const res = await fetch(`${getApiBase()}/api/facility-tasks/${task.id}/complete`, { method: 'POST', body });
      if (!res.ok) throw new Error(await responseMessage(res));
      setCompletionNotes(current => ({ ...current, [task.id]: '' }));
      setCompletionFiles(current => ({ ...current, [task.id]: null }));
      await loadData();
      setNotice('완료 처리했습니다. 반복 업무는 다음 예정일로 자동 갱신됩니다.');
    } catch (err) {
      setNotice(err instanceof Error ? err.message : '완료 처리 중 오류가 발생했습니다.');
    } finally {
      setLoading(false);
    }
  }

  async function pauseTask(task: FacilityTask) {
    if (!confirm(`${task.title} 업무를 중지하시겠습니까?`)) return;
    setLoading(true);
    try {
      const res = await fetch(`${getApiBase()}/api/facility-tasks/${task.id}`, { method: 'DELETE' });
      if (!res.ok) throw new Error(await responseMessage(res));
      await loadData();
      setNotice('업무를 중지했습니다.');
    } catch (err) {
      setNotice(err instanceof Error ? err.message : '업무 중지 중 오류가 발생했습니다.');
    } finally {
      setLoading(false);
    }
  }

  function changeScope(nextScope: string) {
    setScope(nextScope);
    loadData(nextScope).catch(err => setNotice(err instanceof Error ? err.message : '조회 실패'));
  }

  return (
    <main className="min-h-screen bg-slate-100 px-3 py-4 text-slate-950 sm:px-6 lg:px-8">
      <div className="mx-auto w-full max-w-7xl">
        <header className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-6">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-xs font-black uppercase tracking-[0.22em] text-emerald-800">Facility Essentials</p>
              <h1 className="mt-2 text-2xl font-black tracking-tight sm:text-4xl">시설과장 업무관리</h1>
              <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
                반드시 해야 할 법정점검과 정기점검을 지연 없이 확인하고, 완료하면 다음 예정일을 자동으로 잡습니다.
              </p>
            </div>
            <a href="/" className="rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm font-bold text-slate-700">
              업무보고로 이동
            </a>
          </div>
        </header>

        <section className="mt-4 grid grid-cols-2 gap-3 lg:grid-cols-6">
          <Stat label="전체 활성" value={summary?.total ?? 0} tone="slate" />
          <Stat label="지연" value={summary?.overdue ?? 0} tone="rose" />
          <Stat label="오늘" value={summary?.today ?? 0} tone="amber" />
          <Stat label="7일 내" value={summary?.week ?? 0} tone="sky" />
          <Stat label="법정" value={summary?.statutory ?? 0} tone="indigo" />
          <Stat label="증빙필수" value={summary?.evidence_required ?? 0} tone="emerald" />
        </section>

        {notice && <div className="mt-4 rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm font-semibold text-slate-700 shadow-sm">{notice}</div>}

        <section className="mt-4 grid min-w-0 gap-4 lg:grid-cols-[400px_minmax(0,1fr)]">
          <form onSubmit={submitTask} className="min-w-0 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
            <div>
              <h2 className="text-lg font-black">필수업무 등록</h2>
              <p className="mt-1 text-xs font-semibold text-slate-500">처음에는 반드시 잊으면 안 되는 업무만 등록하세요.</p>
            </div>
            <div className="mt-4 grid gap-3">
              <label className="grid gap-1 text-sm font-bold">
                업무명
                <input value={form.title} onChange={event => updateField('title', event.target.value)} className="w-full min-w-0 rounded-xl border border-slate-300 px-3 py-3 font-semibold" placeholder="예: 소방 종합정밀점검" />
              </label>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <label className="grid gap-1 text-sm font-bold">
                  구분
                  <select value={form.category} onChange={event => updateField('category', event.target.value as TaskCategory)} className="w-full rounded-xl border border-slate-300 px-3 py-3 font-semibold">
                    {CATEGORY_OPTIONS.map(option => (
                      <option key={option.value} value={option.value}>{option.label}</option>
                    ))}
                  </select>
                </label>
                <label className="grid gap-1 text-sm font-bold">
                  중요도
                  <select value={form.priority} onChange={event => updateField('priority', event.target.value as Priority)} className="w-full rounded-xl border border-slate-300 px-3 py-3 font-semibold">
                    {PRIORITY_OPTIONS.map(option => (
                      <option key={option.value} value={option.value}>{option.label}</option>
                    ))}
                  </select>
                </label>
              </div>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <label className="grid gap-1 text-sm font-bold">
                  다음 예정일
                  <input type="date" value={form.due_date} onChange={event => updateField('due_date', event.target.value)} className="w-full rounded-xl border border-slate-300 px-3 py-3 font-semibold" />
                </label>
                <label className="grid gap-1 text-sm font-bold">
                  담당자
                  <input value={form.assignee} onChange={event => updateField('assignee', event.target.value)} className="w-full rounded-xl border border-slate-300 px-3 py-3 font-semibold" placeholder="시설과장" />
                </label>
              </div>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <label className="grid gap-1 text-sm font-bold">
                  반복주기
                  <select value={form.recurrence_type} onChange={event => updateField('recurrence_type', event.target.value as RecurrenceType)} className="w-full rounded-xl border border-slate-300 px-3 py-3 font-semibold">
                    {RECURRENCE_OPTIONS.map(option => (
                      <option key={option.value} value={option.value}>{option.label}</option>
                    ))}
                  </select>
                </label>
                <label className="grid gap-1 text-sm font-bold">
                  사용자 지정 일수
                  <input value={form.recurrence_interval_days} onChange={event => updateField('recurrence_interval_days', event.target.value)} disabled={form.recurrence_type !== 'custom_days'} className="w-full rounded-xl border border-slate-300 px-3 py-3 font-semibold disabled:bg-slate-100" inputMode="numeric" placeholder="예: 45" />
                </label>
              </div>
              <label className="grid gap-1 text-sm font-bold">
                알림 기준
                <input value={form.reminder_days} onChange={event => updateField('reminder_days', event.target.value)} className="w-full rounded-xl border border-slate-300 px-3 py-3 font-semibold" placeholder="30,7,1,0" />
              </label>
              <label className="flex items-center gap-2 rounded-xl border border-slate-300 bg-slate-50 px-3 py-3 text-sm font-bold">
                <input type="checkbox" checked={form.evidence_required} onChange={event => updateField('evidence_required', event.target.checked)} className="h-4 w-4" />
                완료 시 증빙파일 필수
              </label>
              <label className="grid gap-1 text-sm font-bold">
                메모
                <textarea value={form.description} onChange={event => updateField('description', event.target.value)} className="min-h-24 w-full rounded-xl border border-slate-300 px-3 py-3 font-semibold" placeholder="점검 기준, 업체, 준비물 등" />
              </label>
              <button disabled={loading} className="rounded-xl bg-slate-950 px-4 py-3 text-sm font-black text-white disabled:bg-slate-400">
                {loading ? '처리 중...' : '필수업무 등록'}
              </button>
            </div>
          </form>

          <section className="min-w-0 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-lg font-black">해야 할 일</h2>
                <p className="mt-1 text-xs font-semibold text-slate-500">지연 업무는 완료 전까지 사라지지 않습니다.</p>
              </div>
              <button onClick={() => loadData().catch(err => setNotice(err instanceof Error ? err.message : '새로고침 실패'))} className="rounded-lg border border-slate-300 px-3 py-2 text-xs font-bold text-slate-700">
                새로고침
              </button>
            </div>

            <div className="mt-4 grid gap-2 md:grid-cols-[1fr_150px_90px]">
              <input value={query} onChange={event => setQuery(event.target.value)} onKeyDown={event => event.key === 'Enter' && loadData().catch(err => setNotice(err instanceof Error ? err.message : '검색 실패'))} className="w-full rounded-xl border border-slate-300 px-3 py-3 text-sm font-semibold" placeholder="업무명, 담당자 검색" />
              <select value={scope} onChange={event => changeScope(event.target.value)} className="w-full rounded-xl border border-slate-300 px-3 py-3 text-sm font-semibold">
                <option value="attention">지연/오늘/7일</option>
                <option value="overdue">지연</option>
                <option value="today">오늘</option>
                <option value="week">7일 내</option>
                <option value="month">30일 내</option>
                <option value="all">전체</option>
              </select>
              <button onClick={() => loadData().catch(err => setNotice(err instanceof Error ? err.message : '검색 실패'))} className="rounded-xl bg-slate-900 px-3 py-3 text-sm font-black text-white">
                조회
              </button>
            </div>

            {(overdueTasks.length > 0 || todayTasks.length > 0 || weekTasks.length > 0) && (
              <div className="mt-4 grid gap-2 sm:grid-cols-3">
                <AlertBand label="지연" value={overdueTasks.length} tone="rose" />
                <AlertBand label="오늘" value={todayTasks.length} tone="amber" />
                <AlertBand label="7일 내" value={weekTasks.length} tone="sky" />
              </div>
            )}

            <div className="mt-4 grid gap-3">
              {sortedTasks.map(task => (
                <article key={task.id} className={`rounded-2xl border p-3 ${statusTone(task)}`}>
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex flex-wrap gap-2">
                        <span className="rounded-full bg-white px-2 py-1 text-xs font-black">{task.category_label}</span>
                        <span className="rounded-full bg-white px-2 py-1 text-xs font-black">{task.priority_label}</span>
                        {task.evidence_required && <span className="rounded-full bg-white px-2 py-1 text-xs font-black">증빙필수</span>}
                      </div>
                      <h3 className="mt-2 break-words text-lg font-black">{task.title}</h3>
                      <div className="mt-2 grid gap-1 text-sm font-semibold sm:grid-cols-2">
                        <div>예정일: {task.due_date} / {statusLabel(task)}</div>
                        <div>담당: {task.assignee || '-'}</div>
                        <div>반복: {task.recurrence_label}</div>
                        <div>완료: {task.completion_count}회</div>
                      </div>
                      {task.description && <p className="mt-2 whitespace-pre-wrap text-sm leading-6">{task.description}</p>}
                    </div>
                    <button onClick={() => pauseTask(task)} disabled={loading} className="shrink-0 rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-bold text-slate-700 disabled:opacity-50">
                      중지
                    </button>
                  </div>
                  <div className="mt-3 grid gap-2 md:grid-cols-[1fr_180px_auto]">
                    <input value={completionNotes[task.id] || ''} onChange={event => setCompletionNotes(current => ({ ...current, [task.id]: event.target.value }))} className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm font-semibold" placeholder="완료 메모" />
                    <input type="file" onChange={event => setCompletionFiles(current => ({ ...current, [task.id]: event.target.files?.[0] || null }))} className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-xs" />
                    <button onClick={() => completeTask(task)} disabled={loading} className="rounded-xl bg-emerald-800 px-3 py-2 text-sm font-black text-white disabled:bg-slate-300">
                      완료
                    </button>
                  </div>
                </article>
              ))}
              {sortedTasks.length === 0 && <div className="rounded-xl border border-dashed border-slate-300 p-8 text-center text-sm font-semibold text-slate-500">조회된 필수업무가 없습니다.</div>}
            </div>
          </section>
        </section>
      </div>
    </main>
  );
}

function Stat({ label, value, tone }: { label: string; value: number; tone: 'slate' | 'rose' | 'amber' | 'sky' | 'indigo' | 'emerald' }) {
  const tones = {
    slate: 'border-slate-200 bg-white text-slate-900',
    rose: 'border-rose-200 bg-rose-50 text-rose-950',
    amber: 'border-amber-200 bg-amber-50 text-amber-950',
    sky: 'border-sky-200 bg-sky-50 text-sky-950',
    indigo: 'border-indigo-200 bg-indigo-50 text-indigo-950',
    emerald: 'border-emerald-200 bg-emerald-50 text-emerald-950',
  };
  return (
    <div className={`rounded-2xl border p-4 shadow-sm ${tones[tone]}`}>
      <div className="text-xs font-black">{label}</div>
      <div className="mt-2 text-2xl font-black">{value}</div>
    </div>
  );
}

function AlertBand({ label, value, tone }: { label: string; value: number; tone: 'rose' | 'amber' | 'sky' }) {
  const tones = {
    rose: 'border-rose-200 bg-rose-50 text-rose-950',
    amber: 'border-amber-200 bg-amber-50 text-amber-950',
    sky: 'border-sky-200 bg-sky-50 text-sky-950',
  };
  return (
    <div className={`rounded-xl border px-3 py-2 text-sm font-black ${tones[tone]}`}>
      {label} {value}건
    </div>
  );
}

