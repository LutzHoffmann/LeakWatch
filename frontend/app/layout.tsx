import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "LeakWatch",
  description: "Credential Leak Monitor",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
