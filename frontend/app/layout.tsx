import './globals.css';
import type { Metadata } from 'next';
export const metadata: Metadata = { title: '시설관리 업무보고서 생성기', description: '카카오톡 대화를 기간별 업무보고서로 변환합니다.' };
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <html lang="ko"><body>{children}</body></html>;
}
