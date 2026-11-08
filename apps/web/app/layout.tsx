import type { Metadata } from 'next';

import './globals.css';

export const metadata: Metadata = {
  title: 'IKIP — Technician Assistant',
  description: 'Grounded, cited answers from equipment documentation.',
};

export default function RootLayout({ children }: { children: React.ReactNode }): React.JSX.Element {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
