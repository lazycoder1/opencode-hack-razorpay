import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Website Creator Starter",
  description: "Basic Next.js frontend connected to a FastAPI backend.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
