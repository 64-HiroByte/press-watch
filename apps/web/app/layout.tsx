import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "PressWatch",
  description: "環境省の報道発表を確認するためのアプリケーション",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ja">
      <body>{children}</body>
    </html>
  );
}
