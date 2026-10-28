import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Rivalens",
  description: "Competitor website monitoring with AI summarization",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ru">
      <body>{children}</body>
    </html>
  );
}
