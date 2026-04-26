'use client';

import { useEffect, useMemo, useRef, useState } from 'react';

type MessageStatus = 'work' | 'review' | 'excluded';
type MatchStatus = 'confirmed' | 'needs_review' | 'unmatched';
type ImageRole = 'before' | 'during' | 'after' | 'evidence';
type MessageFilter = 'active' | 'work' | 'review' | 'excluded' | 'all';
type ReportFormat = 'excel' | 'pdf';

type ReviewMessage = {
  id: string;
  datetime: string | null;
  date: string | null;
  time: string | null;
  user: string | null;
  message: string;
  summary: string;
  status: MessageStatus;
  confidence: number;
  keywords: string[];
  reasons: string[];
};

type ReviewImage = {
  id: string;
  filename: string;
  content_type: string;
  size: number;
  captured_at: string | null;
  captured_at_source: string | null;
  excluded: boolean;
};

type ImageMatch = {
  image_id: string;
  message_id: string | null;
  confidence: number;
  status: MatchStatus;
  role: ImageRole;
  reasons: string[];
};

type ReviewSummary = {
  total_messages: number;
  work_messages: number;
  review_messages: number;
  excluded_messages: number;
  total_images: number;
  confirmed_matches: number;
  needs_review_matches: number;
  unmatched_images: number;
  ai_used: boolean;
  ai_error: string;
  ai_model: string;
};

type ParseDiagnostics = {
  non_empty_lines: number;
  preview_lines: string[];
  recognized_formats: string[];
};

type ReviewResponse = {
  total: number;
  filtered: number;
  messages: ReviewMessage[];
  images: ReviewImage[];
  matches: ImageMatch[];
  summary: ReviewSummary;
  parse_diagnostics: ParseDiagnostics | null;
};

type OpenAiUsage = {
  configured: boolean;
  status: string;
  message?: string;
  days?: number;
  generated_at?: string;
  usage?: {
    input_tokens: number;
    output_tokens: number;
    cached_tokens: number;
    requests: number;
    total_tokens: number;
  };
  costs?: {
    total: number;
    currency: string;
  };
  usage_dashboard_url?: string;
  billing_url?: string;
  limits_url?: string;
};

const ROLE_LABELS: Record<ImageRole, string> = {
  before: '전',
  during: '중',
  after: '후',
  evidence: '자료',
};

const STATUS_LABELS: Record<MessageStatus, string> = {
  work: '작업',
  review: '확인',
  excluded: '제외',
};

const PICKER_PAGE_SIZE = 6;
const AI_MODEL_OPTIONS = [
  {
    id: 'gpt-5-nano',
    label: '저렴/빠름',
    description: '분류 추천',
  },
  {
    id: 'gpt-5-mini',
    label: '균형',
    description: '애매한 대화 보강',
  },
  {
    id: 'gpt-5.2',
    label: '정확도 우선',
    description: '비용과 시간이 늘어남',
  },
];

type ExportRow = {
  date: string;
  time: string;
  user: string;
  status: string;
  message: string;
  images: string;
};

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

function confidenceLabel(value: number) {
  if (value >= 75) return '높음';
  if (value >= 45) return '확인';
  if (value > 0) return '낮음';
  return '없음';
}

function formatBytes(size: number) {
  if (!size) return '-';
  if (size < 1024 * 1024) return `${Math.round(size / 1024)}KB`;
  return `${(size / (1024 * 1024)).toFixed(1)}MB`;
}

function formatNumber(value: number | undefined) {
  return typeof value === 'number' ? value.toLocaleString('ko-KR') : '-';
}

function shortText(value: string, max = 70) {
  const compact = value.replace(/\s+/g, ' ').trim();
  return compact.length > max ? `${compact.slice(0, max)}...` : compact;
}

function escapeHtml(value: string) {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function escapeXml(value: string) {
  return escapeHtml(value);
}

function colName(index: number) {
  let name = '';
  let current = index;
  while (current > 0) {
    const mod = (current - 1) % 26;
    name = String.fromCharCode(65 + mod) + name;
    current = Math.floor((current - mod) / 26);
  }
  return name;
}

function crc32(bytes: Uint8Array) {
  let crc = 0xffffffff;
  for (const byte of bytes) {
    crc ^= byte;
    for (let index = 0; index < 8; index += 1) {
      crc = (crc >>> 1) ^ (0xedb88320 & -(crc & 1));
    }
  }
  return (crc ^ 0xffffffff) >>> 0;
}

function createZip(files: { name: string; data: Uint8Array }[]) {
  const encoder = new TextEncoder();
  const localParts: Uint8Array[] = [];
  const centralParts: Uint8Array[] = [];
  let offset = 0;
  const now = new Date();
  const dosTime = (now.getHours() << 11) | (now.getMinutes() << 5) | Math.floor(now.getSeconds() / 2);
  const dosDate = ((now.getFullYear() - 1980) << 9) | ((now.getMonth() + 1) << 5) | now.getDate();

  function header(size: number) {
    const buffer = new ArrayBuffer(size);
    return { bytes: new Uint8Array(buffer), view: new DataView(buffer) };
  }

  for (const file of files) {
    const nameBytes = encoder.encode(file.name);
    const checksum = crc32(file.data);
    const local = header(30);
    local.view.setUint32(0, 0x04034b50, true);
    local.view.setUint16(4, 20, true);
    local.view.setUint16(6, 0, true);
    local.view.setUint16(8, 0, true);
    local.view.setUint16(10, dosTime, true);
    local.view.setUint16(12, dosDate, true);
    local.view.setUint32(14, checksum, true);
    local.view.setUint32(18, file.data.length, true);
    local.view.setUint32(22, file.data.length, true);
    local.view.setUint16(26, nameBytes.length, true);
    local.view.setUint16(28, 0, true);
    localParts.push(local.bytes, nameBytes, file.data);

    const central = header(46);
    central.view.setUint32(0, 0x02014b50, true);
    central.view.setUint16(4, 20, true);
    central.view.setUint16(6, 20, true);
    central.view.setUint16(8, 0, true);
    central.view.setUint16(10, 0, true);
    central.view.setUint16(12, dosTime, true);
    central.view.setUint16(14, dosDate, true);
    central.view.setUint32(16, checksum, true);
    central.view.setUint32(20, file.data.length, true);
    central.view.setUint32(24, file.data.length, true);
    central.view.setUint16(28, nameBytes.length, true);
    central.view.setUint16(30, 0, true);
    central.view.setUint16(32, 0, true);
    central.view.setUint16(34, 0, true);
    central.view.setUint16(36, 0, true);
    central.view.setUint32(38, 0, true);
    central.view.setUint32(42, offset, true);
    centralParts.push(central.bytes, nameBytes);

    offset += local.bytes.length + nameBytes.length + file.data.length;
  }

  const centralSize = centralParts.reduce((sum, part) => sum + part.length, 0);
  const end = header(22);
  end.view.setUint32(0, 0x06054b50, true);
  end.view.setUint16(8, files.length, true);
  end.view.setUint16(10, files.length, true);
  end.view.setUint32(12, centralSize, true);
  end.view.setUint32(16, offset, true);
  end.view.setUint16(20, 0, true);

  const blobParts = [...localParts, ...centralParts, end.bytes].map(part => {
    const buffer = new ArrayBuffer(part.byteLength);
    new Uint8Array(buffer).set(part);
    return buffer;
  });
  return new Blob(blobParts, {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  });
}

export default function Home() {
  const chatFileInputRef = useRef<HTMLInputElement | null>(null);
  const imageFileInputRef = useRef<HTMLInputElement | null>(null);
  const [text, setText] = useState('');
  const [showPasteInput, setShowPasteInput] = useState(false);
  const [chatFile, setChatFile] = useState<File | null>(null);
  const [imageFiles, setImageFiles] = useState<File[]>([]);
  const [imagePreviews, setImagePreviews] = useState<Record<string, string>>({});
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [messages, setMessages] = useState<ReviewMessage[]>([]);
  const [images, setImages] = useState<ReviewImage[]>([]);
  const [matches, setMatches] = useState<ImageMatch[]>([]);
  const [summary, setSummary] = useState<ReviewSummary | null>(null);
  const [parseDiagnostics, setParseDiagnostics] = useState<ParseDiagnostics | null>(null);
  const [messageFilter, setMessageFilter] = useState<MessageFilter>('active');
  const [selectedImageId, setSelectedImageId] = useState<string | null>(null);
  const [imagePickerMessageId, setImagePickerMessageId] = useState<string | null>(null);
  const [imagePickerPage, setImagePickerPage] = useState(0);
  const [pickerSelectedIds, setPickerSelectedIds] = useState<string[]>([]);
  const [report, setReport] = useState('');
  const [reportFormat, setReportFormat] = useState<ReportFormat>('excel');
  const [includeApproval, setIncludeApproval] = useState(true);
  const [useAiClassification, setUseAiClassification] = useState(false);
  const [aiModel, setAiModel] = useState('gpt-5-nano');
  const [openAiUsage, setOpenAiUsage] = useState<OpenAiUsage | null>(null);
  const [notice, setNotice] = useState('');
  const [loading, setLoading] = useState(false);
  const [imageBatchLoading, setImageBatchLoading] = useState(false);
  const [reportLoading, setReportLoading] = useState(false);
  const [usageLoading, setUsageLoading] = useState(false);

  useEffect(() => {
    return () => {
      Object.values(imagePreviews).forEach(url => URL.revokeObjectURL(url));
    };
  }, [imagePreviews]);

  const activeMessages = useMemo(() => messages.filter(message => message.status !== 'excluded'), [messages]);
  const visibleMessages = useMemo(() => {
    if (messageFilter === 'active') return activeMessages;
    if (messageFilter === 'all') return messages;
    return messages.filter(message => message.status === messageFilter);
  }, [activeMessages, messageFilter, messages]);
  const activeImages = useMemo(() => images.filter(image => !image.excluded), [images]);
  const imageById = useMemo(() => new Map(images.map(image => [image.id, image])), [images]);
  const matchByImageId = useMemo(() => new Map(matches.map(match => [match.image_id, match])), [matches]);
  const activeMessageIds = useMemo(() => new Set(activeMessages.map(message => message.id)), [activeMessages]);
  const selectedImage = selectedImageId ? imageById.get(selectedImageId) : null;
  const unmatchedImages = activeImages.filter(image => {
    const match = matchByImageId.get(image.id);
    return !match || !match.message_id || !activeMessageIds.has(match.message_id) || match.status === 'unmatched';
  });
  const needsReviewImages = activeImages.filter(image => {
    const match = matchByImageId.get(image.id);
    return Boolean(match?.message_id && activeMessageIds.has(match.message_id) && match.status === 'needs_review');
  });
  const currentMatchStats = {
    confirmed: activeImages.filter(image => {
      const match = matchByImageId.get(image.id);
      return Boolean(match?.message_id && activeMessageIds.has(match.message_id) && match.status === 'confirmed');
    }).length,
    needsReview: needsReviewImages.length,
    unmatched: unmatchedImages.length,
  };
  const canAnalyze = Boolean(chatFile || text.trim());
  const canReviewImagesOnly = messages.length > 0 && imageFiles.length > 0;
  const noParsedMessages = Boolean(summary && summary.total_messages === 0);
  const counts = {
    work: messages.filter(message => message.status === 'work').length,
    review: messages.filter(message => message.status === 'review').length,
    excluded: messages.filter(message => message.status === 'excluded').length,
    all: messages.length,
  };

  function chooseImages(files: FileList | null) {
    const nextFiles = Array.from(files || []);
    setImageFiles(nextFiles);
    const previews: Record<string, string> = {};
    nextFiles.forEach((file, index) => {
      previews[`i${index + 1}`] = URL.createObjectURL(file);
    });
    setImagePreviews(previews);
    setSelectedImageId(null);
  }

  function imageMetadataPayload() {
    return JSON.stringify(
      imageFiles.map((file, index) => ({
        index,
        filename: file.name,
        size: file.size,
        type: file.type,
        lastModified: file.lastModified,
        lastModifiedIso: new Date(file.lastModified).toISOString(),
      })),
    );
  }

  async function analyze() {
    setLoading(true);
    setReport('');
    setNotice('');
    try {
      const form = new FormData();
      if (chatFile) form.append('chat_file', chatFile);
      else form.append('text', text);
      if (startDate) form.append('start_date', startDate);
      if (endDate) form.append('end_date', endDate);
      imageFiles.forEach(file => form.append('images', file));
      form.append('image_metadata', imageMetadataPayload());
      form.append('use_ai', useAiClassification ? 'true' : 'false');
      form.append('ai_model', aiModel);

      const res = await fetch(`${getApiBase()}/api/review-file`, { method: 'POST', body: form });
      if (!res.ok) {
        const detail: unknown = await res.json().catch(() => null);
        const message = typeof detail === 'object' && detail && 'detail' in detail ? String(detail.detail) : `서버 오류: ${res.status}`;
        throw new Error(message);
      }
      const data = (await res.json()) as ReviewResponse;
      setMessages(data.messages);
      setImages(data.images.map(image => ({ ...image, excluded: Boolean(image.excluded) })));
      setMatches(data.matches);
      setSummary(data.summary);
      setParseDiagnostics(data.parse_diagnostics);
      setMessageFilter(data.summary.review_messages > 0 ? 'review' : 'active');
      if (data.filtered === 0) {
        setNotice('카톡 대화가 0건입니다. 카카오톡에서 내보낸 txt 파일을 다시 선택하거나 직접 붙여넣기를 확인하세요.');
      } else {
        setNotice(
          `분석 완료: 대화 ${data.filtered}건, 이미지 ${data.summary.total_images}장, 확인 필요 매칭 ${data.summary.needs_review_matches + data.summary.unmatched_images}건`,
        );
      }
    } catch (err) {
      setNotice(err instanceof Error ? err.message : '분석 중 오류가 발생했습니다.');
    } finally {
      setLoading(false);
    }
  }

  async function reviewImagesOnly() {
    if (!canReviewImagesOnly) return;
    setImageBatchLoading(true);
    setNotice('');
    try {
      const form = new FormData();
      form.append('messages_json', JSON.stringify(messages));
      imageFiles.forEach(file => form.append('images', file));
      form.append('image_metadata', imageMetadataPayload());

      const res = await fetch(`${getApiBase()}/api/review-images`, { method: 'POST', body: form });
      if (!res.ok) {
        const detail: unknown = await res.json().catch(() => null);
        const message = typeof detail === 'object' && detail && 'detail' in detail ? String(detail.detail) : `서버 오류: ${res.status}`;
        throw new Error(message);
      }
      const data = (await res.json()) as ReviewResponse;
      setImages(data.images.map(image => ({ ...image, excluded: Boolean(image.excluded) })));
      setMatches(data.matches);
      setSummary(data.summary);
      setSelectedImageId(null);
      setImagePickerMessageId(null);
      setImagePickerPage(0);
      setPickerSelectedIds([]);
      setNotice(`대화 상태는 유지하고 새 사진 ${data.summary.total_images}장을 다시 매칭했습니다.`);
    } catch (err) {
      setNotice(err instanceof Error ? err.message : '사진 재매칭 중 오류가 발생했습니다.');
    } finally {
      setImageBatchLoading(false);
    }
  }

  async function generateReviewedReport() {
    const printWindow = reportFormat === 'pdf' ? window.open('', '_blank') : null;
    setReportLoading(true);
    setNotice('');
    try {
      const res = await fetch(`${getApiBase()}/api/report-reviewed`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages, images, matches, start_date: startDate || null, end_date: endDate || null, ai_model: aiModel }),
      });
      if (!res.ok) throw new Error(`서버 오류: ${res.status}`);
      const data = (await res.json()) as { report: string };
      setReport(data.report);
      exportReport(data.report, printWindow);
      setNotice(`${reportFormat === 'excel' ? '엑셀' : 'PDF'} 보고서를 생성했습니다. 사진 묶음이 더 있으면 사진만 초기화하고 이어서 작업하세요.`);
    } catch (err) {
      if (printWindow) printWindow.close();
      setNotice(err instanceof Error ? err.message : '보고서 생성 중 오류가 발생했습니다.');
    } finally {
      setReportLoading(false);
    }
  }

  function buildExportRows(): ExportRow[] {
    const imageMap = new Map(images.filter(image => !image.excluded).map(image => [image.id, image]));
    const byMessage = new Map<string, string[]>();
    matches.forEach(match => {
      if (!match.message_id) return;
      const image = imageMap.get(match.image_id);
      if (!image) return;
      const role = ROLE_LABELS[match.role] || '자료';
      byMessage.set(match.message_id, [...(byMessage.get(match.message_id) || []), `${role}: ${image.filename}`]);
    });
    return messages
      .filter(message => message.status !== 'excluded')
      .map(message => ({
        date: message.date || '',
        time: message.time || '',
        user: message.user || '',
        status: STATUS_LABELS[message.status] || message.status,
        message: message.message,
        images: (byMessage.get(message.id) || []).join(', '),
      }));
  }

  function exportReport(reportText: string, printWindow: Window | null) {
    const rows = buildExportRows();
    if (reportFormat === 'excel') {
      downloadExcelReport(reportText, rows);
      return;
    }
    openPdfPrintReport(reportText, rows, printWindow);
  }

  function reportFilename(extension: string) {
    const start = startDate || messages[0]?.date || new Date().toISOString().slice(0, 10);
    const end = endDate || messages[messages.length - 1]?.date || start;
    return `work-report_${start}_${end}.${extension}`;
  }

  function reportHtml(reportText: string, rows: ExportRow[]) {
    const rowHtml = rows
      .map(
        row =>
          `<tr><td>${escapeHtml(row.date)}</td><td>${escapeHtml(row.time)}</td><td>${escapeHtml(row.user)}</td><td>${escapeHtml(row.status)}</td><td>${escapeHtml(row.message).replace(/\n/g, '<br>')}</td><td>${escapeHtml(row.images)}</td></tr>`,
      )
      .join('');
    return `<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8" />
<title>작업보고서</title>
<style>
body{font-family:"Malgun Gothic","맑은 고딕",Arial,sans-serif;color:#111827;margin:22px;background:#fff}
.top{display:flex;align-items:flex-start;justify-content:space-between;gap:18px;margin-bottom:14px}
h1{font-size:22px;margin:0 0 4px}
.period{font-size:12px;color:#475569}
h2{font-size:15px;margin:18px 0 8px}
table{border-collapse:collapse;width:100%;font-size:12px}
th,td{border:1px solid #cbd5e1;padding:7px;vertical-align:top}
th{background:#f1f5f9}
pre{white-space:pre-wrap;font-family:"Malgun Gothic","맑은 고딕",Arial,sans-serif;font-size:12px;line-height:1.55;margin:0}
.approval{width:360px;margin:0 0 8px auto}
.approval th,.approval td{text-align:center}
.approval .vertical{width:34px;writing-mode:vertical-rl;text-orientation:upright;font-weight:700;letter-spacing:2px;background:#f8fafc}
.approval .name{height:28px;font-weight:700;background:#f1f5f9}
.approval .sign{height:76px}
@page{size:A4;margin:14mm}
</style>
</head>
<body>
<div class="top">
<div><h1>작업보고서</h1><div class="period">${escapeHtml(startDate || rows[0]?.date || '')} ~ ${escapeHtml(endDate || rows[rows.length - 1]?.date || '')}</div></div>
${includeApproval ? '<table class="approval"><tbody><tr><td class="vertical" rowspan="2">결재</td><td class="name">계장</td><td class="name">과장</td><td class="name">소장</td></tr><tr><td class="sign"></td><td class="sign"></td><td class="sign"></td></tr></tbody></table>' : ''}
</div>
<h2>작업 내역</h2>
<table>
<thead><tr><th>날짜</th><th>시간</th><th>담당자</th><th>상태</th><th>내용</th><th>첨부 사진</th></tr></thead>
<tbody>${rowHtml || '<tr><td colspan="6">작업 내역이 없습니다.</td></tr>'}</tbody>
</table>
<h2>보고서 문안</h2>
<pre>${escapeHtml(reportText)}</pre>
</body>
</html>`;
  }

  function downloadExcelReport(reportText: string, rows: ExportRow[]) {
    const blob = buildXlsxReport(reportText, rows);
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = reportFilename('xlsx');
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  function buildXlsxReport(reportText: string, rows: ExportRow[]) {
    const encoder = new TextEncoder();
    const sheetRows: string[][] = [['작업보고서']];
    sheetRows.push([`기간: ${startDate || rows[0]?.date || ''} ~ ${endDate || rows[rows.length - 1]?.date || ''}`]);
    sheetRows.push([]);
    if (includeApproval) {
      sheetRows.push(['결\n재', '계장', '과장', '소장']);
      sheetRows.push(['', '', '', '']);
      sheetRows.push(['', '', '', '']);
      sheetRows.push([]);
    }
    sheetRows.push(['날짜', '시간', '담당자', '상태', '내용', '첨부 사진']);
    rows.forEach(row => sheetRows.push([row.date, row.time, row.user, row.status, row.message, row.images]));
    sheetRows.push([]);
    sheetRows.push(['보고서 문안']);
    reportText.split('\n').forEach(line => sheetRows.push([line]));

    const sheetData = sheetRows
      .map((row, rowIndex) => {
        const rowNumber = rowIndex + 1;
        const rowAttrs = includeApproval && (rowNumber === 5 || rowNumber === 6) ? ` r="${rowNumber}" ht="38" customHeight="1"` : ` r="${rowNumber}"`;
        const cells = row
          .map((value, columnIndex) => {
            const cellRef = `${colName(columnIndex + 1)}${rowNumber}`;
            return `<c r="${cellRef}" s="1" t="inlineStr"><is><t xml:space="preserve">${escapeXml(value)}</t></is></c>`;
          })
          .join('');
        return `<row${rowAttrs}>${cells}</row>`;
      })
      .join('');
    const mergeRefs = includeApproval ? ['A4:A6', 'B5:B6', 'C5:C6', 'D5:D6'] : [];
    const mergeXml = mergeRefs.length ? `<mergeCells count="${mergeRefs.length}">${mergeRefs.map(ref => `<mergeCell ref="${ref}"/>`).join('')}</mergeCells>` : '';

    const worksheet = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<cols><col min="1" max="1" width="13"/><col min="2" max="2" width="10"/><col min="3" max="3" width="14"/><col min="4" max="4" width="10"/><col min="5" max="5" width="58"/><col min="6" max="6" width="46"/></cols>
<sheetData>${sheetData}</sheetData>
${mergeXml}
</worksheet>`;

    const files = [
      {
        name: '[Content_Types].xml',
        data: encoder.encode(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
</Types>`),
      },
      {
        name: '_rels/.rels',
        data: encoder.encode(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>`),
      },
      {
        name: 'xl/workbook.xml',
        data: encoder.encode(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheets><sheet name="작업보고서" sheetId="1" r:id="rId1"/></sheets>
</workbook>`),
      },
      {
        name: 'xl/_rels/workbook.xml.rels',
        data: encoder.encode(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>`),
      },
      {
        name: 'xl/styles.xml',
        data: encoder.encode(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<fonts count="1"><font><name val="맑은 고딕"/><family val="2"/><sz val="10"/></font></fonts>
<fills count="1"><fill><patternFill patternType="none"/></fill></fills>
<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf></cellXfs>
</styleSheet>`),
      },
      { name: 'xl/worksheets/sheet1.xml', data: encoder.encode(worksheet) },
    ];
    return createZip(files);
  }

  function openPdfPrintReport(reportText: string, rows: ExportRow[], printWindow: Window | null) {
    const target = printWindow || window.open('', '_blank');
    if (!target) {
      setNotice('팝업이 차단되어 PDF 창을 열지 못했습니다. 브라우저 팝업 허용 후 다시 시도하세요.');
      return;
    }
    target.document.open();
    target.document.write(reportHtml(reportText, rows));
    target.document.close();
    target.focus();
    window.setTimeout(() => target.print(), 500);
  }

  async function copyReport() {
    if (!report) return;
    await navigator.clipboard.writeText(report);
    setNotice('보고서를 복사했습니다.');
  }

  async function fetchOpenAiUsage() {
    setUsageLoading(true);
    try {
      const res = await fetch(`${getApiBase()}/api/openai-usage?days=7`);
      if (!res.ok) throw new Error(`사용량 조회 오류: ${res.status}`);
      const data = (await res.json()) as OpenAiUsage;
      setOpenAiUsage(data);
    } catch (err) {
      setOpenAiUsage({
        configured: false,
        status: 'client_error',
        message: err instanceof Error ? err.message : '사용량 조회 중 오류가 발생했습니다.',
      });
    } finally {
      setUsageLoading(false);
    }
  }

  function resetAll() {
    setText('');
    setShowPasteInput(false);
    setChatFile(null);
    setImageFiles([]);
    setImagePreviews({});
    setMessages([]);
    setImages([]);
    setMatches([]);
    setSummary(null);
    setParseDiagnostics(null);
    setSelectedImageId(null);
    setImagePickerMessageId(null);
    setImagePickerPage(0);
    setPickerSelectedIds([]);
    setReport('');
    setNotice('');
    setMessageFilter('active');
    setImageBatchLoading(false);
    if (chatFileInputRef.current) chatFileInputRef.current.value = '';
    if (imageFileInputRef.current) imageFileInputRef.current.value = '';
  }

  function completeWork() {
    const ok = window.confirm('현재 대화와 사진 상태를 모두 비우고 새 작업을 시작할까요? 보고서가 필요하면 먼저 복사해 두세요.');
    if (!ok) return;
    resetAll();
    setNotice('작업을 완료하고 새 작업을 시작할 준비가 되었습니다.');
  }

  function resetImagesOnly() {
    setImageFiles([]);
    setImagePreviews({});
    setImages([]);
    setMatches([]);
    setSelectedImageId(null);
    setImagePickerMessageId(null);
    setImagePickerPage(0);
    setPickerSelectedIds([]);
    if (imageFileInputRef.current) imageFileInputRef.current.value = '';
    if (summary) {
      setSummary({
        ...summary,
        total_images: 0,
        confirmed_matches: 0,
        needs_review_matches: 0,
        unmatched_images: 0,
      });
    }
    setNotice('대화 검토 상태는 그대로 두고 사진만 초기화했습니다. 새 사진을 선택한 뒤 사진만 다시 매칭하세요.');
  }

  function updateMessageStatus(messageId: string, status: MessageStatus) {
    setMessages(current => current.map(message => (message.id === messageId ? { ...message, status } : message)));
    if (status === 'excluded') {
      setMatches(current =>
        current.map(match =>
          match.message_id === messageId
            ? { ...match, message_id: null, status: 'unmatched', confidence: 0, reasons: ['사용자가 대화를 제외해 사진을 분리했습니다.'] }
            : match,
        ),
      );
    }
  }

  function excludeVisibleReview() {
    const targetIds = new Set(visibleMessages.filter(message => message.status === 'review').map(message => message.id));
    if (targetIds.size === 0) return;
    const ok = window.confirm(`현재 화면에 보이는 확인 필요 대화 ${targetIds.size}건을 보고서에서 제외할까요? 제외 후에도 '제외' 탭에서 다시 작업으로 복원할 수 있습니다.`);
    if (!ok) return;
    setMessages(current => current.map(message => (targetIds.has(message.id) ? { ...message, status: 'excluded' } : message)));
    setMatches(current =>
      current.map(match =>
        match.message_id && targetIds.has(match.message_id)
          ? { ...match, message_id: null, status: 'unmatched', confidence: 0, reasons: ['확인 필요 대화 일괄 제외로 분리됨'] }
          : match,
      ),
    );
  }

  function attachImages(imageIds: string[], messageId: string) {
    const ids = Array.from(new Set(imageIds));
    if (ids.length === 0) return;
    setMatches(current => {
      const seen = new Set(current.map(match => match.image_id));
      const updated = current.map(match =>
        ids.includes(match.image_id)
          ? {
              ...match,
              message_id: messageId,
              status: 'confirmed' as MatchStatus,
              confidence: Math.max(match.confidence, 90),
              reasons: ['사용자가 직접 연결했습니다.'],
            }
          : match,
      );
      for (const imageId of ids) {
        if (!seen.has(imageId)) {
          updated.push({
            image_id: imageId,
            message_id: messageId,
            confidence: 90,
            status: 'confirmed',
            role: 'evidence',
            reasons: ['사용자가 직접 연결했습니다.'],
          });
        }
      }
      return updated;
    });
    setSelectedImageId(null);
  }

  function attachImage(imageId: string, messageId: string) {
    attachImages([imageId], messageId);
  }

  function attachSelectedImage(messageId: string) {
    if (!selectedImageId) return;
    attachImage(selectedImageId, messageId);
  }

  function openImagePicker(messageId: string) {
    setImagePickerMessageId(current => (current === messageId ? null : messageId));
    setImagePickerPage(0);
    setPickerSelectedIds([]);
  }

  function togglePickerImage(imageId: string) {
    setPickerSelectedIds(current => (current.includes(imageId) ? current.filter(id => id !== imageId) : [...current, imageId]));
  }

  function attachPickerSelection(messageId: string) {
    attachImages(pickerSelectedIds, messageId);
    setNotice(`${pickerSelectedIds.length}장 사진을 선택한 대화에 연결했습니다.`);
    setPickerSelectedIds([]);
    setImagePickerMessageId(null);
    setImagePickerPage(0);
  }

  function unlinkImage(imageId: string) {
    setMatches(current =>
      current.map(match =>
        match.image_id === imageId
          ? { ...match, message_id: null, status: 'unmatched', confidence: 0, reasons: ['사용자가 사진을 분리했습니다.'] }
          : match,
      ),
    );
  }

  function setImageRole(imageId: string, role: ImageRole) {
    setMatches(current =>
      current.map(match => (match.image_id === imageId ? { ...match, role, reasons: ['사용자가 사진 역할을 지정했습니다.', ...match.reasons.slice(0, 2)] } : match)),
    );
  }

  function excludeImage(imageId: string, excluded: boolean) {
    setImages(current => current.map(image => (image.id === imageId ? { ...image, excluded } : image)));
    if (excluded && selectedImageId === imageId) setSelectedImageId(null);
  }

  function imagesForMessage(messageId: string) {
    return activeImages.filter(image => matchByImageId.get(image.id)?.message_id === messageId);
  }

  function pickerImagesForMessage(messageId: string) {
    return [...activeImages.filter(image => matchByImageId.get(image.id)?.message_id !== messageId)].sort((left, right) => {
      const rankDiff = imagePickerRank(left) - imagePickerRank(right);
      if (rankDiff !== 0) return rankDiff;
      return left.filename.localeCompare(right.filename);
    });
  }

  function imagePickerRank(image: ReviewImage) {
    const match = matchByImageId.get(image.id);
    if (!match || !match.message_id || !activeMessageIds.has(match.message_id) || match.status === 'unmatched') return 0;
    if (match.status === 'needs_review') return 1;
    return 2;
  }

  return (
    <main className="mx-auto max-w-7xl px-3 py-4 text-slate-900 md:px-6 md:py-6">
      <section className="grid gap-4 lg:grid-cols-[1.05fr_0.95fr]">
        <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm md:p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="text-xs font-bold uppercase tracking-wide text-emerald-700">Facility Report</p>
              <h1 className="mt-1 text-2xl font-bold tracking-tight text-slate-950 md:text-3xl">카톡+사진 작업보고서</h1>
            </div>
            <div className="rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-800">
              원본 미저장 분석
            </div>
          </div>

          <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <label className="block">
              <span className="text-sm font-semibold text-slate-700">시작일</span>
              <input type="date" value={startDate} onChange={event => setStartDate(event.target.value)} className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" />
            </label>
            <label className="block">
              <span className="text-sm font-semibold text-slate-700">종료일</span>
              <input type="date" value={endDate} onChange={event => setEndDate(event.target.value)} className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm" />
            </label>
            <label className="block sm:col-span-2">
              <span className="text-sm font-semibold text-slate-700">카톡 txt</span>
              <input
                ref={chatFileInputRef}
                type="file"
                accept=".txt,text/plain"
                onChange={event => setChatFile(event.target.files?.[0] || null)}
                className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
              />
            </label>
          </div>

          <label className="mt-3 block">
            <span className="text-sm font-semibold text-slate-700">이미지 여러 장</span>
            <input
              ref={imageFileInputRef}
              type="file"
              accept="image/*"
              multiple
              onChange={event => chooseImages(event.target.files)}
              className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
          </label>
          {messages.length > 0 && (
            <div className="mt-2 rounded-xl border border-sky-200 bg-sky-50 p-3">
              <div className="text-sm font-bold text-sky-950">대화 유지 사진 배치 작업</div>
              <p className="mt-1 text-sm text-sky-900">
                보고서를 만든 뒤에도 대화 분류는 그대로 두고 사진만 바꿔서 다음 묶음을 처리할 수 있습니다.
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                <button
                  onClick={resetImagesOnly}
                  className="rounded-lg border border-sky-300 bg-white px-3 py-2 text-xs font-bold text-sky-800"
                >
                  사진만 초기화
                </button>
                <button
                  onClick={reviewImagesOnly}
                  disabled={!canReviewImagesOnly || imageBatchLoading}
                  className="rounded-lg bg-sky-800 px-3 py-2 text-xs font-bold text-white disabled:cursor-not-allowed disabled:bg-slate-300"
                >
                  {imageBatchLoading ? '사진 매칭 중...' : '현재 대화로 사진만 다시 매칭'}
                </button>
              </div>
            </div>
          )}

          <div className="mt-3 rounded-xl border border-slate-200 bg-white p-3">
            <label className="flex items-start gap-3">
              <input
                type="checkbox"
                checked={useAiClassification}
                onChange={event => setUseAiClassification(event.target.checked)}
                className="mt-1"
              />
              <span>
                <span className="block text-sm font-bold text-slate-900">AI 분류 사용</span>
                <span className="mt-1 block text-xs leading-5 text-slate-600">
                  기본은 꺼짐입니다. 켜면 확실한 제외 대화는 빼고 필요한 대화만 AI로 다시 판단합니다.
                </span>
              </span>
            </label>
            <label className="mt-3 block">
              <span className="text-sm font-semibold text-slate-700">AI 모델</span>
              <select
                value={aiModel}
                onChange={event => setAiModel(event.target.value)}
                className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
              >
                {AI_MODEL_OPTIONS.map(option => (
                  <option key={option.id} value={option.id}>
                    {option.label} - {option.id} ({option.description})
                  </option>
                ))}
              </select>
              <span className="mt-1 block text-xs leading-5 text-slate-500">
                선택한 모델은 AI 분류를 켰을 때와 AI 보고서 요약에 사용됩니다.
              </span>
            </label>
          </div>

          <div className="mt-3">
            <button
              type="button"
              onClick={() => setShowPasteInput(current => !current)}
              className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-bold text-slate-700"
            >
              {showPasteInput ? '붙여넣기 닫기' : 'txt 파일이 없을 때 직접 붙여넣기'}
            </button>
            {showPasteInput && (
              <label className="mt-3 block">
                <span className="text-sm font-semibold text-slate-700">대화내용 붙여넣기</span>
                <textarea
                  value={text}
                  onChange={event => setText(event.target.value)}
                  rows={5}
                  placeholder="카카오톡 대화 내보내기 내용을 붙여넣으세요."
                  className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 font-mono text-sm"
                />
              </label>
            )}
          </div>

          <div className="mt-4 rounded-xl border border-slate-200 bg-slate-50 p-3">
            <div className="text-sm font-bold text-slate-900">사용 순서</div>
            <div className="mt-2 grid gap-2 text-sm text-slate-700 md:grid-cols-3">
              <div className="rounded-lg bg-white px-3 py-2">1. 카톡에서 내보낸 txt 선택</div>
              <div className="rounded-lg bg-white px-3 py-2">2. 현장 사진 여러 장 선택</div>
              <div className="rounded-lg bg-white px-3 py-2">3. 분석 후 확인 필요만 수정</div>
            </div>
          </div>

          <div className="mt-4 flex flex-wrap gap-2">
            <button onClick={analyze} disabled={loading || !canAnalyze} className="rounded-lg bg-slate-950 px-4 py-2 text-sm font-bold text-white disabled:cursor-not-allowed disabled:bg-slate-400">
              {loading ? '분석 중...' : messages.length > 0 ? '처음부터 다시 분석' : '대화 정리와 사진 매칭'}
            </button>
            <button onClick={resetAll} className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-bold text-slate-700">
              초기화
            </button>
          </div>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm md:p-5">
          <h2 className="text-lg font-bold text-slate-950">검토 현황</h2>
          <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
            <Stat label="작업 대화" value={counts.work} tone="emerald" />
            <Stat label="확인 필요" value={counts.review + needsReviewImages.length + unmatchedImages.length} tone="amber" />
            <Stat label="제외 대화" value={counts.excluded} tone="rose" />
            <Stat label="이미지" value={activeImages.length} tone="sky" />
          </div>
          {summary && (
            <div className="mt-3 rounded-xl border border-slate-200 bg-slate-50 p-3 text-sm text-slate-700">
              <div>전체 대화 {summary.total_messages}건 중 현재 작업 {counts.work}건, 확인 {counts.review}건, 제외 {counts.excluded}건</div>
              <div>현재 사진 확정 {currentMatchStats.confirmed}장, 확인 필요 {currentMatchStats.needsReview}장, 미매칭 {currentMatchStats.unmatched}장</div>
              <div>
                {summary.ai_used ? `AI 대화 분류 적용됨 (${summary.ai_model || aiModel})` : '규칙 기반 분류 적용됨'}
                {summary.ai_error ? ` / AI 오류: ${summary.ai_error}` : ''}
              </div>
            </div>
          )}
          <div className="mt-3 rounded-xl border border-slate-200 bg-white p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="text-sm font-bold text-slate-900">OpenAI 사용량</div>
              <button onClick={fetchOpenAiUsage} disabled={usageLoading} className="rounded-lg border border-slate-300 px-3 py-2 text-xs font-bold text-slate-700 disabled:text-slate-300">
                {usageLoading ? '확인 중...' : '최근 7일 확인'}
              </button>
            </div>
            {openAiUsage && (
              <div className="mt-2 text-sm text-slate-700">
                {openAiUsage.status === 'ok' ? (
                  <div className="grid grid-cols-2 gap-2">
                    <div className="rounded-lg bg-slate-50 p-2">비용: {openAiUsage.costs?.currency || 'USD'} {formatNumber(openAiUsage.costs?.total)}</div>
                    <div className="rounded-lg bg-slate-50 p-2">요청: {formatNumber(openAiUsage.usage?.requests)}회</div>
                    <div className="rounded-lg bg-slate-50 p-2">입력 토큰: {formatNumber(openAiUsage.usage?.input_tokens)}</div>
                    <div className="rounded-lg bg-slate-50 p-2">출력 토큰: {formatNumber(openAiUsage.usage?.output_tokens)}</div>
                  </div>
                ) : (
                  <div className="rounded-lg bg-amber-50 p-2 text-amber-900">{openAiUsage.message || '사용량을 확인할 수 없습니다.'}</div>
                )}
                <div className="mt-2 flex flex-wrap gap-2 text-xs">
                  {openAiUsage.usage_dashboard_url && <a className="font-bold text-sky-700" href={openAiUsage.usage_dashboard_url} target="_blank" rel="noreferrer">Usage</a>}
                  {openAiUsage.billing_url && <a className="font-bold text-sky-700" href={openAiUsage.billing_url} target="_blank" rel="noreferrer">Billing</a>}
                  {openAiUsage.limits_url && <a className="font-bold text-sky-700" href={openAiUsage.limits_url} target="_blank" rel="noreferrer">Limits</a>}
                </div>
              </div>
            )}
          </div>
          <div className="mt-3 min-h-10 rounded-xl bg-slate-950 px-3 py-2 text-sm text-slate-100">{notice || 'txt와 이미지를 올린 뒤 분석을 시작하세요.'}</div>
          <NextAction
            hasSummary={Boolean(summary)}
            noParsedMessages={noParsedMessages}
            reviewCount={counts.review}
            unmatchedCount={currentMatchStats.unmatched + currentMatchStats.needsReview}
            canReport={activeMessages.length > 0}
            onChooseChat={() => chatFileInputRef.current?.click()}
            onShowPaste={() => setShowPasteInput(true)}
            onExcludeReview={excludeVisibleReview}
            onGenerateReport={generateReviewedReport}
            reportLoading={reportLoading}
          />
          {noParsedMessages && parseDiagnostics && (
            <div className="mt-3 rounded-xl border border-slate-200 bg-white p-3 text-sm text-slate-700">
              <div className="font-bold text-slate-900">파일은 읽었지만 대화 형식을 못 찾았습니다</div>
              <div className="mt-1">비어있지 않은 줄: {parseDiagnostics.non_empty_lines}줄</div>
              <div className="mt-2 font-semibold text-slate-800">파일 앞부분</div>
              <pre className="mt-1 max-h-36 overflow-auto rounded-lg bg-slate-950 p-2 text-xs leading-5 text-slate-100">
                {parseDiagnostics.preview_lines.join('\n') || '표시할 줄이 없습니다.'}
              </pre>
            </div>
          )}
        </div>
      </section>

      {noParsedMessages && (
        <section className="mt-5 rounded-2xl border border-rose-200 bg-rose-50 p-4 text-rose-950 shadow-sm">
          <h2 className="text-lg font-bold">카톡 대화가 아직 읽히지 않았습니다</h2>
          <p className="mt-2 text-sm">
            지금은 이미지 20장만 들어와서 AI가 사진을 연결할 대화 기준이 없습니다. 카카오톡 대화방에서 `대화 내용 내보내기`로 만든 txt 파일을 선택한 뒤 다시 분석하세요.
          </p>
          {parseDiagnostics && (
            <div className="mt-3 rounded-xl border border-rose-200 bg-white p-3 text-sm">
              <div className="font-bold">인식 가능한 예시</div>
              <ul className="mt-2 space-y-1">
                {parseDiagnostics.recognized_formats.map(format => (
                  <li key={format}>- {format}</li>
                ))}
              </ul>
            </div>
          )}
          <div className="mt-3 flex flex-wrap gap-2">
            <button onClick={() => chatFileInputRef.current?.click()} className="rounded-lg bg-rose-900 px-4 py-2 text-sm font-bold text-white">
              카톡 txt 다시 선택
            </button>
            <button onClick={() => setShowPasteInput(true)} className="rounded-lg border border-rose-300 px-4 py-2 text-sm font-bold text-rose-800">
              직접 붙여넣기 열기
            </button>
          </div>
        </section>
      )}

      {messages.length > 0 && !noParsedMessages && (
        <section className="mt-5 grid gap-5 xl:grid-cols-[0.9fr_1.1fr]">
          <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h2 className="text-lg font-bold text-slate-950">대화 정리</h2>
              <button onClick={excludeVisibleReview} className="rounded-lg border border-rose-300 px-3 py-2 text-xs font-bold text-rose-700">
                현재 보이는 확인 후보 일괄 제외
              </button>
            </div>

            <div className="mt-3 flex flex-wrap gap-2">
              <FilterButton active={messageFilter === 'active'} onClick={() => setMessageFilter('active')} label={`보고서 ${activeMessages.length}`} />
              <FilterButton active={messageFilter === 'work'} onClick={() => setMessageFilter('work')} label={`작업 ${counts.work}`} />
              <FilterButton active={messageFilter === 'review'} onClick={() => setMessageFilter('review')} label={`확인 ${counts.review}`} />
              <FilterButton active={messageFilter === 'excluded'} onClick={() => setMessageFilter('excluded')} label={`제외 ${counts.excluded}`} />
              <FilterButton active={messageFilter === 'all'} onClick={() => setMessageFilter('all')} label={`전체 ${counts.all}`} />
            </div>

            <div className="mt-3 max-h-[680px] space-y-2 overflow-y-auto pr-1">
              {visibleMessages.map(message => (
                <MessageRow key={message.id} message={message} onStatus={status => updateMessageStatus(message.id, status)} />
              ))}
              {visibleMessages.length === 0 && <EmptyBox text="표시할 대화가 없습니다." />}
            </div>
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-lg font-bold text-slate-950">사진 매칭 검토</h2>
                <p className="mt-1 text-sm text-slate-600">
                  대화 안에 보이는 사진은 이미 연결된 상태입니다. `전/중/후/자료`만 고르면 바로 반영됩니다.
                </p>
              </div>
              <div className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-sm font-semibold text-amber-900">
                선택: {selectedImage ? selectedImage.filename : '없음'}
              </div>
            </div>

            {(unmatchedImages.length > 0 || needsReviewImages.length > 0) && (
              <div className="mt-3 rounded-xl border border-amber-200 bg-amber-50 p-3">
                <div className="text-sm font-bold text-amber-950">먼저 확인할 사진</div>
                <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
                  {[...needsReviewImages, ...unmatchedImages.filter(image => !needsReviewImages.some(reviewImage => reviewImage.id === image.id))].map(image => (
                    <ImageTile
                      key={image.id}
                      image={image}
                      preview={imagePreviews[image.id]}
                      match={matchByImageId.get(image.id)}
                      selected={selectedImageId === image.id}
                      onSelect={() => setSelectedImageId(image.id)}
                      onUnlink={() => unlinkImage(image.id)}
                      onExclude={() => excludeImage(image.id, true)}
                      onRole={role => setImageRole(image.id, role)}
                    />
                  ))}
                </div>
              </div>
            )}

            <div className="mt-3 max-h-[720px] space-y-3 overflow-y-auto pr-1">
              {activeMessages.map(message => {
                const linkedImages = imagesForMessage(message.id);
                const selectedAlreadyHere = Boolean(selectedImageId && linkedImages.some(image => image.id === selectedImageId));
                const pickerImages = pickerImagesForMessage(message.id);
                const pickerOpen = imagePickerMessageId === message.id;
                return (
                  <div key={message.id} className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div>
                        <div className="text-xs font-semibold text-slate-500">
                          {message.date} {message.time} / {message.user || '-'} / {STATUS_LABELS[message.status]}
                        </div>
                        <div className="mt-1 text-sm font-semibold text-slate-900">{shortText(message.message, 120)}</div>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {selectedImageId && !selectedAlreadyHere && (
                          <button
                            onClick={() => attachSelectedImage(message.id)}
                            className="rounded-lg bg-emerald-700 px-3 py-2 text-xs font-bold text-white"
                          >
                            위에서 선택한 사진 추가
                          </button>
                        )}
                        <button
                          onClick={() => openImagePicker(message.id)}
                          className="rounded-lg border border-sky-300 bg-white px-3 py-2 text-xs font-bold text-sky-800"
                        >
                          {pickerOpen ? '사진 고르기 닫기' : '사진 고르기'}
                        </button>
                      </div>
                    </div>

                    {pickerOpen && (
                      <ImagePickerPanel
                        images={pickerImages}
                        previews={imagePreviews}
                        matches={matchByImageId}
                        selectedIds={pickerSelectedIds}
                        page={imagePickerPage}
                        pageSize={PICKER_PAGE_SIZE}
                        onPage={setImagePickerPage}
                        onToggle={togglePickerImage}
                        onAttach={() => attachPickerSelection(message.id)}
                      />
                    )}

                    {linkedImages.length > 0 && (
                      <div className="mt-3 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs font-semibold text-emerald-900">
                        아래 사진은 이 대화에 이미 붙어 있습니다. 각 사진의 `전`, `중`, `후`, `자료` 버튼만 바꾸면 됩니다.
                      </div>
                    )}

                    <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3">
                      {linkedImages.map(image => (
                        <ImageTile
                          key={image.id}
                          image={image}
                          preview={imagePreviews[image.id]}
                          match={matchByImageId.get(image.id)}
                          selected={selectedImageId === image.id}
                          onSelect={() => setSelectedImageId(image.id)}
                          onUnlink={() => unlinkImage(image.id)}
                          onExclude={() => excludeImage(image.id, true)}
                          onRole={role => setImageRole(image.id, role)}
                        />
                      ))}
                      {linkedImages.length === 0 && <div className="rounded-lg border border-dashed border-slate-300 p-3 text-sm text-slate-500">연결된 사진 없음</div>}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </section>
      )}

      {messages.length > 0 && !noParsedMessages && (
        <section className="mt-5 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-lg font-bold text-slate-950">보고서 생성</h2>
              <p className="mt-1 text-sm text-slate-600">현재 검토 상태 그대로 보고서에 반영됩니다.</p>
            </div>
            <div className="flex flex-wrap items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 p-2">
              <button
                onClick={() => setReportFormat('excel')}
                className={`rounded-lg px-3 py-2 text-sm font-bold ${reportFormat === 'excel' ? 'bg-slate-950 text-white' : 'bg-white text-slate-700'}`}
              >
                엑셀
              </button>
              <button
                onClick={() => setReportFormat('pdf')}
                className={`rounded-lg px-3 py-2 text-sm font-bold ${reportFormat === 'pdf' ? 'bg-slate-950 text-white' : 'bg-white text-slate-700'}`}
              >
                PDF
              </button>
              <label className="flex items-center gap-2 rounded-lg bg-white px-3 py-2 text-sm font-bold text-slate-700">
                <input type="checkbox" checked={includeApproval} onChange={event => setIncludeApproval(event.target.checked)} />
                결재란 포함
              </label>
            </div>
            <div className="flex flex-wrap gap-2">
              <button onClick={generateReviewedReport} disabled={reportLoading || activeMessages.length === 0} className="rounded-lg bg-slate-950 px-4 py-2 text-sm font-bold text-white disabled:bg-slate-400">
                {reportLoading ? '생성 중...' : `${reportFormat === 'excel' ? '엑셀' : 'PDF'} 보고서 생성`}
              </button>
              <button onClick={resetImagesOnly} className="rounded-lg border border-sky-300 px-4 py-2 text-sm font-bold text-sky-800">
                다음 사진 묶음
              </button>
              <button onClick={copyReport} disabled={!report} className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-bold text-slate-700 disabled:cursor-not-allowed disabled:text-slate-300">
                복사
              </button>
              <button onClick={completeWork} className="rounded-lg border border-rose-300 px-4 py-2 text-sm font-bold text-rose-700">
                전체 작업 완료
              </button>
            </div>
          </div>
          <pre className="mt-4 min-h-80 whitespace-pre-wrap rounded-xl bg-slate-950 p-4 text-sm leading-6 text-slate-100">{report || '보고서가 아직 생성되지 않았습니다.'}</pre>
        </section>
      )}
    </main>
  );
}

function Stat({ label, value, tone }: { label: string; value: number; tone: 'emerald' | 'amber' | 'rose' | 'sky' }) {
  const tones = {
    emerald: 'border-emerald-200 bg-emerald-50 text-emerald-900',
    amber: 'border-amber-200 bg-amber-50 text-amber-900',
    rose: 'border-rose-200 bg-rose-50 text-rose-900',
    sky: 'border-sky-200 bg-sky-50 text-sky-900',
  };
  return (
    <div className={`rounded-xl border p-3 ${tones[tone]}`}>
      <div className="text-xs font-bold">{label}</div>
      <div className="mt-1 text-2xl font-black">{value}</div>
    </div>
  );
}

function NextAction({
  hasSummary,
  noParsedMessages,
  reviewCount,
  unmatchedCount,
  canReport,
  onChooseChat,
  onShowPaste,
  onExcludeReview,
  onGenerateReport,
  reportLoading,
}: {
  hasSummary: boolean;
  noParsedMessages: boolean;
  reviewCount: number;
  unmatchedCount: number;
  canReport: boolean;
  onChooseChat: () => void;
  onShowPaste: () => void;
  onExcludeReview: () => void;
  onGenerateReport: () => void;
  reportLoading: boolean;
}) {
  if (!hasSummary) {
    return (
      <div className="mt-3 rounded-xl border border-slate-200 bg-slate-50 p-3">
        <div className="text-sm font-bold text-slate-900">지금 할 일</div>
        <p className="mt-1 text-sm text-slate-700">카톡 txt와 사진을 선택한 뒤 `대화 정리와 사진 매칭`을 누르세요.</p>
      </div>
    );
  }

  if (noParsedMessages) {
    return (
      <div className="mt-3 rounded-xl border border-rose-200 bg-rose-50 p-3">
        <div className="text-sm font-bold text-rose-950">지금 할 일: 카톡 txt를 다시 넣으세요</div>
        <p className="mt-1 text-sm text-rose-900">대화가 0건이면 사진을 자동 매칭할 수 없습니다.</p>
        <div className="mt-3 flex flex-wrap gap-2">
          <button onClick={onChooseChat} className="rounded-lg bg-rose-900 px-3 py-2 text-xs font-bold text-white">
            카톡 txt 선택
          </button>
          <button onClick={onShowPaste} className="rounded-lg border border-rose-300 px-3 py-2 text-xs font-bold text-rose-800">
            직접 붙여넣기
          </button>
        </div>
      </div>
    );
  }

  if (reviewCount > 0) {
    return (
      <div className="mt-3 rounded-xl border border-amber-200 bg-amber-50 p-3">
        <div className="text-sm font-bold text-amber-950">지금 할 일: 확인 필요 대화를 정리하세요</div>
        <p className="mt-1 text-sm text-amber-900">업무와 상관없는 대화는 제외하고, 필요한 대화만 작업으로 바꾸면 됩니다.</p>
        <button onClick={onExcludeReview} className="mt-3 rounded-lg bg-amber-800 px-3 py-2 text-xs font-bold text-white">
          현재 보이는 확인 후보 일괄 제외
        </button>
      </div>
    );
  }

  if (unmatchedCount > 0) {
    return (
      <div className="mt-3 rounded-xl border border-sky-200 bg-sky-50 p-3">
        <div className="text-sm font-bold text-sky-950">지금 할 일: 미매칭 사진만 확인하세요</div>
        <p className="mt-1 text-sm text-sky-900">대화 카드의 `사진 고르기`를 누르면 사진이 6장씩 보입니다. 필요한 사진을 여러 장 선택하고 `선택 사진 추가`를 누르세요.</p>
      </div>
    );
  }

  return (
    <div className="mt-3 rounded-xl border border-emerald-200 bg-emerald-50 p-3">
      <div className="text-sm font-bold text-emerald-950">지금 할 일: 보고서를 생성하세요</div>
      <p className="mt-1 text-sm text-emerald-900">검토할 항목이 없으면 바로 보고서를 만들 수 있습니다.</p>
      <button onClick={onGenerateReport} disabled={!canReport || reportLoading} className="mt-3 rounded-lg bg-emerald-800 px-3 py-2 text-xs font-bold text-white disabled:bg-slate-300">
        {reportLoading ? '생성 중...' : '보고서 생성'}
      </button>
    </div>
  );
}

function FilterButton({ active, label, onClick }: { active: boolean; label: string; onClick: () => void }) {
  return (
    <button onClick={onClick} className={`rounded-full px-3 py-1.5 text-xs font-bold ${active ? 'bg-slate-950 text-white' : 'border border-slate-300 bg-white text-slate-700'}`}>
      {label}
    </button>
  );
}

function MessageRow({ message, onStatus }: { message: ReviewMessage; onStatus: (status: MessageStatus) => void }) {
  const statusTone =
    message.status === 'work'
      ? 'border-emerald-200 bg-emerald-50 text-emerald-900'
      : message.status === 'review'
        ? 'border-amber-200 bg-amber-50 text-amber-900'
        : 'border-rose-200 bg-rose-50 text-rose-900';
  return (
    <div className="rounded-xl border border-slate-200 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="text-xs font-semibold text-slate-500">
          {message.date} {message.time} / {message.user || '-'}
        </div>
        <div className={`rounded-full border px-2 py-0.5 text-xs font-bold ${statusTone}`}>
          {STATUS_LABELS[message.status]} {Math.round(message.confidence * 100)}%
        </div>
      </div>
      <div className="mt-2 whitespace-pre-wrap text-sm font-medium text-slate-900">{message.message}</div>
      <div className="mt-2 text-xs text-slate-500">{message.reasons.slice(0, 2).join(' / ')}</div>
      <div className="mt-3 flex flex-wrap gap-2">
        <button onClick={() => onStatus('work')} className="rounded-lg border border-emerald-300 px-3 py-1.5 text-xs font-bold text-emerald-800">
          작업
        </button>
        <button onClick={() => onStatus('review')} className="rounded-lg border border-amber-300 px-3 py-1.5 text-xs font-bold text-amber-800">
          확인
        </button>
        <button onClick={() => onStatus('excluded')} className="rounded-lg border border-rose-300 px-3 py-1.5 text-xs font-bold text-rose-700">
          제외
        </button>
      </div>
    </div>
  );
}

function ImageTile({
  image,
  preview,
  match,
  selected,
  onSelect,
  onUnlink,
  onExclude,
  onRole,
}: {
  image: ReviewImage;
  preview?: string;
  match?: ImageMatch;
  selected: boolean;
  onSelect: () => void;
  onUnlink: () => void;
  onExclude: () => void;
  onRole: (role: ImageRole) => void;
}) {
  const status = match?.status || 'unmatched';
  const tone =
    status === 'confirmed'
      ? 'border-emerald-300'
      : status === 'needs_review'
        ? 'border-amber-300'
        : 'border-rose-300';
  return (
    <div className={`overflow-hidden rounded-xl border bg-white ${selected ? 'ring-2 ring-slate-950' : tone}`}>
      <button onClick={onSelect} className="block w-full text-left">
        <div className="aspect-[4/3] bg-slate-100">
          {preview ? <img src={preview} alt={image.filename} className="h-full w-full object-cover" /> : <div className="flex h-full items-center justify-center text-xs text-slate-500">미리보기 없음</div>}
        </div>
        <div className="p-2">
          <div className="truncate text-xs font-bold text-slate-900">{image.filename}</div>
          <div className="mt-1 text-[11px] text-slate-500">
            {image.captured_at || '시간 없음'} / {formatBytes(image.size)}
          </div>
          <div className="mt-1 text-[11px] font-semibold text-slate-600">
            {confidenceLabel(match?.confidence || 0)} {match?.confidence || 0}%
          </div>
        </div>
      </button>
      <div className="border-t border-slate-100 p-2">
        <div className="grid grid-cols-4 gap-1">
          {(Object.keys(ROLE_LABELS) as ImageRole[]).map(role => (
            <button
              key={role}
              onClick={() => onRole(role)}
              className={`rounded-md px-1 py-1 text-[11px] font-bold ${match?.role === role ? 'bg-slate-950 text-white' : 'bg-slate-100 text-slate-700'}`}
            >
              {ROLE_LABELS[role]}
            </button>
          ))}
        </div>
        <div className="mt-2 grid grid-cols-2 gap-1">
          <button onClick={onUnlink} className="rounded-md border border-slate-300 px-2 py-1 text-[11px] font-bold text-slate-700">
            분리
          </button>
          <button onClick={onExclude} className="rounded-md border border-rose-300 px-2 py-1 text-[11px] font-bold text-rose-700">
            제외
          </button>
        </div>
      </div>
    </div>
  );
}

function ImagePickerPanel({
  images,
  previews,
  matches,
  selectedIds,
  page,
  pageSize,
  onPage,
  onToggle,
  onAttach,
}: {
  images: ReviewImage[];
  previews: Record<string, string>;
  matches: Map<string, ImageMatch>;
  selectedIds: string[];
  page: number;
  pageSize: number;
  onPage: (page: number) => void;
  onToggle: (imageId: string) => void;
  onAttach: () => void;
}) {
  const maxPage = Math.max(0, Math.ceil(images.length / pageSize) - 1);
  const currentPage = Math.min(page, maxPage);
  const start = currentPage * pageSize;
  const pageImages = images.slice(start, start + pageSize);

  return (
    <div className="mt-3 rounded-xl border border-sky-200 bg-sky-50 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="text-sm font-bold text-sky-950">추가할 사진 선택</div>
          <div className="mt-1 text-xs text-sky-900">
            {images.length > 0 ? `${start + 1}-${Math.min(start + pageSize, images.length)} / ${images.length}장 표시` : '선택할 수 있는 사진이 없습니다.'}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <button onClick={() => onPage(Math.max(0, currentPage - 1))} disabled={currentPage === 0} className="rounded-lg border border-sky-300 bg-white px-3 py-2 text-xs font-bold text-sky-800 disabled:text-slate-300">
            이전
          </button>
          <button onClick={() => onPage(Math.min(maxPage, currentPage + 1))} disabled={currentPage >= maxPage} className="rounded-lg border border-sky-300 bg-white px-3 py-2 text-xs font-bold text-sky-800 disabled:text-slate-300">
            다음
          </button>
          <button onClick={onAttach} disabled={selectedIds.length === 0} className="rounded-lg bg-sky-800 px-3 py-2 text-xs font-bold text-white disabled:bg-slate-300">
            선택 {selectedIds.length}장 추가
          </button>
        </div>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3">
        {pageImages.map(image => {
          const selected = selectedIds.includes(image.id);
          const match = matches.get(image.id);
          const attachedElsewhere = Boolean(match?.message_id);
          return (
            <button
              key={image.id}
              onClick={() => onToggle(image.id)}
              className={`overflow-hidden rounded-xl border bg-white text-left ${selected ? 'border-sky-700 ring-2 ring-sky-700' : 'border-slate-200'}`}
            >
              <div className="aspect-[4/3] bg-slate-100">
                {previews[image.id] ? <img src={previews[image.id]} alt={image.filename} className="h-full w-full object-cover" /> : <div className="flex h-full items-center justify-center text-xs text-slate-500">미리보기 없음</div>}
              </div>
              <div className="p-2">
                <div className="truncate text-xs font-bold text-slate-900">{image.filename}</div>
                <div className="mt-1 text-[11px] text-slate-500">{image.captured_at || '시간 없음'}</div>
                <div className={`mt-2 inline-flex rounded-full px-2 py-0.5 text-[11px] font-bold ${selected ? 'bg-sky-900 text-white' : attachedElsewhere ? 'bg-amber-100 text-amber-900' : 'bg-slate-100 text-slate-700'}`}>
                  {selected ? '선택됨' : attachedElsewhere ? '다른 대화 연결됨' : '미연결'}
                </div>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function EmptyBox({ text }: { text: string }) {
  return <div className="rounded-xl border border-dashed border-slate-300 p-5 text-center text-sm text-slate-500">{text}</div>;
}
