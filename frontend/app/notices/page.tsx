'use client';

import { FormEvent, useEffect, useMemo, useState } from 'react';

type NoticeStatus = 'draft' | 'scheduled' | 'posted' | 'removal_due' | 'expired' | 'removed' | 'unauthorized';
type NoticeCategory = 'notice' | 'announcement' | 'move' | 'commercial' | 'other';

type BoardPost = {
  id: number;
  category: NoticeCategory;
  category_label: string;
  title: string;
  description: string | null;
  location: string;
  line: string | null;
  floor: string | null;
  board_name: string | null;
  start_date: string;
  end_date: string;
  removal_due_date: string | null;
  advertiser: string | null;
  contact: string | null;
  status: NoticeStatus;
  computed_status: NoticeStatus;
  status_label: string;
  note: string | null;
  image_url: string | null;
  attachment_url: string | null;
  attachment_filename: string | null;
  attachment_content_type: string | null;
  removal_image_url: string | null;
  removal_note: string | null;
  removed_at: string | null;
  created_at: string;
};

type LocationOption = {
  id: number;
  building: string;
  line: string;
  floor: string;
  sort_order: number;
};

type Summary = {
  total: number;
  posted: number;
  removal_due: number;
  expired: number;
  scheduled: number;
  unauthorized: number;
};

type LocationFormState = {
  building: string;
  line: string;
  floor: string;
  sort_order: string;
};

type FormState = {
  category: NoticeCategory;
  title: string;
  description: string;
  location: string;
  line: string;
  floor: string;
  start_date: string;
  end_date: string;
  removal_due_date: string;
  advertiser: string;
  contact: string;
  status: NoticeStatus;
  note: string;
};

const CATEGORY_OPTIONS: { value: NoticeCategory; label: string }[] = [
  { value: 'notice', label: '안내' },
  { value: 'announcement', label: '공고문' },
  { value: 'move', label: '전입/전출' },
  { value: 'commercial', label: '상업게시물' },
  { value: 'other', label: '기타' },
];

const STATUS_OPTIONS: { value: NoticeStatus | ''; label: string }[] = [
  { value: '', label: '전체' },
  { value: 'posted', label: '게시 중' },
  { value: 'removal_due', label: '철거 대상' },
  { value: 'expired', label: '기간 만료' },
  { value: 'scheduled', label: '게시 예정' },
  { value: 'removed', label: '철거 완료' },
  { value: 'unauthorized', label: '무단 게시' },
];

const ATTACHMENT_ACCEPT = '.jpg,.jpeg,.png,.webp,.gif,.pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.hwp,.hwpx,.txt';

const blankForm = (): FormState => {
  const today = formatDateInput(new Date());
  const end = new Date();
  end.setDate(end.getDate() + 7);
  const removal = new Date(end);
  removal.setDate(removal.getDate() + 1);
  return {
    category: 'notice',
    title: '',
    description: '',
    location: '',
    line: '',
    floor: '',
    start_date: today,
    end_date: formatDateInput(end),
    removal_due_date: formatDateInput(removal),
    advertiser: '',
    contact: '',
    status: 'posted',
    note: '',
  };
};

const blankLocationForm = (): LocationFormState => ({
  building: '',
  line: '',
  floor: '',
  sort_order: '0',
});

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

function imageSrc(path: string | null) {
  if (!path) return '';
  if (path.startsWith('http')) return path;
  return `${getApiBase()}${path}`;
}

function fileExtension(post: BoardPost) {
  const filename = (post.attachment_filename || post.attachment_url || '').toLowerCase();
  const dotIndex = filename.lastIndexOf('.');
  return dotIndex >= 0 ? filename.slice(dotIndex + 1) : '';
}

function isImageFile(post: BoardPost) {
  const contentType = post.attachment_content_type || '';
  return Boolean(post.image_url || contentType.startsWith('image/'));
}

function isPdfFile(post: BoardPost) {
  const contentType = post.attachment_content_type || '';
  const filename = post.attachment_filename || post.attachment_url || '';
  return contentType.includes('pdf') || filename.toLowerCase().endsWith('.pdf');
}

function fileLabel(post: BoardPost) {
  return post.attachment_filename || (post.attachment_url ? post.attachment_url.split('/').pop() : '') || '게시파일';
}

function isOfficePreviewFile(post: BoardPost) {
  return ['doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx'].includes(fileExtension(post));
}

function isTextPreviewFile(post: BoardPost) {
  return fileExtension(post) === 'txt';
}

function isHwpFile(post: BoardPost) {
  return ['hwp', 'hwpx'].includes(fileExtension(post));
}

function previewMessage(post: BoardPost) {
  if (!post.attachment_url) return '파일 없음';
  if (isTextPreviewFile(post)) return 'TXT 파일은 원본 보기로 확인합니다.';
  if (isHwpFile(post)) return 'HWP/HWPX는 기기 환경에 따라 원본 보기로 확인합니다.';
  if (isOfficePreviewFile(post)) return '문서 파일은 아래 문서목록에서 열 수 있습니다.';
  return fileLabel(post);
}

async function responseMessage(res: Response) {
  const body = await res.json().catch(() => null);
  if (body && typeof body.detail === 'string') return body.detail;
  return `요청 실패: ${res.status}`;
}

function statusTone(status: NoticeStatus) {
  if (status === 'posted') return 'border-emerald-200 bg-emerald-50 text-emerald-900';
  if (status === 'removal_due' || status === 'expired') return 'border-rose-200 bg-rose-50 text-rose-900';
  if (status === 'scheduled') return 'border-sky-200 bg-sky-50 text-sky-900';
  if (status === 'unauthorized') return 'border-amber-200 bg-amber-50 text-amber-950';
  if (status === 'removed') return 'border-slate-200 bg-slate-100 text-slate-600';
  return 'border-slate-200 bg-white text-slate-700';
}

function categoryTone(category: NoticeCategory) {
  if (category === 'announcement') return 'bg-indigo-50 text-indigo-900';
  if (category === 'move') return 'bg-sky-50 text-sky-900';
  if (category === 'commercial') return 'bg-amber-50 text-amber-950';
  if (category === 'other') return 'bg-slate-100 text-slate-700';
  return 'bg-emerald-50 text-emerald-900';
}

function formFromNotice(row: BoardPost): FormState {
  return {
    category: row.category,
    title: row.title || '',
    description: row.description || '',
    location: row.location || '',
    line: row.line || '',
    floor: row.floor || row.board_name || '',
    start_date: row.start_date || '',
    end_date: row.end_date || '',
    removal_due_date: row.removal_due_date || '',
    advertiser: row.advertiser || '',
    contact: row.contact || '',
    status: row.status || 'posted',
    note: row.note || '',
  };
}

export default function NoticeBoardPage() {
  const [posts, setPosts] = useState<BoardPost[]>([]);
  const [locationOptions, setLocationOptions] = useState<LocationOption[]>([]);
  const [locationForm, setLocationForm] = useState<LocationFormState>(() => blankLocationForm());
  const [summary, setSummary] = useState<Summary | null>(null);
  const [form, setForm] = useState<FormState>(() => blankForm());
  const [attachmentFile, setAttachmentFile] = useState<File | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [query, setQuery] = useState('');
  const [categoryFilter, setCategoryFilter] = useState<NoticeCategory | ''>('');
  const [statusFilter, setStatusFilter] = useState<NoticeStatus | ''>('removal_due');
  const [notice, setNotice] = useState('');
  const [loading, setLoading] = useState(false);
  const [removalNotes, setRemovalNotes] = useState<Record<number, string>>({});
  const [removalFiles, setRemovalFiles] = useState<Record<number, File | null>>({});

  const actionPosts = useMemo(
    () => posts.filter(post => post.computed_status === 'removal_due' || post.computed_status === 'expired' || post.computed_status === 'unauthorized'),
    [posts],
  );
  const buildingOptions = useMemo(() => Array.from(new Set(locationOptions.map(option => option.building))).sort(), [locationOptions]);
  const lineOptions = useMemo(
    () => Array.from(new Set(locationOptions.filter(option => option.building === form.location).map(option => option.line))).sort(),
    [form.location, locationOptions],
  );
  const floorOptions = useMemo(
    () => Array.from(new Set(locationOptions.filter(option => option.building === form.location && option.line === form.line).map(option => option.floor))).sort(),
    [form.line, form.location, locationOptions],
  );

  async function loadPosts() {
    const params = new URLSearchParams({ limit: '150' });
    if (query.trim()) params.set('q', query.trim());
    if (categoryFilter) params.set('category', categoryFilter);
    if (statusFilter) params.set('status', statusFilter);
    const [listRes, summaryRes] = await Promise.all([
      fetch(`${getApiBase()}/api/notices?${params.toString()}`),
      fetch(`${getApiBase()}/api/notices/summary`),
    ]);
    if (!listRes.ok) throw new Error(await responseMessage(listRes));
    if (!summaryRes.ok) throw new Error(await responseMessage(summaryRes));
    setPosts(await listRes.json());
    setSummary(await summaryRes.json());
  }

  async function loadLocations() {
    const res = await fetch(`${getApiBase()}/api/notices/locations`);
    if (!res.ok) throw new Error(await responseMessage(res));
    const data = await res.json();
    setLocationOptions(Array.isArray(data.items) ? data.items : []);
  }

  useEffect(() => {
    Promise.all([loadPosts(), loadLocations()]).catch(err => setNotice(err instanceof Error ? err.message : '게시물을 불러오지 못했습니다.'));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function updateField<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm(current => ({ ...current, [key]: value }));
  }

  function resetForm() {
    setForm(blankForm());
    setAttachmentFile(null);
    setEditingId(null);
  }

  function updateBuilding(value: string) {
    setForm(current => ({ ...current, location: value, line: '', floor: '' }));
  }

  function updateLine(value: string) {
    setForm(current => ({ ...current, line: value, floor: '' }));
  }

  async function saveLocationOption() {
    if (!locationForm.building.trim() || !locationForm.line.trim() || !locationForm.floor.trim()) {
      setNotice('동, 라인, 층을 모두 입력해 주세요.');
      return;
    }
    setLoading(true);
    try {
      const res = await fetch(`${getApiBase()}/api/notices/locations`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...locationForm, sort_order: Number(locationForm.sort_order || 0) }),
      });
      if (!res.ok) throw new Error(await responseMessage(res));
      setLocationForm(blankLocationForm());
      await loadLocations();
      setNotice('위치 옵션을 등록했습니다.');
    } catch (err) {
      setNotice(err instanceof Error ? err.message : '위치 옵션 저장 중 오류가 발생했습니다.');
    } finally {
      setLoading(false);
    }
  }

  async function deleteLocationOption(option: LocationOption) {
    if (!confirm(`${option.building} / ${option.line} / ${option.floor} 위치 옵션을 삭제하시겠습니까?`)) return;
    setLoading(true);
    try {
      const res = await fetch(`${getApiBase()}/api/notices/locations/${option.id}`, { method: 'DELETE' });
      if (!res.ok) throw new Error(await responseMessage(res));
      await loadLocations();
      setNotice('위치 옵션을 삭제했습니다.');
    } catch (err) {
      setNotice(err instanceof Error ? err.message : '위치 옵션 삭제 중 오류가 발생했습니다.');
    } finally {
      setLoading(false);
    }
  }

  async function submitPost(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!form.title.trim() || !form.location.trim() || !form.line.trim()) {
      setNotice('제목, 동, 라인을 입력해 주세요.');
      return;
    }
    setLoading(true);
    setNotice(editingId ? '게시물 수정 중입니다.' : '게시물 등록 중입니다.');
    try {
      if (editingId) {
        const res = await fetch(`${getApiBase()}/api/notices/${editingId}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(form),
        });
        if (!res.ok) throw new Error(await responseMessage(res));
      } else {
        const body = new FormData();
        Object.entries(form).forEach(([key, value]) => body.append(key, String(value || '')));
        if (attachmentFile) body.append('attachment', attachmentFile);
        const res = await fetch(`${getApiBase()}/api/notices`, { method: 'POST', body });
        if (!res.ok) throw new Error(await responseMessage(res));
      }
      resetForm();
      await loadPosts();
      setNotice(editingId ? '게시물 수정이 완료되었습니다.' : '게시물 등록이 완료되었습니다.');
    } catch (err) {
      setNotice(err instanceof Error ? err.message : '저장 중 오류가 발생했습니다.');
    } finally {
      setLoading(false);
    }
  }

  async function removePost(post: BoardPost) {
    setLoading(true);
    setNotice(`${post.title} 철거 완료 처리 중입니다.`);
    try {
      const body = new FormData();
      body.append('removal_note', removalNotes[post.id] || '');
      const file = removalFiles[post.id];
      if (file) body.append('removal_image', file);
      const res = await fetch(`${getApiBase()}/api/notices/${post.id}/remove`, { method: 'POST', body });
      if (!res.ok) throw new Error(await responseMessage(res));
      await loadPosts();
      setRemovalNotes(current => ({ ...current, [post.id]: '' }));
      setRemovalFiles(current => ({ ...current, [post.id]: null }));
      setNotice('철거 완료 처리했습니다.');
    } catch (err) {
      setNotice(err instanceof Error ? err.message : '철거 처리 중 오류가 발생했습니다.');
    } finally {
      setLoading(false);
    }
  }

  async function deletePost(post: BoardPost) {
    if (!confirm(`${post.title} 게시물을 삭제하시겠습니까?`)) return;
    setLoading(true);
    try {
      const res = await fetch(`${getApiBase()}/api/notices/${post.id}`, { method: 'DELETE' });
      if (!res.ok) throw new Error(await responseMessage(res));
      await loadPosts();
      setNotice('게시물을 삭제했습니다.');
    } catch (err) {
      setNotice(err instanceof Error ? err.message : '삭제 중 오류가 발생했습니다.');
    } finally {
      setLoading(false);
    }
  }

  function startEdit(post: BoardPost) {
    setEditingId(post.id);
    setForm(formFromNotice(post));
    setAttachmentFile(null);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  return (
    <main className="min-h-screen overflow-x-hidden bg-slate-100 px-3 py-4 text-slate-950 sm:px-6 lg:px-8">
      <div className="mx-auto w-full max-w-7xl">
        <header className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm sm:p-6">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-xs font-black uppercase tracking-[0.22em] text-emerald-800">Board Operations</p>
              <h1 className="mt-2 text-2xl font-black tracking-tight sm:text-4xl">아파트 게시물 관리 시스템</h1>
              <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
                안내문, 공고문, 전입/전출 안내, 상업게시물을 기간 기준으로 게시하고 철거까지 기록합니다.
              </p>
            </div>
            <a href="/" className="rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm font-bold text-slate-700">
              업무보고로 이동
            </a>
          </div>
        </header>

        <section className="mt-4 grid grid-cols-2 gap-3 lg:grid-cols-6">
          <Stat label="전체" value={summary?.total ?? 0} tone="slate" />
          <Stat label="게시 중" value={summary?.posted ?? 0} tone="emerald" />
          <Stat label="철거 대상" value={summary?.removal_due ?? 0} tone="rose" />
          <Stat label="기간 만료" value={summary?.expired ?? 0} tone="amber" />
          <Stat label="게시 예정" value={summary?.scheduled ?? 0} tone="sky" />
          <Stat label="무단 게시" value={summary?.unauthorized ?? 0} tone="orange" />
        </section>

        {notice && (
          <div className="mt-4 rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm font-semibold text-slate-700 shadow-sm">
            {notice}
          </div>
        )}

        <section className="mt-4 grid min-w-0 gap-4 lg:grid-cols-[420px_minmax(0,1fr)]">
          <form onSubmit={submitPost} className="min-w-0 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h2 className="text-lg font-black">{editingId ? '게시물 수정' : '게시물 등록'}</h2>
                <p className="mt-1 text-xs font-semibold text-slate-500">게시파일은 등록 시 첨부하고, 내용 수정은 카드의 수정 버튼을 사용합니다.</p>
              </div>
              {editingId && (
                <button type="button" onClick={resetForm} className="rounded-lg border border-slate-300 px-3 py-2 text-xs font-bold text-slate-700">
                  취소
                </button>
              )}
            </div>

            <div className="mt-4 grid gap-3">
              <label className="grid gap-1 text-sm font-bold">
                분류
                <select value={form.category} onChange={event => updateField('category', event.target.value as NoticeCategory)} className="w-full min-w-0 rounded-xl border border-slate-300 px-3 py-3 font-semibold">
                  {CATEGORY_OPTIONS.map(option => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="grid gap-1 text-sm font-bold">
                제목
                <input value={form.title} onChange={event => updateField('title', event.target.value)} className="w-full min-w-0 rounded-xl border border-slate-300 px-3 py-3 font-semibold" placeholder="예: 지하주차장 청소 안내" />
              </label>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                <label className="grid gap-1 text-sm font-bold">
                  동
                  <select value={form.location} onChange={event => updateBuilding(event.target.value)} className="w-full min-w-0 rounded-xl border border-slate-300 px-3 py-3 font-semibold">
                    <option value="">동 선택</option>
                    {form.location && !buildingOptions.includes(form.location) && <option value={form.location}>{form.location}</option>}
                    {buildingOptions.map(building => (
                      <option key={building} value={building}>
                        {building}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="grid gap-1 text-sm font-bold">
                  라인
                  <select value={form.line} onChange={event => updateLine(event.target.value)} className="w-full min-w-0 rounded-xl border border-slate-300 px-3 py-3 font-semibold" disabled={!form.location}>
                    <option value="">라인 선택</option>
                    {form.line && !lineOptions.includes(form.line) && <option value={form.line}>{form.line}</option>}
                    {lineOptions.map(line => (
                      <option key={line} value={line}>
                        {line}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="grid gap-1 text-sm font-bold">
                  층
                  <select value={form.floor} onChange={event => updateField('floor', event.target.value)} className="w-full min-w-0 rounded-xl border border-slate-300 px-3 py-3 font-semibold" disabled={!form.line}>
                    <option value="">층 선택</option>
                    {form.floor && !floorOptions.includes(form.floor) && <option value={form.floor}>{form.floor}</option>}
                    {floorOptions.map(floor => (
                      <option key={floor} value={floor}>
                        {floor}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              {locationOptions.length === 0 && (
                <div className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-bold text-amber-950">
                  먼저 아래 위치 관리에서 동/라인/층을 등록하세요.
                </div>
              )}
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
                <label className="grid gap-1 text-xs font-bold">
                  시작
                  <input type="date" value={form.start_date} onChange={event => updateField('start_date', event.target.value)} className="w-full min-w-0 rounded-xl border border-slate-300 px-2 py-3 font-semibold" />
                </label>
                <label className="grid gap-1 text-xs font-bold">
                  종료
                  <input type="date" value={form.end_date} onChange={event => updateField('end_date', event.target.value)} className="w-full min-w-0 rounded-xl border border-slate-300 px-2 py-3 font-semibold" />
                </label>
                <label className="grid gap-1 text-xs font-bold">
                  철거
                  <input type="date" value={form.removal_due_date} onChange={event => updateField('removal_due_date', event.target.value)} className="w-full min-w-0 rounded-xl border border-slate-300 px-2 py-3 font-semibold" />
                </label>
              </div>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <label className="grid gap-1 text-sm font-bold">
                  게시자/업체
                  <input value={form.advertiser} onChange={event => updateField('advertiser', event.target.value)} className="w-full min-w-0 rounded-xl border border-slate-300 px-3 py-3 font-semibold" placeholder="관리사무소 또는 업체" />
                </label>
                <label className="grid gap-1 text-sm font-bold">
                  연락처
                  <input value={form.contact} onChange={event => updateField('contact', event.target.value)} className="w-full min-w-0 rounded-xl border border-slate-300 px-3 py-3 font-semibold" placeholder="선택" />
                </label>
              </div>
              <label className="grid gap-1 text-sm font-bold">
                상태
                <select value={form.status} onChange={event => updateField('status', event.target.value as NoticeStatus)} className="w-full min-w-0 rounded-xl border border-slate-300 px-3 py-3 font-semibold">
                  {STATUS_OPTIONS.filter(option => option.value).map(option => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                  <option value="draft">임시</option>
                </select>
              </label>
              <label className="grid gap-1 text-sm font-bold">
                내용
                <textarea value={form.description} onChange={event => updateField('description', event.target.value)} className="min-h-24 w-full min-w-0 rounded-xl border border-slate-300 px-3 py-3 font-semibold" placeholder="게시물 내용 또는 철거 기준" />
              </label>
              <label className="grid gap-1 text-sm font-bold">
                메모
                <input value={form.note} onChange={event => updateField('note', event.target.value)} className="w-full min-w-0 rounded-xl border border-slate-300 px-3 py-3 font-semibold" placeholder="내부 참고사항" />
              </label>
              {!editingId && (
                <label className="grid gap-1 text-sm font-bold">
                  게시파일
                  <input type="file" accept={ATTACHMENT_ACCEPT} onChange={event => setAttachmentFile(event.target.files?.[0] || null)} className="w-full min-w-0 rounded-xl border border-slate-300 px-3 py-3 text-sm" />
                  <span className="text-xs font-semibold text-slate-500">이미지, PDF, Word, Excel, PPT, HWP, TXT 파일을 선택할 수 있습니다.</span>
                </label>
              )}
              <button disabled={loading} className="rounded-xl bg-slate-950 px-4 py-3 text-sm font-black text-white disabled:bg-slate-400">
                {loading ? '처리 중...' : editingId ? '수정 저장' : '게시물 등록'}
              </button>
            </div>

            <details className="mt-4 rounded-2xl border border-slate-200 bg-slate-50 p-3">
              <summary className="cursor-pointer text-sm font-black text-slate-900">위치 관리</summary>
              <div className="mt-3 grid gap-2">
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-4">
                  <input value={locationForm.building} onChange={event => setLocationForm(current => ({ ...current, building: event.target.value }))} className="w-full min-w-0 rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm font-semibold" placeholder="동 예: 101동" />
                  <input value={locationForm.line} onChange={event => setLocationForm(current => ({ ...current, line: event.target.value }))} className="w-full min-w-0 rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm font-semibold" placeholder="라인 예: 1-2라인" />
                  <input value={locationForm.floor} onChange={event => setLocationForm(current => ({ ...current, floor: event.target.value }))} className="w-full min-w-0 rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm font-semibold" placeholder="층 예: 1층" />
                  <input value={locationForm.sort_order} onChange={event => setLocationForm(current => ({ ...current, sort_order: event.target.value }))} className="w-full min-w-0 rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm font-semibold" placeholder="순서" inputMode="numeric" />
                </div>
                <button type="button" onClick={saveLocationOption} disabled={loading} className="rounded-xl bg-emerald-800 px-3 py-2 text-sm font-black text-white disabled:bg-slate-300">
                  위치 등록
                </button>
              </div>
              <div className="mt-3 grid max-h-56 gap-2 overflow-y-auto pr-1">
                {locationOptions.map(option => (
                  <div key={option.id} className="flex min-w-0 items-center justify-between gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2">
                    <span className="min-w-0 break-words text-xs font-bold text-slate-700">
                      {option.building} / {option.line} / {option.floor}
                    </span>
                    <button type="button" onClick={() => deleteLocationOption(option)} className="shrink-0 rounded-lg border border-rose-300 px-2 py-1 text-xs font-bold text-rose-700">
                      삭제
                    </button>
                  </div>
                ))}
                {locationOptions.length === 0 && <div className="rounded-xl border border-dashed border-slate-300 p-3 text-center text-xs font-bold text-slate-500">등록된 위치 옵션이 없습니다.</div>}
              </div>
            </details>
          </form>

          <section className="min-w-0 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-lg font-black">게시물 목록</h2>
                <p className="mt-1 text-xs font-semibold text-slate-500">기본값은 철거 대상입니다. 전체 목록은 상태를 전체로 바꾸세요.</p>
              </div>
              <button onClick={() => loadPosts().catch(err => setNotice(err instanceof Error ? err.message : '새로고침 실패'))} className="rounded-lg border border-slate-300 px-3 py-2 text-xs font-bold text-slate-700">
                새로고침
              </button>
            </div>

            <div className="mt-4 grid gap-2 md:grid-cols-[1fr_150px_150px_90px]">
              <input value={query} onChange={event => setQuery(event.target.value)} onKeyDown={event => event.key === 'Enter' && loadPosts().catch(err => setNotice(err instanceof Error ? err.message : '검색 실패'))} className="w-full min-w-0 rounded-xl border border-slate-300 px-3 py-3 text-sm font-semibold" placeholder="제목, 동, 라인, 층, 업체, 연락처 검색" />
              <select value={categoryFilter} onChange={event => setCategoryFilter(event.target.value as NoticeCategory | '')} className="w-full min-w-0 rounded-xl border border-slate-300 px-3 py-3 text-sm font-semibold">
                <option value="">분류 전체</option>
                {CATEGORY_OPTIONS.map(option => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              <select value={statusFilter} onChange={event => setStatusFilter(event.target.value as NoticeStatus | '')} className="w-full min-w-0 rounded-xl border border-slate-300 px-3 py-3 text-sm font-semibold">
                {STATUS_OPTIONS.map(option => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              <button onClick={() => loadPosts().catch(err => setNotice(err instanceof Error ? err.message : '검색 실패'))} className="w-full min-w-0 rounded-xl bg-slate-900 px-3 py-3 text-sm font-black text-white">
                조회
              </button>
            </div>

            {actionPosts.length > 0 && (
              <div className="mt-4 rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm font-bold text-rose-950">
                즉시 확인할 게시물이 {actionPosts.length}건 있습니다. 철거 후 사진과 메모를 남기면 이력이 보관됩니다.
              </div>
            )}

            <div className="mt-4 grid gap-3">
              {posts.map(post => (
                <article key={post.id} className="overflow-hidden rounded-2xl border border-slate-200 bg-slate-50">
                  <div className="grid gap-3 p-3 sm:grid-cols-[160px_minmax(0,1fr)]">
                    <div className="aspect-[4/3] overflow-hidden rounded-xl bg-slate-200">
                      {post.attachment_url && isImageFile(post) ? (
                        <img src={imageSrc(post.attachment_url)} alt={post.title} className="h-full w-full object-cover" />
                      ) : post.attachment_url && isPdfFile(post) ? (
                        <iframe src={imageSrc(post.attachment_url)} title={post.title} className="h-full w-full border-0 bg-white" />
                      ) : (
                        <div className="flex h-full flex-col items-center justify-center gap-2 px-3 text-center text-xs font-bold text-slate-500">
                          <span className="rounded-full bg-white px-3 py-1 text-[11px] font-black text-slate-700">
                            {post.attachment_url ? fileExtension(post).toUpperCase() || 'FILE' : 'EMPTY'}
                          </span>
                          <span>{previewMessage(post)}</span>
                        </div>
                      )}
                    </div>
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className={`rounded-full px-2 py-1 text-xs font-black ${categoryTone(post.category)}`}>{post.category_label}</span>
                          <span className={`rounded-full border px-2 py-1 text-xs font-black ${statusTone(post.computed_status)}`}>{post.status_label}</span>
                        </div>
                        <div className="text-xs font-bold text-slate-500">#{post.id}</div>
                      </div>
                      <h3 className="mt-2 break-words text-lg font-black text-slate-950">{post.title}</h3>
                      <div className="mt-2 grid gap-1 text-sm font-semibold text-slate-600 sm:grid-cols-2">
                        <div>위치: {post.location}{post.line ? ` / ${post.line}` : ''}{post.floor ? ` / ${post.floor}` : ''}</div>
                        <div>기간: {post.start_date} ~ {post.end_date}</div>
                        <div>철거 예정: {post.removal_due_date || post.end_date}</div>
                        <div>게시자: {post.advertiser || '-'}</div>
                      </div>
                      {post.description && <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-slate-700">{post.description}</p>}
                      {post.note && <p className="mt-2 rounded-lg bg-white px-3 py-2 text-xs font-semibold text-slate-600">메모: {post.note}</p>}
                      {post.attachment_url && (isImageFile(post) || isPdfFile(post)) && (
                        <div className="mt-2 flex flex-wrap items-center gap-2 rounded-lg bg-white px-3 py-2 text-xs font-semibold text-slate-600">
                          <span className="min-w-0 break-words">게시파일: {fileLabel(post)}</span>
                          <a href={imageSrc(post.attachment_url)} target="_blank" rel="noopener noreferrer" className="rounded-lg border border-slate-300 px-2 py-1 text-xs font-bold text-slate-700">
                            원본 보기
                          </a>
                          <a href={imageSrc(post.attachment_url)} download className="rounded-lg border border-slate-300 px-2 py-1 text-xs font-bold text-slate-700">
                            다운로드
                          </a>
                        </div>
                      )}
                      {post.attachment_url && !isImageFile(post) && !isPdfFile(post) && (
                        <div className="mt-2 rounded-xl border border-slate-200 bg-white p-3">
                          <div className="text-xs font-black text-slate-500">문서목록</div>
                          <div className="mt-2 grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto_auto] sm:items-center">
                            <div className="min-w-0">
                              <div className="truncate text-sm font-black text-slate-900">{fileLabel(post)}</div>
                              <div className="mt-1 text-xs font-semibold text-slate-500">
                                형식: {(fileExtension(post) || 'file').toUpperCase()}
                              </div>
                            </div>
                            <a href={imageSrc(post.attachment_url)} target="_blank" rel="noopener noreferrer" className="rounded-lg border border-slate-300 px-3 py-2 text-center text-xs font-bold text-slate-700">
                              열기
                            </a>
                            <a href={imageSrc(post.attachment_url)} download className="rounded-lg border border-slate-300 px-3 py-2 text-center text-xs font-bold text-slate-700">
                              다운로드
                            </a>
                          </div>
                        </div>
                      )}
                      {post.removal_image_url && (
                        <div className="mt-2 rounded-lg bg-white px-3 py-2 text-xs font-semibold text-slate-600">
                          철거 완료: {post.removed_at || '-'} / {post.removal_note || '메모 없음'}
                        </div>
                      )}

                      <div className="mt-3 grid gap-2 md:grid-cols-[1fr_180px_auto]">
                        <input value={removalNotes[post.id] || ''} onChange={event => setRemovalNotes(current => ({ ...current, [post.id]: event.target.value }))} className="w-full min-w-0 rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm font-semibold" placeholder="철거 메모" />
                        <input type="file" accept="image/*" onChange={event => setRemovalFiles(current => ({ ...current, [post.id]: event.target.files?.[0] || null }))} className="w-full min-w-0 rounded-xl border border-slate-300 bg-white px-3 py-2 text-xs" />
                        <button onClick={() => removePost(post)} disabled={loading || post.computed_status === 'removed'} className="w-full min-w-0 rounded-xl bg-emerald-800 px-3 py-2 text-sm font-black text-white disabled:bg-slate-300">
                          철거 완료
                        </button>
                      </div>

                      <div className="mt-3 flex flex-wrap gap-2">
                        <button onClick={() => startEdit(post)} className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-bold text-slate-700">
                          수정
                        </button>
                        <button onClick={() => deletePost(post)} className="rounded-lg border border-rose-300 bg-white px-3 py-2 text-xs font-bold text-rose-700">
                          삭제
                        </button>
                      </div>
                    </div>
                  </div>
                </article>
              ))}
              {posts.length === 0 && <div className="rounded-xl border border-dashed border-slate-300 p-8 text-center text-sm font-semibold text-slate-500">조회된 게시물이 없습니다.</div>}
            </div>
          </section>
        </section>
      </div>
    </main>
  );
}

function Stat({ label, value, tone }: { label: string; value: number; tone: 'slate' | 'emerald' | 'rose' | 'amber' | 'sky' | 'orange' }) {
  const tones = {
    slate: 'border-slate-200 bg-white text-slate-900',
    emerald: 'border-emerald-200 bg-emerald-50 text-emerald-900',
    rose: 'border-rose-200 bg-rose-50 text-rose-900',
    amber: 'border-amber-200 bg-amber-50 text-amber-950',
    sky: 'border-sky-200 bg-sky-50 text-sky-900',
    orange: 'border-orange-200 bg-orange-50 text-orange-950',
  };
  return (
    <div className={`rounded-2xl border p-3 shadow-sm ${tones[tone]}`}>
      <div className="text-xs font-black">{label}</div>
      <div className="mt-1 text-2xl font-black">{value.toLocaleString('ko-KR')}</div>
    </div>
  );
}
