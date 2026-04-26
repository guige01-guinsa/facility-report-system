'use client';
import { useState } from 'react';

function getApiBase() {
  if (process.env.NEXT_PUBLIC_API_BASE) return process.env.NEXT_PUBLIC_API_BASE;
  if (typeof window !== 'undefined') {
    const hostname = window.location.hostname;
    if (hostname.endsWith('.onrender.com') && hostname.includes('frontend')) {
      return `https://${hostname.replace('frontend', 'backend')}`;
    }
    if (hostname.endsWith('.app.github.dev')) {
      return `https://${hostname.replace(/-3000\.app\.github\.dev$/, '-8000.app.github.dev')}`;
    }
  }
  return 'http://localhost:8000';
}

export default function Home() {
  const [text, setText] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [report, setReport] = useState('');
  const [loading, setLoading] = useState(false);
  const [meta, setMeta] = useState('');

  async function generate() {
    setLoading(true);
    setReport('');
    setMeta('');
    try {
      const apiBase = getApiBase();
      let res: Response;
      if (file) {
        const form = new FormData();
        form.append('file', file);
        if (startDate) form.append('start_date', startDate);
        if (endDate) form.append('end_date', endDate);
        res = await fetch(`${apiBase}/api/report-file`, { method: 'POST', body: form });
      } else {
        res = await fetch(`${apiBase}/api/report`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text, start_date: startDate || null, end_date: endDate || null }),
        });
      }
      if (!res.ok) throw new Error(`서버 오류: ${res.status}`);
      const data = await res.json();
      setMeta(`전체 ${data.total}건 / 선택기간 ${data.filtered}건`);
      setReport(data.report);
    } catch (err) {
      setReport(err instanceof Error ? err.message : '알 수 없는 오류가 발생했습니다.');
    } finally {
      setLoading(false);
    }
  }

  async function copyReport() {
    await navigator.clipboard.writeText(report);
    alert('보고서를 복사했습니다.');
  }

  return (
    <main className="mx-auto max-w-5xl p-4 md:p-8">
      <section className="rounded-3xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
        <p className="text-sm font-semibold text-slate-500">Facility Report System</p>
        <h1 className="mt-2 text-3xl font-bold tracking-tight text-slate-900">카톡 단톡방 업무보고서 생성기</h1>
        <p className="mt-3 text-slate-600">카카오톡 대화 내보내기 txt 파일을 올리거나 내용을 붙여넣고, 기간을 선택하면 업무보고서로 변환합니다.</p>
      </section>

      <section className="mt-6 grid gap-4 md:grid-cols-3">
        <label className="rounded-2xl bg-white p-4 shadow-sm ring-1 ring-slate-200 md:col-span-1">
          <span className="text-sm font-semibold text-slate-700">시작일</span>
          <input type="date" value={startDate} onChange={e => setStartDate(e.target.value)} className="mt-2 w-full rounded-xl border border-slate-300 p-3" />
        </label>
        <label className="rounded-2xl bg-white p-4 shadow-sm ring-1 ring-slate-200 md:col-span-1">
          <span className="text-sm font-semibold text-slate-700">종료일</span>
          <input type="date" value={endDate} onChange={e => setEndDate(e.target.value)} className="mt-2 w-full rounded-xl border border-slate-300 p-3" />
        </label>
        <label className="rounded-2xl bg-white p-4 shadow-sm ring-1 ring-slate-200 md:col-span-1">
          <span className="text-sm font-semibold text-slate-700">카톡 txt 파일</span>
          <input type="file" accept=".txt,text/plain" onChange={e => setFile(e.target.files?.[0] || null)} className="mt-2 w-full rounded-xl border border-slate-300 p-3" />
        </label>
      </section>

      <section className="mt-6 rounded-2xl bg-white p-4 shadow-sm ring-1 ring-slate-200">
        <label className="text-sm font-semibold text-slate-700">또는 대화내용 붙여넣기</label>
        <textarea value={text} onChange={e => setText(e.target.value)} rows={12} placeholder="카카오톡 대화 내보내기 내용을 붙여넣으세요." className="mt-2 w-full rounded-xl border border-slate-300 p-3 font-mono text-sm" />
        <div className="mt-4 flex flex-wrap gap-3">
          <button onClick={generate} disabled={loading || (!file && !text.trim())} className="rounded-xl bg-slate-900 px-5 py-3 font-semibold text-white disabled:cursor-not-allowed disabled:bg-slate-400">{loading ? '생성 중...' : '보고서 생성'}</button>
          <button onClick={() => { setText(''); setFile(null); setReport(''); setMeta(''); }} className="rounded-xl border border-slate-300 px-5 py-3 font-semibold text-slate-700">초기화</button>
          {report && <button onClick={copyReport} className="rounded-xl border border-slate-300 px-5 py-3 font-semibold text-slate-700">보고서 복사</button>}
        </div>
      </section>

      <section className="mt-6 rounded-2xl bg-white p-4 shadow-sm ring-1 ring-slate-200">
        <div className="flex items-center justify-between gap-4">
          <h2 className="text-xl font-bold text-slate-900">생성 결과</h2>
          <span className="text-sm text-slate-500">{meta}</span>
        </div>
        <pre className="mt-4 min-h-80 whitespace-pre-wrap rounded-xl bg-slate-950 p-4 text-sm leading-6 text-slate-100">{report || '아직 생성된 보고서가 없습니다.'}</pre>
      </section>
    </main>
  );
}
