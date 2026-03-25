import './globals.css';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'QPilot Agent - Universal AI QA',
  description: 'Universal AI QA agent with chat, history, settings, and guided test execution',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
